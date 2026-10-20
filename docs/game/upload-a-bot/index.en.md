# Upload a new bot

Everything you need to write an AI of your own and get it into the tournament.
Two pages, no detours.

---

## The path

```mermaid
flowchart LR
    R["📖 Rules"] --> P["🤖 You write<br/>your class"]
    P --> T["✅ You test it<br/>locally"]
    T --> PR["🔀 You open<br/>a PR"]
    PR --> M["🎉 It is merged"]
    M --> S["🏆 It competes in<br/>the tournament"]
```

<div class="grid cards" markdown>

- :material-code-braces:{ .lg .middle } **[1 · Player API](player-api.md)**

    ---

    The exact interface every AI implements, with a minimal example you can
    copy and that already works.

- :material-source-pull:{ .lg .middle } **[2 · Submit a player](submit-a-player.md)**

    ---

    The Pull Request flow that puts it in the next tournament run.

</div>

---

## Before you start

| If you do not have… | Go to |
|---|---|
| the rules of BlackHole clear | [Game rules](../rules.md) |
| the package installed | [Getting started](../advanced/getting-started.md) |
| a grip on Git and pull requests | [GitHub's docs on pull requests](https://docs.github.com/en/pull-requests) |

---

## Once it is merged

- [The tournament](../advanced/tournament.md) — how your bot is scored.
- [The scoreboard](../advanced/scoreboard.md) — where the result shows up.
