"""Boot the web app headlessly and drive it, via Node.

The Python suite cannot see the browser layer at all, and that blind spot has
shipped two bugs that were indistinguishable from outside — "the button does
nothing":

* a duplicate element id, so the board was painted into a text input;
* ``main()`` throwing before the wiring ran, leaving buttons with no handler.

``tests/js/boot_test.js`` boots the real scripts against a small DOM and drives a
whole tournament. This wrapper runs it as part of the normal test run.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BOOT_TEST = ROOT / "tests" / "js" / "boot_test.js"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_web_app_boots_and_runs_a_tournament():
    result = subprocess.run(
        ["node", str(BOOT_TEST)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=ROOT,
    )
    # The script prints one line per check; surface all of it on failure.
    assert result.returncode == 0, (
        "the web app failed to boot or run:\n"
        f"{result.stdout}\n{result.stderr}"
    )
    assert "all checks passed" in result.stdout
