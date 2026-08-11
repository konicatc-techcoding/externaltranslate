import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { VmixSettings, generateFieldNames } from "./VmixSettings";
import {
  DEFAULT_VMIX_SETTINGS,
  type VmixInputItem,
  type VmixSettings as VmixConfig,
} from "../types/runtime";

const TITLE: VmixInputItem = {
  guid: "877bb3e7-58bd-46a1-85ce-0d673aec6bf5",
  number: 1,
  name: "字幕標題",
  kind: "GT",
  text_fields: ["Line1.Text", "Line2.Text"],
};

function renderPanel(
  overrides: Partial<VmixConfig> = {},
  props: Partial<Parameters<typeof VmixSettings>[0]> = {},
) {
  const onChange = vi.fn();
  render(
    <VmixSettings
      settings={{ ...DEFAULT_VMIX_SETTINGS, ...overrides }}
      inputs={[TITLE]}
      maxLines={2}
      overlayUrl="http://localhost:8765/overlay"
      notice={null}
      onChange={onChange}
      onRefresh={vi.fn()}
      onTest={vi.fn()}
      onClearFields={vi.fn()}
      {...props}
    />,
  );
  return onChange;
}

describe("VmixSettings", () => {
  it("選擇 input 時記 GUID，名稱只是給人看的", async () => {
    // A number would shift when inputs are added or removed, and SetText
    // would then write to a different input with no error.
    const user = userEvent.setup();
    const onChange = renderPanel();

    await user.selectOptions(screen.getByLabelText("輸出到哪個 input"), TITLE.guid);

    expect(onChange).toHaveBeenLastCalledWith({
      input_guid: TITLE.guid,
      input_name: "字幕標題",
    });
  });

  it("依行數產生欄位名稱", async () => {
    const user = userEvent.setup();
    const onChange = renderPanel({}, { maxLines: 3 });

    await user.click(screen.getByRole("button", { name: "依目前行數產生欄位名稱" }));

    expect(onChange).toHaveBeenLastCalledWith({
      fields: ["Line1.Text", "Line2.Text", "Line3.Text"],
    });
  });

  it("欄位數少於行數時當場說明會被截斷", () => {
    renderPanel({ fields: ["Line1.Text"] }, { maxLines: 4 });

    expect(
      screen.getByText(/目前字幕有 4 行，但只設定了 1 個欄位/),
    ).toBeInTheDocument();
  });

  it("非本機主機時警告字幕會以明文經過網路", () => {
    renderPanel({ host: "192.168.1.50" });

    expect(screen.getByText(/沒有加密/)).toBeInTheDocument();
  });

  it("本機主機不顯示該警告", () => {
    renderPanel({ host: "127.0.0.1" });

    expect(screen.queryByText(/沒有加密/)).toBeNull();
  });

  it("空白的欄位清單不會送出", () => {
    const onChange = renderPanel();

    const fields = screen.getByLabelText("文字欄位名稱（一行一個）");
    fireEvent.change(fields, { target: { value: "   \n  " } });
    fireEvent.blur(fields);

    expect(onChange).not.toHaveBeenCalled();
  });

  it("尚未選 input 時不能送測試字幕", () => {
    renderPanel({ input_guid: null });

    expect(screen.getByRole("button", { name: "送出測試字幕" })).toBeDisabled();
  });

  it("翻譯執行中不能測試，並說明原因", () => {
    // The next caption would overwrite the test within one throttle window,
    // so the result would say nothing about the wiring.
    renderPanel({}, { running: true });

    expect(screen.getByRole("button", { name: "送出測試字幕" })).toBeDisabled();
    expect(screen.getByText("翻譯執行中無法測試")).toBeInTheDocument();
  });

  it("選好 input 後可以清空欄位", () => {
    renderPanel({ input_guid: TITLE.guid });

    expect(screen.getByRole("button", { name: "清空欄位" })).toBeEnabled();
  });

  it("顯示可貼進 Browser Input 的網址", () => {
    renderPanel();

    expect(screen.getByLabelText("Browser Input 網址")).toHaveValue(
      "http://localhost:8765/overlay",
    );
  });

  it("讀不到 input 時說明可能原因", () => {
    renderPanel({}, { inputs: [] });

    expect(screen.getByText(/請確認 vMix 已啟動/)).toBeInTheDocument();
  });

  it("欄位名稱用 Line{n}.Text 慣例", () => {
    expect(generateFieldNames(2)).toEqual(["Line1.Text", "Line2.Text"]);
  });
});

describe("主機與連接埠輸入", () => {
  it("逐字輸入 IP 不會被吃掉，失焦才送出", async () => {
    // "192." ends in a dot, which the server rejects. Committing per keystroke
    // echoed the rejected value back and swallowed the character.
    const user = userEvent.setup();
    const onChange = renderPanel({ host: "127.0.0.1" });

    const field = screen.getByLabelText("vMix 主機");
    await user.clear(field);
    await user.type(field, "192.168.1.50");

    expect(field).toHaveValue("192.168.1.50");
    expect(onChange).not.toHaveBeenCalled();

    await user.tab();

    expect(onChange).toHaveBeenLastCalledWith({ host: "192.168.1.50" });
  });

  it("清空主機欄位不會送出，失焦時還原生效值", async () => {
    const user = userEvent.setup();
    const onChange = renderPanel({ host: "127.0.0.1" });

    const field = screen.getByLabelText("vMix 主機");
    await user.clear(field);
    await user.tab();

    expect(onChange).not.toHaveBeenCalled();
    expect(field).toHaveValue("127.0.0.1");
  });

  it("連接埠可以清空重打", async () => {
    const user = userEvent.setup();
    const onChange = renderPanel({ port: 8088 });

    const field = screen.getByLabelText("連接埠");
    await user.clear(field);
    await user.type(field, "8099");
    await user.tab();

    expect(onChange).toHaveBeenLastCalledWith({ port: 8099 });
  });

  it("超出範圍的連接埠不送出，還原生效值", async () => {
    const user = userEvent.setup();
    const onChange = renderPanel({ port: 8088 });

    const field = screen.getByLabelText("連接埠");
    await user.clear(field);
    await user.type(field, "99999");
    await user.tab();

    expect(onChange).not.toHaveBeenCalled();
    expect(field).toHaveValue(8088);
  });

  it("按 Enter 也會送出", async () => {
    const user = userEvent.setup();
    const onChange = renderPanel({ host: "127.0.0.1" });

    const field = screen.getByLabelText("vMix 主機");
    await user.clear(field);
    await user.type(field, "192.168.1.50{Enter}");

    expect(onChange).toHaveBeenLastCalledWith({ host: "192.168.1.50" });
  });
});
