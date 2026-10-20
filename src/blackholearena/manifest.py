"""Manifest-based player discovery.

Players are discovered from **explicit, human-edited manifests** — never by
auto-scanning a folder. This is a deliberate design choice: when someone opens a
PR to add a bot, the reviewer sees, in a single diff, both the new file and the
one line that admits it. That legibility *is* the security gate; auto-importing a
directory would hide what is being admitted and would run a stranger's top-level
code merely to discover it.

There are **two** manifests, each next to the players it admits::

    players/
      builtin/players.yaml   the reference ladder that ships with the project
      custom/players.yaml    everything submitted by pull request

The split is not cosmetic. It keeps a submission's diff inside ``custom/``, so no
two submissions collide in the same manifest and none of them can touch the
reference ladder. It also tells the tournament which players are which, which is
what decides how many roster copies each one is entered with (see
:data:`~blackholearena.tournament.BUILTIN_PLAYER_COPIES` and
:data:`~blackholearena.tournament.CUSTOM_PLAYER_COPIES`).

A manifest is purely an **admission list**: which file, and which class in it.
Nothing else::

    players:
      - file: random.py    # path to the .py file (see resolution below)
        class: Random      # the Player subclass to admit

A player's *identity* — name, authors, description — is declared by the class
itself, via :meth:`~blackholearena.player.Player.get_name` and friends. Keeping it there
rather than here means there is exactly one source of truth: a submission cannot
claim one name in the manifest and another in the code, and there is nothing to
drift. The manifest answers "is this admitted?"; the class answers "what is it?".

Path resolution for ``file``:

* A bare filename (e.g. ``random_bot.py``) is resolved **next to its own
  manifest**, so an entry in ``players/custom/players.yaml`` names a file in
  ``players/custom/``.
* A path with a separator (e.g. ``community/foo/bar.py``) is resolved relative
  to the repo root.

Loading a player *imports its file*, which runs that file's top-level code. That
is expected and safe **only because** files arrive through reviewed PRs.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .player import Player
from .registry import REGISTRY, Registry

#: Repo root, inferred as the parent of ``src/``.
REPO_ROOT = Path(__file__).resolve().parents[2]
#: Directory holding every player, in one subdirectory per origin.
PLAYERS_DIR = REPO_ROOT / "players"
#: Label for a player admitted by the built-in manifest.
BUILTIN = "builtin"
#: Label for a player admitted by the submissions manifest.
CUSTOM = "custom"
#: The manifest admitting the reference ladder.
BUILTIN_MANIFEST = PLAYERS_DIR / BUILTIN / "players.yaml"
#: The manifest admitting submitted players.
CUSTOM_MANIFEST = PLAYERS_DIR / CUSTOM / "players.yaml"
#: Every manifest, as ``origin label -> path``, in load order.
DEFAULT_MANIFESTS: dict[str, Path] = {
    BUILTIN: BUILTIN_MANIFEST,
    CUSTOM: CUSTOM_MANIFEST,
}


@dataclass
class ManifestEntry:
    """One line of the manifest, already parsed and validated.

    Attributes:
        file: the ``file`` field, verbatim (not yet resolved to a path).
        cls: name of the :class:`~blackholearena.player.Player` subclass to admit.
    """

    file: str
    cls: str


class ManifestError(Exception):
    """Raised when the manifest itself is malformed (not when a bot misbehaves)."""


def parse_manifest(manifest_path: str | Path) -> list[ManifestEntry]:
    """Parse ``players.yaml`` into a list of :class:`ManifestEntry`.

    Raises:
        ManifestError: if the file is missing, unparseable, or an entry is
            missing a required field.
    """
    path = Path(manifest_path)
    if not path.exists():
        raise ManifestError(f"Manifest not found: {path}")
    try:
        data: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:  # pragma: no cover - defensive
        raise ManifestError(f"Could not parse {path}: {exc}") from exc

    if not isinstance(data, dict) or "players" not in data:
        raise ManifestError("Manifest must be a mapping with a top-level 'players' list")
    raw_players = data["players"]
    if not isinstance(raw_players, list):
        raise ManifestError("'players' must be a list")

    entries: list[ManifestEntry] = []
    for i, raw in enumerate(raw_players):
        if not isinstance(raw, dict):
            raise ManifestError(f"players[{i}] must be a mapping")
        try:
            entries.append(ManifestEntry(file=str(raw["file"]), cls=str(raw["class"])))
        except KeyError as exc:
            raise ManifestError(f"players[{i}] is missing required field {exc}") from exc
    return entries


def _resolve_file(file: str, players_dir: Path, repo_root: Path) -> Path:
    """Resolve a manifest ``file`` field to an absolute path (see module docs)."""
    p = Path(file)
    if p.is_absolute():
        return p
    if len(p.parts) == 1:  # bare filename -> beside its own manifest
        return players_dir / p
    return repo_root / p


def _load_class_from_file(path: Path, class_name: str) -> type[Player]:
    """Import ``path`` and return its ``class_name`` attribute.

    The module is loaded under a unique synthetic name so that two player files
    that happen to share a filename never collide in ``sys.modules``.
    """
    if not path.exists():
        raise ManifestError(f"Player file not found: {path}")
    module_name = f"blackholearena_player_{path.stem}_{abs(hash(str(path)))}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ManifestError(f"Could not import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    try:
        obj = getattr(module, class_name)
    except AttributeError as exc:
        raise ManifestError(f"{path} has no class {class_name!r}") from exc
    if not (isinstance(obj, type) and issubclass(obj, Player)):
        raise ManifestError(f"{class_name!r} in {path} is not a Player subclass")
    return obj


def _build_and_validate(cls: type[Player], path: Path) -> Player:
    """Construct ``cls`` via its factory and check it declares a usable identity.

    ``ABCMeta`` already refuses to instantiate a subclass that has not implemented
    the abstract accessors — that check happens here, on ``create``. But it only
    guards *instantiation*: reading ``cls.get_name()`` statically on a subclass
    that skipped it returns ``None`` silently. Since the tournament, the docs and
    the web app all read metadata without constructing, validate it once here so a
    bad submission fails loudly at load time instead of leaking a ``None`` into
    the scoreboard.

    Raises:
        ManifestError: if construction fails or any accessor returns something
            unusable.
    """
    try:
        instance = cls.create(seed=0)
    except TypeError as exc:
        # The overwhelmingly common cause is an unimplemented abstract accessor.
        raise ManifestError(f"{cls.__name__} in {path} could not be created: {exc}") from exc

    name = cls.get_name()
    if not isinstance(name, str) or not name.strip():
        raise ManifestError(f"{cls.__name__} in {path}: get_name() must return a non-empty str")

    authors = cls.get_authors()
    if not isinstance(authors, list) or not authors or not all(
        isinstance(a, str) and a.strip() for a in authors
    ):
        raise ManifestError(
            f"{cls.__name__} in {path}: get_authors() must return a non-empty list of names"
        )

    description = cls.get_description()
    if not isinstance(description, str) or not description.strip():
        raise ManifestError(
            f"{cls.__name__} in {path}: get_description() must return a non-empty str"
        )

    icon = cls.get_icon()
    if not isinstance(icon, str) or not icon.strip():
        raise ManifestError(
            f"{cls.__name__} in {path}: get_icon() must return a single emoji"
        )

    return instance


def load_players(
    manifests: str | Path | Mapping[str, str | Path] = DEFAULT_MANIFESTS,
    players_dir: str | Path | None = None,
    registry: Registry | None = None,
    *,
    strict: bool = False,
) -> Registry:
    """Load every player named in the manifests into one registry.

    Each admitted class is constructed once through
    :meth:`~blackholearena.player.Player.create` and its identity is validated, so a
    submission that forgets an accessor, cannot be built, or reuses an existing
    player's name fails here rather than midway through a tournament.

    Args:
        manifests: ``origin label -> manifest path``, loaded in order; the label
            is recorded on each player it admits (see
            :meth:`~blackholearena.registry.Registry.origin`). A bare path is accepted
            as shorthand for a single unlabelled manifest.
        players_dir: directory used to resolve bare filenames. Defaults to each
            manifest's own directory.
        registry: registry to populate; defaults to the global
            :data:`~blackholearena.registry.REGISTRY` (cleared first).
        strict: if ``True``, any bad entry raises. If ``False`` (default), a bad
            entry is skipped with a warning printed to stderr so that one broken
            submission never blocks loading the rest.

    Returns:
        The populated registry.

    Raises:
        ManifestError: in ``strict`` mode, for any unusable entry.
    """
    if registry is None:
        registry = REGISTRY
        registry.clear()

    if isinstance(manifests, (str, Path)):
        manifests = {"": manifests}
    for origin, manifest_path in manifests.items():
        _load_one(manifest_path, players_dir, registry, origin, strict=strict)
    return registry


def _load_one(
    manifest_path: str | Path,
    players_dir: str | Path | None,
    registry: Registry,
    origin: str,
    *,
    strict: bool,
) -> None:
    """Load a single manifest into ``registry``, tagging its players ``origin``."""
    manifest = Path(manifest_path).resolve()
    # Bare filenames resolve beside the manifest; a path with a separator is
    # relative to the repo root, which is two levels up from players/<origin>/.
    here = manifest.parent
    repo_root = here.parent.parent if here.parent.name == PLAYERS_DIR.name else here
    players_dir = here if players_dir is None else Path(players_dir)
    entries = parse_manifest(manifest)

    for entry in entries:
        label = f"{entry.file}:{entry.cls}"
        try:
            path = _resolve_file(entry.file, players_dir, repo_root)
            cls = _load_class_from_file(path, entry.cls)
            instance = _build_and_validate(cls, path)
            # No `replace=True`: a duplicate name must be a hard error. "Unique
            # name" is a documented merge gate, and silently overwriting let one
            # submission shadow another with no output at all.
            registry.register(instance, origin=origin)
        except ValueError as exc:
            # Registry rejected the name (already taken).
            if strict:
                raise ManifestError(f"{label}: {exc}") from exc
            print(f"[manifest] skipping {label}: {exc}", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001 - one bad bot must not stop the rest
            if strict:
                raise
            print(f"[manifest] skipping {label}: {exc}", file=sys.stderr)
