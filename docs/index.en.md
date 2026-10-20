# BlackHole Arena

A complete project built on GitHub around the game of **BlackHole**: a Python
library holding the rules and several reference bots, a web interface where a human can play, a tournament that evaluates the different bots, and these docs.

This is an educational project: its purpose is for you to write your own AI for BlackHole, upload it to the repository and have it compete in the tournament against everyone else's.

[![Tests](https://github.com/jparisu/blackhole-arena/actions/workflows/tests.yml/badge.svg)](https://github.com/jparisu/blackhole-arena/actions/workflows/tests.yml)
[![Tournament](https://github.com/jparisu/blackhole-arena/actions/workflows/tournament.yml/badge.svg)](https://github.com/jparisu/blackhole-arena/actions/workflows/tournament.yml)
[![Docs](https://readthedocs.org/projects/blackhole-arena/badge/?version=latest)](https://blackhole-arena.readthedocs.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/jparisu/blackhole-arena/blob/main/LICENSE)

[:material-play: Play now](https://jparisu.github.io/blackhole-arena){ .md-button .md-button--primary }
[:material-github: See the code](https://github.com/jparisu/blackhole-arena){ .md-button }

---

## The project

| Piece | What it is | Where |
|---|---|---|
| 🐍 **Library** | the rules of BlackHole written in Python | [The game](game/index.md) |
| 🌐 **Web page** | play against any bot online, on the graph of your choice | [play](https://jparisu.github.io/blackhole-arena) |
| 📚 **Documentation** | explains the rules, the player API and how everything works | [index](https://blackhole-arena.readthedocs.io/en/latest/) |
| 🏆 **Tournament** | runs every bot against every other and publishes a ranking by points | [The tournament](game/advanced/tournament.md) |
| 🤖 **Your bot** | write a class and test a bot of your own | [Upload a bot](game/upload-a-bot/index.md) |

---

## Where to start

<div class="grid cards" markdown>

- :material-book-open-variant:{ .lg .middle } **[Game rules](game/rules.md)**

    ---

    How BlackHole is played, with a complete worked example from start to
    finish, and how the state and the moves look in the code.

    Read them to **play**.

- :material-robot:{ .lg .middle } **[Upload a new bot](game/upload-a-bot/index.md)**

    ---

    The [player API](game/upload-a-bot/player-api.md) your AI implements, and
    the [pull request flow](game/upload-a-bot/submit-a-player.md) that gets it
    into the tournament.

    Read it to **write a bot**.

- :material-cog-outline:{ .lg .middle } **[Advanced documentation](game/advanced/index.md)**

    ---

    The [code structure](game/advanced/code-structure.md), the
    [tournament](game/advanced/tournament.md), the
    [scoreboard](game/advanced/scoreboard.md), the
    [web app](game/advanced/web.md) and the
    [API reference](game/advanced/api.md).

    Read it to **understand the machinery**.

</div>
