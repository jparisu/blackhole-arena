# Contributing to BlackHole Arena

Thanks for your interest! The main way to contribute is by **adding a new AI
player** through a Pull Request.

> **The full, worked guide lives in the docs:**
> [Submit a player](https://blackhole-arena.readthedocs.io/en/latest/en/game/upload-a-bot/submit-a-player/)
> — every step, with copy-pasteable code.
>
> This page is the short version.

## The upload mechanism is the Pull Request

There is no separate upload form. You **fork the repo, add your player file,
register it in the manifest, and open a PR**. CI runs the tests. A maintainer
reviews and merges. Your code only ever runs *after* a human accepts your PR —
which is exactly why review is the security and correctness gate.

## Add a player in 4 steps

1. **Fork & clone**, then create a branch.

2. **Add your player file** at `players/custom/<your_bot>.py`. It must subclass
   `blackholearena.player.Player`, declare its identity (`get_name`,
   `get_authors`, `get_description`, `get_icon`) and implement
   `choose_move(self, state) -> int` (the free node to place its tiles on). Copy
   [`players/builtin/random.py`](players/builtin/random.py) as a template, or the
   minimal example from the
   [Player API docs](https://blackhole-arena.readthedocs.io/en/latest/en/game/upload-a-bot/player-api/).
   You may also subclass one of the reusable strategies in
   [`blackholearena.bots`](src/blackholearena/bots/) (that is how every built-in
   player is made) — for instance `SearchBot`, writing only a utility.

3. **Register it** — add exactly one entry to
   [`players/custom/players.yaml`](players/custom/players.yaml):

   ```yaml
     - file: my_bot.py
       class: MyBot
   ```

4. **Verify locally**, then open the PR:

   ```bash
   pip install -e ".[dev]"
   pytest tests/test_custom_players.py      # checks your player
   blackhole-tournament --no-subprocess     # play your bot against the reference players
   ```

   Run the tournament, not just the tests: it is what catches an illegal move, a
   crash or a timeout in your player.

## Rules your player must follow

- **Output** a legal move: an `int` `node` with
  `0 <= node < len(state["owner"])` and `state["owner"][node] is None`.
- **Do not mutate** the `state` you receive.
- **Declare a unique name.** CI rejects a name already used by an admitted player.
- **No external dependencies** beyond the standard library and `blackholearena`.
- **No network, filesystem, or subprocess access.** Your `choose_move` should be
  a pure function of the board.
- **Be reasonably fast.** Each player gets a budget for a *whole game* plus a
  separate one for being constructed, both *measured on GitHub's runners*, which
  are slower than your laptop. A player that runs out, or that hangs, forfeits
  that game: it scores 0 and its opponent scores the maximum.

## Acceptance criteria (what the maintainer checks)

A PR is merged only if it passes **all** of these:

1. **Design** — one file in `players/custom/`, one manifest line, subclasses
   `Player`, unique `name`, minimal and readable.
2. **Correctness** — CI is green; the bot returns legal moves and never mutates
   state; it does not error or time out against the reference bots.
3. **No malware** — the reviewer reads the code. No obfuscation, no
   network/file/subprocess/`eval`/`exec`, no attempts to read secrets or escape
   the sandbox. Anything suspicious is rejected on sight.

A player that errors or times out **will not be merged** — robustness of your
bot is your responsibility.

## Contributing to the library itself

Bug fixes and improvements to the engine, docs, or web app are welcome too. Open
an issue to discuss larger changes first. Please run `ruff check .` and `pytest`
before opening a PR.

## Code of Conduct

By participating you agree to the
[Code of Conduct](CODE_OF_CONDUCT.md).
