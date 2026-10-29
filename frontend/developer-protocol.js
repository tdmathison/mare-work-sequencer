class DeveloperProtocol {
  constructor({ base, csrf, id, mode, onEvent, onOutput }) {
    Object.assign(this, { base, csrf, id, mode, onEvent, onOutput });
    this.sequence = 0;
    this.pending = /* @__PURE__ */ new Map();
    this.closed = false;
    this.timer = null;
  }
  async http(path, data) {
    const options = { credentials: "same-origin", keepalive: path.endsWith("/cancel") };
    if (data !== void 0) {
      const form = new FormData();
      form.set("csrf", this.csrf);
      form.set("payload", JSON.stringify(data));
      options.method = "POST";
      options.body = form;
    }
    const response = await fetch(this.base + path, options);
    if (!response.ok) {
      const raw = await response.text();
      throw Error(new DOMParser().parseFromString(raw, "text/html").querySelector("p")?.textContent || "Worker request failed.");
    }
    return response.json();
  }
  async start(context = {}) {
    const result = await this.http("/plugins/" + this.id + "/" + this.mode, context);
    this.session = result.id;
    this.consume(result);
    this.timer = setInterval(() => this.poll().catch((error) => {
      this.onOutput?.(error.message);
      this.close();
    }), 500);
    return this;
  }
  consume(result) {
    if (result.output) this.onOutput?.(result.output);
    for (const message of result.messages || []) {
      if (this.mode === "language" && message.method && message.id !== void 0) {
        const result2 = message.method === "workspace/configuration" ? (message.params?.items || []).map(() => null) : null;
        this.http("/executions/" + this.session + "/rpc", { jsonrpc: "2.0", id: message.id, result: result2 }).then((value) => this.consume(value)).catch((e) => this.onOutput?.(e.message));
        continue;
      }
      const id = this.mode === "language" ? message.id : message.request_seq;
      if (id !== void 0 && this.pending.has(id)) {
        const pending = this.pending.get(id);
        this.pending.delete(id);
        clearTimeout(pending.timer);
        if (message.error || message.success === false) pending.reject(Error(message.error?.message || message.message || "Worker request failed."));
        else pending.resolve(this.mode === "language" ? message.result : message.body);
      } else this.onEvent?.(message);
    }
    if (!["Starting", "Running"].includes(result.status)) {
      this.onOutput?.(result.status);
      this.close(false);
    }
  }
  async poll() {
    if (!this.closed) this.consume(await this.http("/executions/" + this.session));
  }
  request(method, params = {}) {
    if (this.closed) return Promise.reject(Error("Session ended."));
    const id = ++this.sequence;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(Error("Development request timed out."));
      }, 15e3);
      this.pending.set(id, { resolve, reject, timer });
      const message = this.mode === "language" ? { jsonrpc: "2.0", id, method, params } : { seq: id, type: "request", command: method, arguments: params };
      this.http("/executions/" + this.session + "/rpc", message).then((value) => this.consume(value)).catch((error) => {
        clearTimeout(timer);
        this.pending.delete(id);
        reject(error);
      });
    });
  }
  async notify(method, params = {}) {
    const message = { jsonrpc: "2.0", method, params };
    this.consume(await this.http("/executions/" + this.session + "/rpc", message));
  }
  async close(cancel = true) {
    if (this.closed) return;
    this.closed = true;
    clearInterval(this.timer);
    for (const p of this.pending.values()) {
      clearTimeout(p.timer);
      p.reject(Error("Session ended."));
    }
    this.pending.clear();
    if (cancel && this.session) try {
      await this.http("/executions/" + this.session + "/cancel", {});
    } catch {
    }
  }
}
export {
  DeveloperProtocol
};
