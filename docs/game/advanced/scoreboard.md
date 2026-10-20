# El marcador

El marcador no es un programa. Es **un archivo JSON** que escribe el torneo y
lee la página web. Nada más los conecta: sin base de datos, sin backend, sin API.

---

## El camino que recorren los datos

```mermaid
flowchart LR
    A["🏆 blackhole-tournament"] --> B["results/<br/>leaderboard.json"]
    B --> C["🔨 build_web.py"]
    C --> D["web/<br/>leaderboard.json"]
    D --> E["📄 GitHub Pages"]
    E --> F["🌐 scoreboard.js"]
```

| Paso | Qué pasa |
|---|---|
| 1 · **Se produce** | `blackhole-tournament --out results/leaderboard.json` juega todas las partidas y vuelca un único objeto JSON. El workflow hace commit del archivo en el repositorio |
| 2 · **Se copia** | `scripts/build_web.py` lo pone junto a la página como `web/leaderboard.json`. Si aún no existe, avisa y sigue |
| 3 · **Se sirve** | el workflow de Pages sube todo el directorio `web/` como artefacto estático |
| 4 · **Se pide** | `scoreboard.js` hace `fetch("leaderboard.json", { cache: "no-cache" })` al cargar. Si falla, la pantalla dice *«No leaderboard yet…»* en lugar de romperse |

!!! info "Por qué un archivo versionado y no una base de datos"
    Una página estática no puede consultar nada. Que los resultados sean un
    archivo del repositorio significa que el marcador no tiene infraestructura
    que mantener viva, que el historial de cada ejecución publicada está en
    `git log`, y que cualquiera puede reproducir una ejecución en local y
    comparar.

---

## Qué hay en el archivo

Ocho claves de primer nivel, siempre presentes:

| Clave | Qué contiene |
|---|---|
| `generated_at` | marca de tiempo UTC de la ejecución |
| `config` | los ajustes que usó la ejecución — suficientes para reproducirla |
| `players` | el directorio de jugadores: una entrada por **tipo**, con icono, autores y descripción |
| `standings` | la clasificación ordenada — la tabla en sí |
| `matches` | una entrada por enfrentamiento, agregada sobre sus partidas |
| `player_stats` | detalle por jugador, incluido el cara a cara |
| `totals` | contadores de toda la ejecución para los recuadros resumen |
| `structure` | específico del formato: grupos y cuadro en un campeonato |

Así es una fila de `standings`, que es la parte que vas a mirar:

```json
{
  "rank": 1, "player": "random_1",
  "points": 55, "avg_points": 3.056, "points_against": 54,
  "wins": 7, "draws": 4, "losses": 7, "forfeits": 0,
  "games": 18, "win_rate": 0.389,
  "avg_move_ms": 0.018, "std_move_ms": 0.002, "max_move_ms": 0.025,
  "elo": 1519.243
}
```

| Campo | Qué es |
|---|---|
| `points` | **el criterio de clasificación**: la suma de lo puntuado en todas sus partidas |
| `avg_points` | puntos por partida |
| `points_against` | lo que puntuaron sus rivales en esas mismas partidas |
| `wins` / `draws` / `losses` | partidas en las que puntuó más, lo mismo o menos que el rival — **solo informativo** |
| `win_rate` | fracción de partidas en las que puntuó más que el rival |
| `forfeits` | partidas en las que fue descalificado |

`elo` aparece siempre, en todos los formatos: se calcula tratando cada partida como ganada, empatada o perdida. Solo decide la clasificación en una ejecución `league` con Elo activado.

