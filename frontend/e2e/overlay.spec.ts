import { expect, test, type Page } from "@playwright/test";

const STYLE = {
  font: "jhenghei",
  size: 48,
  weight: "normal",
  color: "#FFFFFF",
  outline_width: 0,
  outline_color: "#000000",
  shadow: false,
  background_color: "#000000",
  background_opacity: 0.5,
  padding: 12,
  radius: 8,
  align: "left",
  scroll: true,
  scroll_ms: 250,
};

const LINE_HEIGHT = 1.3;
const VIEWPORT = '[data-testid="caption-viewport"]';

function snapshot(lines: string[], maxLines: number) {
  return {
    running: true,
    layout: {
      chars_per_line: 20,
      max_lines: maxLines,
      sentence_breaks: true,
      idle_reset_ms: 0,
    },
    style: STYLE,
    elapsed_seconds: 1,
    status_revision: 1,
    components: [],
    caption: {
      revision: 1,
      status: "partial",
      text: lines.join(""),
      lines,
      language_code: "zh-Hant",
      updated_at: 1,
      session_generation: 1,
    },
    meter: null,
    last_error: null,
    audio_notice: null,
    vmix_notice: null,
  };
}

/**
 * Replace the caption socket before the bundle loads, so the test decides
 * exactly which snapshots arrive and when. Driving it through a real backend
 * would need an API key and a microphone, and would make the timing of a
 * two-scroll sequence — the thing being measured — impossible to control.
 */
async function stubSocket(page: Page): Promise<void> {
  await page.addInitScript(() => {
    class FakeSocket {
      onopen: (() => void) | null = null;
      onmessage: ((event: { data: string }) => void) | null = null;
      onclose: (() => void) | null = null;
      onerror: (() => void) | null = null;
      constructor() {
        (window as unknown as { __socket: FakeSocket }).__socket = this;
        queueMicrotask(() => this.onopen?.());
      }
      close(): void {}
    }
    (window as unknown as { WebSocket: unknown }).WebSocket = FakeSocket;
  });
}

async function push(page: Page, lines: string[], maxLines: number): Promise<void> {
  await page.evaluate((payload) => {
    const socket = (
      window as unknown as {
        __socket: { onmessage: ((event: { data: string }) => void) | null };
      }
    ).__socket;
    socket.onmessage?.({ data: JSON.stringify(payload) });
  }, snapshot(lines, maxLines));
}

async function animations(
  page: Page,
): Promise<{ name: string; currentTime: number }[]> {
  return page.evaluate((selector) => {
    const element = document.querySelector(selector);
    if (element === null) {
      return [];
    }
    return element.getAnimations().map((animation) => ({
      name: (animation as unknown as { animationName?: string }).animationName ?? "",
      currentTime: Number(animation.currentTime ?? 0),
    }));
  }, VIEWPORT);
}

async function firstAnimation(
  page: Page,
): Promise<{ name: string; currentTime: number }> {
  await expect.poll(async () => (await animations(page)).length).toBeGreaterThan(0);
  return (await animations(page))[0];
}

test.beforeEach(async ({ page }) => {
  await stubSocket(page);
  await page.goto("/overlay");
});

test("字幕框高度等於字級 × 行高 × 行數", async ({ page }) => {
  await push(page, ["第一行"], 2);

  const box = await page.locator(VIEWPORT).boundingBox();

  expect(box).not.toBeNull();
  // A fixed height whatever the caption says: a Browser Input is placed once
  // and must not move when a second line arrives.
  expect(box!.height).toBeCloseTo(STYLE.size * LINE_HEIGHT * 2, 0);
});

test("超出行數的內容被裁掉，框不會長高", async ({ page }) => {
  await push(page, ["一", "二"], 2);
  const before = await page.locator(VIEWPORT).boundingBox();

  await push(page, ["一", "二", "三", "四"], 2);
  const after = await page.locator(VIEWPORT).boundingBox();

  expect(await page.locator(".caption-box__text").count()).toBe(2);
  expect(after!.height).toBeCloseTo(before!.height, 0);
});

test("最上面那行被擠掉時才播滑動", async ({ page }) => {
  await push(page, ["一", "二"], 2);
  expect(await animations(page)).toHaveLength(0);

  await push(page, ["二", "三"], 2);

  const running = await animations(page);
  expect(running).toHaveLength(1);
  expect(running[0].name).toContain("caption-slide");
});

test("前一次還沒播完就再滑動時，動畫要從頭重播", async ({ page }) => {
  // The jitter reported from vMix: re-applying a running animation does
  // nothing, so the second scroll showed no motion and then snapped when the
  // first one's timer removed the class. Only a real browser can show this —
  // jsdom has no animation timeline.
  await push(page, ["一", "二"], 2);
  await push(page, ["二", "三"], 2);
  // The animation starts asynchronously; reading straight after the push
  // sometimes finds nothing at all.
  const first = await firstAnimation(page);

  await page.waitForTimeout(120);
  const midway = await firstAnimation(page);
  await push(page, ["三", "四"], 2);

  // A restart swaps which of the two identical keyframes is in use. Waiting
  // for that is what distinguishes "started over" from "still running".
  await expect
    .poll(async () => (await animations(page))[0]?.name)
    .not.toBe(first.name);

  const second = await firstAnimation(page);
  expect(midway.currentTime).toBeGreaterThan(80);
  expect(second.currentTime).toBeLessThan(midway.currentTime);
});

test("整段被換掉時不播滑動", async ({ page }) => {
  await push(page, ["一", "二", "三"], 3);

  await push(page, ["新的一段"], 3);

  expect(await animations(page)).toHaveLength(0);
});

test("頁面背景保持全透明，vMix 才去得掉底", async ({ page }) => {
  await push(page, ["第一行"], 2);

  const background = await page.evaluate(
    () => getComputedStyle(document.body).backgroundColor,
  );

  expect(background).toBe("rgba(0, 0, 0, 0)");
});

test("頁面不會出現捲軸", async ({ page }) => {
  await push(page, ["一", "二", "三", "四", "五"], 5);

  const overflows = await page.evaluate(() => {
    const root = document.documentElement;
    return root.scrollHeight > root.clientHeight;
  });

  expect(overflows).toBe(false);
});
