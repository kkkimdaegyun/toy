/* ============================================================
 * guide.js — beginner teaching UI for 숫자 섯다
 * ------------------------------------------------------------
 * Design goal: nobody should have to study the rules first.
 * Exposes on window:
 *   HAND_GUIDE, HAND_GUIDE_GROUPS, PHASE_TIPS,
 *   renderHandGuidePanel(), openGuide(which), closeGuide(), initGuide()
 * No modules, no build step, ES5-safe syntax only.
 * ============================================================ */
(function (global) {
  'use strict';

  var doc = global.document;

  /* ----------------------------------------------------------
   * 1. Data — the complete strength order (23 entries, strongest first)
   * -------------------------------------------------------- */

  var HAND_GUIDE = [
    /* 광땡 — only three combinations exist */
    { key: 'gwang38', name: '38광땡', cards: '3 + 8', group: 'gwang', note: '가장 강한 패' },
    { key: 'gwang18', name: '18광땡', cards: '1 + 8', group: 'gwang', note: '' },
    { key: 'gwang13', name: '13광땡', cards: '1 + 3', group: 'gwang', note: '광땡 중 가장 약함' },

    /* 땡 — a pair */
    { key: 'ttaeng0', name: '장땡', cards: '0 + 0', group: 'ttaeng', note: '0은 장(10) · 가장 강한 땡' },
    { key: 'ttaeng9', name: '9땡', cards: '9 + 9', group: 'ttaeng', note: '' },
    { key: 'ttaeng8', name: '8땡', cards: '8 + 8', group: 'ttaeng', note: '' },
    { key: 'ttaeng7', name: '7땡', cards: '7 + 7', group: 'ttaeng', note: '' },
    { key: 'ttaeng6', name: '6땡', cards: '6 + 6', group: 'ttaeng', note: '' },
    { key: 'ttaeng5', name: '5땡', cards: '5 + 5', group: 'ttaeng', note: '' },
    { key: 'ttaeng4', name: '4땡', cards: '4 + 4', group: 'ttaeng', note: '' },
    { key: 'ttaeng3', name: '3땡', cards: '3 + 3', group: 'ttaeng', note: '' },
    { key: 'ttaeng2', name: '2땡', cards: '2 + 2', group: 'ttaeng', note: '' },
    { key: 'ttaeng1', name: '1땡', cards: '1 + 1', group: 'ttaeng', note: '땡 중 가장 약함' },

    /* 끗 — everything else: (a + b) % 10 */
    { key: 'kkeut9', name: '9끗', cards: '4 + 5', group: 'kkeut', note: '끗 중 가장 강함' },
    { key: 'kkeut8', name: '8끗', cards: '3 + 5', group: 'kkeut', note: '' },
    { key: 'kkeut7', name: '7끗', cards: '9 + 8', group: 'kkeut', note: '9 + 8 = 17 → 7끗' },
    { key: 'kkeut6', name: '6끗', cards: '2 + 4', group: 'kkeut', note: '' },
    { key: 'kkeut5', name: '5끗', cards: '1 + 4', group: 'kkeut', note: '' },
    { key: 'kkeut4', name: '4끗', cards: '6 + 8', group: 'kkeut', note: '6 + 8 = 14 → 4끗' },
    { key: 'kkeut3', name: '3끗', cards: '4 + 9', group: 'kkeut', note: '4 + 9 = 13 → 3끗 (49파토 없음)' },
    { key: 'kkeut2', name: '2끗', cards: '5 + 7', group: 'kkeut', note: '' },
    { key: 'kkeut1', name: '1끗', cards: '4 + 7', group: 'kkeut', note: '' },
    { key: 'kkeut0', name: '0끗', cards: '2 + 8', group: 'kkeut', note: '가장 약한 패' }
  ];

  var HAND_GUIDE_GROUPS = [
    {
      key: 'gwang',
      label: '광땡',
      desc: '3+8 · 1+8 · 1+3 세 조합만 광땡입니다. 가장 강해요.'
    },
    {
      key: 'ttaeng',
      label: '땡',
      desc: '같은 숫자 두 장. 0 + 0 은 장땡으로 가장 강한 땡입니다.'
    },
    {
      key: 'kkeut',
      label: '끗',
      desc: '나머지는 두 숫자를 더해 일의 자리로 정합니다.'
    }
  ];

  var PHASE_TIPS = {
    LOBBY: '방장이 시작하면 바로 게임이 시작됩니다. 족보는 위쪽 버튼에서 언제든 볼 수 있어요.',
    ANTE: '참가비를 걷는 중입니다...',
    DEAL2: '카드 2장을 받았습니다. 내 족보는 화면 아래에서 바로 확인할 수 있어요.',
    BET1: '카드 2장을 확인하고 베팅해보세요. 패가 마음에 안 들면 바로 다이해도 됩니다.',
    DEAL3: '세 번째 카드를 나눠주는 중...',
    DISCARD: '3장 중 1장을 버리세요. 카드를 눌러보면 완성 족보를 미리 보여드립니다.',
    BET2: '마지막 베팅입니다. 여기서 결정됩니다!',
    SHOWDOWN: '카드 공개!',
    ROUND_END: '이번 판 결과입니다. 방장이 다음 판을 시작할 수 있어요.',
    FINISHED: '게임이 끝났습니다. 최종 순위를 확인해보세요.'
  };

  /* ----------------------------------------------------------
   * 2. Small helpers
   * -------------------------------------------------------- */

  function esc(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function entriesOf(groupKey) {
    var out = [];
    var i;
    for (i = 0; i < HAND_GUIDE.length; i++) {
      if (HAND_GUIDE[i].group === groupKey) out.push(HAND_GUIDE[i]);
    }
    return out;
  }

  function groupMeta(groupKey) {
    var i;
    for (i = 0; i < HAND_GUIDE_GROUPS.length; i++) {
      if (HAND_GUIDE_GROUPS[i].key === groupKey) return HAND_GUIDE_GROUPS[i];
    }
    return { key: groupKey, label: groupKey, desc: '' };
  }

  /* 끗 entries always show a worked example, others show the plain combo. */
  function comboText(entry) {
    return entry.group === 'kkeut' ? '예: ' + entry.cards : entry.cards;
  }

  function closestWithAttr(node, attr) {
    while (node && node !== doc) {
      if (node.nodeType === 1 && node.hasAttribute && node.hasAttribute(attr)) return node;
      node = node.parentNode;
    }
    return null;
  }

  /* ----------------------------------------------------------
   * 3. The always-visible compact side panel
   * -------------------------------------------------------- */

  function divider(label) {
    return '<div class="gd-divider"><span class="gd-divider__label">' + esc(label) + '</span></div>';
  }

  function panelRow(entry) {
    return '' +
      '<li class="gd-row gd-row--' + esc(entry.group) + '">' +
        '<span class="gd-row__name">' + esc(entry.name) + '</span>' +
        '<span class="gd-row__cards">' + esc(comboText(entry)) + '</span>' +
      '</li>';
  }

  function renderHandGuidePanel() {
    var html = [];
    var g;
    var i;
    var list;
    var j;

    html.push('<aside class="gd-panel" id="gdHandPanel" aria-label="족보 요약">');
    html.push(
      '<div class="gd-panel__head">' +
        '<span class="gd-panel__title">족보</span>' +
        '<span class="gd-panel__hint">위가 더 강함 ↑</span>' +
      '</div>'
    );
    html.push('<div class="gd-panel__body">');
    html.push('<ul class="gd-panel__list">');

    for (i = 0; i < HAND_GUIDE_GROUPS.length; i++) {
      g = HAND_GUIDE_GROUPS[i];
      html.push('<li class="gd-panel__group">' + divider(g.label) + '</li>');
      list = entriesOf(g.key);
      for (j = 0; j < list.length; j++) {
        html.push(panelRow(list[j]));
      }
    }

    html.push('</ul>');
    html.push('<p class="gd-panel__note">0 은 <b>장(10)</b> · 49파토는 없어요</p>');
    html.push('</div>');
    html.push(
      '<div class="gd-panel__foot">' +
        '<button type="button" class="gd-btn gd-btn--ghost" data-guide-open="hands">족보 크게 보기</button>' +
      '</div>'
    );
    html.push('</aside>');

    return html.join('');
  }

  /* ----------------------------------------------------------
   * 4. Modal contents
   * -------------------------------------------------------- */

  function handItem(entry) {
    var note = entry.note
      ? '<span class="gd-hand__note">' + esc(entry.note) + '</span>'
      : '';
    return '' +
      '<li class="gd-hand gd-hand--' + esc(entry.group) + '">' +
        '<span class="gd-hand__name">' + esc(entry.name) + '</span>' +
        '<span class="gd-hand__cards">' + esc(comboText(entry)) + '</span>' +
        note +
      '</li>';
  }

  function handSection(groupKey) {
    var meta = groupMeta(groupKey);
    var list = entriesOf(groupKey);
    var html = [];
    var i;

    html.push('<section class="gd-sec gd-sec--' + esc(groupKey) + '">');
    html.push(
      '<div class="gd-sec__head">' +
        '<span class="gd-sec__label">' + esc(meta.label) + '</span>' +
        '<span class="gd-sec__desc">' + esc(meta.desc) + '</span>' +
      '</div>'
    );
    html.push('<ul class="gd-hands">');
    for (i = 0; i < list.length; i++) html.push(handItem(list[i]));
    html.push('</ul>');
    html.push('</section>');

    return html.join('');
  }

  function bodyHands() {
    var html = [];

    html.push(
      '<div class="gd-banner">' +
        '<p class="gd-banner__item"><b>0</b> 은 <b>장(10)</b> 을 의미합니다.</p>' +
        '<p class="gd-banner__item">이 게임에는 <b>49파토가 없습니다.</b> 4 + 9 는 항상 <b>3끗</b> 입니다.</p>' +
      '</div>'
    );

    html.push('<p class="gd-scale gd-scale--top">가장 강함 ↑</p>');
    html.push(handSection('gwang'));
    html.push(handSection('ttaeng'));
    html.push(handSection('kkeut'));
    html.push('<p class="gd-scale gd-scale--bottom">↓ 가장 약함</p>');

    html.push(
      '<div class="gd-explain">' +
        '<p class="gd-explain__row">' +
          '<b class="gd-explain__term gd-explain__term--gwang">광땡</b>' +
          '<span>가장 강합니다. 38 &gt; 18 &gt; 13</span>' +
        '</p>' +
        '<p class="gd-explain__row">' +
          '<b class="gd-explain__term gd-explain__term--ttaeng">땡</b>' +
          '<span>같은 숫자 두 장. 0 + 0 은 장땡으로 가장 강한 땡입니다.</span>' +
        '</p>' +
        '<p class="gd-explain__row">' +
          '<b class="gd-explain__term gd-explain__term--kkeut">끗</b>' +
          '<span>나머지는 두 숫자를 더해 일의 자리로 정합니다. 예) 4 + 9 = 13 → 3끗</span>' +
        '</p>' +
      '</div>'
    );

    html.push(
      '<div class="gd-tip">' +
        '<b class="gd-tip__title">이게 전부예요</b>' +
        '<p>알리 · 독사 · 구삥 · 장삥 · 장사 · 세륙 · 암행어사 · 멍텅구리 · 구사 같은 특수 족보는 ' +
        '이 게임에 <b>없습니다.</b> 위의 23가지가 전부입니다.</p>' +
      '</div>'
    );

    return html.join('');
  }

  var HOWTO_STEPS = [
    { label: '참가비', text: '모두 10,000씩 내고 판을 엽니다.' },
    { label: '카드 2장', text: '각자 카드 두 장을 받습니다.' },
    { label: '1차 베팅', text: '두 장을 보고 첫 베팅을 합니다.' },
    { label: '카드 1장 추가', text: '세 번째 카드를 한 장 더 받습니다.' },
    { label: '3장 중 1장 버리기', text: '가장 좋은 두 장만 남깁니다.' },
    { label: '2차 베팅', text: '완성된 패로 마지막 베팅을 합니다.' },
    { label: '카드 공개', text: '남아 있는 사람들이 패를 보여줍니다.' },
    { label: '승자 결정', text: '족보가 가장 강한 사람이 이깁니다.' },
    { label: '판돈 지급', text: '쌓인 판돈을 승자가 모두 가져갑니다.' },
    { label: '다음 판', text: '방장이 누르면 새 판이 시작됩니다.' }
  ];

  var HOWTO_CARDS = [
    {
      title: '칩',
      text: '모두 300,000 가상 칩으로 시작하고, 베팅은 10,000 단위로 움직입니다. 실제 돈이 아닌 가상 칩이에요.'
    },
    {
      title: '참가비',
      text: '매 판 시작할 때 모두 10,000씩 냅니다. 이 돈이 첫 판돈이 됩니다.'
    },
    {
      title: '다이',
      text: '이번 판만 포기합니다. 방에서 나가는 게 아니고 계속 구경할 수 있어요. 지금까지 넣은 칩은 판돈에 남습니다. 패가 나쁘면 내 차례가 오기 전에 바로 눌러도 됩니다!'
    },
    {
      title: '버리기',
      text: '세 번째 카드를 받으면 3장 중 1장을 버립니다. 어떤 카드를 버리면 어떤 족보가 되는지 미리 보여드려요.'
    },
    {
      title: '대출',
      text: '칩이 부족하면 은행(?) 찬스. 100,000을 빌리면 선이자 10%를 떼고 90,000을 받습니다. 최대 2번까지 가능하고, 두 번째 대출을 받으면 최종 순위에서 최하위 그룹이 됩니다.'
    }
  ];

  function bodyHowto() {
    var html = [];
    var i;

    html.push('<p class="gd-lead">한 판은 이렇게 흘러갑니다. 순서대로 따라오기만 하면 돼요.</p>');

    html.push('<ol class="gd-flow">');
    for (i = 0; i < HOWTO_STEPS.length; i++) {
      html.push(
        '<li class="gd-flow__step">' +
          '<div class="gd-flow__box">' +
            '<span class="gd-flow__top">' +
              '<span class="gd-flow__num">' + (i + 1) + '</span>' +
              '<span class="gd-flow__label">' + esc(HOWTO_STEPS[i].label) + '</span>' +
            '</span>' +
            '<span class="gd-flow__text">' + esc(HOWTO_STEPS[i].text) + '</span>' +
          '</div>' +
        '</li>'
      );
    }
    html.push('</ol>');

    html.push('<div class="gd-cards">');
    for (i = 0; i < HOWTO_CARDS.length; i++) {
      html.push(
        '<div class="gd-card">' +
          '<b class="gd-card__title">' + esc(HOWTO_CARDS[i].title) + '</b>' +
          '<p class="gd-card__text">' + esc(HOWTO_CARDS[i].text) + '</p>' +
        '</div>'
      );
    }
    html.push('</div>');

    html.push(
      '<div class="gd-tip">' +
        '<p>규칙을 다 외울 필요 없어요. 화면이 내 족보와 필요한 금액을 항상 알려드립니다.</p>' +
      '</div>'
    );

    return html.join('');
  }

  var BETTING_TERMS = [
    { term: '체크', desc: '추가 칩 없이 넘깁니다. 아무도 베팅하지 않았을 때만 가능합니다.' },
    { term: '베팅', desc: '처음으로 판돈을 올립니다. (기본 10,000)' },
    { term: '콜', desc: '현재 베팅 금액을 맞춥니다.' },
    { term: '레이즈', desc: '조금 더 올립니다. (기본 +10,000, 한 라운드에 최대 3번)' },
    { term: '다이', desc: '이번 판만 포기합니다. 넣은 칩은 판돈에 남고, 내 카드는 끝까지 공개되지 않습니다.' }
  ];

  function bodyBetting() {
    var html = [];
    var i;

    html.push('<p class="gd-lead">베팅 버튼은 다섯 가지뿐입니다.</p>');
    html.push('<dl class="gd-dl">');
    for (i = 0; i < BETTING_TERMS.length; i++) {
      html.push(
        '<div class="gd-def">' +
          '<dt class="gd-def__term">' + esc(BETTING_TERMS[i].term) + '</dt>' +
          '<dd class="gd-def__desc">' + esc(BETTING_TERMS[i].desc) + '</dd>' +
        '</div>'
      );
    }
    html.push('</dl>');

    html.push(
      '<div class="gd-tip">' +
        '<b class="gd-tip__title">걱정 마세요</b>' +
        '<p>버튼에는 항상 실제로 내는 금액이 적혀 있습니다. 계산은 저희가 할게요.</p>' +
      '</div>'
    );

    return html.join('');
  }

  var MODALS = {
    hands: {
      title: '족보 한눈에 보기',
      body: bodyHands,
      links: [{ which: 'howto', label: '게임 방법 보기' }]
    },
    howto: {
      title: '게임 방법',
      body: bodyHowto,
      links: [
        { which: 'hands', label: '족보 보기' },
        { which: 'betting', label: '베팅 도움말' }
      ]
    },
    betting: {
      title: '베팅 도움말',
      body: bodyBetting,
      links: [{ which: 'hands', label: '족보 보기' }]
    }
  };

  function modalHtml(which) {
    var spec = MODALS[which];
    var html = [];
    var i;

    html.push(
      '<div class="gd-modal" role="dialog" aria-modal="true" aria-labelledby="gdModalTitle">'
    );
    html.push(
      '<div class="gd-modal__head">' +
        '<h2 class="gd-modal__title" id="gdModalTitle">' + esc(spec.title) + '</h2>' +
        '<button type="button" class="gd-btn gd-btn--ghost gd-modal__close" ' +
          'data-guide-close="1" aria-label="닫기">닫기</button>' +
      '</div>'
    );
    html.push('<div class="gd-modal__body">' + spec.body() + '</div>');

    html.push('<div class="gd-modal__foot">');
    for (i = 0; i < spec.links.length; i++) {
      html.push(
        '<button type="button" class="gd-btn gd-btn--ghost" data-guide-open="' +
          esc(spec.links[i].which) + '">' + esc(spec.links[i].label) + '</button>'
      );
    }
    html.push('<button type="button" class="gd-btn" data-guide-close="1">닫기</button>');
    html.push('</div>');

    html.push('</div>');
    return html.join('');
  }

  /* ----------------------------------------------------------
   * 5. Modal open / close
   * -------------------------------------------------------- */

  var ROOT_ID = 'gdGuideRoot';
  var lastFocused = null;
  var currentModal = null;

  function getRoot(createIfMissing) {
    var root;
    if (!doc || !doc.body) return null;
    root = doc.getElementById(ROOT_ID);
    if (!root && createIfMissing) {
      root = doc.createElement('div');
      root.id = ROOT_ID;
      root.className = 'gd-modal-backdrop';
      root.setAttribute('hidden', 'hidden');
      doc.body.appendChild(root);
    }
    return root || null;
  }

  function setModalOpenClass(on) {
    var el = doc && doc.documentElement;
    var parts;
    var out = [];
    var i;
    if (!el) return;
    parts = String(el.className || '').split(/\s+/);
    for (i = 0; i < parts.length; i++) {
      if (parts[i] && parts[i] !== 'gd-modal-open') out.push(parts[i]);
    }
    if (on) out.push('gd-modal-open');
    el.className = out.join(' ');
  }

  function focusables(scope) {
    var nodes = scope.querySelectorAll(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    var out = [];
    var i;
    for (i = 0; i < nodes.length; i++) {
      if (!nodes[i].disabled && nodes[i].offsetParent !== null) out.push(nodes[i]);
    }
    return out;
  }

  function hasModal(which) {
    return typeof which === 'string' &&
      Object.prototype.hasOwnProperty.call(MODALS, which);
  }

  function openGuide(which) {
    var key = hasModal(which) ? which : 'hands';
    var root = getRoot(true);
    var first;

    if (!root) return false;

    ensureListeners();

    if (!currentModal && doc.activeElement) lastFocused = doc.activeElement;

    root.innerHTML = modalHtml(key);
    root.removeAttribute('hidden');
    setModalOpenClass(true);
    currentModal = key;

    first = root.querySelector('.gd-modal__close');
    if (first && first.focus) {
      try { first.focus(); } catch (e) {}
    }
    return true;
  }

  function closeGuide() {
    var root = getRoot(false);

    currentModal = null;

    if (root) {
      root.setAttribute('hidden', 'hidden');
      root.innerHTML = '';
    }
    setModalOpenClass(false);
    if (lastFocused && lastFocused.focus) {
      try { lastFocused.focus(); } catch (e2) {}
    }
    lastFocused = null;
    return true;
  }

  function isOpen() {
    var root = getRoot(false);
    return !!(root && !root.hasAttribute('hidden'));
  }

  /* ----------------------------------------------------------
   * 6. Delegated listeners (installed once)
   * -------------------------------------------------------- */

  function onDocumentClick(ev) {
    var target = ev.target || ev.srcElement;
    var opener = closestWithAttr(target, 'data-guide-open');
    var closer;
    var root;

    if (opener) {
      if (ev.preventDefault) ev.preventDefault();
      openGuide(opener.getAttribute('data-guide-open'));
      return;
    }

    closer = closestWithAttr(target, 'data-guide-close');
    if (closer) {
      if (ev.preventDefault) ev.preventDefault();
      closeGuide();
      return;
    }

    /* backdrop click (only when the backdrop itself was hit) */
    root = getRoot(false);
    if (root && target === root && isOpen()) closeGuide();
  }

  function onDocumentKeydown(ev) {
    var key = ev.key;
    var root;
    var list;
    var firstEl;
    var lastEl;

    if (!isOpen()) return;

    if (key === 'Escape' || key === 'Esc' || ev.keyCode === 27) {
      if (ev.preventDefault) ev.preventDefault();
      closeGuide();
      return;
    }

    /* keep tabbing inside the dialog */
    if (key === 'Tab' || ev.keyCode === 9) {
      root = getRoot(false);
      if (!root) return;
      list = focusables(root);
      if (!list.length) return;
      firstEl = list[0];
      lastEl = list[list.length - 1];
      if (ev.shiftKey && doc.activeElement === firstEl) {
        if (ev.preventDefault) ev.preventDefault();
        lastEl.focus();
      } else if (!ev.shiftKey && doc.activeElement === lastEl) {
        if (ev.preventDefault) ev.preventDefault();
        firstEl.focus();
      }
    }
  }

  var listenersInstalled = false;

  function ensureListeners() {
    if (listenersInstalled || !doc || !doc.addEventListener) return;
    listenersInstalled = true;
    doc.addEventListener('click', onDocumentClick, false);
    doc.addEventListener('keydown', onDocumentKeydown, false);
  }

  /* Safe to call any number of times. */
  function initGuide() {
    ensureListeners();
    return true;
  }

  /* ----------------------------------------------------------
   * 7. Exports
   * -------------------------------------------------------- */

  global.HAND_GUIDE = HAND_GUIDE;
  global.HAND_GUIDE_GROUPS = HAND_GUIDE_GROUPS;
  global.PHASE_TIPS = PHASE_TIPS;
  global.renderHandGuidePanel = renderHandGuidePanel;
  global.openGuide = openGuide;
  global.closeGuide = closeGuide;
  global.initGuide = initGuide;

  /* The [data-guide-open] buttons already exist in the served HTML, so wire the
     delegated listeners at load time instead of waiting for a caller.
     initGuide() stays exported and is idempotent. */
  initGuide();
})(window);
