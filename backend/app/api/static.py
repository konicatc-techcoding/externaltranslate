from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# The two pages the app has. `App.tsx` picks between them from
# `window.location.pathname`, so both are the same document and neither is a
# file on disk. A catch-all would serve HTML for a mistyped API path too,
# which turns a 404 into a JSON parse error at the caller.
_PAGES = ("/", "/overlay")


def default_frontend_dist() -> Path:
    """Where `npm run build` puts the page, in a source checkout."""
    return Path(__file__).resolve().parents[3] / "frontend" / "dist"


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
        return FileResponse(index)

    for path in _PAGES:
        app.add_api_route(path, page, methods=["GET"], include_in_schema=False)
    return root
