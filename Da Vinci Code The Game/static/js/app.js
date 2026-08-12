window.NumberCode = (() => {
  const app = { state: null, selectedTarget: null, selectedValue: null, busy: false };
  const $ = (id) => document.getElementById(id);
  const sessionKey = "numberCodeSession";

  function session() { try { return JSON.parse(localStorage.getItem(sessionKey)); } catch { return null; } }
  function saveSession(data) { localStorage.setItem(sessionKey, JSON.stringify(data)); }
  function show(id) { ["home-screen", "lobby-screen", "game-screen"].forEach(x => $(x).classList.toggle("hidden", x !== id)); }
  function toast(message, kind = "") { const node = $("toast"); node.textContent = message; node.className = `toast ${kind}`; setTimeout(() => node.classList.add("hidden"), 4200); }
  function status(text, online) { const node = $("connection"); node.textContent = text; node.classList.toggle("online", online); }
  function inviteUrl(code) { return `${window.location.origin}/?room=${encodeURIComponent(code)}`; }
  function clearSelection() { app.selectedTarget = null; app.selectedValue = null; }
  function setBusy(value) { app.busy = value; }

  document.addEventListener("DOMContentLoaded", () => {
    const code = new URLSearchParams(location.search).get("room");
    if (code) $("join-code").value = code.toUpperCase();
    $("create-form").addEventListener("submit", (event) => { event.preventDefault(); if (!app.busy) { setBusy(true); window.gameSocket.emit("create_room", { nickname: $("create-nickname").value }); } });
    $("join-form").addEventListener("submit", (event) => { event.preventDefault(); if (!app.busy) { setBusy(true); window.gameSocket.emit("join_room", { nickname: $("join-nickname").value, roomCode: $("join-code").value }); } });
    $("copy-invite").addEventListener("click", async () => { const url = $("invite-link").value; try { await navigator.clipboard.writeText(url); toast("초대 링크를 복사했습니다.", "good"); } catch { $("invite-link").focus(); $("invite-link").select(); toast("선택된 링크를 직접 복사해주세요."); } });
  });
  return { app, $, session, saveSession, show, toast, status, inviteUrl, clearSelection, setBusy };
})();
