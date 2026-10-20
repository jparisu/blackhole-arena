"""Static checks on the shipped web assets.

The browser code has no unit tests of its own — it needs a DOM — but the ways it
breaks most cheaply are structural and visible from the text alone. These checks
exist because of a real bug: ``id="t-board"`` was used twice, once for the setup
input and once for the board container. ``getElementById`` returns the *first*
match, so the tournament painted its board into a text input and nothing appeared.
Nothing in the test suite or in CI noticed.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parent.parent / "web"
#: The shell plus every screen partial: ids live in the partials now.
HTML = "\n".join(
    p.read_text(encoding="utf-8")
    for p in [WEB / "index.html", *sorted((WEB / "screens").glob("*.html"))]
)
#: Every screen script. `main.js` is included: it wires the others.
APP_JS = "\n".join(p.read_text(encoding="utf-8") for p in sorted((WEB / "js").glob("*.js")))
BOOT_JS = (WEB / "pyodide-bootstrap.js").read_text(encoding="utf-8")

#: Every ``id="..."`` in the page, in document order.
IDS = re.findall(r'id="([^"]+)"', HTML)
#: Every ``$("...")`` lookup in app.js.
LOOKUPS = set(re.findall(r'\$\("([^"]+)"\)', APP_JS))


def test_every_screen_partial_exists():
    """main.js fetches these by name; a missing file is a blank page."""
    for name in ("menu", "game", "scoreboard", "tournament", "about"):
        assert (WEB / "screens" / f"{name}.html").is_file(), f"screens/{name}.html is missing"


def test_index_loads_every_script():
    shell = (WEB / "index.html").read_text(encoding="utf-8")
    for name in ("core", "play", "scoreboard", "tournament", "main"):
        assert f"js/{name}.js" in shell, f"index.html does not load js/{name}.js"
    # core defines the helpers the others use, so it must come first.
    assert shell.index("js/core.js") < shell.index("js/play.js")
    assert shell.index("js/main.js") == max(
        shell.index(f"js/{n}.js") for n in ("core", "play", "scoreboard", "tournament", "main")
    ), "main.js must be loaded last"


def test_every_screen_setup_is_called_by_main():
    """A screen whose setup never runs has dead controls and no error."""
    main_js = (WEB / "js" / "main.js").read_text(encoding="utf-8")
    for fn in ("setupNav", "setupPlay", "setupScoreboard", "setupTournament"):
        assert fn in main_js, f"main.js never calls {fn}()"


def test_no_duplicate_ids():
    """Two elements sharing an id makes getElementById silently pick the first."""
    seen: dict[str, int] = {}
    for name in IDS:
        seen[name] = seen.get(name, 0) + 1
    duplicates = sorted(n for n, c in seen.items() if c > 1)
    assert not duplicates, f"duplicate id(s) in index.html: {duplicates}"


def test_every_lookup_resolves_to_an_element():
    """A `$("typo")` returns null and the first property access throws."""
    missing = sorted(LOOKUPS - set(IDS))
    assert not missing, f"app.js looks up ids that index.html does not define: {missing}"


@pytest.mark.parametrize("prefix", ["screen-", "seat-"])
def test_template_literal_lookups_have_targets(prefix):
    """`$(`screen-${name}`)` cannot be checked exactly, but the family must exist."""
    assert any(i.startswith(prefix) for i in IDS), f"no id starts with {prefix!r}"


def test_every_screen_has_a_nav_control():
    """A screen nobody can reach is dead weight; a nav to nowhere throws."""
    screens = {i[len("screen-"):] for i in IDS if i.startswith("screen-")}
    navs = set(re.findall(r'data-nav="([^"]+)"', HTML))
    assert navs <= screens, f"nav targets with no screen: {sorted(navs - screens)}"
    assert screens <= navs, f"screens with no nav control: {sorted(screens - navs)}"


def test_the_bridge_exposes_everything_app_js_calls():
    """`window.BH.foo()` must be something pyodide-bootstrap.js actually defines."""
    used = set(re.findall(r"window\.BH\.(\w+)", APP_JS))
    defined = set(re.findall(r"^\s{4}(\w+):", BOOT_JS, re.M))
    missing = sorted(used - defined)
    assert not missing, f"app.js calls window.BH.{{{', '.join(missing)}}}, not exposed"


def test_bridge_calls_exist_in_webglue():
    """Each bridge entry must map to a real function in the Python module."""
    webglue_src = (WEB / "webglue.py").read_text(encoding="utf-8")
    functions = set(re.findall(r"^def (\w+)", webglue_src, re.M))
    called = set(re.findall(r"webglue\.(\w+)\(", BOOT_JS))
    missing = sorted(called - functions)
    assert not missing, f"the bridge calls webglue.{{{', '.join(missing)}}}, which do not exist"
