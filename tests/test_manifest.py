"""Tests for the manifest loader and registry."""

from __future__ import annotations

import textwrap

import pytest

from blackholearena.manifest import ManifestError, load_players, parse_manifest
from blackholearena.player import Player
from blackholearena.registry import Registry

#: A complete, valid player file. Tests below mutate it to break one thing.
GOOD_PLAYER = """
from blackholearena.player import Player

class Tiny(Player):
    @classmethod
    def get_name(cls): return "Tiny"
    @classmethod
    def get_authors(cls): return ["me"]
    @classmethod
    def get_description(cls): return "Plays the lowest free node."
    @classmethod
    def get_icon(cls): return "\U0001F9EA"
    def choose_move(self, state):
        return state["owner"].index(None)
"""


def _write(tmp_path, source: str, *, filename: str = "tiny.py", cls: str = "Tiny"):
    """Write ``source`` as a player file plus a manifest admitting it, side by side.

    This mirrors the real layout: ``players/<origin>/players.yaml`` names files in
    its own directory.
    """
    players_dir = tmp_path / "players"
    players_dir.mkdir(exist_ok=True)
    (players_dir / filename).write_text(textwrap.dedent(source))
    manifest = players_dir / "players.yaml"
    manifest.write_text(f"players:\n  - file: {filename}\n    class: {cls}\n")
    return manifest, players_dir


def test_parse_real_builtin_manifest_admits_the_reference_players():
    from blackholearena.manifest import BUILTIN_MANIFEST

    entries = parse_manifest(BUILTIN_MANIFEST)
    assert {e.cls for e in entries} >= {"Random"}
    # The manifest is an admission list: file + class, and nothing else.
    assert all(e.file.endswith(".py") for e in entries)


def test_the_custom_manifest_exists_and_parses():
    """Submissions land here. An empty list is not an error."""
    from blackholearena.manifest import CUSTOM_MANIFEST

    assert isinstance(parse_manifest(CUSTOM_MANIFEST), list)


def test_both_manifests_load_into_one_registry_tagged_by_origin():
    from blackholearena.manifest import BUILTIN

    # Not strict: a broken submission must not fail this suite. It is checked,
    # strictly, by tests/test_custom_players.py.
    reg = load_players(registry=Registry(), strict=False)
    assert {"random"} <= set(reg.names())
    assert reg.origin("random") == BUILTIN


def test_a_bare_filename_resolves_next_to_its_own_manifest(tmp_path):
    """Two origins can hold same-named files without a players_dir argument."""
    manifest, _ = _write(tmp_path, GOOD_PLAYER)
    reg = load_players(manifest, registry=Registry(), strict=True)
    assert reg.names() == ["Tiny"]


def test_missing_manifest_raises(tmp_path):
    with pytest.raises(ManifestError):
        parse_manifest(tmp_path / "does_not_exist.yaml")


def test_malformed_manifest_raises(tmp_path):
    bad = tmp_path / "players.yaml"
    bad.write_text("players:\n  - class: X\n")  # missing 'file'
    with pytest.raises(ManifestError):
        parse_manifest(bad)


def test_load_from_custom_dir(tmp_path):
    manifest, players_dir = _write(tmp_path, GOOD_PLAYER)
    reg = load_players(manifest, players_dir, Registry(), strict=True)
    assert reg.names() == ["Tiny"]
    assert isinstance(reg.get("Tiny"), Player)


def test_bad_entry_skipped_when_not_strict(tmp_path, capsys):
    manifest = tmp_path / "players.yaml"
    manifest.write_text("players:\n  - file: missing.py\n    class: Ghost\n")
    reg = load_players(manifest, tmp_path, Registry(), strict=False)
    assert reg.names() == []  # bad entry skipped, no crash
    assert "skipping" in capsys.readouterr().err


@pytest.mark.parametrize(
    "missing",
    ["get_name", "get_authors", "get_description", "get_icon"],
)
def test_player_missing_an_accessor_is_rejected(tmp_path, missing):
    """ABCMeta refuses to construct it, and the loader reports it clearly."""
    source = "\n".join(
        line for line in GOOD_PLAYER.splitlines() if f"def {missing}(" not in line
    )
    # Drop the now-orphaned @classmethod immediately above the removed def.
    lines, cleaned = source.splitlines(), []
    for i, line in enumerate(lines):
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        if line.strip() == "@classmethod" and not nxt.strip().startswith("def get_"):
            continue
        cleaned.append(line)
    manifest, players_dir = _write(tmp_path, "\n".join(cleaned))
    with pytest.raises(ManifestError):
        load_players(manifest, players_dir, Registry(), strict=True)


def test_player_with_a_blank_name_is_rejected(tmp_path):
    manifest, players_dir = _write(
        tmp_path, GOOD_PLAYER.replace('return "Tiny"', 'return "   "')
    )
    with pytest.raises(ManifestError, match="get_name"):
        load_players(manifest, players_dir, Registry(), strict=True)


def test_player_with_no_authors_is_rejected(tmp_path):
    manifest, players_dir = _write(
        tmp_path, GOOD_PLAYER.replace('return ["me"]', "return []")
    )
    with pytest.raises(ManifestError, match="get_authors"):
        load_players(manifest, players_dir, Registry(), strict=True)


def test_duplicate_names_are_rejected(tmp_path):
    """Two admitted classes claiming the same name must fail, not shadow silently."""
    players_dir = tmp_path / "players"
    players_dir.mkdir()
    (players_dir / "a.py").write_text(textwrap.dedent(GOOD_PLAYER))
    (players_dir / "b.py").write_text(textwrap.dedent(GOOD_PLAYER))
    manifest = tmp_path / "players.yaml"
    manifest.write_text(
        "players:\n"
        "  - file: a.py\n    class: Tiny\n"
        "  - file: b.py\n    class: Tiny\n"
    )
    with pytest.raises(ManifestError):
        load_players(manifest, players_dir, Registry(), strict=True)


def test_registry_rejects_duplicate_names():
    from players.builtin.random import Random

    reg = Registry()
    reg.register(Random.create(seed=0))
    with pytest.raises(ValueError):
        reg.register(Random.create(seed=1))
    reg.register(Random.create(seed=2), replace=True)  # ok with replace
    assert len(reg) == 1
