#!/usr/bin/env python3
"""Assemble the static web assets that Pyodide loads in the browser.

The web page runs the *same* Python as the tournament. To make that code
available to Pyodide, we bundle it into ``web/py.zip``:

    py.zip
    ├── blackholearena/        (the installable package, copied from src/)
    ├── players/         (copied whole: builtin/ and custom/, each with its
    │                     own players.yaml manifest)
    └── webglue.py       (the JS<->Python bridge)

We also copy ``results/leaderboard.json`` next to the page so the scoreboard can
fetch it. In the browser, ``pyodide-bootstrap.js`` fetches ``py.zip``, unpacks it
into the virtual filesystem, and imports ``webglue``.

Run this locally before serving ``web/`` with a static server; the GitHub Pages
workflow runs it too.
"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WEB = REPO_ROOT / "web"
STAGE = WEB / "py"

#: Bytes per kibibyte, used to report the built archive size.
_BYTES_PER_KIB = 1024


def main() -> int:
    """Assemble ``web/py.zip`` (and copy the leaderboard) for the browser build.

    Returns:
        Process exit code (``0`` on success).
    """
    if STAGE.exists():
        shutil.rmtree(STAGE)
    STAGE.mkdir(parents=True)

    # 1. The package.
    shutil.copytree(
        REPO_ROOT / "src" / "blackholearena",
        STAGE / "blackholearena",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    # 2. Player files and their manifests. Copied as a tree: each origin
    #    directory carries its own players.yaml, and the loader resolves a bare
    #    filename next to the manifest that names it.
    shutil.copytree(
        REPO_ROOT / "players",
        STAGE / "players",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.md"),
    )
    # 3. Bridge.
    shutil.copy2(WEB / "webglue.py", STAGE / "webglue.py")

    # 4. Zip it up (a single fetch in the browser).
    zip_path = WEB / "py.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(STAGE.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(STAGE))

    # The staging tree has served its purpose. Remove it: the Pages workflow
    # uploads the whole of web/ as the site root, so leaving it behind published
    # an unzipped duplicate of the entire package at /py/ alongside py.zip.
    shutil.rmtree(STAGE)

    # 5. Leaderboard for the scoreboard (best-effort).
    leaderboard = REPO_ROOT / "results" / "leaderboard.json"
    if leaderboard.exists():
        shutil.copy2(leaderboard, WEB / "leaderboard.json")
        print(f"Copied leaderboard -> {WEB / 'leaderboard.json'}")
    else:
        print("No results/leaderboard.json yet (run: blackhole-tournament).")

    print(f"Built {zip_path} ({zip_path.stat().st_size // _BYTES_PER_KIB} KiB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
