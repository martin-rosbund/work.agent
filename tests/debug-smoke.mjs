// Connect through the same DAP endpoints/path mappings used by VS Code.
// Run only against the isolated development environment (5173/5678/5679).
import net from "node:net";
import fs from "node:fs";
import path from "node:path";
import assert from "node:assert/strict";
const root = path.resolve(import.meta.dirname, "..");

class DAP {
  constructor(port) {
    this.sequence = 0; this.pending = new Map(); this.events = []; this.waiters = [];
    this.buffer = Buffer.alloc(0);
    this.socket = net.connect(port, "127.0.0.1");
    this.socket.on("data", chunk => {
      this.buffer = Buffer.concat([this.buffer, chunk]);
      while (true) {
        const end = this.buffer.indexOf("\r\n\r\n");
        if (end < 0) break;
        const length = Number(this.buffer.subarray(0, end).toString().match(/Content-Length: (\d+)/i)[1]);
        if (this.buffer.length < end + 4 + length) break;
        const message = JSON.parse(this.buffer.subarray(end + 4, end + 4 + length));
        this.buffer = this.buffer.subarray(end + 4 + length);
        if (message.type === "response") {
          const handler = this.pending.get(message.request_seq);
          if (handler) { this.pending.delete(message.request_seq); message.success ? handler.resolve(message.body) : handler.reject(Error(message.message)); }
        } else if (message.type === "event") {
          const index = this.waiters.findIndex(w => w.name === message.event);
          if (index >= 0) this.waiters.splice(index, 1)[0].resolve(message.body);
          else this.events.push(message);
        }
      }
    });
    this.socket.on("error", error => { for (const pending of this.pending.values()) pending.reject(error); });
  }
  request(command, args = {}) {
    const seq = ++this.sequence;
    const body = JSON.stringify({ seq, type: "request", command, arguments: args });
    return new Promise((resolve, reject) => {
      this.pending.set(seq, { resolve, reject });
      this.socket.write(`Content-Length: ${Buffer.byteLength(body)}\r\n\r\n${body}`);
    });
  }
  event(name) {
    const index = this.events.findIndex(e => e.event === name);
    if (index >= 0) return Promise.resolve(this.events.splice(index, 1)[0].body);
    return new Promise(resolve => this.waiters.push({ name, resolve }));
  }
}

async function verify(port, relative, marker, trigger) {
  const client = new DAP(port);
  const timeout = setTimeout(() => { console.error(`Debugger ${port}: timeout`); process.exit(1); }, 55000);
  try {
    await client.request("initialize", { clientID: "workagent-smoke", adapterID: "python", pathFormat: "path", linesStartAt1: true, columnsStartAt1: true });
    const attached = client.request("attach", { clientOS: "Windows", justMyCode: true, pathMappings: [{ localRoot: path.join(root, "backend"), remoteRoot: "/app" }] });
    await client.event("initialized");
    const filename = path.join(root, "backend", relative);
    const line = fs.readFileSync(filename, "utf8").split(/\r?\n/).findIndex(l => l.includes(marker)) + 1;
    assert(line > 0);
    const result = await client.request("setBreakpoints", { source: { path: filename }, breakpoints: [{ line }] });
    assert(result.breakpoints[0].verified, JSON.stringify(result));
    await client.request("configurationDone");
    await attached;
    const running = trigger?.();
    const stopped = await client.event("stopped");
    assert.equal(stopped.reason, "breakpoint");
    const stack = await client.request("stackTrace", { threadId: stopped.threadId, levels: 1 });
    assert.equal(stack.stackFrames[0].line, line);
    // Docker health probes may hit the same handler concurrently. Clear the
    // breakpoint before continuing so our own HTTP request cannot stop twice.
    await client.request("setBreakpoints", { source: { path: filename }, breakpoints: [] });
    await client.request("continue", { threadId: stopped.threadId });
    if (running) assert((await running).ok);
    await client.request("disconnect", { terminateDebuggee: false });
    console.log(`PASS ${port}: ${relative}:${line}, breakpoint hit and resumed`);
  } finally { clearTimeout(timeout); client.socket.destroy(); }
}
await verify(5678, "app/features/system/service.py", 'return {"status": "ok"}', () => fetch("http://localhost:5173/api/v1/health"));
await verify(5679, "app/worker.py", "github_sync.schedule(db)");
