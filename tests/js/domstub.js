// A small but faithful DOM, enough to run the web app headlessly under Node.
//
// It exists because the browser code kept failing in ways no Python test could
// see: a duplicate element id, and `main()` throwing so that buttons were never
// wired at all. Both looked identical from outside — "the button does nothing".
//
// Elements build a real tree, innerHTML serialises, classList works, and
// listeners fire. Nodes are seeded from the ids, classes and values actually
// present in the shipped markup.
"use strict";

const fs = require("fs");
const path = require("path");

function makeNode(tag = "div") {
  const n = {
    tagName: String(tag).toUpperCase(),
    children: [],
    parentElement: null,
    _text: "",
    _rawHtml: null,
    _classes: new Set(),
    style: {},
    dataset: {},
    value: "",
    title: "",
    type: "",
    placeholder: "",
    checked: false,
    disabled: false,
    min: "",
    max: "",
    open: false,
    _listeners: {},
    onclick: null,
    oninput: null,
    onchange: null,
  };
  n.classList = {
    add: (...c) => c.forEach((x) => x && n._classes.add(x)),
    remove: (...c) => c.forEach((x) => n._classes.delete(x)),
    toggle: (c, on) => {
      if (on === undefined) n._classes.has(c) ? n._classes.delete(c) : n._classes.add(c);
      else if (on) n._classes.add(c);
      else n._classes.delete(c);
    },
    contains: (c) => n._classes.has(c),
  };
  Object.defineProperty(n, "className", {
    get: () => [...n._classes].join(" "),
    set: (v) => { n._classes = new Set(String(v).split(/\s+/).filter(Boolean)); },
  });
  Object.defineProperty(n, "textContent", {
    get: () => n._text,
    set: (v) => { n._text = String(v); n.children = []; n._rawHtml = null; },
  });
  Object.defineProperty(n, "innerHTML", {
    get: () => (n._rawHtml !== null ? n._rawHtml : n.children.map(serialize).join("")),
    set: (v) => { n._rawHtml = String(v); n.children = []; n._text = ""; },
  });
  Object.defineProperty(n, "firstChild", { get: () => n.children[0] || null });
  n.appendChild = (c) => { c.parentElement = n; n._rawHtml = null; n.children.push(c); return c; };
  n.insertBefore = (c, ref) => {
    c.parentElement = n;
    n._rawHtml = null;
    const i = ref ? n.children.indexOf(ref) : -1;
    if (i < 0) n.children.push(c); else n.children.splice(i, 0, c);
    return c;
  };
  n.after = (c) => { if (n.parentElement) n.parentElement.appendChild(c); };
  n.remove = () => {
    if (n.parentElement) {
      n.parentElement.children = n.parentElement.children.filter((x) => x !== n);
    }
  };
  n.contains = (other) => {
    let x = other;
    while (x) { if (x === n) return true; x = x.parentElement; }
    return false;
  };
  n.setAttribute = (k, v) => { if (k === "class") n.className = v; };
  n.addEventListener = (ev, fn) => { (n._listeners[ev] ||= []).push(fn); };
  n.dispatchEvent = (e) => (n._listeners[e.type] || []).forEach((f) => f(e));
  n.scrollIntoView = () => {};
  n.querySelectorAll = (sel) => {
    const want = sel.replace(/^\./, "").replace(/\[.*\]$/, "");
    const out = [];
    const walk = (x) => {
      for (const c of x.children) {
        if (c._classes.has(want) || c.tagName === want.toUpperCase()) out.push(c);
        walk(c);
      }
    };
    walk(n);
    return out;
  };
  n.querySelector = (sel) => n.querySelectorAll(sel)[0] || null;
  return n;
}

function serialize(n) {
  const cls = n.className ? ` class="${n.className}"` : "";
  const inner = n._rawHtml !== null ? n._rawHtml : (n._text || n.children.map(serialize).join(""));
  return `<${n.tagName.toLowerCase()}${cls}>${inner}</${n.tagName.toLowerCase()}>`;
}

/* Build a document from the shell plus every screen partial. */
function buildDocument(webDir) {
  const files = [path.join(webDir, "index.html")].concat(
    fs.readdirSync(path.join(webDir, "screens")).sort()
      .map((f) => path.join(webDir, "screens", f)),
  );
  const html = files.map((f) => fs.readFileSync(f, "utf8")).join("\n");
  const byId = new Map();
  const missing = new Set();

  for (const m of html.matchAll(/<(\w+)([^>]*\bid="([^"]+)"[^>]*)>/g)) {
    const [, tag, attrs, id] = m;
    if (byId.has(id)) continue; // getElementById returns the first match
    const node = makeNode(tag);
    const cls = /class="([^"]*)"/.exec(attrs);
    if (cls) node.className = cls[1];
    const val = /value="([^"]*)"/.exec(attrs);
    if (val) node.value = val[1];
    makeNode("div").appendChild(node); // real markup nests; code reads parentElement
    byId.set(id, node);
  }
  for (const [id, node] of byId) {
    if (node.tagName !== "SELECT") continue;
    const block = new RegExp(`id="${id}"[^>]*>([\\s\\S]*?)</select>`).exec(html);
    if (!block) continue;
    const opts = [...block[1].matchAll(/<option value="([^"]+)"([^>]*)>/g)];
    const sel = opts.find((o) => /\bselected\b/.test(o[2]));
    node.value = sel ? sel[1] : (opts[0]?.[1] ?? "");
  }

  return {
    getElementById: (id) => {
      if (!byId.has(id)) { missing.add(id); byId.set(id, makeNode("div")); }
      return byId.get(id);
    },
    querySelectorAll: () => [],
    createElement: (t) => makeNode(t),
    createElementNS: (_ns, t) => makeNode(t),
    documentElement: makeNode("html"),
    addEventListener: () => {},
    head: makeNode("head"),
    _missing: missing,
    _html: html,
  };
}

module.exports = { makeNode, serialize, buildDocument };
