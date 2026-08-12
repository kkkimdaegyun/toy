(() => {
  const NC = window.NumberCode;
  const el = (tag, text, className) => { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; if (className) node.className = className; return node; };
  const playerById = (state, id) => state.players.find(player => player.id === id);
  const isMyTurn = (state) => state.currentPlayerId === state.selfId && state.phase === "game" && state.turnPhase === "guessing";

  function tileNode(tile, canSelect, player) {
    const node = el("button", "", `tile ${tile.color} ${tile.revealed ? "revealed" : "hidden-tile"}`);
    node.type = "button"; node.disabled = !canSelect;
    if (canSelect) {
      node.classList.add("selectable");
      node.addEventListener("click", () => { NC.app.selectedTarget = { playerId: player.id, tileId: tile.id, label: `${player.nickname} 님의 ${tile.color === "black" ? "검정" : "흰색"} 타일` }; renderAction(NC.app.state); renderOpponents(NC.app.state); });
    }
    node.append(el("span", tile.color === "black" ? "검정" : "흰색", "tile-color"));
    node.append(el("strong", Object.hasOwn(tile, "value") ? tile.value : "?", "tile-value"));
    if (tile.revealed) node.append(el("small", "공개됨", "revealed-label"));
    return node;
  }

  function renderLobby(state) {
    NC.show("lobby-screen"); NC.$("lobby-code").textContent = state.roomCode;
    NC.$("invite-link").value = NC.inviteUrl(state.roomCode);
    NC.$("lobby-count").textContent = `${state.players.length} / 4`;
    const list = NC.$("lobby-players"); list.replaceChildren();
    state.players.forEach(player => { const row = el("div", "", "lobby-player"); row.append(el("strong", player.nickname)); if (player.host) row.append(el("span", "방장", "badge")); row.append(el("span", player.connected ? "접속 중" : "연결 끊김", player.connected ? "connected-text" : "muted")); list.append(row); });
    const controls = NC.$("lobby-controls"); controls.replaceChildren();
    if (state.hostPlayerId === state.selfId) { const start = el("button", "게임 시작"); start.disabled = state.players.length < 2 || NC.app.busy; start.addEventListener("click", () => { NC.setBusy(true); window.gameSocket.emit("start_game"); }); controls.append(start); controls.append(el("p", state.players.length < 2 ? "게임을 시작하려면 한 명 이상 더 참가해야 합니다." : "모두 준비되었습니다.", "muted")); }
    else controls.append(el("p", "방장이 게임을 시작하기를 기다리고 있습니다…", "muted"));
  }

  function renderOpponents(state) {
    const holder = NC.$("opponents"); holder.replaceChildren();
    state.players.filter(player => player.id !== state.selfId).forEach(player => {
      const card = el("section", "", `player-card panel ${player.id === state.currentPlayerId ? "active-player" : ""}`);
      const header = el("div", "", "player-card-header"); header.append(el("h2", player.nickname));
      if (player.eliminated) header.append(el("span", "탈락", "badge danger")); else if (!player.connected) header.append(el("span", "연결 끊김", "badge muted-badge")); else if (player.id === state.currentPlayerId) header.append(el("span", "현재 차례", "badge current"));
      card.append(header); const tiles = el("div", "", "tile-row");
      player.tiles.forEach(tile => { const selectable = isMyTurn(state) && !player.eliminated && !tile.revealed; const node = tileNode(tile, selectable, player); if (NC.app.selectedTarget && NC.app.selectedTarget.tileId === tile.id) node.classList.add("selected"); tiles.append(node); }); card.append(tiles); holder.append(card);
    });
  }

  function renderAction(state) {
    const panel = NC.$("action-panel"); panel.replaceChildren();
    const current = state.currentPlayerId ? playerById(state, state.currentPlayerId) : null;
    if (state.turnPhase === "paused") { panel.append(el("h2", "게임 일시 정지")); panel.append(el("p", `${current?.nickname || "참가자"} 님의 재접속을 기다리고 있습니다.`, "muted")); return; }
    if (state.currentPlayerId !== state.selfId || state.phase !== "game") { panel.append(el("h2", "상대의 차례")); panel.append(el("p", current ? `${current.nickname} 님이 선택 중입니다.` : "게임 시작을 기다리고 있습니다.", "muted")); return; }
    if (state.turnPhase === "decision") {
      panel.append(el("h2", "정답입니다!")); panel.append(el("p", "계속 맞히거나, 지금 턴을 끝내서 새로 뽑은 타일을 숨길 수 있습니다.", "muted"));
      const actions = el("div", "", "decision-actions"); const cont = el("button", "계속 추리하기"); const end = el("button", "턴 끝내기", "secondary"); cont.disabled = end.disabled = NC.app.busy;
      cont.addEventListener("click", () => { NC.setBusy(true); window.gameSocket.emit("continue_turn"); }); end.addEventListener("click", () => { NC.setBusy(true); window.gameSocket.emit("end_turn"); }); actions.append(cont, end); panel.append(actions); return;
    }
    panel.append(el("h2", "숫자 추리하기"));
    panel.append(el("p", NC.app.selectedTarget ? `선택한 타일: ${NC.app.selectedTarget.label}` : "상대의 숨겨진 타일 하나를 선택하세요.", "muted"));
    const keypad = el("div", "", "keypad"); for (let value = 0; value <= 11; value += 1) { const button = el("button", String(value), `number-key ${NC.app.selectedValue === value ? "selected" : ""}`); button.type = "button"; button.addEventListener("click", () => { NC.app.selectedValue = value; renderAction(state); }); keypad.append(button); } panel.append(keypad);
    const confirm = el("button", "이 숫자로 추리하기"); confirm.disabled = !NC.app.selectedTarget || NC.app.selectedValue === null || NC.app.busy;
    confirm.addEventListener("click", () => { NC.setBusy(true); window.gameSocket.emit("make_guess", { targetPlayerId: NC.app.selectedTarget.playerId, targetTileId: NC.app.selectedTarget.tileId, value: NC.app.selectedValue }); }); panel.append(confirm);
  }

  function renderGame(state) {
    if (state.phase === "lobby") { renderLobby(state); NC.$("game-over-modal").classList.add("hidden"); return; }
    NC.show("game-screen"); NC.$("game-code").textContent = state.roomCode; NC.$("deck-count").textContent = state.deckCount;
    const current = playerById(state, state.currentPlayerId); const mine = playerById(state, state.selfId);
    NC.$("turn-title").textContent = state.turnPhase === "paused" ? "게임 일시 정지" : (state.currentPlayerId === state.selfId ? "내 차례입니다" : `${current?.nickname || ""} 님의 차례`);
    NC.$("turn-detail").textContent = state.turnPhase === "decision" && state.currentPlayerId === state.selfId ? "정답을 맞혔습니다. 계속할지 선택하세요." : (current ? `${current.nickname} 님이 플레이 중입니다.` : "");
    NC.$("my-name").textContent = mine.nickname; NC.$("my-status").textContent = mine.eliminated ? "ELIMINATED" : "";
    const myTiles = NC.$("my-tiles"); myTiles.replaceChildren(); mine.tiles.forEach(tile => myTiles.append(tileNode(tile, false, mine)));
    renderOpponents(state); renderAction(state);
    const log = NC.$("event-log"); log.replaceChildren(); state.eventLog.forEach(line => log.append(el("div", line)));
    const modal = NC.$("game-over-modal"); if (state.phase === "finished") { const winner = playerById(state, state.winnerPlayerId); NC.$("winner-text").textContent = `${winner?.nickname || "참가자"} 님의 승리!`; const buttons = NC.$("game-over-buttons"); buttons.replaceChildren(); if (state.hostPlayerId === state.selfId) { const again = el("button", "같은 멤버로 다시 하기"); again.addEventListener("click", () => window.gameSocket.emit("play_again")); const lobby = el("button", "대기실로 돌아가기", "secondary"); lobby.addEventListener("click", () => window.gameSocket.emit("return_to_lobby")); buttons.append(again, lobby); } else buttons.append(el("p", "방장이 다음 게임을 선택할 때까지 기다려주세요.", "muted")); modal.classList.remove("hidden"); } else modal.classList.add("hidden");
  }
  window.renderGame = renderGame;
})();
