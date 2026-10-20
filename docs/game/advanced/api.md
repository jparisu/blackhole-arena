# Referencia de la API

Todos los nombres públicos del paquete `blackholearena`, **generados desde el
código fuente** por [mkdocstrings](https://mkdocstrings.github.io/) cada vez que
se construye este sitio. Cambia un docstring y esta página cambia con él, así
que la referencia y el código nunca pueden contradecirse.

!!! info "Estos bloques están en inglés"
    Salen directamente de los docstrings del paquete, que están escritos en
    inglés. La prosa que los rodea sí está traducida.

---

## El juego

Las reglas, como funciones puras sobre un estado `{"edges", "owner", "tiles"}`.

::: blackholearena.game

---

## Los grafos

Grafos listos para jugar: los que usa el torneo por defecto y los que ofrece la
página web.

::: blackholearena.graphs

---

## El contrato del jugador

La única clase que implementa alguien de fuera.

::: blackholearena.player.Player

---

## El registro

Cómo se descubren los jugadores y cómo se buscan por nombre.

::: blackholearena.registry.Registry

::: blackholearena.manifest.load_players

---

## El torneo

Ejecutar partidas, construir la plantilla y puntuarlas.

::: blackholearena.tournament.run_tournament

::: blackholearena.tournament.copies_for

::: blackholearena.tournament.build_roster

::: blackholearena.tournament.play_match

---

## Puntuación Elo

::: blackholearena.elo

---

## Estrategias reutilizables

Las piezas con las que están montados los jugadores de referencia: `RandomBot`
(🎲 `random`), `FreeNeighbourBot` (🌱 `easy`) y la búsqueda `SearchBot` con sus
tres utilidades (⚔️ `aggressive-max`, 🗡️ `aggressive-min` y 🤝 `cooperative`).
Cómo buscan estos tres se explica en [El torneo](tournament.md#como-juegan-los-jugadores-de-busqueda).

::: blackholearena.bots.random_bot.RandomBot

::: blackholearena.bots.neighbour_bot

::: blackholearena.bots.search

::: blackholearena.bots.aggressive

::: blackholearena.bots.cooperative
