import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AudioSourceSelector } from "./AudioSourceSelector";
import {
  DEFAULT_CAPTION_STYLE,
  DEFAULT_VMIX_SETTINGS,
  type AppSettings,
} from "../types/runtime";

const DEVICES = [
  {
    index: 3,
    name: "Line In",
    host_api: "Windows WASAPI",
    max_input_channels: 2,
    default_sample_rate: 48000,
  },
];

const ENDPOINTS = [
  {
    index: 7,
    name: "Speakers",
    host_api: "Windows WASAPI",
    channels: 2,
    default_sample_rate: 48000,
    is_default: true,
  },
];

function settings(overrides: Partial<AppSettings> = {}): AppSettings {
  return {
    source_kind: "wasapi_loopback",
    device_index: null,
    loopback_endpoint_index: null,
    channel: 1,
    caption_max_payload_length: 4096,
    caption_chars_per_line: 20,
    caption_max_lines: 2,
    caption_sentence_breaks: true,
    caption_style: DEFAULT_CAPTION_STYLE,
    vmix: DEFAULT_VMIX_SETTINGS,
    session_rotation_seconds: 480,
    ...overrides,
  };
}

describe("AudioSourceSelector", () => {
  it("切換到輸入裝置時清除 loopback 選擇", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <AudioSourceSelector
        settings={settings()}
        devices={DEVICES}
        endpoints={ENDPOINTS}
        onRefresh={vi.fn()}
        onChange={onChange}
      />,
    );

    await user.click(screen.getByLabelText("麥克風／Audio Interface"));

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ source_kind: "input_device", device_index: 3 }),
    );
    expect(onChange.mock.calls[0][0]).not.toHaveProperty("loopback_endpoint_index");
  });

  it("兩種來源在 UI 上互斥", () => {
    render(
      <AudioSourceSelector
        settings={settings({ source_kind: "input_device", device_index: 3 })}
        devices={DEVICES}
        endpoints={ENDPOINTS}
        onRefresh={vi.fn()}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByLabelText("麥克風／Audio Interface")).toBeChecked();
    expect(screen.getByLabelText("電腦播放聲音（系統輸出）")).not.toBeChecked();
    expect(screen.queryByLabelText("電腦播放聲音（系統輸出）", { selector: "select" })).toBeNull();
  });

  it("標示裝置編號可能改變", () => {
    render(
      <AudioSourceSelector
        settings={settings()}
        devices={DEVICES}
        endpoints={ENDPOINTS}
        onRefresh={vi.fn()}
        onChange={vi.fn()}
      />,
    );
    expect(
      screen.getByText("裝置編號可能在重新插拔或重開機後改變，開始前請重新列舉。"),
    ).toBeInTheDocument();
  });

  it("執行中停用所有選擇", () => {
    render(
      <AudioSourceSelector
        settings={settings()}
        devices={DEVICES}
        endpoints={ENDPOINTS}
        disabled
        onRefresh={vi.fn()}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByLabelText("麥克風／Audio Interface")).toBeDisabled();
    expect(screen.getByRole("button", { name: "重新列舉" })).toBeDisabled();
  });

  it("系統輸出可選擇跟隨預設", () => {
    render(
      <AudioSourceSelector
        settings={settings()}
        devices={DEVICES}
        endpoints={ENDPOINTS}
        onRefresh={vi.fn()}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText("跟隨系統預設輸出")).toBeInTheDocument();
    expect(screen.getByText("7: Speakers（目前預設輸出）")).toBeInTheDocument();
  });
});
