"""Entry point for the packaged build.

Kept separate from `backend/app/cli/app_launcher.py` so the spec has a single
concrete script to analyse, and so the frozen program gets the multiprocessing
guard that a console_script wrapper would otherwise provide.
"""

from __future__ import annotations

import multiprocessing
import sys

from backend.app.cli.app_launcher import main

if __name__ == "__main__":
    # Without this a frozen program that ever spawns a process re-runs the
    # whole launcher in the child, which on Windows means a second server.
    multiprocessing.freeze_support()
    sys.exit(main())
