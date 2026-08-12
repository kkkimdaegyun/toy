/* =========================================================================
   socket.js — window.Net
   Thin wrapper over the locally bundled Socket.IO client.
   Owns: connection lifecycle, the "연결 끊김" banner, and re-join on reconnect.
   ========================================================================= */
(function (global) {
  'use strict';

  var socket = null;
  var listeners = {};
  var banner, bannerText;
  var everConnected = false;
  var reconnectPayload = null;   // {roomCode, token}

  function el(id) { return document.getElementById(id); }

  function showBanner(text) {
    if (!banner) { banner = el('conn-banner'); bannerText = el('conn-banner-text'); }
    if (!banner) return;
    if (bannerText) bannerText.textContent = text;
    banner.hidden = false;
  }

  function hideBanner() {
    if (!banner) banner = el('conn-banner');
    if (banner) banner.hidden = true;
  }

  function emitLocal(name, data) {
    var fns = listeners[name];
    if (!fns) return;
    for (var i = 0; i < fns.length; i++) {
      try { fns[i](data); } catch (e) { if (global.console) console.error(e); }
    }
  }

  function on(name, fn) {
    if (!listeners[name]) listeners[name] = [];
    listeners[name].push(fn);
  }

  function send(name, data) {
    if (!socket || !socket.connected) {
      emitLocal('game_error', { message: '서버와 연결이 끊겼습니다. 잠시만 기다려주세요.', code: 'offline' });
      return false;
    }
    socket.emit(name, data || {});
    return true;
  }

  /** Remember what to re-send after an automatic reconnect. */
  function setReconnect(roomCode, token) {
    reconnectPayload = (roomCode && token) ? { roomCode: roomCode, token: token } : null;
  }

  function connect() {
    if (socket) return socket;
    showBanner('서버와 연결하는 중...');

    socket = global.io({
      transports: ['websocket', 'polling'],
      reconnection: true,
      reconnectionDelay: 500,
      reconnectionDelayMax: 3000,
      timeout: 8000
    });

    socket.on('connect', function () {
      hideBanner();
      if (everConnected && reconnectPayload) {
        socket.emit('rejoin', reconnectPayload);
      }
      everConnected = true;
      emitLocal('net:connect', {});
    });

    socket.on('disconnect', function () {
      showBanner('잠시 연결이 끊겼습니다. 다시 연결하는 중...');
      emitLocal('net:disconnect', {});
    });

    socket.on('connect_error', function () {
      showBanner('서버에 연결하지 못했습니다. 다시 시도하는 중...');
    });

    ['hello', 'joined', 'state', 'game_error', 'room_info', 'left', 'kicked']
      .forEach(function (name) {
        socket.on(name, function (data) { emitLocal(name, data); });
      });

    return socket;
  }

  global.Net = {
    connect: connect,
    on: on,
    send: send,
    setReconnect: setReconnect,
    isConnected: function () { return !!(socket && socket.connected); }
  };
}(window));
