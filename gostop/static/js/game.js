/* =========================================================================
   game.js — window.Game
   Renders the table from a server state snapshot.

   Rendering is *reconciling*, not "innerHTML everything": seats and cards are
   kept in place and keyed by id so CSS transitions (the 3D card flip, the
   turn bounce) survive across updates.
   ========================================================================= */
(function (global) {
  'use strict';

  var handlers = {};
  var state = null;
  var prev = null;

  var seatEls = {};        // pid -> seat element
  var lastLogSeq = 0;
  var lastTurnPid = null;
  var lastChips = null;
  var pendingDiscardId = null;

  /* ------------------------------------------------------------------ */
  /* helpers                                                            */
  /* ------------------------------------------------------------------ */
  function el(id) { return document.getElementById(id); }
  function clear(node) { while (node && node.firstChild) node.removeChild(node.firstChild); }

  function money(n) {
    n = Number(n) || 0;
    return n.toLocaleString('ko-KR');
  }

  function sfx(name) { if (global.Sfx) global.Sfx.play(name); }

  function avatar(charId, expression, size) {
    if (!global.renderCharacter) return '';
    return global.renderCharacter(charId, { expression: expression || 'normal', size: size || 56 });
  }

  function expressionFor(p) {
    if (!p) return 'normal';
    if (p.statusKey === 'winner') return 'winner';
    if (p.folded) return 'folded';
    if (p.spectating) return 'normal';
    if (!p.connected) return 'normal';
    if (p.isTurn) return 'turn';
    if (p.choosingDiscard) return 'thinking';
    if (p.lastAction === 'bet' || p.lastAction === 'raise') return 'betting';
    if (p.lastAction === 'call' || p.lastAction === 'check') return 'happy';
    return 'normal';
  }

  /* ------------------------------------------------------------------ */
  /* cards                                                              */
  /* ------------------------------------------------------------------ */
  function buildCard(card) {
    var node = document.createElement('div');
    node.className = 'card';
    node.setAttribute('data-card-id', card.id);

    var inner = document.createElement('div');
    inner.className = 'card__inner';

    var back = document.createElement('div');
    back.className = 'card__face card__face--back';

    var front = document.createElement('div');
    front.className = 'card__face card__face--front';

    var num = document.createElement('span');
    num.className = 'card__num';
    var sub = document.createElement('span');
    sub.className = 'card__sub';
    front.appendChild(num);
    front.appendChild(sub);

    inner.appendChild(back);
    inner.appendChild(front);
    node.appendChild(inner);
    return node;
  }

  function paintCard(node, card) {
    var faceUp = !card.hidden;
    var num = node.querySelector('.card__num');
    var sub = node.querySelector('.card__sub');
    if (faceUp) {
      if (num) num.textContent = String(card.number);
      if (sub) sub.textContent = card.number === 0 ? '장(10)' : '';
      node.classList.toggle('card--zero', card.number === 0);
    }
    if (faceUp && !node.classList.contains('is-faceup')) {
      node.classList.add('is-faceup');
      return true;   // newly flipped
    }
    if (!faceUp) node.classList.remove('is-faceup');
    return false;
  }

  /**
   * Reconcile a row of cards.  Returns freshly created elements so the
   * caller can run the "flying from the deck" animation on them.
   */
  function syncCards(row, cards, opts) {
    opts = opts || {};
    var created = [];
    var flipped = 0;
    var seen = {};
    var i, node, card;

    for (i = 0; i < cards.length; i++) {
      card = cards[i];
      seen[card.id] = true;
      node = row.querySelector('[data-card-id="' + card.id + '"]');
      if (!node) {
        node = buildCard(card);
        row.appendChild(node);
        created.push(node);
      }
      if (paintCard(node, card)) flipped++;
      node.classList.toggle('is-muted', !!opts.muted);
      // keep DOM order stable with the server order
      if (row.children[i] !== node) row.insertBefore(node, row.children[i] || null);
    }

    var kids = Array.prototype.slice.call(row.children);
    for (i = 0; i < kids.length; i++) {
      var id = kids[i].getAttribute('data-card-id');
      if (id && !seen[id]) row.removeChild(kids[i]);
    }
    return { created: created, flipped: flipped };
  }

  /* ------------------------------------------------------------------ */
  /* seat positions                                                     */
  /* ------------------------------------------------------------------ */
  /* [left%, top%] per opponent count.
     Seats that sit *above* the centre pile (roughly 25%-75% across) must stay
     near the top edge or their cards land on the deck; seats out at the rim
     clear the centre horizontally, so they can hang lower and look seated. */
  var LAYOUTS = {
    0: [],
    1: [[50, 2]],
    2: [[27, 2], [73, 2]],
    3: [[12, 20], [50, 0], [88, 20]],
    4: [[8, 22], [33, 1], [67, 1], [92, 22]],
    5: [[6, 24], [26, 1], [50, 0], [74, 1], [94, 24]]
  };

  function layoutSeats(container, count) {
    var stacked = container.classList.contains('is-stacked');
    var spots = LAYOUTS[Math.min(count, 5)] || [];
    var kids = container.querySelectorAll('.seat');
    for (var i = 0; i < kids.length; i++) {
      if (stacked) {
        kids[i].style.left = '';
        kids[i].style.top = '';
      } else if (spots[i]) {
        kids[i].style.left = spots[i][0] + '%';
        kids[i].style.top = spots[i][1] + '%';
      }
    }
    positionCenter(container, stacked);
  }

  /**
   * Slide the deck/pot block down until it clears every seat that sits above
   * it.  Doing this by measurement instead of fixed percentages keeps the
   * table honest at any window size and any player count.
   */
  function positionCenter(container, stacked) {
    var felt = el('felt');
    var center = felt && felt.querySelector('.center');
    if (!felt || !center) return;

    center.style.top = '';                       // fall back to the CSS value
    if (stacked) return;                         // narrow layout flows normally

    var fr = felt.getBoundingClientRect();
    var cr = center.getBoundingClientRect();
    if (!fr.height || !cr.height) return;

    var lowest = 0;
    var seats = container.querySelectorAll('.seat');
    for (var i = 0; i < seats.length; i++) {
      var sr = seats[i].getBoundingClientRect();
      var overlapsHorizontally = sr.right > cr.left && sr.left < cr.right;
      if (overlapsHorizontally) lowest = Math.max(lowest, sr.bottom - fr.top);
    }

    var half = cr.height / 2;
    var wanted = (fr.height - cr.height) * 0.62;         // the pleasant default
    var minTop = lowest ? lowest + 12 : 10;
    var maxTop = Math.max(10, fr.height - cr.height - 10);
    var top = Math.min(Math.max(wanted, minTop), maxTop);
    center.style.top = (top + half) + 'px';
  }

  /* ------------------------------------------------------------------ */
  /* seats                                                              */
  /* ------------------------------------------------------------------ */
  function buildSeat(p) {
    var seat = document.createElement('div');
    seat.className = 'seat';
    seat.setAttribute('data-pid', p.pid);
    seat.innerHTML =
      '<div class="seat__avatar chr-wrap"></div>' +
      '<div class="seat__plate">' +
        '<span class="seat__nick"></span>' +
        '<span class="seat__chips"></span>' +
        '<div class="seat__badges"></div>' +
        '<span class="seat__status"></span>' +
        '<div class="seat__contrib"></div>' +
      '</div>' +
      '<div class="cardrow cardrow--seat"></div>';
    return seat;
  }

  function paintSeat(seat, p) {
    var av = seat.querySelector('.seat__avatar');
    var expr = expressionFor(p);
    if (av.getAttribute('data-expr') !== expr || av.getAttribute('data-char') !== p.character) {
      var bubbleNode = av.querySelector('.seat__bubble');
      av.innerHTML = avatar(p.character, expr, 48);
      if (bubbleNode) av.appendChild(bubbleNode);
      av.setAttribute('data-expr', expr);
      av.setAttribute('data-char', p.character);
    }

    seat.querySelector('.seat__nick').textContent = p.nickname;
    seat.querySelector('.seat__chips').textContent = money(p.chips);

    var st = seat.querySelector('.seat__status');
    st.textContent = p.status;
    st.setAttribute('data-s', p.statusKey);

    var badges = seat.querySelector('.seat__badges');
    var key = p.badges.map(function (b) { return b.key; }).join('|');
    if (badges.getAttribute('data-key') !== key) {
      badges.setAttribute('data-key', key);
      clear(badges);
      p.badges.forEach(function (b) {
        var s = document.createElement('span');
        s.className = 'badge';
        s.setAttribute('data-b', b.key);
        s.textContent = b.label;
        badges.appendChild(s);
      });
    }

    var contrib = seat.querySelector('.seat__contrib');
    contrib.textContent = p.roundContrib > 0 ? ('낸 칩 ' + money(p.roundContrib)) : '';

    seat.classList.toggle('is-turn', !!p.isTurn);
    seat.classList.toggle('is-folded', !!p.folded);
    seat.classList.toggle('is-spectating', !!p.spectating);
    seat.classList.toggle('is-offline', !p.connected);

    return syncCards(seat.querySelector('.cardrow'), p.cards, { muted: p.folded });
  }

  function renderSeats(st) {
    var container = el('opponents');
    var mePid = st.you ? st.you.pid : null;
    var others = st.players.filter(function (p) { return p.pid !== mePid; });

    // keep clockwise order starting from the seat after mine
    if (mePid) {
      var mine = st.players.filter(function (p) { return p.pid === mePid; })[0];
      if (mine) {
        others.sort(function (a, b) {
          var n = st.players.length;
          var da = (a.seat - mine.seat + n) % n;
          var db = (b.seat - mine.seat + n) % n;
          return da - db;
        });
      }
    }

    var created = [];
    var flipped = 0;
    var alive = {};

    others.forEach(function (p, i) {
      alive[p.pid] = true;
      var seat = seatEls[p.pid];
      if (!seat) {
        seat = buildSeat(p);
        seatEls[p.pid] = seat;
      }
      if (container.children[i] !== seat) {
        container.insertBefore(seat, container.children[i] || null);
      }
      var r = paintSeat(seat, p);
      created = created.concat(r.created);
      flipped += r.flipped;
    });

    Object.keys(seatEls).forEach(function (pid) {
      if (!alive[pid]) {
        if (seatEls[pid].parentNode) seatEls[pid].parentNode.removeChild(seatEls[pid]);
        delete seatEls[pid];
      }
    });

    container.classList.toggle('is-stacked', global.innerWidth < 860);
    layoutSeats(container, others.length);
    return { created: created, flipped: flipped };
  }

  /* ------------------------------------------------------------------ */
  /* my area                                                            */
  /* ------------------------------------------------------------------ */
  function renderMe(st) {
    var you = st.you;
    if (!you) return { created: [], flipped: 0 };

    var mine = st.players.filter(function (p) { return p.pid === you.pid; })[0];
    var expr = expressionFor(mine || {});
    var av = el('me-avatar');
    if (av.getAttribute('data-expr') !== expr || av.getAttribute('data-char') !== you.character) {
      var bub = av.querySelector('.seat__bubble');
      av.innerHTML = avatar(you.character, expr, 62);
      if (bub) av.appendChild(bub);
      av.setAttribute('data-expr', expr);
      av.setAttribute('data-char', you.character);
    }

    el('me-nick').textContent = you.nickname;

    var chipsEl = el('me-chips');
    chipsEl.textContent = money(you.chips);
    if (lastChips !== null && you.chips !== lastChips) {
      var cls = you.chips > lastChips ? 'is-up' : 'is-down';
      chipsEl.classList.remove('is-up', 'is-down');
      void chipsEl.offsetWidth;
      chipsEl.classList.add(cls);
    }
    lastChips = you.chips;

    var badges = el('me-badges');
    var bs = (mine && mine.badges) || [];
    var key = bs.map(function (b) { return b.key; }).join('|');
    if (badges.getAttribute('data-key') !== key) {
      badges.setAttribute('data-key', key);
      clear(badges);
      bs.forEach(function (b) {
        var s = document.createElement('span');
        s.className = 'badge';
        s.setAttribute('data-b', b.key);
        s.textContent = b.label;
        badges.appendChild(s);
      });
    }

    // --- cards -------------------------------------------------------
    var row = el('my-cards');
    var res = syncCards(row, you.cards, { muted: you.folded });
    var choosing = !!you.needsDiscard;
    row.classList.toggle('is-choosing', choosing);

    // Every card gets a permanent little "what happens if I drop this" tag.
    var previews = {};
    (you.discardPreviews || []).forEach(function (pv) { previews[pv.discard] = pv; });
    Array.prototype.forEach.call(row.children, function (node) {
      var id = node.getAttribute('data-card-id');
      var tip = node.querySelector('.card__tip');
      if (choosing && previews[id]) {
        if (!tip) {
          tip = document.createElement('div');
          tip.className = 'card__tip';
          node.appendChild(tip);
        }
        tip.textContent = '버리면 ' + previews[id].hand.name;
      } else if (tip) {
        node.removeChild(tip);
      }
      node.classList.toggle('is-picked', choosing && id === pendingDiscardId);
    });

    // --- my hand -----------------------------------------------------
    var handBox = el('my-hand');
    if (you.hand && you.cards.length === 2) {
      handBox.hidden = false;
      el('my-hand-combo').textContent = you.hand.combo;
      el('my-hand-name').textContent = you.hand.name;
      var great = you.hand.category === 'gwang' || you.hand.name === '장땡';
      handBox.classList.toggle('is-great', great);
    } else {
      handBox.hidden = true;
    }
    el('discard-hint').hidden = !choosing;

    return res;
  }

  /* ------------------------------------------------------------------ */
  /* action buttons                                                     */
  /* ------------------------------------------------------------------ */
  function mkBtn(label, cls, onClick, disabled, title) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'btn ' + cls;
    b.textContent = label;
    if (disabled) b.disabled = true;
    if (title) b.title = title;
    b.addEventListener('click', function () {
      if (global.Sfx) global.Sfx.play('click');
      onClick();
    });
    return b;
  }

  function renderActions(st) {
    var box = el('action-buttons');
    var extra = el('extra-buttons');
    var note = el('action-note');
    var sum = el('bet-summary');
    clear(box); clear(extra);
    note.textContent = '';
    note.classList.remove('is-warn');

    var you = st.you;
    var room = st.room;
    if (!you) { sum.hidden = true; return; }

    var betting = room.phase === 'BET1' || room.phase === 'BET2';
    sum.hidden = !(betting && you.inRound && !you.folded);
    if (!sum.hidden) {
      el('betsum-tocall').textContent = money(you.toCall);
      el('betsum-pot').textContent = money(room.pot);
      el('betsum-raises').textContent = room.raiseCount + ' / ' + room.maxRaises;
      // highlight the one number a beginner actually needs
      el('betsum-tocall').parentNode.classList.toggle('betsum__item--need', you.toCall > 0);
    }

    // --- betting turn ------------------------------------------------
    if (betting && you.isTurn && you.actions.length) {
      you.actions.forEach(function (a) {
        if (a.type === 'die') return;   // 다이 is added last, always visible
        var cls = (a.type === 'call' || a.type === 'bet') ? 'btn--primary'
          : (a.type === 'raise' ? 'btn--gold' : 'btn--teal');
        box.appendChild(mkBtn(a.label, cls, function () {
          if (handlers.onAction) handlers.onAction(a.type);
        }, !a.enabled, a.reason || a.hint));
      });
      note.textContent = '내 차례입니다! ' +
        (you.toCall > 0 ? ('콜하려면 ' + money(you.toCall) + ' 칩이 필요합니다.')
                        : '추가로 낼 칩이 없습니다. 체크해도 됩니다.');
      var blocked = you.actions.filter(function (a) { return !a.enabled && a.reason; });
      if (blocked.length && you.toCall > 0 && you.chips < you.toCall) {
        note.textContent = '칩이 부족합니다. 대출을 받거나 다이를 선택해주세요.';
        note.classList.add('is-warn');
      }
    } else if (betting && you.inRound && !you.folded) {
      note.textContent = room.turnNickname
        ? (room.turnNickname + '님의 차례를 기다리는 중...')
        : '베팅 진행 중...';
    }

    // --- discard phase -----------------------------------------------
    if (room.phase === 'DISCARD') {
      if (you.needsDiscard) {
        note.textContent = '버릴 카드를 눌러보세요. 남는 두 장의 족보를 미리 보여드립니다.';
      } else if (you.inRound && !you.folded) {
        note.textContent = '다른 분들이 카드를 고르는 중... (' +
          room.pendingDiscardCount + '명 남음)';
      }
    }

    // --- 다이 : always one click away --------------------------------
    if (you.canDie) {
      // During the discard phase we spell out that no card needs picking.
      var dieLabel = (room.phase === 'DISCARD' && you.needsDiscard) ? '그냥 다이' : '다이';
      box.appendChild(mkBtn(dieLabel, 'btn--die', function () {
        if (handlers.onDie) handlers.onDie();
      }, false, '이번 판만 포기합니다. 카드를 고르지 않아도 됩니다.'));
    }

    // --- extras -------------------------------------------------------
    if (you.loan && you.loan.allowed) {
      extra.appendChild(mkBtn(
        '🏦 대출 ' + you.loan.count + ' / ' + you.loan.max,
        'btn--soft btn--sm',
        function () { if (handlers.onLoan) handlers.onLoan(); },
        false, '칩이 부족할 때 사용할 수 있어요.'
      ));
    } else if (you.loan && you.loan.count >= you.loan.max) {
      extra.appendChild(mkBtn('🏦 대출 ' + you.loan.count + ' / ' + you.loan.max,
        'btn--soft btn--sm', function () {}, true, '대출은 2번까지만 가능합니다.'));
    }
    extra.appendChild(mkBtn('베팅 도움말', 'btn--ghost btn--sm', function () {
      if (global.openGuide) global.openGuide('betting');
    }));

    if (you.spectating) {
      note.textContent = '이번 판은 관전 중입니다. 다음 판부터 다시 참여할 수 있어요.';
    }
    if (you.folded) {
      note.textContent = '이번 판은 다이했습니다. 카드는 공개되지 않아요. 편하게 구경하세요!';
    }
  }

  /* ------------------------------------------------------------------ */
  /* misc panels                                                        */
  /* ------------------------------------------------------------------ */
  function renderPhase(st) {
    var room = st.room;
    var strip = el('phase-strip');
    var flow = (global.GAME_CONFIG && global.GAME_CONFIG.phaseFlow) || [];
    if (strip.getAttribute('data-built') !== String(flow.length)) {
      strip.setAttribute('data-built', String(flow.length));
      clear(strip);
      flow.forEach(function (f, i) {
        if (i) {
          var sep = document.createElement('span');
          sep.className = 'phase-sep';
          sep.textContent = '›';
          strip.appendChild(sep);
        }
        var li = document.createElement('li');
        li.className = 'phase-step';
        li.setAttribute('data-phase', f.key);
        li.textContent = f.label;
        strip.appendChild(li);
      });
    }
    Array.prototype.forEach.call(strip.querySelectorAll('.phase-step'), function (li, i) {
      li.classList.toggle('is-current', li.getAttribute('data-phase') === room.phase);
      li.classList.toggle('is-done', room.phaseIndex >= 0 && i < room.phaseIndex);
    });

    el('table-code').textContent = room.code;
    el('table-round').textContent = room.roundNo ? (room.roundNo + '번째 판') : '대기 중';
    el('pot-amount').textContent = money(room.pot);
    el('discard-count').textContent = room.discardCount;

    var status = el('phase-status');
    if (room.phase === 'BET1' || room.phase === 'BET2') {
      status.textContent = (room.phase === 'BET1' ? '1차 베팅' : '2차 베팅') +
        (room.turnNickname ? (' · ' + room.turnNickname + '님 차례') : '');
    } else {
      status.textContent = room.phaseLabel;
    }

    var tips = global.PHASE_TIPS || {};
    el('phase-tip').textContent = tips[room.phase] || '';

    var wbox = el('waiting-box');
    var forceBtn = el('btn-force-fold');
    if (room.waitingFor) {
      wbox.hidden = false;
      el('waiting-text').textContent = room.waitingFor.text;
      var amHost = st.you && st.you.isHost;
      forceBtn.hidden = !amHost;
      forceBtn.setAttribute('data-pid', room.waitingFor.pid);
    } else {
      wbox.hidden = true;
      forceBtn.hidden = true;
    }

    el('btn-endgame').hidden = !(st.you && st.you.isHost && room.started);
  }

  function renderLog(st) {
    var list = el('game-log');
    var entries = st.log || [];
    if (entries.length && entries[0].seq > lastLogSeq + 1) lastLogSeq = entries[0].seq - 1;
    if (!entries.length) { clear(list); lastLogSeq = 0; return; }
    entries.forEach(function (e) {
      if (e.seq <= lastLogSeq) return;
      var li = document.createElement('li');
      li.textContent = e.text;
      if (e.text.indexOf('──') === 0) li.className = 'is-round';
      li.classList.add('is-new');
      list.appendChild(li);
      lastLogSeq = e.seq;
    });
    while (list.children.length > 60) list.removeChild(list.firstChild);
    list.scrollTop = list.scrollHeight;
  }

  function renderRankInto(node, rows, mePid, isFinal) {
    clear(node);
    (rows || []).forEach(function (r) {
      var li = document.createElement('li');
      var cls = [];
      if (r.pid === mePid) cls.push('is-you');
      if (isFinal && r.autoLast) cls.push('is-penalty');
      li.className = cls.join(' ');

      var no = document.createElement('span');
      no.className = 'rank-no' + (r.rank === 1 && !r.autoLast ? ' is-top' : '');
      no.textContent = r.rank;

      var av = document.createElement('span');
      av.innerHTML = avatar(r.character, r.autoLast ? 'folded' : 'normal', isFinal ? 34 : 22);

      var nick = document.createElement('span');
      nick.className = 'rank-nick';
      nick.textContent = r.nickname;

      var chips = document.createElement('span');
      chips.className = 'rank-chips';
      chips.textContent = money(r.chips);

      li.appendChild(no); li.appendChild(av); li.appendChild(nick);
      if (isFinal && r.penalty) {
        var pen = document.createElement('span');
        pen.className = 'rank-penalty';
        pen.textContent = r.penalty;
        li.appendChild(pen);
      }
      if (r.loanCount) {
        var ln = document.createElement('span');
        ln.className = 'rank-loan';
        ln.textContent = '대출 ' + r.loanCount + '회';
        li.appendChild(ln);
      }
      li.appendChild(chips);
      node.appendChild(li);
    });
  }

  function renderRanking(st) {
    renderRankInto(el('rank-list'), st.ranking, st.you && st.you.pid, false);
  }

  function renderReactions(st) {
    var bar = el('reaction-bar');
    if (bar.getAttribute('data-built')) return;
    bar.setAttribute('data-built', '1');
    var list = (global.GAME_CONFIG && global.GAME_CONFIG.reactions) || [];
    list.forEach(function (r) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'reaction-btn';
      b.textContent = r.text;
      b.addEventListener('click', function () {
        if (handlers.onReaction) handlers.onReaction(r.key);
        b.disabled = true;
        global.setTimeout(function () { b.disabled = false; }, 2000);
      });
      bar.appendChild(b);
    });
  }

  function renderGuidePanel() {
    var slot = el('hand-guide-slot');
    if (!slot || slot.getAttribute('data-built')) return;
    slot.setAttribute('data-built', '1');
    if (global.renderHandGuidePanel) slot.innerHTML = global.renderHandGuidePanel();
  }

  /* ------------------------------------------------------------------ */
  /* fx                                                                 */
  /* ------------------------------------------------------------------ */
  function seatAvatarEl(pid) {
    if (state && state.you && state.you.pid === pid) return el('me-avatar');
    var s = seatEls[pid];
    return s ? s.querySelector('.seat__avatar') : null;
  }

  function seatAnchorEl(pid) {
    if (state && state.you && state.you.pid === pid) return el('me-bar');
    return seatEls[pid] || null;
  }

  var BET_BUBBLE = { bet: '가자!', raise: '더!', call: '콜!', check: '체크' };

  function handleFx(events, newCards) {
    var potEl = el('pot-amount');
    var deck = el('deck-pile');
    var discardPile = el('discard-pile');

    if (newCards && newCards.length && global.Fx) {
      global.Fx.dealCards(newCards, deck, 90);
      sfx('deal');
    }

    (events || []).forEach(function (e) {
      var anchor, av;
      switch (e.type) {
        case 'ante':
          (e.players || []).forEach(function (row, i) {
            var from = seatAnchorEl(row.pid);
            global.setTimeout(function () {
              if (global.Fx) global.Fx.flyChips(from, potEl, 2);
            }, i * 70);
          });
          sfx('chip');
          break;

        case 'bet':
          anchor = seatAnchorEl(e.pid);
          av = seatAvatarEl(e.pid);
          if (e.amount > 0 && global.Fx) global.Fx.flyChips(anchor, potEl, 3);
          if (global.Fx && av) global.Fx.bubble(av, BET_BUBBLE[e.action] || '', 1400);
          sfx(e.action === 'check' ? 'check' : 'bet');
          break;

        case 'die':
          av = seatAvatarEl(e.pid);
          if (global.Fx && av) global.Fx.bubble(av, '다이!', 1600);
          sfx('die');
          break;

        case 'discard':
          anchor = seatAnchorEl(e.pid);
          if (global.Fx && anchor) {
            var row = anchor.querySelector('.cardrow');
            global.Fx.flyCardTo(row || anchor, discardPile, { w: 44, h: 62 });
          }
          sfx('flip');
          break;

        case 'reveal':
          sfx('flip');
          break;

        case 'winner':
          (e.pids || []).forEach(function (pid) {
            var a = seatAnchorEl(pid);
            if (global.Fx) {
              global.Fx.confetti(a, 26);
              global.Fx.floatText(a, '+' + money(e.pot), '#e3a72f');
            }
          });
          sfx(state && state.you && (e.pids || []).indexOf(state.you.pid) >= 0 ? 'win' : 'lose');
          break;

        case 'reaction':
          av = seatAvatarEl(e.pid);
          if (global.Fx && av) global.Fx.bubble(av, e.text, 1800);
          break;

        case 'loan':
          anchor = seatAnchorEl(e.pid);
          if (global.Fx) global.Fx.floatText(anchor, '+' + money(e.net), '#3f9d8f');
          sfx('loan');
          break;
      }
    });
  }

  /* ------------------------------------------------------------------ */
  /* public                                                             */
  /* ------------------------------------------------------------------ */
  function render(newState) {
    prev = state;
    state = newState;

    renderGuidePanel();
    renderReactions(state);
    renderPhase(state);

    var a = renderSeats(state);
    var b = renderMe(state);
    renderActions(state);
    renderLog(state);
    renderRanking(state);

    var newCards = a.created.concat(b.created);

    // "it's my turn" cue
    var turnPid = state.room.turnPid;
    if (turnPid !== lastTurnPid) {
      if (state.you && turnPid === state.you.pid) {
        sfx('turn');
        var mine = el('me-avatar');
        if (global.Fx && mine) global.Fx.flashExpression(mine, 'turn', 1200);
      }
      lastTurnPid = turnPid;
    }

    // sparkle a really good hand once
    if (state.you && state.you.hand &&
        (state.you.hand.category === 'gwang' || state.you.hand.name === '장땡')) {
      var pk = state.you.hand.name + '|' + state.room.roundNo;
      if (render._sparkKey !== pk) {
        render._sparkKey = pk;
        if (global.Fx) global.Fx.sparkle(el('my-hand'), 6);
      }
    }

    handleFx(state.fx, newCards);
    return state;
  }

  function reset() {
    seatEls = {};
    lastLogSeq = 0;
    lastTurnPid = null;
    lastChips = null;
    pendingDiscardId = null;
    prev = null; state = null;
    render._sparkKey = null;
    var op = el('opponents'); if (op) clear(op);
    var lg = el('game-log'); if (lg) clear(lg);
    var mc = el('my-cards'); if (mc) clear(mc);
  }

  function init(h) {
    handlers = h || {};

    // discard: clicking one of my three cards
    var row = el('my-cards');
    row.addEventListener('click', function (ev) {
      if (!state || !state.you || !state.you.needsDiscard) return;
      var node = ev.target.closest ? ev.target.closest('.card') : null;
      if (!node) return;
      var id = node.getAttribute('data-card-id');
      if (!id) return;
      pendingDiscardId = id;
      Array.prototype.forEach.call(row.children, function (c) {
        c.classList.toggle('is-picked', c === node);
      });
      if (global.Sfx) global.Sfx.play('click');
      if (handlers.onDiscardPick) {
        var pv = (state.you.discardPreviews || []).filter(function (p) { return p.discard === id; })[0];
        handlers.onDiscardPick(id, pv);
      }
    });

    global.addEventListener('resize', function () {
      if (!state) return;
      var c = el('opponents');
      c.classList.toggle('is-stacked', global.innerWidth < 860);
      layoutSeats(c, c.querySelectorAll('.seat').length);
    });
  }

  global.Game = {
    init: init,
    render: render,
    reset: reset,
    renderRankInto: renderRankInto,
    money: money,
    avatar: avatar,
    getState: function () { return state; },
    clearPick: function () { pendingDiscardId = null; }
  };
}(window));
