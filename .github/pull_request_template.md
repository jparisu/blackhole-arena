<!--
Default PR template: a NEW PLAYER submission — which is what nearly every pull
request here is. Not adding a player? Append ?template=other.md to the PR URL,
or just replace this with a description of your change.
-->

## New player: <!-- your bot's name -->

**Author:** <!-- your GitHub handle -->
**Strategy in one sentence:** <!-- what does your bot do? -->

### Submission checklist

- [ ] Added a single file `players/custom/<my_bot>.py`.
- [ ] The class subclasses `blackholearena.player.Player`.
- [ ] `get_name`, `get_authors`, `get_description` and `get_icon` are implemented.
- [ ] The icon is a **single** emoji, and not already used by another player.
- [ ] The name is **unique** — no admitted player already uses it.
- [ ] `choose_move(self, state) -> int` returns a **legal** move (a free node).
- [ ] Does **not** mutate the `state` it receives.
- [ ] Added **exactly one** entry to `players/custom/players.yaml` (`file` and `class`).
- [ ] No external dependencies beyond the standard library and `blackholearena`.
- [ ] No network / filesystem / subprocess / `eval` / `exec`.
- [ ] Runs locally: `pytest tests/test_custom_players.py` is green and `blackhole-tournament --no-subprocess` works.

### Maintainer review (acceptance criteria)

- [ ] **Design** — one file in `players/custom/` + one manifest line, minimal.
- [ ] **Correctness** — CI green; legal moves; no mutation; no errors/timeouts vs
      the reference bots.
- [ ] **No malware** — code read in full; nothing suspicious.

<!--
A player that errors or times out will not be merged — robustness is the
submitter's responsibility. See CONTRIBUTING.md and
https://blackhole-arena.readthedocs.io/en/latest/game/upload-a-bot/submit-a-player/
-->
