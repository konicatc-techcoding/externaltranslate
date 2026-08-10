import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, api } from "./client";

function mockFetch(response: Partial<Response> & { jsonBody?: unknown }): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: response.ok ?? true,
      status: response.status ?? 200,
      json: async () => response.jsonBody,
    })),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("api client", () => {
  it("回傳 typed 結果", async () => {
    mockFetch({ jsonBody: { configured: true } });
    await expect(api.credentialState()).resolves.toEqual({ configured: true });
  });

  it("把後端的繁體中文訊息帶到 ApiError", async () => {
    mockFetch({
      ok: false,
      status: 409,
      jsonBody: { detail: "翻譯已在執行中。" },
    });
    await expect(api.start()).rejects.toMatchObject({
      message: "翻譯已在執行中。",
      status: 409,
    });
  });

  it("驗證錯誤不會把後端結構丟到畫面上", async () => {
    mockFetch({
      ok: false,
      status: 422,
      jsonBody: { detail: [{ loc: ["body", "device_index"], msg: "field required" }] },
    });
    await expect(
      api.updateSettings({ source_kind: "input_device" }),
    ).rejects.toMatchObject({ message: "送出的設定不符合格式，請確認後再試。" });
  });

  it("連線失敗時回報可行動的訊息", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("network down");
      }),
    );
    const error = await api.status().catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).message).toContain("本機服務");
  });

  it("送出 API key 後不留在瀏覽器儲存空間", async () => {
    mockFetch({ jsonBody: { configured: true } });
    await api.submitCredential("AIzaSyFAKEKEY");

    const stored = [
      ...Object.values(window.localStorage),
      ...Object.values(window.sessionStorage),
      document.cookie,
    ].join("|");
    expect(stored).not.toContain("AIzaSyFAKEKEY");
  });

  it("API key 只走請求主體，不進 URL", async () => {
    const spy = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ configured: true }),
    }));
    vi.stubGlobal("fetch", spy);

    await api.submitCredential("AIzaSyFAKEKEY");

    const [path, init] = spy.mock.calls[0] as unknown as [string, RequestInit];
    expect(path).toBe("/api/credentials");
    expect(path).not.toContain("AIzaSyFAKEKEY");
    expect(String(init.body)).toContain("AIzaSyFAKEKEY");
  });
});
