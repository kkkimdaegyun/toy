/*
 * sound.js — runtime-synthesized sound effects for 숫자 섯다.
 *
 * No audio files, no network, no build step. Everything is generated with the
 * Web Audio API (oscillators + gain envelopes + a tiny white-noise buffer).
 *
 * Global API:
 *   window.Sfx.init()            create/resume the AudioContext (call in a user gesture)
 *   window.Sfx.play(name)        play a named effect; never throws, no-op when muted
 *   window.Sfx.setEnabled(bool)  turn sound on/off and persist
 *   window.Sfx.isEnabled()       read persisted on/off state
 *   window.Sfx.toggle()          flip + persist, returns the new boolean
 *
 * Preference is stored in localStorage under 'gostop.sfx' (default: enabled).
 * Volume ceiling is intentionally low — this is meant to be played in an office.
 */
(function (window, document) {
  'use strict';

  if (!window) { return; }

  var STORAGE_KEY = 'gostop.sfx';

  /* Master ceiling. Every voice below is a *relative* amplitude (0..1) that gets
     multiplied by this, so the absolute peak can never exceed 0.13. */
  var MASTER_PEAK = 0.13;

  /* The same effect may not fire more than once per this many ms. */
  var THROTTLE_MS = 40;

  /* Length of the reusable white-noise buffer, in seconds. */
  var NOISE_SECONDS = 0.4;

  var ctx = null;          // AudioContext (created lazily, inside a gesture)
  var master = null;       // master GainNode
  var noiseBuffer = null;  // shared white-noise AudioBuffer
  var supported = true;    // flipped off if the browser has no Web Audio
  var enabled = true;      // in-memory mirror of the persisted preference
  var storageOk = true;    // false once a write proves storage is unusable
  var lastPlayedAt = {};   // effect name -> Date.now() of last trigger

  /* ------------------------------------------------------------------ *
   * Persistence
   * ------------------------------------------------------------------ */

  function readStored() {
    try {
      if (!window.localStorage) { return true; }
      var raw = window.localStorage.getItem(STORAGE_KEY);
      if (raw === null || raw === undefined) { return true; } // default ON
      return raw !== '0' && raw !== 'false' && raw !== 'off';
    } catch (e) {
      return true;
    }
  }

  function writeStored(value) {
    try {
      if (!window.localStorage) { storageOk = false; return; }
      window.localStorage.setItem(STORAGE_KEY, value ? '1' : '0');
    } catch (e) {
      /* private mode / quota: the in-memory value becomes authoritative, otherwise
         the next isEnabled() would read the default back and undo the user's mute. */
      storageOk = false;
    }
  }

  enabled = readStored();

  /* ------------------------------------------------------------------ *
   * AudioContext lifecycle
   * ------------------------------------------------------------------ */

  function init() {
    try {
      if (!supported) { return false; }

      if (!ctx) {
        var Ctor = window.AudioContext || window.webkitAudioContext;
        if (!Ctor) { supported = false; return false; }
        ctx = new Ctor();
        master = ctx.createGain();
        master.gain.value = MASTER_PEAK;
        master.connect(ctx.destination);
      }

      /* Autoplay policy: a context created outside a gesture starts suspended. */
      if (ctx.state === 'suspended' && typeof ctx.resume === 'function') {
        var p = ctx.resume();
        if (p && typeof p['catch'] === 'function') { p['catch'](function () {}); }
      }
      return true;
    } catch (e) {
      supported = false;
      return false;
    }
  }

  function ready() {
    if (!supported) { return false; }
    if (!ctx || !master) { return init(); }
    if (ctx.state === 'suspended' && typeof ctx.resume === 'function') {
      try {
        var p = ctx.resume();
        if (p && typeof p['catch'] === 'function') { p['catch'](function () {}); }
      } catch (e) { /* ignore */ }
    }
    return true;
  }

  function getNoiseBuffer() {
    if (noiseBuffer) { return noiseBuffer; }
    var rate = ctx.sampleRate || 44100;
    var frames = Math.max(1, Math.floor(rate * NOISE_SECONDS));
    var buf = ctx.createBuffer(1, frames, rate);
    var data = buf.getChannelData(0);
    for (var i = 0; i < frames; i++) {
      data[i] = Math.random() * 2 - 1;
    }
    noiseBuffer = buf;
    return noiseBuffer;
  }

  /* ------------------------------------------------------------------ *
   * Voice builders
   * ------------------------------------------------------------------ */

  function cleanup(node, gain, extra) {
    try {
      node.onended = function () {
        try { node.disconnect(); } catch (e) {}
        try { gain.disconnect(); } catch (e) {}
        if (extra) { try { extra.disconnect(); } catch (e) {} }
      };
    } catch (e) { /* ignore */ }
  }

  function envelope(gainNode, t0, dur, peak, attack) {
    var a = attack === undefined ? 0.006 : attack;
    if (a > dur * 0.4) { a = dur * 0.4; }
    if (a <= 0) { a = 0.001; }
    var g = gainNode.gain;
    g.setValueAtTime(0.0001, t0);
    g.exponentialRampToValueAtTime(Math.max(0.0002, peak), t0 + a);
    g.exponentialRampToValueAtTime(0.0001, t0 + dur);
    g.setValueAtTime(0, t0 + dur);
  }

  /**
   * A single oscillator note.
   * @param {number} at      start offset, seconds from now
   * @param {number} dur     length in seconds
   * @param {number} freq    start frequency
   * @param {number} freqEnd end frequency (glide); pass 0/null for none
   * @param {string} type    'sine' | 'triangle' | 'square' | 'sawtooth'
   * @param {number} peak    relative amplitude 0..1
   * @param {number} attack  attack time in seconds (optional)
   * @param {number} lowpass optional lowpass cutoff to tame harsh waveforms
   */
  function tone(at, dur, freq, freqEnd, type, peak, attack, lowpass) {
    var t0 = ctx.currentTime + at;
    var osc = ctx.createOscillator();
    var gain = ctx.createGain();
    var filt = null;

    osc.type = type || 'sine';
    osc.frequency.setValueAtTime(Math.max(1, freq), t0);
    if (freqEnd && freqEnd !== freq) {
      osc.frequency.exponentialRampToValueAtTime(Math.max(1, freqEnd), t0 + dur);
    }

    envelope(gain, t0, dur, peak, attack);

    if (lowpass) {
      filt = ctx.createBiquadFilter();
      filt.type = 'lowpass';
      filt.frequency.setValueAtTime(lowpass, t0);
      filt.Q.value = 0.6;
      osc.connect(filt);
      filt.connect(gain);
    } else {
      osc.connect(gain);
    }
    gain.connect(master);

    osc.start(t0);
    osc.stop(t0 + dur + 0.02);
    cleanup(osc, gain, filt);
  }

  /**
   * A short burst of filtered white noise — paper / chip texture.
   * @param {number} at    start offset in seconds
   * @param {number} dur   length in seconds
   * @param {number} peak  relative amplitude 0..1
   * @param {string} type  biquad filter type ('bandpass' | 'highpass' | ...)
   * @param {number} f0    filter frequency at the start
   * @param {number} f1    filter frequency at the end (sweep); 0/null for none
   * @param {number} q     filter Q
   */
  function noise(at, dur, peak, type, f0, f1, q) {
    var t0 = ctx.currentTime + at;
    var src = ctx.createBufferSource();
    var filt = ctx.createBiquadFilter();
    var gain = ctx.createGain();

    src.buffer = getNoiseBuffer();

    filt.type = type || 'bandpass';
    filt.frequency.setValueAtTime(Math.max(20, f0), t0);
    if (f1 && f1 !== f0) {
      filt.frequency.exponentialRampToValueAtTime(Math.max(20, f1), t0 + dur);
    }
    filt.Q.value = (q === undefined || q === null) ? 0.8 : q;

    envelope(gain, t0, dur, peak, Math.min(0.012, dur * 0.35));

    src.connect(filt);
    filt.connect(gain);
    gain.connect(master);

    /* Start at a random point in the buffer so repeats do not sound identical. */
    var maxOffset = Math.max(0, NOISE_SECONDS - dur - 0.03);
    try {
      src.start(t0, Math.random() * maxOffset, dur + 0.03);
    } catch (e) {
      src.start(t0);
    }
    try { src.stop(t0 + dur + 0.03); } catch (e) {}
    cleanup(src, gain, filt);
  }

  /* ------------------------------------------------------------------ *
   * Effect definitions — every one is <= 320ms and quiet.
   * ------------------------------------------------------------------ */

  function chipBlips(at, peak) {
    /* two very short square-ish clinks, a few ms apart */
    tone(at,         0.035, 1760, 1660, 'square', peak, 0.002, 3600);
    tone(at + 0.045, 0.048, 2349, 2150, 'square', peak, 0.002, 4200);
  }

  var EFFECTS = {

    /* card sliding — soft filtered noise swish, ~90ms */
    'deal': function () {
      noise(0, 0.09, 0.50, 'bandpass', 780, 2350, 0.7);
    },

    /* card flip — brighter, snappier tick, ~70ms */
    'flip': function () {
      noise(0, 0.07, 0.46, 'bandpass', 2400, 3700, 1.3);
    },

    /* chips clinking, ~110ms */
    'chip': function () {
      chipBlips(0, 0.24);
    },

    /* placing a bet — chips plus a small rising blip, ~220ms */
    'bet': function () {
      chipBlips(0, 0.20);
      tone(0.070, 0.070, 784.0, 0, 'triangle', 0.34, 0.005);
      tone(0.135, 0.085, 1046.5, 0, 'triangle', 0.34, 0.005);
    },

    /* check / pass — single soft mid blip, ~70ms */
    'check': function () {
      tone(0, 0.07, 660, 0, 'sine', 0.48, 0.008);
    },

    /* going out / busted — gentle descending two-note, ~220ms */
    'die': function () {
      tone(0,     0.105, 523.3, 0, 'sine', 0.44, 0.010);
      tone(0.100, 0.120, 392.0, 0, 'sine', 0.40, 0.012);
    },

    /* your turn — soft rising two-note, ~160ms */
    'turn': function () {
      tone(0,     0.070, 587.3, 0, 'sine', 0.42, 0.008);
      tone(0.075, 0.085, 880.0, 0, 'sine', 0.44, 0.008);
    },

    /* victory — cheerful ascending major triad + octave (C-E-G-C), ~285ms */
    'win': function () {
      tone(0,     0.085, 1046.5, 0, 'triangle', 0.38, 0.005);
      tone(0.065, 0.085, 1318.5, 0, 'triangle', 0.38, 0.005);
      tone(0.130, 0.085, 1568.0, 0, 'triangle', 0.38, 0.005);
      tone(0.195, 0.090, 2093.0, 0, 'triangle', 0.34, 0.005);
    },

    /* defeat — soft descending three-note, ~260ms */
    'lose': function () {
      tone(0,     0.100, 440.0, 0, 'sine', 0.42, 0.010);
      tone(0.080, 0.100, 349.2, 0, 'sine', 0.40, 0.010);
      tone(0.160, 0.100, 293.7, 0, 'sine', 0.38, 0.012);
    },

    /* taking a loan — quirky bouncy wobble, ~240ms */
    'loan': function () {
      tone(0,     0.075, 659.3, 740.0, 'triangle', 0.36, 0.005);
      tone(0.075, 0.075, 987.8, 880.0, 'triangle', 0.36, 0.005);
      tone(0.150, 0.090, 740.0, 830.6, 'triangle', 0.34, 0.005);
    },

    /* UI tick, ~35ms */
    'click': function () {
      noise(0, 0.03, 0.30, 'highpass', 2600, 0, 0.7);
    },

    /* invalid action — short low buzz, deliberately dull, ~140ms */
    'error': function () {
      tone(0, 0.14, 165, 124, 'sawtooth', 0.30, 0.010, 780);
    }
  };

  /* ------------------------------------------------------------------ *
   * Public API
   * ------------------------------------------------------------------ */

  function play(name) {
    try {
      if (!enabled || !supported) { return; }
      if (typeof name !== 'string') { return; }

      var effect = Object.prototype.hasOwnProperty.call(EFFECTS, name)
        ? EFFECTS[name]
        : null;
      if (!effect) { return; } // unknown name: silent no-op

      var now = Date.now();
      var last = lastPlayedAt[name];
      if (last && (now - last) < THROTTLE_MS) { return; }
      lastPlayedAt[name] = now;

      if (!ready()) { return; }
      effect();
    } catch (e) {
      /* Never let audio break gameplay. */
    }
  }

  function isEnabled() {
    if (!storageOk) { return enabled; }
    try {
      enabled = readStored();
    } catch (e) { /* keep the in-memory value */ }
    return enabled;
  }

  function setEnabled(value) {
    var next = !!value;
    enabled = next;
    writeStored(next);
    if (next) { init(); }
    return next;
  }

  function toggle() {
    return setEnabled(!isEnabled());
  }

  window.Sfx = {
    init: function () { try { return init(); } catch (e) { return false; } },
    play: play,
    setEnabled: function (v) { try { return setEnabled(v); } catch (e) { return !!v; } },
    isEnabled: function () { try { return isEnabled(); } catch (e) { return true; } },
    toggle: function () { try { return toggle(); } catch (e) { return enabled; } }
  };

  /* ------------------------------------------------------------------ *
   * One-time gesture bootstrap (autoplay policy)
   * ------------------------------------------------------------------ */

  (function installGestureHook() {
    try {
      if (!document || !document.addEventListener) { return; }

      var unlock = function () {
        try { document.removeEventListener('pointerdown', unlock, true); } catch (e) {}
        try { document.removeEventListener('pointerdown', unlock, false); } catch (e) {}
        try { document.removeEventListener('keydown', unlock, true); } catch (e) {}
        try { document.removeEventListener('keydown', unlock, false); } catch (e) {}
        init();
      };

      /* Either listener firing removes both (see unlock above), so even a very
         old browser that ignores the options object still behaves as one-shot. */
      document.addEventListener('pointerdown', unlock, { once: true });
      document.addEventListener('keydown', unlock, { once: true });
    } catch (e) { /* no DOM — nothing to hook */ }
  }());

}(typeof window !== 'undefined' ? window : this,
  typeof document !== 'undefined' ? document : null));
