/* =========================================================================
   animations.js — window.Fx
   Small, subtle, office-friendly motion.  Everything degrades to "nothing
   happens" if an element is missing, so callers never need null checks.
   ========================================================================= */
(function (global) {
  'use strict';

  var layer = null;
  function fxLayer() {
    if (!layer) layer = document.getElementById('fx-layer');
    return layer;
  }

  function reduced() {
    try {
      return global.matchMedia &&
        global.matchMedia('(prefers-reduced-motion: reduce)').matches;
    } catch (e) { return false; }
  }

  function center(el) {
    if (!el || !el.getBoundingClientRect) return null;
    var r = el.getBoundingClientRect();
    if (!r.width && !r.height) return null;
    return { x: r.left + r.width / 2, y: r.top + r.height / 2, w: r.width, h: r.height, rect: r };
  }

  function place(node, x, y) {
    node.style.left = (x) + 'px';
    node.style.top = (y) + 'px';
  }

  function remove(node) {
    if (node && node.parentNode) node.parentNode.removeChild(node);
  }

  /* --------------------------------------------------------------------
   * 1. Deal — cards fly out of the centre deck into their slot.
   *    We do not move real DOM around; we just tell each freshly rendered
   *    card where it "came from" via --dx / --dy and let CSS do the work.
   * ------------------------------------------------------------------ */
  function dealCards(cardEls, originEl, stagger) {
    if (!cardEls || !cardEls.length) return 0;
    var origin = center(originEl);
    var step = (typeof stagger === 'number') ? stagger : 95;
    if (reduced() || !origin) return 0;

    var last = 0;
    for (var i = 0; i < cardEls.length; i++) {
      var el = cardEls[i];
      var c = center(el);
      if (!c) continue;
      el.style.setProperty('--dx', Math.round(origin.x - c.x) + 'px');
      el.style.setProperty('--dy', Math.round(origin.y - c.y) + 'px');
      el.style.animationDelay = (i * step) + 'ms';
      el.classList.add('card--deal');
      last = i * step + 460;
      (function (node) {
        node.addEventListener('animationend', function handler() {
          node.classList.remove('card--deal');
          node.style.animationDelay = '';
          node.removeEventListener('animationend', handler);
        });
      }(el));
    }
    var deck = originEl;
    if (deck) {
      deck.classList.add('is-dealing');
      global.setTimeout(function () { deck.classList.remove('is-dealing'); }, last + 60);
    }
    return last;
  }

  /* --------------------------------------------------------------------
   * 2. A face-down card flying to the discard pile.
   * ------------------------------------------------------------------ */
  function flyCardTo(fromEl, toEl, opts) {
    var host = fxLayer();
    var a = center(fromEl), b = center(toEl);
    if (!host || !a || !b || reduced()) return;
    opts = opts || {};

    var node = document.createElement('div');
    node.className = 'fx-ghost-card';
    node.style.width = (opts.w || a.w || 46) + 'px';
    node.style.height = (opts.h || a.h || 64) + 'px';
    node.style.transform = 'translate(-50%,-50%)';
    place(node, a.x, a.y);
    host.appendChild(node);

    // force layout so the transition actually runs
    void node.offsetWidth;
    node.style.transition = 'transform .5s cubic-bezier(.3,.7,.3,1), opacity .5s ease';
    node.style.transform = 'translate(-50%,-50%) translate(' +
      Math.round(b.x - a.x) + 'px,' + Math.round(b.y - a.y) + 'px) scale(.62) rotate(23deg)';
    node.style.opacity = '0.15';
    global.setTimeout(function () { remove(node); }, 560);
  }

  /* --------------------------------------------------------------------
   * 3. Chips flying into the pot.
   * ------------------------------------------------------------------ */
  function flyChips(fromEl, toEl, count) {
    var host = fxLayer();
    var a = center(fromEl), b = center(toEl);
    if (!host || !a || !b || reduced()) return;
    var n = Math.max(1, Math.min(count || 3, 6));

    for (var i = 0; i < n; i++) {
      (function (i) {
        global.setTimeout(function () {
          var node = document.createElement('div');
          node.className = 'fx-chip';
          node.style.transform = 'translate(-50%,-50%)';
          place(node, a.x + (Math.random() * 20 - 10), a.y + (Math.random() * 12 - 6));
          host.appendChild(node);
          void node.offsetWidth;
          node.style.transition = 'transform .52s cubic-bezier(.35,.8,.4,1), opacity .5s ease .16s';
          node.style.transform = 'translate(-50%,-50%) translate(' +
            Math.round(b.x - a.x + (Math.random() * 26 - 13)) + 'px,' +
            Math.round(b.y - a.y + (Math.random() * 16 - 8)) + 'px) scale(.7)';
          node.style.opacity = '0';
          global.setTimeout(function () { remove(node); }, 620);
        }, i * 55);
      }(i));
    }
    var pot = document.querySelector('.pot');
    if (pot) {
      pot.classList.remove('is-bump');
      void pot.offsetWidth;
      pot.classList.add('is-bump');
    }
  }

  /* --------------------------------------------------------------------
   * 4. Confetti for the winner.
   * ------------------------------------------------------------------ */
  var CONFETTI_COLORS = ['#e8734a', '#e3a72f', '#3f9d8f', '#f0a58c', '#8fd0be', '#f6d47a'];

  function confetti(el, amount) {
    var host = fxLayer();
    var a = center(el);
    if (!host || !a || reduced()) return;
    var n = amount || 26;
    for (var i = 0; i < n; i++) {
      (function (i) {
        var node = document.createElement('div');
        node.className = 'fx-confetti';
        node.style.background = CONFETTI_COLORS[i % CONFETTI_COLORS.length];
        node.style.transform = 'translate(-50%,-50%)';
        place(node, a.x, a.y);
        host.appendChild(node);
        var dx = (Math.random() - 0.5) * 300;
        var dy = -80 - Math.random() * 170;
        var rot = (Math.random() - 0.5) * 900;
        void node.offsetWidth;
        node.style.transition = 'transform ' + (900 + Math.random() * 500) + 'ms cubic-bezier(.2,.7,.5,1), opacity 400ms ease ' + (700 + Math.random() * 300) + 'ms';
        node.style.transform = 'translate(-50%,-50%) translate(' + dx + 'px,' + (dy + 320) + 'px) rotate(' + rot + 'deg)';
        node.style.opacity = '0';
        global.setTimeout(function () { remove(node); }, 1700);
      }(i));
    }
  }

  /* --------------------------------------------------------------------
   * 5. A number/word floating up from an element.
   * ------------------------------------------------------------------ */
  function floatText(el, text, color) {
    var host = fxLayer();
    var a = center(el);
    if (!host || !a || reduced()) return;
    var node = document.createElement('div');
    node.className = 'fx-float';
    node.textContent = text;
    if (color) node.style.color = color;
    node.style.transform = 'translate(-50%,-50%)';
    place(node, a.x, a.y - 10);
    host.appendChild(node);
    void node.offsetWidth;
    node.style.transition = 'transform .9s cubic-bezier(.2,.8,.3,1), opacity .9s ease';
    node.style.transform = 'translate(-50%,-50%) translateY(-46px) scale(1.08)';
    node.style.opacity = '0';
    global.setTimeout(function () { remove(node); }, 980);
  }

  function sparkle(el, count) {
    var host = fxLayer();
    var a = center(el);
    if (!host || !a || reduced()) return;
    var marks = ['✦', '✧', '⭑'];
    for (var i = 0; i < (count || 5); i++) {
      (function (i) {
        var node = document.createElement('div');
        node.className = 'fx-sparkle';
        node.textContent = marks[i % marks.length];
        node.style.color = '#e3a72f';
        node.style.transform = 'translate(-50%,-50%)';
        place(node, a.x + (Math.random() - 0.5) * (a.w || 60), a.y + (Math.random() - 0.5) * (a.h || 30));
        host.appendChild(node);
        void node.offsetWidth;
        node.style.transition = 'transform .8s ease, opacity .8s ease';
        node.style.transform = 'translate(-50%,-50%) translateY(-26px) scale(1.5)';
        node.style.opacity = '0';
        global.setTimeout(function () { remove(node); }, 860);
      }(i));
    }
  }

  /* --------------------------------------------------------------------
   * 6. Speech bubble above a character.
   * ------------------------------------------------------------------ */
  var bubbleTimers = {};

  function bubble(anchorEl, text, ms) {
    if (!anchorEl || !text) return;
    var key = anchorEl.getAttribute('data-bubble-key') || String(Math.random());
    anchorEl.setAttribute('data-bubble-key', key);

    var old = anchorEl.querySelector('.seat__bubble');
    if (old) remove(old);
    if (bubbleTimers[key]) global.clearTimeout(bubbleTimers[key]);

    var node = document.createElement('div');
    node.className = 'seat__bubble';
    node.textContent = text;
    anchorEl.appendChild(node);
    bubbleTimers[key] = global.setTimeout(function () {
      remove(node);
      delete bubbleTimers[key];
    }, ms || 1800);
  }

  /* --------------------------------------------------------------------
   * 7. One-shot expression flash on a character.
   * ------------------------------------------------------------------ */
  function flashExpression(wrapEl, expression, ms) {
    if (!wrapEl) return;
    var chr = wrapEl.querySelector('.chr');
    if (!chr) return;
    var prev = chr.getAttribute('data-expression') || 'normal';
    if (prev === expression) {
      chr.classList.remove('chr--' + expression);
      void chr.offsetWidth;
      chr.classList.add('chr--' + expression);
      return;
    }
    chr.classList.remove('chr--' + prev);
    chr.classList.add('chr--' + expression);
    global.setTimeout(function () {
      if (!chr.parentNode) return;
      chr.classList.remove('chr--' + expression);
      chr.classList.add('chr--' + (chr.getAttribute('data-expression') || 'normal'));
    }, ms || 900);
  }

  global.Fx = {
    dealCards: dealCards,
    flyCardTo: flyCardTo,
    flyChips: flyChips,
    confetti: confetti,
    floatText: floatText,
    sparkle: sparkle,
    bubble: bubble,
    flashExpression: flashExpression,
    reduced: reduced
  };
}(window));
