from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from backend.app.prerequisites import checker as checker_module
from backend.app.prerequisites.checker import DefaultSystemProbe, PrerequisiteChecker
from backend.app.prerequisites.models import PrerequisiteStatus


@dataclass(frozen=True)
class FakeProbe:
    commands: dict[str, str | None]
    system_name: str = "Windows"
    machine_name: str = "AMD64"
    system_version: str = "10.0.26200"

    def system(self) -> str:
        return self.system_name

    def machine(self) -> str:
        return self.machine_name

    def windows_version(self) -> str:
        return self.system_version

    def installation_path(self, command: str) -> str | None:
        return None

    def command_version(self, command: str, _args: tuple[str, ...]) -> str | None:
        return self.commands.get(command)


def test_stage0_report_marks_required_tools_ready() -> None:
    checker = PrerequisiteChecker(
        probe=FakeProbe(
            commands={
                "node": "v22.23.1",
                "npm": "10.9.8",
                "git": "git version 2.54.0.windows.1",
                "ffmpeg": "ffmpeg version 8.1.1",
                "vmix": "28.0.0.42",
            }
        ),
        python_version=(3, 11, 0),
    )

    report = {item.identifier: item for item in checker.stage0_report()}

    assert report["windows"].status is PrerequisiteStatus.READY
    assert report["python"].status is PrerequisiteStatus.READY
    assert report["node"].status is PrerequisiteStatus.READY
    assert report["npm"].status is PrerequisiteStatus.READY
    assert report["git"].status is PrerequisiteStatus.READY
    assert report["ffmpeg"].status is PrerequisiteStatus.NOT_REQUIRED
    assert report["ffmpeg"].version == "ffmpeg version 8.1.1"
    assert report["vmix"].status is PrerequisiteStatus.OPTIONAL
    assert report["audio"].status is PrerequisiteStatus.NOT_CHECKED


def test_stage0_report_gives_traditional_chinese_actions_for_missing_tools() -> None:
    checker = PrerequisiteChecker(
        probe=FakeProbe(commands={}),
        python_version=(3, 10, 9),
    )

    report = {item.identifier: item for item in checker.stage0_report()}

    assert report["python"].status is PrerequisiteStatus.MISSING
    assert "Python 3.11" in report["python"].action
    assert report["node"].status is PrerequisiteStatus.MISSING
    assert "安裝" in report["node"].action
    assert report["git"].status is PrerequisiteStatus.MISSING
    assert report["vmix"].status is PrerequisiteStatus.OPTIONAL


def test_stage0_report_rejects_unsupported_windows_and_node() -> None:
    checker = PrerequisiteChecker(
        probe=FakeProbe(
            commands={"node": "v18.20.8", "npm": "10.9.8", "git": "git 2.54"},
            system_version="6.1.7601",
        ),
        python_version=(3, 11, 0),
    )

    report = {item.identifier: item for item in checker.stage0_report()}

    assert report["windows"].status is PrerequisiteStatus.MISSING
    assert "Windows 10/11" in report["windows"].action
    assert report["node"].status is PrerequisiteStatus.MISSING
    assert "20.19" in report["node"].action


def test_default_probe_rejects_failed_version_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(checker_module.shutil, "which", lambda command: f"{command}.exe")
    monkeypatch.setattr(
        checker_module.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], returncode=1, stdout="", stderr="invalid option"
        ),
    )

    assert DefaultSystemProbe().command_version("tool", ("--version",)) is None


def test_default_probe_reads_vmix_file_version(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    vmix_path = tmp_path / "vmix.exe"
    vmix_path.write_bytes(b"fixture")
    monkeypatch.setattr(DefaultSystemProbe, "_VMIX_CANDIDATES", (vmix_path,))
    monkeypatch.setattr(
        checker_module.shutil,
        "which",
        lambda command: "powershell.exe" if command == "powershell.exe" else None,
    )
    monkeypatch.setattr(
        checker_module.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], returncode=0, stdout=b"28.0.0.42\r\n", stderr=b""
        ),
    )

    assert DefaultSystemProbe().command_version("vmix", ()) == "28.0.0.42"
    assert DefaultSystemProbe().installation_path("vmix") == str(vmix_path)


def test_default_probe_separates_vmix_location_from_unavailable_version(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    vmix_path = tmp_path / "vmix.exe"
    vmix_path.write_bytes(b"fixture")
    monkeypatch.setattr(DefaultSystemProbe, "_VMIX_CANDIDATES", (vmix_path,))
    monkeypatch.setattr(checker_module.shutil, "which", lambda command: None)

    probe = DefaultSystemProbe()

    assert probe.installation_path("vmix") == str(vmix_path)
    assert probe.command_version("vmix", ()) is None
