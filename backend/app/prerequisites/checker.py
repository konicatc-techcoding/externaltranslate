from __future__ import annotations

import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Protocol

from backend.app.prerequisites.models import PrerequisiteResult, PrerequisiteStatus


class SystemProbe(Protocol):
    """Read-only system query boundary for deterministic prerequisite checks."""

    def system(self) -> str: ...

    def machine(self) -> str: ...

    def windows_version(self) -> str: ...

    def installation_path(self, command: str) -> str | None: ...

    def command_version(self, command: str, args: tuple[str, ...]) -> str | None: ...


class DefaultSystemProbe:
    """Probe the local machine without installing or changing prerequisites."""

    _VMIX_CANDIDATES = (
        Path(r"C:\Program Files (x86)\vMix\vmix.exe"),
        Path(r"C:\Program Files\vMix\vmix.exe"),
    )

    def system(self) -> str:
        return platform.system()

    def machine(self) -> str:
        return platform.machine()

    def windows_version(self) -> str:
        return platform.version()

    def installation_path(self, command: str) -> str | None:
        if command == "vmix":
            installed = next(
                (path for path in self._VMIX_CANDIDATES if path.is_file()), None
            )
            return str(installed) if installed is not None else shutil.which(command)
        return shutil.which(command)

    def command_version(self, command: str, args: tuple[str, ...]) -> str | None:
        if command == "vmix":
            installation_path = self.installation_path(command)
            if installation_path is None:
                return None
            return self._windows_file_version(Path(installation_path))

        executable = shutil.which(command)
        if executable is None:
            return None

        try:
            completed = subprocess.run(
                [executable, *args],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            return None

        if completed.returncode != 0:
            return None

        output = completed.stdout.strip() or completed.stderr.strip()
        if not output:
            return None
        return output.splitlines()[0]

    @staticmethod
    def _windows_file_version(path: Path) -> str | None:
        powershell = shutil.which("powershell.exe")
        if powershell is None:
            return None

        escaped_path = str(path).replace("'", "''")
        script = (
            f"(Get-Item -LiteralPath '{escaped_path}').VersionInfo.ProductVersion"
        )

        try:
            completed = subprocess.run(
                [
                    powershell,
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    script,
                ],
                check=False,
                capture_output=True,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            return None

        if completed.returncode != 0:
            return None
        version = completed.stdout.decode("ascii", errors="replace").strip()
        return version or None


class PrerequisiteChecker:
    """Build the Stage 0 prerequisite report without changing the machine."""

    def __init__(
        self,
        probe: SystemProbe | None = None,
        python_version: tuple[int, int, int] | None = None,
    ) -> None:
        self._probe = probe or DefaultSystemProbe()
        self._python_version = python_version or (
            sys.version_info.major,
            sys.version_info.minor,
            sys.version_info.micro,
        )

    def stage0_report(self) -> list[PrerequisiteResult]:
        return [
            self._windows_result(),
            self._python_result(),
            self._node_result(),
            self._required_command(
                "npm",
                "npm",
                ("--version",),
                "安裝 npm，並確認可在專案內安裝前端依賴。",
            ),
            self._required_command(
                "git",
                "Git",
                ("--version",),
                "安裝 Git for Windows，供版本控制與變更檢查使用。",
            ),
            self._ffmpeg_result(),
            self._vmix_result(),
            PrerequisiteResult(
                identifier="audio",
                label="音訊輸入裝置與驅動",
                status=PrerequisiteStatus.NOT_CHECKED,
                required_for="Stage 1",
                detail="Stage 0 不開啟音訊裝置；Stage 1 將執行 WASAPI/WDM 功能測試。",
                action="進入 Stage 1 前選定麥克風或 Audio Interface 與輸入 channel。",
            ),
        ]

    def _windows_result(self) -> PrerequisiteResult:
        system = self._probe.system()
        machine = self._probe.machine()
        windows_version = self._probe.windows_version()
        version_match = re.match(r"^(\d+)\.(\d+)\.(\d+)", windows_version)
        version_parts = (
            tuple(int(part) for part in version_match.groups())
            if version_match is not None
            else None
        )
        supported_version = version_parts is not None and (
            version_parts[0] > 10
            or (version_parts[0] == 10 and version_parts[2] >= 10240)
        )
        ready = (
            system == "Windows"
            and machine.lower() in {"amd64", "x86_64"}
            and supported_version
        )
        return PrerequisiteResult(
            identifier="windows",
            label="Windows 64-bit",
            status=PrerequisiteStatus.READY if ready else PrerequisiteStatus.MISSING,
            required_for="v0.1",
            version=f"{system} {windows_version} {machine}",
            detail="需要 Windows 10/11 64-bit。",
            action="使用 Windows 10/11 64-bit 執行本程式。" if not ready else "",
        )

    def _node_result(self) -> PrerequisiteResult:
        version = self._probe.command_version("node", ("--version",))
        version_match = re.match(r"^v?(\d+)\.(\d+)\.(\d+)", version or "")
        version_parts = (
            tuple(int(part) for part in version_match.groups())
            if version_match is not None
            else None
        )
        supported = version_parts is not None and (
            (version_parts[0] == 20 and version_parts[1] >= 19)
            or (version_parts[0] >= 22 and version_parts[:2] >= (22, 12))
        )
        return PrerequisiteResult(
            identifier="node",
            label="Node.js",
            status=PrerequisiteStatus.READY if supported else PrerequisiteStatus.MISSING,
            required_for="Stage 0",
            version=version,
            detail="目前前端工具鏈需要 Node.js 20.19+ 或 22.12+。",
            action=(
                "安裝 Node.js 20.19+ 或 22.12+，供 React 前端建置使用。"
                if not supported
                else ""
            ),
        )

    def _python_result(self) -> PrerequisiteResult:
        ready = self._python_version[:2] == (3, 11)
        version = ".".join(str(part) for part in self._python_version)
        return PrerequisiteResult(
            identifier="python",
            label="Python",
            status=PrerequisiteStatus.READY if ready else PrerequisiteStatus.MISSING,
            required_for="開發與打包",
            version=version,
            detail="專案固定使用 Python 3.11。",
            action="安裝 Python 3.11，並建立專案專用虛擬環境。" if not ready else "",
        )

    def _required_command(
        self,
        identifier: str,
        label: str,
        args: tuple[str, ...],
        missing_action: str,
    ) -> PrerequisiteResult:
        version = self._probe.command_version(identifier, args)
        return PrerequisiteResult(
            identifier=identifier,
            label=label,
            status=PrerequisiteStatus.READY if version else PrerequisiteStatus.MISSING,
            required_for="Stage 0",
            version=version,
            action="" if version else missing_action,
        )

    def _ffmpeg_result(self) -> PrerequisiteResult:
        version = self._probe.command_version("ffmpeg", ("-version",))
        return PrerequisiteResult(
            identifier="ffmpeg",
            label="FFmpeg",
            status=PrerequisiteStatus.NOT_REQUIRED,
            required_for="v0.1 不需要",
            version=version,
            detail="Stage 0–4 不依賴 FFmpeg；若後續加入功能會先說明並取得同意。",
        )

    def _vmix_result(self) -> PrerequisiteResult:
        version = self._probe.command_version("vmix", ())
        installation_path = self._probe.installation_path("vmix")
        if installation_path is None:
            detection_detail = "目前未偵測到 vMix 安裝位置。"
        elif version is None:
            detection_detail = f"已偵測安裝位置，但無法讀取版本：{installation_path}。"
        else:
            detection_detail = f"已偵測 vMix {version}：{installation_path}。"
        return PrerequisiteResult(
            identifier="vmix",
            label="vMix",
            status=PrerequisiteStatus.OPTIONAL,
            required_for="Stage 5",
            version=version,
            detail=(
                f"{detection_detail}v0.1 不使用 vMix；"
                "Stage 5 必須執行真實 Web API smoke test。"
            ),
            action="Stage 5 前確認 vMix 已安裝、啟動且 Web API 已啟用。",
        )
