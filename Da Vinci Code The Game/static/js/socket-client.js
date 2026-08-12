/* Small offline Socket.IO v4 polling client for this single-purpose LAN app.
   It speaks Engine.IO polling, avoiding a CDN or Node install on player PCs. */
(() => {
  class NumberCodeSocket {
    constructor() { this.handlers = {}; this.sid = null; this.connected = false; this.closed = false; this.connect(); }
    on(name, handler) { (this.handlers[name] ||= []).push(handler); return this; }
    fire(name, value) { (this.handlers[name] || []).forEach(handler => handler(value)); }
    endpoint(extra = "") { return `/socket.io/?EIO=4&transport=polling${this.sid ? `&sid=${encodeURIComponent(this.sid)}` : ""}&t=${Date.now()}${extra}`; }
    async post(packet) { await fetch(this.endpoint(), { method: "POST", headers: { "Content-Type": "text/plain;charset=UTF-8" }, body: packet }); }
    async connect() {
      if (this.closed) return;
      try {
        const response = await fetch(this.endpoint());
        const packet = await response.text();
        if (!packet.startsWith("0")) throw new Error("Engine.IO handshake failed");
        this.sid = JSON.parse(packet.slice(1)).sid;
        await this.post("40");
        this.poll();
      } catch { this.retry(); }
    }
    async poll() {
      while (this.sid && !this.closed) {
        try { this.handle(await (await fetch(this.endpoint())).text()); }
        catch { this.drop(); return; }
      }
    }
    handle(payload) {
      payload.split("\x1e").filter(Boolean).forEach(packet => {
        if (packet === "2") this.post("3");
        else if (packet.startsWith("40") && !this.connected) { this.connected = true; this.fire("connect"); }
        else if (packet.startsWith("42")) {
          try { const [event, data] = JSON.parse(packet.slice(2)); this.fire(event, data); } catch { /* Ignore malformed packets. */ }
        } else if (packet === "1") this.drop();
      });
    }
    emit(event, data) {
      if (!this.connected) return;
      const payload = data === undefined ? [event] : [event, data];
      this.post(`42${JSON.stringify(payload)}`).catch(() => this.drop());
    }
    drop() { const wasConnected = this.connected; this.connected = false; this.sid = null; if (wasConnected) this.fire("disconnect"); this.retry(); }
    retry() { if (!this.closed) window.setTimeout(() => this.connect(), 1000); }
  }
  window.io = () => new NumberCodeSocket();
})();
