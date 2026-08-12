/* =========================================================================
   app.js — boot, screens, forms, modals, socket wiring.
   ========================================================================= */
(function (global) {
  'use strict';

  var CFG = global.GAME_CONFIG || {};
  var doc = document;

  var me = {
    nickname: '',
    character: '',
    roomCode: '',
    token: '',
    pid: '',
    isHost: false
  };

  var mode = 'create';         // 'create' | 'join'
  var joinRoomInfo = null;     // {usedCharacters:[...]}
  var lastResultRound = -1;
  var lastPhase = null;
  var pendingDiscard = null;   // {cardId, preview}
  var latest = null;

  function el(id) { return doc.getElementById(id); }
  function money(n) { return (Number(n) || 0).toLocaleString('ko-KR'); }

  /* ------------------------------------------------------------------ */
  /* storage                                                            */
  /* ------------------------------------------------------------------ */
  function store(area, key, value) {
    try {
      if (value === undefined) {
        var raw = global[area].getItem(key);
        return raw ? JSON.parse(raw) : null;
      }
      if (value === null) global[area].removeItem(key);
      else global[area].setItem(key, JSON.stringify(value));
    } catch (e) { /* private mode etc. */ }
    return null;
  }
  var lsGet = function (k) { return store('localStorage', k); };
  var lsSet = function (k, v) { store('localStorage', k, v); };
  var ssGet = function (k) { return store('sessionStorage', k); };
  var ssSet = function (k, v) { store('sessionStorage', k, v); };

  /* ------------------------------------------------------------------ */
  /* toasts                                                             */
  /* ------------------------------------------------------------------ */
  function toast(message, kind) {
    var box = el('toasts');
    var t = doc.createElement('div');
    t.className = 'toast' + (kind ? ' toast--' + kind : '');
    t.textContent = message;
    box.appendChild(t);
    global.setTimeout(function () {
      t.classList.add('is-out');
      global.setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); }, 260);
    }, 2600);
  }

  /* ------------------------------------------------------------------ */
  /* screens & modals                                                   */
  /* ------------------------------------------------------------------ */
  function showScreen(name) {
    ['home', 'lobby', 'table'].forEach(function (s) {
      el('screen-' + s).classList.toggle('is-active', s === name);
    });
  }

  function openModal(id) { el(id).hidden = false; }
  function closeModal(id) { el(id).hidden = true; }
  function closeAllModals() {
    ['modal-dai', 'modal-discard', 'modal-loan', 'modal-end', 'modal-result', 'modal-final']
      .forEach(closeModal);
  }

  /* ------------------------------------------------------------------ */
  /* character grid                                                     */
  /* ------------------------------------------------------------------ */
  function buildCharacterGrid() {
    var grid = el('character-grid');
    grid.innerHTML = '';
    (CFG.characters || []).forEach(function (c) {
      var cell = doc.createElement('div');
      cell.className = 'char-cell';
      cell.setAttribute('role', 'radio');
      cell.setAttribute('tabindex', '0');
      cell.setAttribute('data-char', c.id);
      cell.innerHTML =
        (global.renderCharacter ? global.renderCharacter(c.id, { expression: 'normal', size: 52 }) : '') +
        '<span class="char-cell__name">' + c.name + '</span>' +
        '<span class="char-cell__taken" hidden>사용 중</span>';
      cell.addEventListener('click', function () { pickCharacter(c.id); });
      cell.addEventListener('keydown', function (ev) {
        if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); pickCharacter(c.id); }
      });
      grid.appendChild(cell);
    });
  }

  function pickCharacter(id) {
    var cell = doc.querySelector('.char-cell[data-char="' + id + '"]');
    if (!cell || cell.classList.contains('is-taken')) {
      toast('이 캐릭터는 다른 플레이어가 사용 중입니다.', 'error');
      return;
    }
    me.character = id;
    if (global.Sfx) global.Sfx.play('click');
    refreshCharacterGrid();
    var name = global.characterName ? global.characterName(id) : '';
    el('char-status').textContent = name + ' 선택 완료!';
  }

  function refreshCharacterGrid() {
    var used = (joinRoomInfo && joinRoomInfo.usedCharacters) || [];
    doc.querySelectorAll('.char-cell').forEach(function (cell) {
      var id = cell.getAttribute('data-char');
      var taken = mode === 'join' && used.indexOf(id) >= 0;
      cell.classList.toggle('is-taken', taken);
      cell.classList.toggle('is-selected', me.character === id && !taken);
      cell.setAttribute('aria-checked', me.character === id ? 'true' : 'false');
      cell.querySelector('.char-cell__taken').hidden = !taken;
      if (taken && me.character === id) {
        me.character = '';
        el('char-status').textContent = '';
      }
    });
  }

  /* ------------------------------------------------------------------ */
  /* home form                                                          */
  /* ------------------------------------------------------------------ */
  function readForm() {
    me.nickname = (el('input-nickname').value || '').trim();
    return me;
  }

  function validateIdentity() {
    readForm();
    if (!me.nickname) { toast('닉네임을 입력해주세요.', 'error'); el('input-nickname').focus(); return false; }
    if (me.nickname.length > (CFG.nicknameMax || 12)) { toast('닉네임은 12자까지 가능합니다.', 'error'); return false; }
    if (!me.character) { toast('캐릭터를 선택해주세요.', 'error'); return false; }
    lsSet('gostop.profile', { nickname: me.nickname, character: me.character });
    return true;
  }

  function setMode(next) {
    mode = next;
    el('join-code-field').hidden = (next !== 'join');
    el('btn-join-back').hidden = (next !== 'join');
    el('btn-create').hidden = (next === 'join');
    el('btn-join').textContent = (next === 'join') ? '이 방에 참가하기' : '방 참가하기';
    refreshCharacterGrid();
    if (next === 'join') el('input-roomcode').focus();
  }

  function requestRoomInfo() {
    var code = (el('input-roomcode').value || '').trim().toUpperCase();
    if (code.length >= 4) global.Net.send('room_info', { roomCode: code });
    else { joinRoomInfo = null; refreshCharacterGrid(); }
  }

  /* ------------------------------------------------------------------ */
  /* lobby                                                              */
  /* ------------------------------------------------------------------ */
  function inviteUrl() {
    return global.location.origin + '/?room=' + me.roomCode;
  }

  function copyInvite() {
    var input = el('invite-url');
    var text = input.value;
    var done = function () { toast('초대 주소를 복사했습니다!', 'good'); };
    // http:// on a LAN IP is not a secure context, so clipboard API is often
    // unavailable — the execCommand fallback is the one that actually runs.
    if (global.navigator && global.navigator.clipboard && global.navigator.clipboard.writeText) {
      global.navigator.clipboard.writeText(text).then(done, legacyCopy);
    } else { legacyCopy(); }

    function legacyCopy() {
      try {
        input.removeAttribute('readonly');
        input.select();
        input.setSelectionRange(0, 99999);
        var ok = doc.execCommand('copy');
        input.setAttribute('readonly', 'readonly');
        if (ok) done();
        else toast('주소를 직접 복사해주세요.', 'error');
      } catch (e) {
        toast('주소를 직접 복사해주세요.', 'error');
      }
    }
  }

  function renderLobby(state) {
    el('lobby-code').textContent = state.room.code;
    el('invite-url').value = inviteUrl();
    el('lobby-count').textContent = state.room.playerCount + ' / ' + state.room.maxPlayers + '명';
    el('lobby-chips').textContent = money(CFG.startingChips);

    var grid = el('lobby-grid');
    grid.innerHTML = '';
    state.players.forEach(function (p) {
      var card = doc.createElement('div');
      card.className = 'lobby-card' + (p.isYou ? ' is-you' : '');
      card.innerHTML =
        (global.renderCharacter ? global.renderCharacter(p.character, { expression: p.isYou ? 'happy' : 'normal', size: 54 }) : '') +
        '<span class="lobby-card__nick">' + escapeHtml(p.nickname) + '</span>' +
        (p.isHost ? '<span class="lobby-card__tag">👑 방장</span>' : '') +
        (!p.connected ? '<span class="lobby-card__off">연결 끊김</span>' : '');
      grid.appendChild(card);
    });
    for (var i = state.players.length; i < state.room.maxPlayers; i++) {
      var empty = doc.createElement('div');
      empty.className = 'lobby-card lobby-card__empty';
      empty.textContent = '빈 자리';
      grid.appendChild(empty);
    }

    var host = state.you && state.you.isHost;
    var canStart = state.room.canStart;
    el('btn-start').hidden = !host;
    el('btn-start').disabled = !canStart;
    el('btn-start').textContent = canStart ? '게임 시작'
      : (CFG.minPlayers + '명 이상 필요합니다');
    el('lobby-wait').hidden = host;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  /* ------------------------------------------------------------------ */
  /* result / final                                                     */
  /* ------------------------------------------------------------------ */
  function renderResult(state) {
    var r = state.result;
    if (!r) return;
    el('result-headline').textContent = r.headline || '이번 판 결과';
    el('result-explain').textContent = r.explain || '';

    var box = el('result-winners');
    box.innerHTML = '';
    (r.winners || []).forEach(function (w) {
      var card = doc.createElement('div');
      card.className = 'winner-card';
      card.innerHTML =
        (global.renderCharacter ? global.renderCharacter(w.character, { expression: 'winner', size: 64 }) : '') +
        '<span class="winner-card__nick">' + escapeHtml(w.nickname) + '</span>' +
        (w.hand ? '<span class="winner-card__combo">' + escapeHtml(w.hand.combo) + '</span>' +
                  '<span class="winner-card__hand">' + escapeHtml(w.hand.name) + '</span>' : '') +
        '<span class="winner-card__gain">+' + money(w.amount) + '</span>';
      box.appendChild(card);
    });

    var rev = el('result-reveals');
    rev.innerHTML = '';
    (r.reveals || []).forEach(function (row) {
      var line = doc.createElement('div');
      line.className = 'reveal-row' + (row.winner ? ' is-winner' : '');
      var cards = row.cards.map(function (c) {
        return '<span class="mini-card">' + (c.hidden ? '?' : c.number) + '</span>';
      }).join('');
      line.innerHTML =
        (global.renderCharacter ? global.renderCharacter(row.character, { expression: row.winner ? 'winner' : 'normal', size: 34 }) : '') +
        '<span class="reveal-row__nick">' + escapeHtml(row.nickname) + '</span>' +
        '<span class="reveal-row__cards">' + cards + '</span>' +
        '<span class="reveal-row__hand">' + escapeHtml(row.hand.name) + '</span>';
      rev.appendChild(line);
    });
    var foldedCount = (state.players || []).filter(function (p) {
      return p.inRound && p.folded;
    }).length;
    if (r.type === 'allFolded' || foldedCount > 0) {
      var names = (state.players || []).filter(function (p) { return p.inRound && p.folded; })
        .map(function (p) { return p.nickname; });
      var note = doc.createElement('p');
      note.className = 'result__explain';
      note.style.marginBottom = '0';
      note.textContent = names.length
        ? ('다이한 ' + names.join(', ') + '님의 카드는 공개되지 않습니다.')
        : '다이한 분들의 카드는 공개되지 않습니다.';
      rev.appendChild(note);
    }

    global.Game.renderRankInto(el('result-rank'), state.ranking, state.you && state.you.pid, false);

    var host = state.you && state.you.isHost;
    el('btn-next-round').hidden = !host;
    el('result-wait').hidden = !!host;

    // A player who cannot afford the next 참가비 should not have to hunt for
    // the bank button behind this modal.
    var you = state.you;
    var broke = you && you.chips < (CFG.ante || 10000);
    el('btn-result-loan').hidden = !(you && you.loan && you.loan.allowed && broke);
  }

  function renderFinal(state) {
    if (!state.final) return;
    global.Game.renderRankInto(el('final-list'), state.final.standings, state.you && state.you.pid, true);
  }

  /* ------------------------------------------------------------------ */
  /* 다이 confirmation                                                   */
  /* ------------------------------------------------------------------ */
  function askDie() {
    if (ssGet('gostop.dai.skip')) { global.Net.send('die', {}); return; }
    el('dai-dontask').checked = false;
    openModal('modal-dai');
  }

  /* ------------------------------------------------------------------ */
  /* discard confirmation                                               */
  /* ------------------------------------------------------------------ */
  function askDiscard(cardId, preview) {
    if (!preview) return;
    pendingDiscard = { cardId: cardId, preview: preview };
    var throwBox = el('discard-throw');
    var keepBox = el('discard-keep');
    throwBox.innerHTML = miniCard(preview.discardNumber);
    keepBox.innerHTML = preview.keepNumbers.map(miniCard).join('');
    el('discard-handname').textContent = preview.hand.name;
    openModal('modal-discard');
  }

  function miniCard(n) {
    return '<div class="card is-faceup" style="--w:52px;--h:74px">' +
      '<div class="card__inner"><div class="card__face card__face--back"></div>' +
      '<div class="card__face card__face--front">' +
      '<span class="card__num">' + n + '</span>' +
      '<span class="card__sub">' + (n === 0 ? '장(10)' : '') + '</span>' +
      '</div></div></div>';
  }

  /* ------------------------------------------------------------------ */
  /* loan                                                               */
  /* ------------------------------------------------------------------ */
  function askLoan() {
    var you = latest && latest.you;
    if (!you) return;
    el('loan-amount').textContent = money(you.loan.amount);
    el('loan-interest').textContent = '-' + money(you.loan.interest);
    el('loan-net').textContent = money(you.loan.net);
    el('loan-count').textContent = you.loan.count + ' / ' + you.loan.max;
    el('loan-warning').hidden = !you.loan.nextIsPenalty;
    openModal('modal-loan');
  }

  /* ------------------------------------------------------------------ */
  /* main state handler                                                 */
  /* ------------------------------------------------------------------ */
  function onState(state) {
    latest = state;
    if (!state || !state.room) return;
    me.roomCode = state.room.code;
    if (state.you) { me.pid = state.you.pid; me.isHost = state.you.isHost; }

    var phase = state.room.phase;

    if (phase === 'LOBBY') {
      showScreen('lobby');
      renderLobby(state);
      closeAllModals();
      lastResultRound = -1;
      lastPhase = phase;
      return;
    }

    showScreen('table');
    global.Game.render(state);

    // round result
    if (phase === 'ROUND_END' && state.result) {
      if (lastResultRound !== state.room.roundNo) {
        lastResultRound = state.room.roundNo;
        global.Game.clearPick();
        pendingDiscard = null;
        global.setTimeout(function () {
          if (latest && latest.room.phase === 'ROUND_END') {
            renderResult(latest);
            openModal('modal-result');
          }
        }, 700);
      } else if (!el('modal-result').hidden) {
        renderResult(state);
      }
    } else if (phase !== 'ROUND_END') {
      closeModal('modal-result');
    }

    if (phase === 'FINISHED') {
      renderFinal(state);
      openModal('modal-final');
    } else {
      closeModal('modal-final');
    }

    // a new round wipes the discard picker
    if (lastPhase !== phase) {
      if (phase === 'ANTE' || phase === 'DEAL2') {
        global.Game.clearPick();
        pendingDiscard = null;
        closeModal('modal-discard');
      }
      lastPhase = phase;
    }

    // if I already discarded, make sure the modal is gone
    if (state.you && !state.you.needsDiscard) closeModal('modal-discard');
  }

  /* ------------------------------------------------------------------ */
  /* wiring                                                             */
  /* ------------------------------------------------------------------ */
  function wire() {
    // nickname counter
    el('input-nickname').addEventListener('input', function () {
      el('nick-count').textContent = String((this.value || '').length);
    });
    el('input-nickname').addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter') { ev.preventDefault(); (mode === 'join' ? el('btn-join') : el('btn-create')).click(); }
    });

    el('input-roomcode').addEventListener('input', function () {
      this.value = this.value.toUpperCase().replace(/[^A-Z0-9]/g, '');
      requestRoomInfo();
    });
    el('input-roomcode').addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter') { ev.preventDefault(); el('btn-join').click(); }
    });

    el('btn-create').addEventListener('click', function () {
      if (!validateIdentity()) return;
      global.Net.send('create_room', { nickname: me.nickname, character: me.character });
    });

    el('btn-join').addEventListener('click', function () {
      if (mode !== 'join') { setMode('join'); return; }
      if (!validateIdentity()) return;
      var code = (el('input-roomcode').value || '').trim().toUpperCase();
      if (code.length < 4) { toast('방 코드를 입력해주세요.', 'error'); return; }
      global.Net.send('join_room', { roomCode: code, nickname: me.nickname, character: me.character });
    });

    el('btn-join-back').addEventListener('click', function () { setMode('create'); });

    el('btn-copy-invite').addEventListener('click', copyInvite);
    el('btn-start').addEventListener('click', function () { global.Net.send('start_game', {}); });

    ['btn-leave-lobby', 'btn-leave-table'].forEach(function (id) {
      el(id).addEventListener('click', function () {
        global.Net.send('leave_room', {});
        goHome();
      });
    });

    // 다이
    el('btn-dai-cancel').addEventListener('click', function () { closeModal('modal-dai'); });
    el('btn-dai-confirm').addEventListener('click', function () {
      if (el('dai-dontask').checked) ssSet('gostop.dai.skip', true);
      closeModal('modal-dai');
      global.Net.send('die', {});
    });

    // 버리기
    el('btn-discard-cancel').addEventListener('click', function () {
      closeModal('modal-discard');
      global.Game.clearPick();
      if (latest) global.Game.render(latest);
    });
    el('btn-discard-confirm').addEventListener('click', function () {
      if (!pendingDiscard) return;
      closeModal('modal-discard');
      global.Net.send('discard_card', { cardId: pendingDiscard.cardId });
      pendingDiscard = null;
    });

    // 대출
    el('btn-loan-cancel').addEventListener('click', function () { closeModal('modal-loan'); });
    el('btn-loan-confirm').addEventListener('click', function () {
      closeModal('modal-loan');
      global.Net.send('take_loan', {});
    });

    // 게임 종료
    el('btn-endgame').addEventListener('click', function () { openModal('modal-end'); });
    el('btn-end-cancel').addEventListener('click', function () { closeModal('modal-end'); });
    el('btn-end-confirm').addEventListener('click', function () {
      closeModal('modal-end');
      global.Net.send('end_game', {});
    });

    // 결과
    el('btn-next-round').addEventListener('click', function () {
      closeModal('modal-result');
      global.Net.send('next_round', {});
    });
    el('btn-result-close').addEventListener('click', function () { closeModal('modal-result'); });
    el('btn-result-loan').addEventListener('click', function () {
      closeModal('modal-result');
      askLoan();
    });
    el('btn-final-home').addEventListener('click', function () {
      global.Net.send('leave_room', {});
      goHome();
    });

    el('btn-force-fold').addEventListener('click', function () {
      var pid = this.getAttribute('data-pid');
      if (pid) global.Net.send('force_fold', { pid: pid });
    });

    // 효과음
    var sfxBtn = el('btn-sfx');
    function paintSfx() {
      var on = global.Sfx ? global.Sfx.isEnabled() : false;
      sfxBtn.textContent = on ? '🔊' : '🔇';
      sfxBtn.title = on ? '효과음 끄기' : '효과음 켜기';
    }
    sfxBtn.addEventListener('click', function () {
      if (global.Sfx) { global.Sfx.init(); global.Sfx.toggle(); }
      paintSfx();
    });
    paintSfx();

    // Escape closes our own modals (guide.js owns its own)
    doc.addEventListener('keydown', function (ev) {
      if (ev.key !== 'Escape') return;
      ['modal-dai', 'modal-discard', 'modal-loan', 'modal-end'].forEach(function (id) {
        if (!el(id).hidden) closeModal(id);
      });
    });

    // backdrop click closes the light modals
    ['modal-dai', 'modal-discard', 'modal-loan', 'modal-end'].forEach(function (id) {
      el(id).addEventListener('click', function (ev) {
        if (ev.target === this) closeModal(id);
      });
    });
  }

  function goHome() {
    ssSet('gostop.session', null);
    global.Net.setReconnect(null, null);
    closeAllModals();
    global.Game.reset();
    latest = null;
    lastResultRound = -1;
    lastPhase = null;
    me.roomCode = ''; me.token = ''; me.pid = ''; me.isHost = false;
    setMode('create');
    showScreen('home');
  }

  /* ------------------------------------------------------------------ */
  /* boot                                                               */
  /* ------------------------------------------------------------------ */
  function boot() {
    if (global.initGuide) global.initGuide();
    buildCharacterGrid();

    var profile = lsGet('gostop.profile');
    if (profile) {
      if (profile.nickname) {
        el('input-nickname').value = profile.nickname;
        el('nick-count').textContent = String(profile.nickname.length);
      }
      if (profile.character) { me.character = profile.character; }
    }
    refreshCharacterGrid();
    if (me.character) {
      el('char-status').textContent =
        (global.characterName ? global.characterName(me.character) : '') + ' 선택 완료!';
    }

    global.Game.init({
      onAction: function (type) { global.Net.send('bet_action', { action: type }); },
      onDie: askDie,
      onDiscardPick: askDiscard,
      onLoan: askLoan,
      onReaction: function (key) { global.Net.send('reaction', { key: key }); }
    });

    wire();

    // ---- socket ----
    global.Net.on('state', onState);
    global.Net.on('game_error', function (d) {
      var code = d && d.code;
      // The room is gone (server restarted, or everyone left) — drop the stale
      // reconnect token so we stop retrying and just show the start screen.
      if (code === 'no_seat' || code === 'no_room') {
        ssSet('gostop.session', null);
        global.Net.setReconnect(null, null);
        if (!me.pid) { showScreen('home'); return; }
      }
      toast((d && d.message) || '문제가 생겼어요.', 'error');
      if (global.Sfx) global.Sfx.play('error');
    });
    global.Net.on('joined', function (d) {
      me.roomCode = d.roomCode;
      me.token = d.token;
      me.pid = d.pid;
      me.isHost = !!d.isHost;
      ssSet('gostop.session', { roomCode: d.roomCode, token: d.token });
      global.Net.setReconnect(d.roomCode, d.token);
      if (!d.restored) toast('입장했습니다! 방 코드 ' + d.roomCode, 'good');
    });
    global.Net.on('room_info', function (d) {
      joinRoomInfo = (d && d.found) ? d : null;
      refreshCharacterGrid();
      if (d && d.found === false) el('char-status').textContent = '';
    });
    global.Net.on('left', function () { goHome(); });
    global.Net.on('kicked', function () {
      toast('방에서 나가게 되었습니다.', 'error');
      goHome();
    });

    global.Net.connect();

    // ---- resume / invite link ----
    var params = new URLSearchParams(global.location.search || '');
    var invited = (params.get('room') || '').toUpperCase();
    var session = ssGet('gostop.session');

    global.Net.on('net:connect', function () {
      if (session && session.roomCode && session.token && !me.pid) {
        global.Net.setReconnect(session.roomCode, session.token);
        global.Net.send('rejoin', session);
      }
    });

    if (invited) {
      setMode('join');
      el('input-roomcode').value = invited;
      global.setTimeout(requestRoomInfo, 350);
    } else {
      setMode('create');
    }
    showScreen('home');
  }

  if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', boot);
  else boot();
}(window));
