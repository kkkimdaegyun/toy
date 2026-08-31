(function () {
  "use strict";

  const AVATARS = [
    ["bear", "곰"], ["cat", "고양이"], ["dog", "강아지"], ["rabbit", "토끼"],
    ["chick", "병아리"], ["penguin", "펭귄"], ["robot", "로봇"], ["ghost", "유령"]
  ];
  const REACTIONS = ["ㅋㅋ", "헉", "아깝다!", "뭐야!", "굿", "😎"];
  const CLIENT_SLOT = new URLSearchParams(location.search).get("client") || "default";
  const STORAGE_KEY = `fruitBellSession:${CLIENT_SLOT}`;
  const TUTORIAL_KEY = "fruitBellTutorialSeen";

  const $ = (selector) => document.querySelector(selector);
  const homeScreen = $("#homeScreen");
  const lobbyScreen = $("#lobbyScreen");
  const gameScreen = $("#gameScreen");
  const socket = io();

  let roomState = null;
  let roomStateReceivedAt = 0;
  let session = readSession();
  let selectedAvatar = session?.avatar || "bear";
  let revealTimer = null;
  let pendingRevealId = null;
  let announcementTimer = null;

  function readSession() {
    try {
      const value = JSON.parse(localStorage.getItem(STORAGE_KEY));
      return value && value.room_code && value.reconnect_token ? value : null;
    } catch (_) {
      return null;
    }
  }

  function saveSession(value) {
    session = value;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
  }

  function clearSession() {
    session = null;
    roomState = null;
    localStorage.removeItem(STORAGE_KEY);
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>'"]/g, (character) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
    })[character]);
  }

  function avatarHtml(avatar, size) {
    const safe = AVATARS.some(([key]) => key === avatar) ? avatar : "bear";
    return `<span class="avatar-icon ${safe} ${size === "large" ? "large" : ""}" aria-hidden="true">
      <i class="ear left"></i><i class="ear right"></i>
      <span class="face"><i class="eye left"></i><i class="eye right"></i><i class="mouth"></i></span>
    </span>`;
  }

  function fruitCardHtml(card, animate) {
    if (!card) return "";
    const objects = Array.from({ length: card.count }, () => '<i class="fruit-object"></i>').join("");
    const names = { strawberry: "딸기", banana: "바나나", lime: "라임", plum: "자두" };
    return `<div class="fruit-card count-${card.count} ${animate ? "flip-in" : ""}" data-fruit="${card.fruit}" data-card-id="${escapeHtml(card.id)}" aria-label="${names[card.fruit]} 과일 카드">
      <div class="fruit-layout">${objects}</div>
    </div>`;
  }

  function setConnection(status) {
    const pill = $("#connectionPill");
    pill.className = "connection-pill";
    if (status === "connected") {
      pill.querySelector("span").textContent = "연결됨";
    } else if (status === "offline") {
      pill.classList.add("is-offline");
      pill.querySelector("span").textContent = "연결 끊김";
    } else {
      pill.classList.add("is-connecting");
      pill.querySelector("span").textContent = "연결 중";
    }
  }

  function showScreen(name) {
    homeScreen.classList.toggle("is-hidden", name !== "home");
    lobbyScreen.classList.toggle("is-hidden", name !== "lobby");
    gameScreen.classList.toggle("is-hidden", name !== "game");
  }

  function toast(message, type) {
    if (!message) return;
    const node = document.createElement("div");
    node.className = `toast ${type || ""}`;
    node.textContent = message;
    $("#toastStack").appendChild(node);
    setTimeout(() => node.remove(), 2800);
  }

  function showModal(dialog) {
    if (dialog && !dialog.open) dialog.showModal();
  }

  function closeModal(dialog) {
    if (dialog?.open) dialog.close();
  }

  function myPlayer() {
    if (!roomState || !session) return null;
    return roomState.players.find((player) => player.id === session.player_id) || null;
  }

  function playerById(playerId) {
    return roomState?.players.find((player) => player.id === playerId) || null;
  }

  function remainingRevealWait() {
    if (!roomState) return 0;
    return Math.max(0, roomState.reveal_wait_ms - (performance.now() - roomStateReceivedAt));
  }

  function isGamePlaying() {
    return roomState?.state === "PLAYING";
  }

  function canRing() {
    const me = myPlayer();
    return socket.connected && isGamePlaying() && me && me.connected && !me.eliminated && me.remaining_card_count > 0;
  }

  function canReveal() {
    const me = myPlayer();
    return Boolean(
      socket.connected && isGamePlaying() && me && me.connected && !me.eliminated &&
      !roomState.reveal_blocked_for_bell &&
      roomState.current_player_id === me.id && remainingRevealWait() <= 0
    );
  }

  function renderAvatarSelectors() {
    $("#avatarGrid").innerHTML = AVATARS.map(([key, label]) => `
      <button class="avatar-option ${key === selectedAvatar ? "selected" : ""}" type="button" data-avatar="${key}" aria-label="${label} 캐릭터 선택">
        ${avatarHtml(key)}<span>${label}</span>
      </button>`).join("");
    $("#lobbyAvatarList").innerHTML = AVATARS.map(([key, label]) => `
      <button class="avatar-mini ${key === (myPlayer()?.avatar || selectedAvatar) ? "selected" : ""}" type="button" data-avatar="${key}" aria-label="${label} 캐릭터 선택">${avatarHtml(key)}</button>`).join("");
  }

  function renderLobby() {
    showScreen("lobby");
    closeModal($("#resultModal"));
    const me = myPlayer();
    if (!me) return;
    selectedAvatar = me.avatar;
    $("#roomCodeDisplay").textContent = roomState.room_code;
    $("#lobbyCapacity").textContent = `${roomState.player_count} / 최대 4명`;
    const invite = `${location.origin}/?room=${encodeURIComponent(roomState.room_code)}`;
    $("#inviteLink").textContent = invite;

    const slots = [...roomState.players];
    while (slots.length < 4) slots.push(null);
    $("#lobbyPlayers").innerHTML = slots.map((player, index) => {
      if (!player) return `<div class="lobby-player empty"><span class="empty-seat">＋</span><strong>${index + 1}번째 자리</strong><span class="ready-status">기다리는 중</span></div>`;
      let status = player.is_host ? "방장" : (player.ready ? "준비 완료" : "준비 전");
      if (!player.connected) status = "연결 끊김";
      return `<div class="lobby-player">
        ${player.is_host ? '<span class="host-crown">방장</span>' : ""}
        ${avatarHtml(player.avatar, "large")}
        <strong>${escapeHtml(player.nickname)}${player.id === me.id ? " (나)" : ""}</strong>
        <span class="ready-status ${player.ready ? "ready" : ""} ${!player.connected ? "disconnect-label" : ""}">${player.ready && !player.is_host ? "✓ " : ""}${status}</span>
      </div>`;
    }).join("");

    const action = $("#lobbyAction");
    if (me.is_host) {
      let waitingCopy = "한 명만 더 들어오면 시작할 수 있어요.";
      if (roomState.can_start) waitingCopy = "참가한 모두가 준비됐어요. 시작해볼까요?";
      else if (roomState.player_count >= roomState.min_players) waitingCopy = "참가한 동료들의 준비를 기다리고 있어요.";
      action.innerHTML = `<p class="waiting-copy">${waitingCopy}</p>
        <button class="primary-button" id="startGameButton" type="button" ${roomState.can_start ? "" : "disabled"}>게임 시작</button>`;
      $("#startGameButton").addEventListener("click", () => socket.emit("start_game"));
    } else {
      action.innerHTML = `<p class="waiting-copy">${me.ready ? "준비 완료! 방장이 시작하기를 기다려주세요." : "준비되면 버튼을 눌러주세요."}</p>
        <button class="${me.ready ? "secondary-button" : "primary-button"}" id="readyButton" type="button">${me.ready ? "준비 취소" : "준비"}</button>`;
      $("#readyButton").addEventListener("click", () => socket.emit("set_ready", { ready: !me.ready }));
    }
    renderAvatarSelectors();
  }

  function relativePosition(playerSeat, localSeat) {
    const offset = (playerSeat - localSeat + 4) % 4;
    return ["bottom", "left", "top", "right"][offset];
  }

  function playerSeatHtml(player, me) {
    const position = relativePosition(player.seat, me.seat);
    const isTurn = roomState.current_player_id === player.id;
    const status = !player.connected ? "연결 끊김" : player.eliminated ? "관전 중" : isTurn ? (player.id === me.id ? "내 차례" : "카드 차례") : "게임 중";
    const clickable = player.id === me.id && canReveal();
    const cardAnimate = player.visible_card && player.visible_card.id === pendingRevealId;
    const draw = player.remaining_card_count > 0
      ? `<button class="draw-pile" type="button" data-reveal="${player.id}" aria-label="${player.id === me.id ? "내 카드 뒤집기" : "상대의 숨은 카드 더미"}" ${clickable ? "" : "disabled"}></button>`
      : '<div class="empty-pile">카드 없음</div>';
    const face = player.visible_card
      ? `${fruitCardHtml(player.visible_card, cardAnimate)}${player.face_up_count > 1 ? `<span class="face-count">${player.face_up_count}장</span>` : ""}`
      : "";
    return `<article class="player-seat position-${position} ${isTurn ? "is-turn" : ""} ${player.id === me.id ? "is-local" : ""} ${player.eliminated ? "is-eliminated" : ""} ${!player.connected ? "is-disconnected" : ""}" data-player-id="${player.id}">
      <div class="seat-meta">
        <span class="seat-avatar">${avatarHtml(player.avatar)}</span>
        <div class="seat-name"><strong>${escapeHtml(player.nickname)}${player.is_host ? " · 방장" : ""}</strong><span>${status}</span></div>
        <div class="seat-count"><span>남은 카드</span><b>${player.remaining_card_count}</b></div>
      </div>
      <div class="seat-cards">${draw}<div class="face-slot ${face ? "" : "empty"}">${face}</div></div>
    </article>`;
  }

  function renderGame() {
    showScreen("game");
    const me = myPlayer();
    if (!me) return;
    $("#gameRoomCode").textContent = roomState.room_code;
    $("#versionTag").textContent = `판 ${roomState.board_version}`;
    $("#seatLayer").innerHTML = roomState.players.map((player) => playerSeatHtml(player, me)).join("");
    // A server reveal event is consumed once, never replayed by UI timers.
    pendingRevealId = null;
    updateGameControls();
    $("#gameLog").innerHTML = [...roomState.logs].reverse().map((line) => `<li>${escapeHtml(line)}</li>`).join("");
    if (roomState.state === "GAME_OVER") renderResult();
  }

  function updateGameControls() {
    const me = myPlayer();
    if (!me || roomState.state === "LOBBY") return;
    const current = playerById(roomState.current_player_id);
    const paused = roomState.state === "PAUSED_DISCONNECT";
    const awaitingBell = roomState.reveal_blocked_for_bell;
    $("#pauseCover").classList.toggle("is-hidden", !paused);
    if (paused) $("#pauseTitle").textContent = `${roomState.waiting_for_name || "플레이어"}님의 재접속을 기다리는 중...`;

    const wait = remainingRevealWait();
    const mine = current?.id === me.id;
    let turnText = current ? `${current.nickname}님의 차례` : "게임을 마쳤어요.";
    if (paused) turnText = "게임이 잠시 멈췄어요.";
    else if (awaitingBell) turnText = "종을 친 뒤 다음 카드를 뒤집을 수 있어요.";
    else if (mine) turnText = wait > 0 ? "내 차례 · 카드가 보이는 중" : "내 차례! 카드를 뒤집으세요.";
    $("#turnBanner").textContent = turnText;
    $("#turnEyebrow").textContent = awaitingBell ? "종 치기" : mine ? "내 차례" : "차례 안내";

    let controlTitle = current ? `${escapeHtml(current.nickname)}님을 기다리는 중` : "게임 결과를 확인하세요.";
    if (me.eliminated) controlTitle = "카드를 모두 사용했습니다. 관전 중이에요.";
    else if (paused) controlTitle = "모두 다시 연결되면 이어집니다.";
    else if (awaitingBell) controlTitle = "먼저 종을 쳐주세요. 공개 카드는 그대로 유지됩니다.";
    else if (mine) controlTitle = wait > 0 ? "잠깐, 새 카드가 모두에게 보이는 중이에요." : "카드 1장을 뒤집으세요.";
    $("#turnTitle").textContent = controlTitle;
    $("#revealButton").disabled = !canReveal();
    const localDeck = document.querySelector(".player-seat.is-local .draw-pile");
    if (localDeck) localDeck.disabled = !canReveal();
    $("#bellButton").disabled = !canRing();

    clearTimeout(revealTimer);
    if (mine && !awaitingBell && wait > 0 && roomState.state === "PLAYING") {
      // Only update controls: rebuilding seats here restarts card animations.
      revealTimer = setTimeout(updateGameControls, wait + 20);
    }
  }

  function renderResult() {
    const winner = playerById(roomState.winner_id);
    if (!winner) return;
    $("#winnerAvatar").innerHTML = avatarHtml(winner.avatar, "large");
    $("#winnerTitle").textContent = `${winner.nickname}님 승리!`;
    $("#winnerCards").textContent = `남은 카드 ${winner.remaining_card_count}장`;
    const me = myPlayer();
    const isHost = me?.is_host;
    $("#resultActions").innerHTML = `
      <button class="primary-button" id="rematchButton" type="button" ${isHost ? "" : "disabled"}>다시 하기</button>
      <button class="secondary-button" id="lobbyReturnButton" type="button" ${isHost ? "" : "disabled"}>방으로 돌아가기</button>
      ${isHost ? "" : '<p class="waiting-copy" style="grid-column:1/-1">방장의 선택을 기다리고 있어요.</p>'}`;
    if (isHost) {
      $("#rematchButton").addEventListener("click", () => { closeModal($("#resultModal")); socket.emit("request_rematch"); });
      $("#lobbyReturnButton").addEventListener("click", () => { closeModal($("#resultModal")); socket.emit("return_to_lobby"); });
    }
    buildConfetti();
    showModal($("#resultModal"));
  }

  function renderState() {
    if (!roomState) {
      showScreen("home");
      return;
    }
    if (roomState.state === "LOBBY") renderLobby();
    else renderGame();
  }

  function buildConfetti() {
    const colors = ["#f4773c", "#f1c342", "#63a96f", "#7b58a1", "#df4b56"];
    $("#confetti").innerHTML = Array.from({ length: 28 }, (_, index) =>
      `<i style="left:${(index * 37) % 100}%;background:${colors[index % colors.length]};animation-delay:${(index % 8) * .16}s;transform:rotate(${index * 21}deg)"></i>`
    ).join("");
  }

  function showAnnouncement(result) {
    const player = playerById(result.player_id);
    if (!player) return;
    const node = $("#bellAnnouncement");
    clearTimeout(announcementTimer);
    node.className = `bell-announcement ${result.status === "wrong" ? "wrong" : ""}`;
    if (result.status === "correct") {
      node.innerHTML = `<strong>땡!</strong><span>${escapeHtml(player.nickname)}님이 가장 빨랐습니다!</span><small>공개 카드 ${result.collected_count}장을 가져갑니다.</small>`;
      $("#bellButton").classList.add("is-correct");
      document.querySelector(`[data-player-id="${player.id}"]`)?.classList.add("winner-pulse");
    } else {
      node.innerHTML = `<strong>앗! 잘못 눌렀어요!</strong><span>${escapeHtml(player.nickname)}님 오답!</span><small>다른 플레이어에게 카드 ${result.transfer_count}장을 줍니다.</small>`;
      document.querySelector(`[data-player-id="${player.id}"]`)?.classList.add("wrong-shake");
    }
    node.classList.remove("is-hidden");
    announcementTimer = setTimeout(() => {
      node.classList.add("is-hidden");
      $("#bellButton").classList.remove("is-correct");
    }, 1150);
  }

  function showTutorialOnce() {
    if (localStorage.getItem(TUTORIAL_KEY) === "yes") return;
    localStorage.setItem(TUTORIAL_KEY, "yes");
    setTimeout(() => showModal($("#tutorialModal")), 500);
  }

  function attemptReveal() {
    if (canReveal()) socket.emit("reveal_card");
  }

  function attemptRing() {
    if (!canRing()) return;
    const bell = $("#bellButton");
    bell.classList.remove("is-pressed");
    void bell.offsetWidth;
    bell.classList.add("is-pressed");
    setTimeout(() => bell.classList.remove("is-pressed"), 190);
    socket.emit("ring_bell");
  }

  function validateIdentity() {
    const nickname = $("#nicknameInput").value.trim();
    if (!nickname) {
      toast("닉네임을 입력해주세요.", "error");
      $("#nicknameInput").focus();
      return null;
    }
    if (nickname.length > 12) {
      toast("닉네임은 12자까지 입력할 수 있어요.", "error");
      return null;
    }
    return { nickname, avatar: selectedAvatar };
  }

  socket.on("connect", () => {
    setConnection("connected");
    if (session) socket.emit("reconnect_player", { room_code: session.room_code, reconnect_token: session.reconnect_token });
    renderState();
  });
  socket.on("disconnect", () => { setConnection("offline"); renderState(); });
  socket.on("connect_error", () => setConnection("offline"));

  socket.on("session_established", (data) => {
    saveSession(data);
    selectedAvatar = data.avatar;
    const url = new URL(location.href);
    url.searchParams.set("room", data.room_code);
    history.replaceState(null, "", url);
  });

  socket.on("reconnect_result", (data) => {
    if (data.ok) toast(data.message, "success");
    else {
      clearSession();
      renderState();
    }
  });

  socket.on("room_state", (data) => {
    roomState = data;
    roomStateReceivedAt = performance.now();
    renderState();
  });

  socket.on("game_started", (data) => {
    const dealer = playerById(data.dealer_id);
    const first = playerById(data.first_player_id);
    if (dealer && first) toast(`이번 게임 카드 배분: ${dealer.nickname}님 · 첫 번째 차례: ${first.nickname}님`, "success");
    showTutorialOnce();
    closeModal($("#resultModal"));
  });

  socket.on("card_revealed", (data) => {
    pendingRevealId = data.card.id;
  });

  socket.on("bell_result", (data) => showAnnouncement(data));
  socket.on("bell_feedback", (data) => toast(data.message));
  socket.on("error_message", (data) => toast(data.message, "error"));

  socket.on("reaction", (data) => {
    const seat = document.querySelector(`[data-player-id="${data.player_id}"]`);
    if (!seat) return;
    seat.querySelector(".reaction-bubble")?.remove();
    const bubble = document.createElement("span");
    bubble.className = "reaction-bubble";
    bubble.textContent = data.reaction;
    seat.appendChild(bubble);
    setTimeout(() => bubble.remove(), 1600);
  });

  socket.on("game_ended", () => setTimeout(renderResult, 80));

  $("#avatarGrid").addEventListener("click", (event) => {
    const button = event.target.closest("[data-avatar]");
    if (!button) return;
    selectedAvatar = button.dataset.avatar;
    renderAvatarSelectors();
  });

  $("#lobbyAvatarList").addEventListener("click", (event) => {
    const button = event.target.closest("[data-avatar]");
    if (!button) return;
    selectedAvatar = button.dataset.avatar;
    socket.emit("select_character", { avatar: selectedAvatar });
  });

  $("#nicknameInput").addEventListener("input", (event) => {
    $("#nicknameCount").textContent = `${[...event.target.value].length} / 12`;
  });

  $("#createRoomButton").addEventListener("click", () => {
    const identity = validateIdentity();
    if (identity) socket.emit("create_room", identity);
  });
  $("#showJoinButton").addEventListener("click", () => {
    $("#roomCodeEntry").classList.remove("is-hidden");
    $("#roomCodeInput").focus();
  });
  $("#joinRoomButton").addEventListener("click", () => {
    const identity = validateIdentity();
    const roomCode = $("#roomCodeInput").value.trim().toUpperCase();
    if (!identity) return;
    if (roomCode.length !== 4) return toast("네 자리 방 코드를 입력해주세요.", "error");
    socket.emit("join_room", { ...identity, room_code: roomCode });
  });
  $("#roomCodeInput").addEventListener("input", (event) => { event.target.value = event.target.value.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 4); });
  $("#roomCodeInput").addEventListener("keydown", (event) => { if (event.key === "Enter") $("#joinRoomButton").click(); });
  $("#copyInviteButton").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText($("#inviteLink").textContent);
      toast("초대 링크를 복사했습니다.", "success");
    } catch (_) {
      toast("주소를 길게 눌러 직접 복사해주세요.");
    }
  });

  $("#seatLayer").addEventListener("click", (event) => {
    if (event.target.closest("[data-reveal]")) attemptReveal();
  });
  $("#revealButton").addEventListener("click", attemptReveal);
  $("#bellButton").addEventListener("click", attemptRing);

  $("#reactionButtons").innerHTML = REACTIONS.map((reaction) => `<button type="button" data-reaction="${reaction}">${reaction}</button>`).join("");
  $("#reactionButtons").addEventListener("click", (event) => {
    const button = event.target.closest("[data-reaction]");
    if (button && roomState) socket.emit("send_reaction", { reaction: button.dataset.reaction });
  });

  document.addEventListener("keydown", (event) => {
    const target = event.target;
    const typing = target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement;
    if (typing) return;
    const modalOpen = Boolean(document.querySelector("dialog[open]"));
    if ((event.code === "Space" || event.key === " ") && isGamePlaying()) {
      event.preventDefault();
      if (!event.repeat && !modalOpen) attemptRing();
      return;
    }
    if (event.key === "Enter" && !event.repeat && !modalOpen && canReveal()) {
      event.preventDefault();
      attemptReveal();
    }
  }, { passive: false });

  document.addEventListener("keyup", (event) => {
    if ((event.code === "Space" || event.key === " ") && isGamePlaying()) event.preventDefault();
  }, { passive: false });

  $("#rulesButton").addEventListener("click", () => showModal($("#rulesModal")));
  $("#lobbyRulesButton").addEventListener("click", () => showModal($("#rulesModal")));
  document.querySelectorAll("[data-close-modal]").forEach((button) => button.addEventListener("click", () => closeModal(document.getElementById(button.dataset.closeModal))));
  $("#tutorialOkButton").addEventListener("click", () => closeModal($("#tutorialModal")));

  const invitedRoom = new URLSearchParams(location.search).get("room");
  if (invitedRoom) {
    $("#roomCodeInput").value = invitedRoom.toUpperCase().slice(0, 4);
    $("#roomCodeEntry").classList.remove("is-hidden");
  }
  renderAvatarSelectors();
  renderState();
})();
