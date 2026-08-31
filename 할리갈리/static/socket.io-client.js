/*
 * Small, offline Socket.IO v4 browser client for this project.
 * It implements the Engine.IO websocket transport and the Socket.IO default
 * namespace event protocol used by app.py. No runtime CDN is required.
 */
(function (global) {
  "use strict";

  function SocketClient() {
    this.handlers = new Map();
    this.connected = false;
    this.manuallyClosed = false;
    this.queue = [];
    this.retry = 0;
    this.ws = null;
    this.connect();
  }

  SocketClient.prototype.on = function (name, handler) {
    if (!this.handlers.has(name)) this.handlers.set(name, []);
    this.handlers.get(name).push(handler);
    return this;
  };

  SocketClient.prototype.dispatch = function (name, payload) {
    const callbacks = this.handlers.get(name) || [];
    callbacks.forEach(function (callback) {
      try {
        callback(payload);
      } catch (error) {
        setTimeout(function () { throw error; }, 0);
      }
    });
  };

  SocketClient.prototype.emit = function (name, payload) {
    const event = payload === undefined ? [name] : [name, payload];
    const packet = "42" + JSON.stringify(event);
    if (this.connected && this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(packet);
    } else {
      this.queue.push(packet);
    }
    return this;
  };

  SocketClient.prototype.flush = function () {
    while (this.connected && this.queue.length && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(this.queue.shift());
    }
  };

  SocketClient.prototype.connect = function () {
    const self = this;
    this.manuallyClosed = false;
    const scheme = location.protocol === "https:" ? "wss:" : "ws:";
    const url = scheme + "//" + location.host + "/socket.io/?EIO=4&transport=websocket&t=" + Date.now();
    const ws = new WebSocket(url);
    this.ws = ws;

    ws.onmessage = function (event) {
      const packet = String(event.data);
      if (packet.charAt(0) === "0") {
        ws.send("40");
        return;
      }
      if (packet === "2") {
        ws.send("3");
        return;
      }
      if (packet.startsWith("40")) {
        self.connected = true;
        self.retry = 0;
        self.flush();
        self.dispatch("connect");
        return;
      }
      if (packet.startsWith("42")) {
        try {
          const decoded = JSON.parse(packet.slice(2));
          if (Array.isArray(decoded) && typeof decoded[0] === "string") {
            self.dispatch(decoded[0], decoded[1]);
          }
        } catch (error) {
          self.dispatch("connect_error", { message: "실시간 메시지를 읽지 못했습니다." });
        }
        return;
      }
      if (packet.startsWith("44")) {
        self.dispatch("connect_error", { message: "서버 연결이 거절되었습니다." });
      }
    };

    ws.onerror = function () {
      self.dispatch("connect_error", { message: "게임 서버에 연결할 수 없습니다." });
    };

    ws.onclose = function () {
      const hadConnection = self.connected;
      self.connected = false;
      if (hadConnection) self.dispatch("disconnect", "transport close");
      if (!self.manuallyClosed) {
        const delay = Math.min(5000, 500 * Math.pow(1.7, self.retry++));
        setTimeout(function () { self.connect(); }, delay);
      }
    };
  };

  SocketClient.prototype.disconnect = function () {
    this.manuallyClosed = true;
    if (this.ws) this.ws.close();
  };

  global.io = function () { return new SocketClient(); };
})(window);
