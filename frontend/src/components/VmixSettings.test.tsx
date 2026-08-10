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

  it("尚未選 input 時不能送測試文字", () => {
    renderPanel({ input_guid: null });

    expect(screen.getByRole("button", { name: "送出測試文字" })).toBeDisabled();
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
