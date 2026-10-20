# Primeros pasos

Cuatro cosas que puedes hacer con el proyecto en local, de menos a más.

| Quiero… | Comando |
|---|---|
| 🔧 instalarlo | `pip install -e ".[dev]"` |
| 🎮 jugar una partida | desde Python, [abajo](#jugar-una-partida-desde-python) |
| ✅ ejecutar las pruebas | `pytest` |
| 🏆 ejecutar un torneo | `blackhole-tournament` |

!!! tip "¿Solo quieres jugar?"
    No hace falta instalar nada: la
    [página web](https://jparisu.github.io/blackhole-arena) ejecuta el mismo Python en
    tu navegador.

---

## Instalar la librería

Requiere Python 3.10 o superior.

```bash
git clone https://github.com/jparisu/blackhole-arena
cd blackhole-arena
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

---

## Jugar una partida desde Python

```python
from blackholearena import game, graphs
from blackholearena.manifest import load_players

registry = load_players()          # lee los dos manifiestos players.yaml
Random = type(registry.get("random"))
players = [Random.create(seed=0), Random.create(seed=1)]

state = graphs.grid(3, 3)          # 9 nodos -> N = 4 turnos por jugador
while not game.is_terminal(state):
    who = game.to_move(state)
    move = players[who].choose_move(state)
    print(f"player {who} places {game.tiles_to_place(state)} on node {move}")
    state = game.apply_move(state, move)
print("Black hole:", game.black_hole(state), "· scores:", game.scores(state))
```

La partida enfrenta a dos copias de `random` con semillas distintas. Cambia una
de ellas por otro jugador de la
[escalera de referencia](tournament.md#la-escalera-de-referencia) — por ejemplo,
`registry.get("aggressive-max")` — o por tu propio bot en cuanto lo tengas.

---

## Ejecutar las pruebas

```bash
pytest
```

La batería comprueba las reglas del juego y la puntuación, que cada jugador de
referencia devuelve jugadas legales y no muta el estado, y que el torneo
sobrevive a bots que se cuelgan, se rompen o hacen trampas.

---

## Ejecutar el torneo en local

```bash
# Escribe la clasificación en results/leaderboard.json
blackhole-tournament --out results/leaderboard.json

# Más rápido para probar tu bot mientras lo escribes
blackhole-tournament --no-subprocess

# Grafos propios: NODOS:A-B,C-D,... (repite la opción)
blackhole-tournament --graph 5:0-1,1-2,2-3,3-4,4-0 --graph 3:0-1,1-2
```

Consulta [El torneo](tournament.md) para los formatos, la puntuación, los
tiempos y las descalificaciones.

---

## Ejecutar la página web en local

La página carga el Python compartido mediante Pyodide. Primero ensambla el
paquete, luego sirve la carpeta `web/` con cualquier servidor estático:

```bash
python scripts/build_web.py           # -> web/py.zip y web/leaderboard.json
python -m http.server -d web 8000     # abre http://localhost:8000
```

!!! warning "Sírvela, no la abras con doble clic"
    Con `file://` el navegador bloquea `fetch()` y la página no carga. Usa
    siempre un servidor, aunque sea el de una línea de arriba.

!!! note "La primera carga necesita internet"
    Pyodide se descarga de un CDN la primera vez. Todo lo demás se ejecuta
    localmente en tu navegador.

---

**Siguiente:** [API de jugador](../upload-a-bot/player-api.md) — escribe tu primera
IA en veinte líneas.
