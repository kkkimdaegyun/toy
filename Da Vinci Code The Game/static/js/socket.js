(() => {
  const NC = window.NumberCode;
  const socket = io({ transports: ["websocket", "polling"] });
  window.gameSocket = socket;
  socket.on("connect", () => { NC.status("서버 연결됨", true); const saved = NC.session(); if (saved) socket.emit("reconnect_player", saved); });
  socket.on("disconnect", () => NC.status("연결이 끊어졌습니다. 다시 연결하는 중…", false));
  socket.on("connect_error", () => NC.status("서버에 연결할 수 없습니다", false));
  socket.on("identity", (data) => { NC.saveSession({ roomCode: data.roomCode, token: data.token }); NC.setBusy(false); });
  socket.on("state", (state) => { NC.setBusy(false); NC.app.state = state; NC.clearSelection(); window.renderGame(state); });
  socket.on("error_message", (data) => { NC.setBusy(false); NC.toast(data.message || "문제가 발생했습니다.", "bad"); });
  socket.on("guess_feedback", (data) => NC.toast(data.message, data.correct ? "good" : "bad"));
})();
