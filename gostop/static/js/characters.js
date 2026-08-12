/* =========================================================================
 * characters.js  —  숫자 섯다 캐릭터 아바타
 * -------------------------------------------------------------------------
 * 100% original geometry. No external assets, no network, no build step.
 * Plain ES5: var / function / string concatenation only.
 *
 * Exposes exactly four globals:
 *   window.CHARACTERS             (array of 12 {id, name, emoji})
 *   window.CHARACTER_EXPRESSIONS  (array of 8 expression keys)
 *   window.renderCharacter(id, opts) -> HTML string
 *   window.characterName(id)         -> Korean name string
 * ========================================================================= */
(function (global) {
  'use strict';

  /* ---------------------------------------------------------------------
   * tiny SVG primitives
   * ------------------------------------------------------------------- */

  var STROKE_W = 2;
  var BLUSH_FILL = '#ef9f9a';
  var BLUSH_OP = '.5';
  var GOLD = '#e3a72f';
  var CREAM = '#fffaf2';
  var THINK_DOT = '#8a7868';

  function n(v) {
    return Math.round(v * 100) / 100;
  }

  function st(stroke, w) {
    if (!stroke) { return ''; }
    return ' stroke="' + stroke + '" stroke-width="' +
      (w === undefined ? STROKE_W : w) +
      '" stroke-linejoin="round" stroke-linecap="round"';
  }

  function circle(cx, cy, r, fill, stroke, extra, w) {
    return '<circle cx="' + n(cx) + '" cy="' + n(cy) + '" r="' + n(r) +
      '" fill="' + fill + '"' + st(stroke, w) + (extra || '') + '/>';
  }

  function ellipse(cx, cy, rx, ry, fill, stroke, extra, w) {
    return '<ellipse cx="' + n(cx) + '" cy="' + n(cy) + '" rx="' + n(rx) +
      '" ry="' + n(ry) + '" fill="' + fill + '"' + st(stroke, w) +
      (extra || '') + '/>';
  }

  function path(d, fill, stroke, extra, w) {
    return '<path d="' + d + '" fill="' + (fill || 'none') + '"' +
      st(stroke, w) + (extra || '') + '/>';
  }

  function rrect(x, y, w, h, r, fill, stroke, extra, sw) {
    return '<rect x="' + n(x) + '" y="' + n(y) + '" width="' + n(w) +
      '" height="' + n(h) + '" rx="' + n(r) + '" ry="' + n(r) +
      '" fill="' + fill + '"' + st(stroke, sw) + (extra || '') + '/>';
  }

  function stroke_line(x1, y1, x2, y2, color, w) {
    return '<path d="M' + n(x1) + ' ' + n(y1) + 'L' + n(x2) + ' ' + n(y2) +
      '" fill="none"' + st(color, w) + '/>';
  }

  /* four-point sparkle / star shape */
  function sparkle(x, y, r, fill) {
    var k = r * 0.24;
    var d = 'M' + n(x) + ' ' + n(y - r) +
      'Q' + n(x + k) + ' ' + n(y - k) + ' ' + n(x + r) + ' ' + n(y) +
      'Q' + n(x + k) + ' ' + n(y + k) + ' ' + n(x) + ' ' + n(y + r) +
      'Q' + n(x - k) + ' ' + n(y + k) + ' ' + n(x - r) + ' ' + n(y) +
      'Q' + n(x - k) + ' ' + n(y - k) + ' ' + n(x) + ' ' + n(y - r) + 'Z';
    return path(d, fill, null);
  }

  function shouldersPath(fill, stroke) {
    return path('M12 100Q16 74 50 74Q84 74 88 100Z', fill, stroke);
  }

  function blushFor(face) {
    if (!face.blush) { return ''; }
    var b = face.blush;
    var extra = ' opacity="' + BLUSH_OP + '"';
    return ellipse(face.cx - b.dx, b.y, b.rx, b.ry, BLUSH_FILL, null, extra) +
      ellipse(face.cx + b.dx, b.y, b.rx, b.ry, BLUSH_FILL, null, extra);
  }

  /* ---------------------------------------------------------------------
   * eyes  —  one small builder per style, swapped by expression
   * ------------------------------------------------------------------- */

  function capR(face) {
    /* keeps chunky-eyed characters (alien / robot) from exploding */
    return Math.min(face.eyeR, 4.6);
  }

  function baseEye(x, y, face, scale) {
    var r = face.eyeR * (scale || 1);
    var out;
    if (face.eyeShape === 'rect') {
      out = rrect(x - r * 1.3, y - r * 0.85, r * 2.6, r * 1.7, r * 0.55,
        face.eyeColor, null);
      if (face.eyeGlint !== false) {
        out += rrect(x - r * 1.0, y - r * 0.5, r * 0.7, r * 0.55, r * 0.25,
          'rgba(255,255,255,.75)', null);
      }
      return out;
    }
    if (face.eyeShape === 'oval') {
      out = ellipse(x, y, r * 0.78, r * 1.12, face.eyeColor, null);
      if (face.eyeGlint !== false) {
        out += ellipse(x - r * 0.24, y - r * 0.45, r * 0.24, r * 0.34,
          'rgba(255,255,255,.85)', null);
      }
      return out;
    }
    out = circle(x, y, r, face.eyeColor, null);
    if (face.eyeGlint !== false && r >= 2.6) {
      out += circle(x - r * 0.3, y - r * 0.34, r * 0.3,
        'rgba(255,255,255,.8)', null);
    }
    return out;
  }

  /* "^" arc — used for happy / wink */
  function arcEye(x, y, face) {
    var b = capR(face);
    var r = b * 1.7;
    var d = 'M' + n(x - r) + ' ' + n(y + r * 0.42) +
      'Q' + n(x) + ' ' + n(y - r * 0.78) + ' ' + n(x + r) + ' ' + n(y + r * 0.42);
    return path(d, 'none', face.eyeColor, null, n(b * 0.85));
  }

  /* big round "!" eyes */
  function wideEye(x, y, face) {
    if (face.eyeShape === 'oval') { return baseEye(x, y, face, 1.18); }
    var white = face.eyeWhite || CREAM;
    if (face.eyeShape === 'rect') {
      var q = face.eyeR * 1.15;
      return rrect(x - q, y - q, q * 2, q * 2, q * 0.5, white, face.eyeColor) +
        circle(x, y, q * 0.5, face.eyeColor, null);
    }
    var r = face.eyeR * 1.55;
    return circle(x, y, r, white, face.eyeColor) +
      circle(x, y, r * 0.5, face.eyeColor, null);
  }

  /* flat "—" eyes */
  function flatEye(x, y, face) {
    var b = capR(face);
    return stroke_line(x - b * 0.95, y, x + b * 0.95, y, face.eyeColor,
      n(b * 0.8));
  }

  function eyesFor(expr, face) {
    var lx = face.cx - face.ex;
    var rx = face.cx + face.ex;
    var sr;
    switch (expr) {
      case 'turn':
        return baseEye(lx, face.ey - 0.8, face, 1.32) +
          baseEye(rx, face.ey - 0.8, face, 1.32);
      case 'thinking':
        return baseEye(lx + face.eyeR * 0.7, face.ey, face, 0.92) +
          baseEye(rx + face.eyeR * 0.7, face.ey, face, 0.92);
      case 'betting':
        return arcEye(lx, face.ey, face) + baseEye(rx, face.ey, face, 1.05);
      case 'happy':
        return arcEye(lx, face.ey, face) + arcEye(rx, face.ey, face);
      case 'surprised':
        return wideEye(lx, face.ey, face) + wideEye(rx, face.ey, face);
      case 'folded':
        return flatEye(lx, face.ey, face) + flatEye(rx, face.ey, face);
      case 'winner':
        sr = Math.min(face.eyeR * 1.8, 7.2);
        return sparkle(lx, face.ey, sr, face.starColor || GOLD) +
          sparkle(rx, face.ey, sr, face.starColor || GOLD);
      default:
        return baseEye(lx, face.ey, face, 1) + baseEye(rx, face.ey, face, 1);
    }
  }

  /* ---------------------------------------------------------------------
   * mouths
   * ------------------------------------------------------------------- */

  function smileStroke(cx, my, w, depth, color, sw) {
    var d = 'M' + n(cx - w) + ' ' + n(my) +
      'Q' + n(cx) + ' ' + n(my + depth) + ' ' + n(cx + w) + ' ' + n(my);
    return path(d, 'none', color, null, sw);
  }

  function smileFilled(cx, my, w, depth, color) {
    var d = 'M' + n(cx - w) + ' ' + n(my) +
      'Q' + n(cx) + ' ' + n(my + depth) + ' ' + n(cx + w) + ' ' + n(my) + 'Z';
    return path(d, color, null);
  }

  function mouthFor(expr, face) {
    var cx = face.cx;
    var my = face.mouthY;
    var s = face.mouthScale || 1;
    var c = face.mouthColor;
    switch (expr) {
      case 'turn':
        return smileStroke(cx, my - 1, 7.6 * s, 8.2 * s, c, 2.5);
      case 'thinking':
        return stroke_line(cx - 4.5 * s, my, cx + 4.5 * s, my, c, 2.2);
      case 'betting':
        return smileFilled(cx, my, 7 * s, 8.5 * s, c);
      case 'happy':
        return smileFilled(cx, my - 0.5, 8.4 * s, 10 * s, c);
      case 'surprised':
        return ellipse(cx, my + 1.5, 2.9 * s, 3.9 * s, c, null);
      case 'folded':
        return smileStroke(cx, my + 2.5 * s, 5 * s, -5 * s, c, 2.2);
      case 'winner':
        return smileFilled(cx, my - 0.5, 8.6 * s, 10.5 * s, c);
      default:
        return smileStroke(cx, my, 5 * s, 4.5 * s, c, 2.2);
    }
  }

  /* ---------------------------------------------------------------------
   * around-the-head extras
   * ------------------------------------------------------------------- */

  function extrasFor(expr) {
    if (expr === 'thinking') {
      /* tucked into the top-right gutter: clears every ear / antenna / bump */
      return circle(85, 30, 2.1, THINK_DOT, CREAM, null, 1.4) +
        circle(90, 22, 2.4, THINK_DOT, CREAM, null, 1.4) +
        circle(95, 13.5, 2.7, THINK_DOT, CREAM, null, 1.4);
    }
    if (expr === 'winner') {
      return sparkle(12, 28, 5, GOLD) +
        sparkle(88, 20, 6.2, GOLD) +
        sparkle(80, 50, 3.8, GOLD);
    }
    return '';
  }

  /* ---------------------------------------------------------------------
   * character definitions  (silhouette + palette + face anchors)
   * ------------------------------------------------------------------- */

  function makeFace(o) {
    return {
      cx: o.cx === undefined ? 50 : o.cx,
      ex: o.ex,
      ey: o.ey,
      eyeR: o.eyeR,
      eyeShape: o.eyeShape || 'dot',
      eyeColor: o.eyeColor,
      eyeWhite: o.eyeWhite || CREAM,
      eyeGlint: o.eyeGlint === false ? false : true,
      starColor: o.starColor || GOLD,
      mouthY: o.mouthY,
      mouthScale: o.mouthScale === undefined ? 1 : o.mouthScale,
      mouthColor: o.mouthColor,
      blush: o.blush || null
    };
  }

  var DEFS = [];

  /* ---- 곰돌 / bear ---------------------------------------------------- */
  (function () {
    var main = '#c19566', dark = '#8f6a43', soft = '#efd9bd', ink = '#4a3728';
    DEFS.push({
      id: 'bear', name: '곰돌', emoji: '🐻',
      body:
        shouldersPath(main, dark) +
        circle(26, 22, 11, main, dark) + circle(74, 22, 11, main, dark) +
        circle(26, 22, 5.4, soft, null) + circle(74, 22, 5.4, soft, null) +
        ellipse(50, 48, 28, 25, main, dark) +
        ellipse(50, 58, 13, 9, soft, null) +
        ellipse(50, 53, 4.2, 3.2, ink, null),
      face: makeFace({
        ex: 11, ey: 43, eyeR: 3.4, eyeColor: ink,
        mouthY: 61, mouthScale: 0.95, mouthColor: ink,
        blush: { dx: 20, y: 54, rx: 6, ry: 3.6 }
      })
    });
  }());

  /* ---- 냥이 / cat ----------------------------------------------------- */
  (function () {
    var main = '#93a9c2', dark = '#6b839e', soft = '#f8d2d0', ink = '#3a4552';
    DEFS.push({
      id: 'cat', name: '냥이', emoji: '🐱',
      body:
        shouldersPath(main, dark) +
        path('M20 34L24 6L46 22Z', main, dark) +
        path('M80 34L76 6L54 22Z', main, dark) +
        path('M25.5 28L27.5 13.5L38 22Z', soft, null) +
        path('M74.5 28L72.5 13.5L62 22Z', soft, null) +
        ellipse(50, 50, 27, 24, main, dark) +
        stroke_line(26, 53, 10, 50, dark, 1.8) +
        stroke_line(26, 58, 11, 60, dark, 1.8) +
        stroke_line(74, 53, 90, 50, dark, 1.8) +
        stroke_line(74, 58, 89, 60, dark, 1.8) +
        path('M46.5 50L53.5 50L50 54.5Z', ink, null),
      face: makeFace({
        ex: 11, ey: 44, eyeR: 3.5, eyeColor: ink,
        mouthY: 60, mouthScale: 0.95, mouthColor: ink,
        blush: { dx: 18, y: 52, rx: 5.8, ry: 3.4 }
      })
    });
  }());

  /* ---- 멍이 / dog ----------------------------------------------------- */
  (function () {
    var main = '#d2a06a', dark = '#a07040', soft = '#f6e6cf', ink = '#4a3a2c';
    var ear = '#b5834d', earLine = '#8a6136';
    DEFS.push({
      id: 'dog', name: '멍이', emoji: '🐶',
      body:
        shouldersPath(main, dark) +
        ellipse(20, 54, 9.5, 19, ear, earLine, ' transform="rotate(-10 20 54)"') +
        ellipse(80, 54, 9.5, 19, ear, earLine, ' transform="rotate(10 80 54)"') +
        ellipse(50, 50, 26, 24, main, dark) +
        ellipse(50, 60, 12.5, 8.5, soft, null) +
        ellipse(50, 55, 4.2, 3.2, ink, null),
      face: makeFace({
        ex: 10.5, ey: 45, eyeR: 3.4, eyeColor: ink,
        mouthY: 63, mouthScale: 0.9, mouthColor: ink,
        blush: { dx: 19, y: 54, rx: 5.6, ry: 3.4 }
      })
    });
  }());

  /* ---- 토깽 / rabbit --------------------------------------------------- */
  (function () {
    var main = '#f0e7dc', dark = '#c6b5a2', soft = '#f7cfd2', ink = '#6b5a4a';
    DEFS.push({
      id: 'rabbit', name: '토깽', emoji: '🐰',
      body:
        shouldersPath(main, dark) +
        ellipse(38, 20, 7.5, 16, main, dark, ' transform="rotate(-9 38 20)"') +
        ellipse(62, 20, 7.5, 16, main, dark, ' transform="rotate(9 62 20)"') +
        ellipse(38, 21, 3.6, 10.5, soft, null, ' transform="rotate(-9 38 21)"') +
        ellipse(62, 21, 3.6, 10.5, soft, null, ' transform="rotate(9 62 21)"') +
        ellipse(50, 53, 25, 23, main, dark) +
        path('M46.5 53L53.5 53L50 57.5Z', '#e0928f', null),
      face: makeFace({
        ex: 10, ey: 47, eyeR: 3.3, eyeColor: ink,
        mouthY: 63, mouthScale: 0.85, mouthColor: ink,
        blush: { dx: 17.5, y: 57, rx: 5.4, ry: 3.2 }
      })
    });
  }());

  /* ---- 여우 / fox ------------------------------------------------------ */
  (function () {
    var main = '#e08a4e', dark = '#b05f28', soft = '#fdf2e4', ink = '#4a3226';
    DEFS.push({
      id: 'fox', name: '여우', emoji: '🦊',
      body:
        shouldersPath(main, dark) +
        path('M18 34L22 5L45 23Z', main, dark) +
        path('M82 34L78 5L55 23Z', main, dark) +
        path('M23.5 27L25.5 13L36 22Z', '#7c4a2c', null) +
        path('M76.5 27L74.5 13L64 22Z', '#7c4a2c', null) +
        ellipse(50, 49, 27, 23, main, dark) +
        path('M50 47Q33 51 33 61Q33 71 50 71Q67 71 67 61Q67 51 50 47Z', soft, dark) +
        path('M45.5 53L54.5 53L50 58.5Z', ink, null),
      face: makeFace({
        ex: 11.5, ey: 42, eyeR: 3.3, eyeColor: ink,
        mouthY: 64, mouthScale: 0.8, mouthColor: ink,
        blush: { dx: 22, y: 48, rx: 5, ry: 3 }
      })
    });
  }());

  /* ---- 판다 / panda ---------------------------------------------------- */
  (function () {
    var white = '#f7f2ea', line = '#cec5b8';
    var black = '#3c3833', blackDark = '#2b2825';
    DEFS.push({
      id: 'panda', name: '판다', emoji: '🐼',
      body:
        shouldersPath(white, line) +
        circle(25, 22, 10.5, black, blackDark) +
        circle(75, 22, 10.5, black, blackDark) +
        ellipse(50, 50, 27, 24, white, line) +
        ellipse(38, 45, 8.5, 10.5, black, null, ' transform="rotate(-14 38 45)"') +
        ellipse(62, 45, 8.5, 10.5, black, null, ' transform="rotate(14 62 45)"') +
        ellipse(50, 56, 4.5, 3.4, black, null),
      face: makeFace({
        ex: 12, ey: 45, eyeR: 3.2, eyeColor: '#fffdf8',
        eyeWhite: blackDark, eyeGlint: false,
        mouthY: 64, mouthScale: 0.85, mouthColor: black,
        blush: { dx: 21, y: 60, rx: 5.4, ry: 3 }
      })
    });
  }());

  /* ---- 펭구 / penguin -------------------------------------------------- */
  (function () {
    var body = '#3a4552', bodyDark = '#2b333d';
    var faceC = '#f7f2ea', faceLine = '#d9d2c6';
    var beak = '#eb9b3c', beakDark = '#c97f26', ink = '#2f3841';
    DEFS.push({
      id: 'penguin', name: '펭구', emoji: '🐧',
      body:
        shouldersPath(body, bodyDark) +
        path('M31 100Q31 80 50 80Q69 80 69 100Z', faceC, null) +
        circle(50, 48, 26, body, bodyDark) +
        path('M50 28Q73 33 73 53Q73 74 50 74Q27 74 27 53Q27 33 50 28Z',
          faceC, faceLine) +
        path('M42 53L58 53L50 63Z', beak, beakDark),
      face: makeFace({
        ex: 10.5, ey: 44, eyeR: 3.4, eyeColor: ink,
        mouthY: 68, mouthScale: 0.7, mouthColor: ink,
        blush: { dx: 19, y: 60, rx: 5.2, ry: 3 }
      })
    });
  }());

  /* ---- 삐약 / chick ---------------------------------------------------- */
  (function () {
    var main = '#f2cd58', dark = '#c9a02a';
    var beak = '#ea8f3a', beakDark = '#c9701f', ink = '#5a4526';
    DEFS.push({
      id: 'chick', name: '삐약', emoji: '🐤',
      body:
        path('M40 26Q42 6 50 20Q58 6 60 26Z', main, dark) +
        circle(50, 54, 27, main, dark) +
        path('M50 56L58.5 61L50 66L41.5 61Z', beak, beakDark),
      face: makeFace({
        ex: 10.5, ey: 48, eyeR: 3.5, eyeColor: ink,
        mouthY: 71, mouthScale: 0.65, mouthColor: ink,
        blush: { dx: 18, y: 62, rx: 5.4, ry: 3.2 }
      })
    });
  }());

  /* ---- 개굴 / frog ----------------------------------------------------- */
  (function () {
    var main = '#82b26b', dark = '#5b8848', ink = '#33482a';
    DEFS.push({
      id: 'frog', name: '개굴', emoji: '🐸',
      body:
        shouldersPath(main, dark) +
        ellipse(50, 58, 28, 21, main, dark) +
        circle(32, 36, 12, main, dark) +
        circle(68, 36, 12, main, dark) +
        circle(32, 36, 8, '#fffaf2', null) +
        circle(68, 36, 8, '#fffaf2', null),
      face: makeFace({
        ex: 18, ey: 36, eyeR: 3.8, eyeColor: ink,
        mouthY: 60, mouthScale: 1.3, mouthColor: ink,
        blush: { dx: 19, y: 64, rx: 5.6, ry: 3.2 }
      })
    });
  }());

  /* ---- 로봇 / robot ---------------------------------------------------- */
  (function () {
    var main = '#a6b8c9', dark = '#70879b', panel = '#d5e0ea';
    var accent = '#e8734a', accentDark = '#c95a34', ink = '#33414e';
    DEFS.push({
      id: 'robot', name: '로봇', emoji: '🤖',
      body:
        path('M14 100Q14 80 34 80L66 80Q86 80 86 100Z', main, dark) +
        stroke_line(50, 21, 50, 10, dark, 3) +
        circle(50, 7, 4.5, accent, accentDark) +
        rrect(20, 22, 60, 54, 14, main, dark) +
        rrect(11.5, 44, 8, 14, 3, dark, null) +
        rrect(80.5, 44, 8, 14, 3, dark, null) +
        rrect(28, 32, 44, 34, 10, panel, null),
      face: makeFace({
        ex: 11, ey: 45, eyeR: 4, eyeShape: 'rect', eyeColor: ink,
        mouthY: 58, mouthScale: 0.85, mouthColor: ink
      })
    });
  }());

  /* ---- 외계 / alien ---------------------------------------------------- */
  (function () {
    var main = '#74c3b0', dark = '#3f8b7c', soft = '#d3efe8', ink = '#23403a';
    DEFS.push({
      id: 'alien', name: '외계', emoji: '👽',
      body:
        path('M37 24Q29 11 24 8', 'none', dark, null, 2.4) +
        path('M63 24Q71 11 76 8', 'none', dark, null, 2.4) +
        circle(23, 7, 4, soft, dark) +
        circle(77, 7, 4, soft, dark) +
        path('M50 14Q88 14 88 44Q88 64 64 79Q57 83 50 83Q43 83 36 79Q12 64 12 44Q12 14 50 14Z',
          main, dark),
      face: makeFace({
        ex: 15, ey: 45, eyeR: 6.6, eyeShape: 'oval', eyeColor: ink,
        mouthY: 67, mouthScale: 0.7, mouthColor: ink
      })
    });
  }());

  /* ---- 유령 / ghost ---------------------------------------------------- */
  (function () {
    var main = '#efe9f5', dark = '#c1b6d4', ink = '#5b5171';
    DEFS.push({
      id: 'ghost', name: '유령', emoji: '👻',
      body:
        path('M18 84L18 48C18 27 32 12 50 12C68 12 82 27 82 48L82 84' +
          'Q75 93 68 84Q61 75 54 84Q47 93 40 84Q33 75 26 84Q22 89 18 84Z',
          main, dark),
      face: makeFace({
        ex: 11, ey: 44, eyeR: 3.6, eyeColor: ink,
        mouthY: 60, mouthScale: 0.95, mouthColor: ink
      })
    });
  }());

  /* ---- neutral fallback (bear-like, muted) ----------------------------- */
  var FALLBACK = (function () {
    var main = '#cbbca9', dark = '#9d8c78', soft = '#efe6d9', ink = '#5a4c3e';
    return {
      id: 'unknown', name: '알 수 없음', emoji: '❔',
      body:
        shouldersPath(main, dark) +
        circle(26, 22, 11, main, dark) + circle(74, 22, 11, main, dark) +
        circle(26, 22, 5.4, soft, null) + circle(74, 22, 5.4, soft, null) +
        ellipse(50, 48, 28, 25, main, dark) +
        ellipse(50, 58, 13, 9, soft, null) +
        ellipse(50, 53, 4.2, 3.2, ink, null),
      face: makeFace({
        ex: 11, ey: 43, eyeR: 3.4, eyeColor: ink,
        mouthY: 61, mouthScale: 0.95, mouthColor: ink,
        blush: { dx: 20, y: 54, rx: 6, ry: 3.6 }
      })
    };
  }());

  /* ---------------------------------------------------------------------
   * public data
   * ------------------------------------------------------------------- */

  var EXPRESSIONS = ['normal', 'turn', 'thinking', 'betting', 'happy',
    'surprised', 'folded', 'winner'];

  var BY_ID = {};
  var LIST = [];
  var i;
  for (i = 0; i < DEFS.length; i++) {
    BY_ID[DEFS[i].id] = DEFS[i];
    LIST.push({ id: DEFS[i].id, name: DEFS[i].name, emoji: DEFS[i].emoji });
  }

  /* ---------------------------------------------------------------------
   * public API
   * ------------------------------------------------------------------- */

  function cleanClassName(v) {
    if (typeof v !== 'string' || !v) { return ''; }
    var s = v.replace(/[^A-Za-z0-9 _-]/g, '').replace(/\s+/g, ' ');
    s = s.replace(/^\s+/, '').replace(/\s+$/, '');
    return s;
  }

  function renderCharacter(id, opts) {
    opts = (opts && typeof opts === 'object') ? opts : {};

    var key = (typeof id === 'string') ? id : '';
    var def = BY_ID[key] || FALLBACK;
    var slug = BY_ID[key] ? key : 'unknown';

    var expr = (typeof opts.expression === 'string') ? opts.expression : 'normal';
    for (var e = 0, ok = false; e < EXPRESSIONS.length; e++) {
      if (EXPRESSIONS[e] === expr) { ok = true; break; }
    }
    if (!ok) { expr = 'normal'; }

    var size = parseFloat(opts.size);
    if (!isFinite(size) || size <= 0) { size = 64; }
    size = Math.round(size);

    var extraClass = cleanClassName(opts.className);
    var face = def.face;

    var inner = def.body +
      blushFor(face) +
      eyesFor(expr, face) +
      mouthFor(expr, face) +
      extrasFor(expr);

    /* no xmlns on purpose: the string is injected as HTML, where the parser
       already puts <svg> in the SVG namespace — keeps the file URL-free */
    var svg = '<svg viewBox="0 0 100 100" width="' + size + '" height="' + size +
      '" aria-hidden="true" focusable="false" class="chr__svg">' +
      inner + '</svg>';

    return '<span class="chr chr--' + expr + ' chr--id-' + slug +
      (extraClass ? ' ' + extraClass : '') +
      '" data-character="' + slug + '" data-expression="' + expr + '">' +
      svg + '</span>';
  }

  function characterName(id) {
    var def = (typeof id === 'string') ? BY_ID[id] : null;
    return def ? def.name : '알 수 없음';
  }

  global.CHARACTERS = LIST;
  global.CHARACTER_EXPRESSIONS = EXPRESSIONS;
  global.renderCharacter = renderCharacter;
  global.characterName = characterName;

}(typeof window !== 'undefined' ? window : this));
