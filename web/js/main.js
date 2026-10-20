// BlackHole Arena — boot and wiring.
//
// Loads the screen partials, wires each screen independently, then starts the
// Python engine.
//
// Two rules here, both learned the hard way:
//
//   1. **Never let one failure kill the wiring.** This file used to set every
//      handler in a single straight line, so an exception anywhere left later
//      buttons with no `onclick` at all — and a button with no handler does
//      nothing, silently, with no clue as to why. Each step is now isolated.
//   2. **Never fail silently.** An exception inside an event handler is
//      swallowed by the browser and only appears in the console. Everything the
//      user can trigger goes through `guard()`, and anything that escapes lands
//      in a visible banner.
"use strict";

const SCREENS = ["menu", "game", "scoreboard", "tournament", "about"];

/* Show a persistent, visible error. The console is not good enough: "nothing
   happened" is the least debuggable bug report there is. */
function showFatal(what, err) {
  const box = $("fatal");
  if (!box) return;
  box.classList.remove("hidden");
  box.innerHTML =
    `<strong>${esc(what)}</strong><br>` +
    `<code>${esc(err && err.message ? err.message : String(err))}</code><br>` +
    `<span class="muted small">See the browser console for the full stack.</span>`;
  console.error(what, err);
}

/* Wrap a user-triggered handler so a throw becomes a toast, not silence. */
function guard(label, fn) {
  return (...args) => {
    try {
      return fn(...args);
    } catch (err) {
      console.error(`${label} failed`, err);
      toast(`${label} failed: ${err.message || err}`);
    }
  };
}

/* Run one setup step in isolation, so a failure cannot disarm the others. */
function step(label, fn) {
  try {
    fn();
    return true;
  } catch (err) {
    showFatal(`Could not set up ${label}`, err);
    return false;
  }
}

/* Fetch each screen's markup and place it in the shell. Screens live in their
   own files so a page is editable without scrolling past the other four. */
async function loadScreens() {
  const host = $("screens");
  const parts = await Promise.all(
    SCREENS.map(async (name) => {
      const resp = await fetch(`screens/${name}.html`, { cache: "no-cache" });
      if (!resp.ok) throw new Error(`screens/${name}.html → HTTP ${resp.status}`);
      return resp.text();
    }),
  );
  host.innerHTML = parts.join("\n");
  // Only the menu starts visible.
  for (const name of SCREENS) {
    const el = $(`screen-${name}`);
    if (el) el.classList.toggle("hidden", name !== "menu");
  }
}

async function main() {
  window.addEventListener("error", (e) => showFatal("Unexpected error", e.error || e.message));
  window.addEventListener("unhandledrejection", (e) => showFatal("Unexpected error", e.reason));

  try {
    await loadScreens();
  } catch (err) {
    showFatal("Could not load the page", err);
    $("boot-status").textContent = "⚠️ " + (err.message || err);
    return;
  }

  // DOM-only wiring: safe before the engine exists.
  step("navigation", setupNav);
  step("the Play screen", setupPlay);
  step("the Scoreboard screen", setupScoreboard);
  step("the Tournament screen", setupTournament);

  try {
    await window.bootArena((msg) => { $("boot-status").textContent = msg; });
  } catch (err) {
    $("boot-status").textContent = "⚠️ " + (err.message || err);
    showFatal("The Python engine did not start", err);
    return;
  }

  // Anything that needs the engine: the player lists and the preset graphs.
  step("the player list", populateSeatSelects);
  step("the graph presets", populatePresets);
  step("the bracket entrants", tBuildSetup);

  $("boot").classList.add("hidden");

  if (!loadFromHash()) {
    newGame(PRESETS.get(DEFAULT_PRESET).state);
    showScreen("menu");
  }
}

window.addEventListener("DOMContentLoaded", main);
