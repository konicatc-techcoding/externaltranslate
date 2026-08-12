"""Build the Windows onedir package.

    PYTHONPATH='' uv run python scripts/build_windows.py

Produces `dist/ExternalTranslate/`: copy that folder to the target machine and
run `ExternalTranslate.exe`. Nothing needs to be installed there — no Python,
no Node, no uv.

The frontend is built first and on every run. A bundle whose `frontend/dist`
is stale ships a page that does not match the backend inside it, and the
mismatch is invisible until someone uses the feature that changed.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = PROJECT_ROOT / "dist" / "ExternalTranslate"
SPEC = PROJECT_ROOT / "packaging" / "externaltranslate.spec"


def run(command: list[str], *, cwd: Path) -> None:
    print(f"$ {' '.join(command)}", flush=True)
    completed = subprocess.run(command, cwd=cwd, shell=False, check=False)
    if completed.returncode != 0:
        raise SystemExit(f"失敗（exit {completed.returncode}）：{' '.join(command)}")


def npm(arguments: list[str]) -> list[str]:
    # npm on Windows is a .cmd shim, which is not directly executable.
    executable = shutil.which("npm")
    if executable is None:
        raise SystemExit(
            "找不到 npm。建置前端需要 Node.js；"
            "安裝後重新執行，或在別台建置好再把 frontend/dist 複製過來。"
        )
    return [executable, *arguments]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="建置 Windows onedir 套件")
    parser.add_argument(
        "--skip-frontend",
        action="store_true",
        help="沿用現有的 frontend/dist（這台沒有 Node 時使用）",
    )
    args = parser.parse_args(argv)

    if args.skip_frontend:
        if not (PROJECT_ROOT / "frontend" / "dist" / "index.html").is_file():
            raise SystemExit("frontend/dist 不存在，無法略過前端建置。")
        print("略過前端建置，沿用現有的 frontend/dist。", flush=True)
    else:
        run(npm(["install"]), cwd=PROJECT_ROOT)
        run(npm(["run", "build"]), cwd=PROJECT_ROOT)

    # A stale output directory hides a file that stopped being produced.
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)

    run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--distpath",
            str(PROJECT_ROOT / "dist"),
            "--workpath",
            str(PROJECT_ROOT / "build"),
            str(SPEC),
        ],
        cwd=PROJECT_ROOT,
    )

    executable = OUTPUT / "ExternalTranslate.exe"
    if not executable.is_file():
        raise SystemExit(f"建置結束但找不到 {executable}")

    print(f"\n完成：{OUTPUT}")
    print("把整個資料夾複製到目標機器，執行 ExternalTranslate.exe 即可。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
