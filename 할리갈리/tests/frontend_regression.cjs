// Development-only regression tests; the game itself only needs Python.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");

const appSource = fs.readFileSync(path.join(__dirname, "../static/app.js"), "utf8");

function clientHarness() {
  let clock = 0;
  let nextTimer = 0;
  const timers = new Map();
  const elements = new Map();
  const documentHandlers = new Map();
  const socketHandlers = new Map();
  const emitted = [];

  class Element {
    constructor() {
      this.html = "";
      this.writes = 0;
      this.flips = 0;
      this.disabled = false;
      this.open = false;
      this.handlers = new Map();
      this.classList = { add() {}, remove() {}, toggle() {} };
    }
    set innerHTML(value) {
      this.html = value;
      this.writes++;
      this.flips += (value.match(/flip-in/g) || []).length;
    }
    get innerHTML() { return this.html; }
    addEventListener(name, callback) { this.handlers.set(name, callback); }
    fire(name, payload = {}) { this.handlers.get(name)?.(payload); }
    querySelector() { return new Element(); }
    appendChild() {}
    setAttribute() {}
    remove() {}
    showModal() { this.open = true; }
    close() { this.open = false; }
  }

  function element(selector) {
    if (!elements.has(selector)) elements.set(selector, new Element());
    return elements.get(selector);
  }

  const storage = new Map([
    ["fruitBellSession:default", JSON.stringify({ room_code: "TEST", player_id: "me", reconnect_token: "test-only", avatar: "cat" })],
    ["fruitBellTutorialSeen", "yes"],
  ]);
  const socket = {
    connected: true,
    on(name, callback) { socketHandlers.set(name, callback); },
    emit(name, payload) { emitted.push({ name, payload }); },
  };
  const context = vm.createContext({
    URL, URLSearchParams,
    location: { search: "", origin: "http://localhost:1337", href: "http://localhost:1337/" },
    history: { replaceState() {} },
    performance: { now: () => clock },
    localStorage: {
      getItem: (key) => storage.get(key) ?? null,
      setItem: (key, value) => storage.set(key, value),
      removeItem: (key) => storage.delete(key),
    },
    document: {
      querySelector(selector) {
        if (selector === "dialog[open]" || selector.startsWith("[data-player-id=")) return null;
        return element(selector);
      },
      querySelectorAll: () => [],
      createElement: () => new Element(),
      addEventListener: (name, callback) => documentHandlers.set(name, callback),
    },
    HTMLInputElement: class {}, HTMLTextAreaElement: class {}, HTMLSelectElement: class {},
    window: {},
    io: () => socket,
    setTimeout(callback, delay) {
      const id = ++nextTimer;
      timers.set(id, { at: clock + delay, callback });
      return id;
    },
    clearTimeout: (id) => timers.delete(id),
  });
  vm.runInContext(appSource, context);

  function advance(milliseconds) {
    const target = clock + milliseconds;
    while (true) {
      const next = [...timers].filter(([, timer]) => timer.at <= target).sort((a, b) => a[1].at - b[1].at)[0];
      if (!next) break;
      timers.delete(next[0]);
      clock = next[1].at;
      next[1].callback();
    }
    clock = target;
  }
  function key(code) {
    const event = { target: {}, code, key: code === "Space" ? " " : code, repeat: false, preventDefault() {} };
    documentHandlers.get("keydown")(event);
  }
  return { element, elements, emitted, advance, key, receive: (name, payload) => socketHandlers.get(name)(payload) };
}

function state(overrides = {}) {
  return {
    room_code: "TEST", state: "PLAYING", board_version: 1,
    current_player_id: "me", reveal_wait_ms: 300, reveal_blocked_for_bell: false,
    logs: [],
    players: [
      { id: "other", nickname: "상대", avatar: "bear", seat: 0, connected: true, remaining_card_count: 27,
        face_up_count: 1, visible_card: { id: "visible-card", fruit: "strawberry", count: 2 } },
      { id: "me", nickname: "나", avatar: "cat", seat: 1, connected: true, remaining_card_count: 28,
        face_up_count: 0, visible_card: null },
    ],
    ...overrides,
  };
}

test("an opponent card flips once; settle timer only updates buttons", () => {
  const client = clientHarness();
  client.receive("card_revealed", { card: { id: "visible-card" } });
  client.receive("room_state", state());
  const seats = client.element("#seatLayer");
  assert.equal(seats.flips, 1);
  assert.equal(client.element("#revealButton").disabled, true);
  const writes = seats.writes;
  client.advance(320);
  assert.equal(seats.writes, writes, "settle must not rebuild animated cards");
  assert.equal(seats.flips, 1);
  assert.equal(client.element("#revealButton").disabled, false);
  assert.equal(client.element(".player-seat.is-local .draw-pile").disabled, false);

  client.receive("room_state", state({ reveal_wait_ms: 0 }));
  assert.equal(seats.flips, 1, "another state update must not replay the consumed reveal");
  client.receive("card_revealed", { card: { id: "visible-card" } });
  client.receive("room_state", state({ board_version: 2, reveal_wait_ms: 0 }));
  assert.equal(seats.flips, 2, "a later genuine reveal of the same physical card may animate");
});

test("bell lock blocks button, deck and Enter, but leaves Space available", () => {
  const client = clientHarness();
  client.receive("room_state", state({ reveal_blocked_for_bell: true }));
  client.advance(5000);
  assert.equal(client.element("#revealButton").disabled, true);
  assert.equal(client.element(".player-seat.is-local .draw-pile").disabled, true);
  assert.equal(client.element("#bellButton").disabled, false);
  client.element("#revealButton").fire("click");
  client.element("#seatLayer").fire("click", { target: { closest: () => ({ dataset: { reveal: "me" } }) } });
  client.key("Enter");
  assert.equal(client.emitted.length, 0);
  client.key("Space");
  assert.deepEqual(client.emitted.map((event) => event.name), ["ring_bell"]);

  client.receive("bell_result", { status: "correct", player_id: "me", collected_count: 2 });
  client.receive("room_state", state({ reveal_wait_ms: 500, reveal_blocked_for_bell: false }));
  assert.equal(client.element("#revealButton").disabled, true);
  client.advance(520);
  client.element("#revealButton").fire("click");
  assert.deepEqual(client.emitted.map((event) => event.name), ["ring_bell", "reveal_card"]);
});

test("audio implementation and sound control are removed", () => {
  const html = fs.readFileSync(path.join(__dirname, "../templates/index.html"), "utf8");
  assert.doesNotMatch(appSource, /AudioContext|createOscillator|playBellSound|playWrongSound|soundButton|fruitBellSound/);
  assert.doesNotMatch(html, /soundButton|<audio|효과음/);
});