??? info "El resto de bloques, con ejemplos"
    **`config`** — cómo se configuró la ejecución. La página lee
    `config.tournament` para decidir qué bloques renderizar.

    ```json
    "config": {
      "tournament": "league",
      "graphs": [
        { "nodes": 5, "edges": [[0, 1], [2, 3], [3, 4], [0, 2], [0, 3], [1, 3], [1, 4]] },
        { "nodes": 7, "edges": [[0, 1], [0, 2], [0, 3], [0, 4], [0, 5], [0, 6],
                                [1, 2], [2, 3], [3, 4], [4, 5], [5, 6], [1, 6]] },
        { "nodes": 9, "edges": [[0, 1], [0, 3], [1, 2], [1, 4], [2, 5], [3, 4],
                                [3, 6], [4, 5], [4, 7], [5, 8], [6, 7], [7, 8]] }
      ],
      "repetitions": 3,
      "game_budget_ms": 2000,
      "build_budget_ms": 2000,
      "elo": true,
      "player_copies": { "random": 2 }
    }
    ```

    **`players`** — el directorio, una entrada por tipo. Existe para que el
    marcador sea **autocontenido**: la página renderiza iconos, autores y
    descripciones desde el archivo, sin importar el registro de Python. Un
    marcador de hace seis meses sigue renderizando bien.

    ```json
    { "name": "random", "icon": "🎲", "authors": ["builtin"],
      "description": "Places its tiles on a free node chosen uniformly at random…" }
    ```

    **`matches`** — una fila por emparejamiento, con los puntos de cada lado
    sumados sobre todas sus partidas. `winner` es quien sumó más puntos, o la
    cadena vacía si empataron. Los tiempos (`a_avg_move_ms`, …) son **solo
    agregados** (media, desviación típica y máximo): un array por jugada
    produciría un archivo demasiado grande para descargarlo en cada carga de
    página.

    ```json
    { "player_a": "random_0", "player_b": "random_1", "phase": "round-robin",
      "games": 18, "a_points": 54, "b_points": 55,
      "a_wins": 7, "b_wins": 7, "draws": 4, "winner": "random_1", "forfeits": 0 }
    ```

    **`player_stats`** — todo lo de `standings`, más `moves_made`, los tiempos
    de construcción y una lista `opponents` de la que sale el desglose cara a
    cara de cada tarjeta.

    ```json
    { "opponent": "random_1", "games": 18, "points": 54, "points_against": 55,
      "wins": 7, "draws": 4, "losses": 7 }
    ```

    **`totals`** — los contadores de los recuadros resumen: jugadores,
    enfrentamientos, partidas, puntos totales (`total_points`) y por partida
    (`avg_game_points`), jugadas totales, partida más larga y
    descalificaciones.

    **`structure`** — para `simple` y `league` es solo un marcador
    (`{"type": "league", "elo": true}`). Para `championship` lleva las tablas de
    grupo (ordenadas por puntos), las rondas del cuadro y el campeón. Cada
    eliminatoria guarda los puntos de cada lado:

    ```json
    { "a": "random_0", "b": "random_1", "a_points": 18, "b_points": 11,
      "winner": "random_0" }
    ```

!!! note "`standings` usa `random_0`; `players` usa `random`"
    Un tipo puede entrar en el torneo más de una vez, y cada copia se llama
    `<tipo>_<semilla>`. `standings`, `matches` y `player_stats` usan esos
    nombres de plantilla; `players` usa el tipo. La página los vuelve a separar
    para dibujar `🎲 random₀`.

---

## Qué dibuja la página con esto

Renderizado puramente mecánico, sin lógica de juego:

- 🏅 una columna de **clasificación por puntos** con 🥇🥈🥉 para los tres primeros;
- 🎯 un **filtro de jugadores** y un **gráfico radar** que compara los
  seleccionados en cuatro ejes: **puntos**, **Elo**, **% de victorias** y
  **tiempo medio por jugada** (invertido: más rápido llega más lejos);
- 🗂️ un bloque plegable de **estructura del torneo** (solo en campeonato);
- ⚔️ una tabla de **resumen de enfrentamientos**;
- 🃏 tarjetas desplegables de **estadísticas por jugador**;
- 📈 recuadros de **estadísticas totales**.

---

## Producir uno tú

```bash
blackhole-tournament --out results/leaderboard.json   # escríbelo
python scripts/build_web.py                          # cópialo junto a la página
python -m http.server -d web 8000                    # sírvelo y míralo
```

---

**Siguiente:** [La página web](web.md) — la página que lo renderiza.
