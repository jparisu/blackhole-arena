# BlackHole Arena

Un proyecto completo construido sobre GitHub alrededor del juego **BlackHole**:
una librería de Python con las reglas y varios bots de referencia, una interfaz web donde un humano puede jugar, un torneo que evalúa los distintos bots, y esta documentación.

Este es un proyecto con fines educativos: su objetivo es que escribas tu propia IA para BlackHole, la subas al repositorio y compita en el torneo contra las de los demás.

[![Tests](https://github.com/jparisu/blackhole-arena/actions/workflows/tests.yml/badge.svg)](https://github.com/jparisu/blackhole-arena/actions/workflows/tests.yml)
[![Tournament](https://github.com/jparisu/blackhole-arena/actions/workflows/tournament.yml/badge.svg)](https://github.com/jparisu/blackhole-arena/actions/workflows/tournament.yml)
[![Docs](https://readthedocs.org/projects/blackhole-arena/badge/?version=latest)](https://blackhole-arena.readthedocs.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/jparisu/blackhole-arena/blob/main/LICENSE)

[:material-play: Jugar ahora](https://jparisu.github.io/blackhole-arena){ .md-button .md-button--primary }
[:material-github: Ver el código](https://github.com/jparisu/blackhole-arena){ .md-button }

---

## El proyecto

| Pieza | Qué es | Dónde |
|---|---|---|
| 🐍 **Librería** | las reglas de BlackHole programadas en Python | [El juego](game/index.md) |
| 🌐 **Página web** | juega contra cualquier bot online, sobre el grafo que elijas | [jugar](https://jparisu.github.io/blackhole-arena) |
| 📚 **Documentación** | explica las reglas, la API de jugador y cómo funciona todo | [índice](https://blackhole-arena.readthedocs.io/en/latest/) |
| 🏆 **Torneo** | enfrenta a todos los bots y publica una clasificación por puntos | [El torneo](game/advanced/tournament.md) |
| 🤖 **Tu bot** | escribe una clase y prueba tu propio bot | [Subir un bot](game/upload-a-bot/index.md) |

---

## Por dónde empezar

<div class="grid cards" markdown>

- :material-book-open-variant:{ .lg .middle } **[Reglas del juego](game/rules.md)**

    ---

    Cómo se juega a BlackHole, con un ejemplo completo de principio a fin, y
    cómo se representan el estado y las jugadas en el código.

    Léelas para **jugar**.

- :material-robot:{ .lg .middle } **[Subir un bot nuevo](game/upload-a-bot/index.md)**

    ---

    La [API de jugador](game/upload-a-bot/player-api.md) que implementa tu IA y
    el [flujo de pull request](game/upload-a-bot/submit-a-player.md) que la mete
    en el torneo.

    Léelo para **programar un bot**.

- :material-cog-outline:{ .lg .middle } **[Documentación avanzada](game/advanced/index.md)**

    ---

    La [estructura del código](game/advanced/code-structure.md), el
    [torneo](game/advanced/tournament.md), el
    [marcador](game/advanced/scoreboard.md), la
    [página web](game/advanced/web.md) y la
    [referencia de la API](game/advanced/api.md).

    Léela para **entender la maquinaria**.

</div>
