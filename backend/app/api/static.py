from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.resources import frontend_dist_path

# The two pages the app has. `App.tsx` picks between them from
# `window.location.pathname`, so both are the same document and neither is a
# file on disk. A catch-all would serve HTML for a mistyped API path too,
# which turns a 404 into a JSON parse error at the caller.
_PAGES = ("/", "/overlay")


def default_frontend_dist() -> Path:
    """Where the built page lives: `frontend/dist`, or the packaged copy."""
    return frontend_dist_path()


def mount_frontend(app: FastAPI, dist: Path | None = None) -> Path | None:
    """Serve the built page from the API process, if it has been built.

    One process and one port instead of a backend plus a dev server: that is
    what makes the program runnable on a machine that has no Node, and it puts
    the page on the same origin as the API it calls.

    A checkout that has not been built yet is not an error. The API keeps
    working and the missing page is reported, so the operator sees "the page
    is not built" rather than a service that refuses to start.
    """
    root = default_frontend_dist() if dist is None else dist
    index = root / "index.html"
    if not index.is_file():
        return None

    assets = root / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    async def page() -> FileResponse:
        # The document must never be cached. Asset filenames carry a content
        # hash, so a cached `index.html` keeps asking for the previous build's
        # files — which an upgrade has deleted, leaving a page that either
        # shows the old UI or fails to load at all. The assets themselves are
        # safe to cache precisely because their names change.
        return FileResponse(index, headers={"Cache-Control": "no-store"})

    for path in _PAGES:
        app.add_api_route(path, page, methods=["GET"], include_in_schema=False)
    return root
