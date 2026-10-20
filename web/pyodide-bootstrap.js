// Loads Pyodide, mounts the shared Python package, and exposes a small JS API
// (`window.BH`) over the Python `webglue` bridge. All game rules and AI moves
// come from Python — JavaScript never re-implements the rules.

const PYODIDE_VERSION = "0.26.2";
const PYODIDE_CDN = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;
const MOUNT = "/lib/blackholesite";

// Load the Pyodide loader script from the CDN.
function loadPyodideScript() {
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = `${PYODIDE_CDN}pyodide.js`;
    s.onload = resolve;
    s.onerror = () => reject(new Error("Failed to load Pyodide from the CDN"));
    document.head.appendChild(s);
  });
}

// Boot Pyodide, unpack py.zip into the virtual FS, import webglue, load players.
async function bootArena(onStatus = () => {}) {
  onStatus("Loading Pyodide…");
  await loadPyodideScript();
  const pyodide = await loadPyodide({ indexURL: PYODIDE_CDN });

  onStatus("Loading PyYAML…");
  await pyodide.loadPackage("pyyaml");

  onStatus("Fetching the Python code…");
  const resp = await fetch("py.zip", { cache: "no-cache" });
  if (!resp.ok) {
    throw new Error(
      "Could not fetch py.zip. Run `python scripts/build_web.py` first."
    );
  }
  const buffer = await resp.arrayBuffer();

  onStatus("Mounting the game engine…");
  pyodide.FS.mkdirTree(MOUNT);
  await pyodide.unpackArchive(buffer, "zip", { extractDir: MOUNT });
  pyodide.runPython(`import sys; sys.path.insert(0, "${MOUNT}")`);

  onStatus("Registering players…");
  const webglue = pyodide.pyimport("webglue");
  // init() loads the manifest and returns the same payload as players_json().
  webglue.init(MOUNT);

  // Public API used by the screens. Every call round-trips JSON strings.
  window.BH = {
    pyodide,
    players: () => JSON.parse(webglue.players_json()), // [{name, icon, authors, description}, ...]
    playerNames: () => JSON.parse(webglue.players_json()).map((p) => p.name),
    presets: () => JSON.parse(webglue.presets_json()), // [{name, label, state}, ...]
    newGame: (nodes, edges) => JSON.parse(webglue.new_game(nodes, JSON.stringify(edges))),
    randomGraph: (nodes, density, seed) =>
      JSON.parse(webglue.random_graph(nodes, density, seed)),
    legalMoves: (state) => JSON.parse(webglue.legal_moves(JSON.stringify(state))),
    applyMove: (state, move) => JSON.parse(webglue.apply_move(JSON.stringify(state), move)),
    isTerminal: (state) => webglue.is_terminal(JSON.stringify(state)),
    analysis: (state) => JSON.parse(webglue.analysis(JSON.stringify(state))),
    askMove: (name, state) =>
      JSON.parse(webglue.ask_move(name, JSON.stringify(state))),

    // Tournament bracket: each slot gets its own seeded instance, so the same
    // kind can enter several times without the copies sharing state.
    resetEntrants: () => webglue.reset_entrants(),
    createEntrant: (id, kind, seed) => webglue.create_entrant(id, kind, seed),
    entrantMove: (id, state) =>
      JSON.parse(webglue.entrant_move(id, JSON.stringify(state))),
    playAuto: (aId, bId, state) =>
      JSON.parse(webglue.play_auto(aId, bId, JSON.stringify(state))),
  };

  onStatus("Ready.");
  return window.BH;
}

window.bootArena = bootArena;
