// app.js - Front-end for Cafe Nilgiri.
// The browser NEVER talks to the database or the LLM directly.
// It only calls our backend's REST API with fetch().

// ---------- A small fetch wrapper that also logs every call ----------
async function api(method, url, body) {
  const t0 = performance.now();
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  let res, data;
  try {
    res = await fetch(url, opts);
    data = await res.json();
  } catch (err) {
    logCall(method, url, "network error", performance.now() - t0);
    throw err;
  }
  logCall(method, url, res.status, performance.now() - t0);
  return { ok: res.ok, status: res.status, data };
}

function logCall(method, url, status, ms) {
  const tr = document.createElement("tr");
  const good = typeof status === "number" && status < 400;
  tr.innerHTML = `<td>${method}</td><td>${escapeHtml(url)}</td>
    <td class="${good ? "status-ok" : "status-bad"}">${status}</td><td>${Math.round(ms)} ms</td>`;
  const body = document.getElementById("logBody");
  body.prepend(tr);
  while (body.children.length > 15) body.lastChild.remove();
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ---------- Health / mode badge ----------
async function loadHealth() {
  try {
    const { data } = await api("GET", "/api/health");
    const badge = document.getElementById("modeBadge");
    badge.textContent = data.agent_mode === "llm" ? `Agent: LLM (${data.model})` : "Agent: mock mode";
    badge.className = "badge " + data.agent_mode;
    document.getElementById("chatMode").textContent =
      data.agent_mode === "llm" ? `powered by ${data.model}` : "mock brain (no API key)";
  } catch {
    document.getElementById("modeBadge").textContent = "backend offline";
  }
}

// ---------- Menu ----------
async function loadMenu(e) {
  if (e) e.preventDefault();
  const params = new URLSearchParams();
  const q = document.getElementById("menuQuery").value.trim();
  const max = document.getElementById("menuMax").value;
  if (q) params.set("q", q);
  if (max) params.set("max_price", max);
  if (document.getElementById("menuVeg").checked) params.set("veg", "1");
  const url = "/api/menu" + (params.toString() ? "?" + params : "");
  const { data } = await api("GET", url);
  const grid = document.getElementById("menuGrid");
  if (!data.items.length) {
    grid.innerHTML = `<p class="hint">No dishes match. Try another search.</p>`;
    return;
  }
  grid.innerHTML = data.items.map(i => `
    <article class="dish ${i.available ? "" : "na"}">
      <div class="dish-top"><h3>${escapeHtml(i.name)}</h3><span class="price">Rs ${i.price}</span></div>
      <p>${escapeHtml(i.description)}</p>
      <div class="tags">
        <span class="tag ${i.veg ? "veg" : "nonveg"}">${i.veg ? "Veg" : "Non-veg"}</span>
        ${i.spicy ? '<span class="tag spicy">Spicy</span>' : ""}
        <span class="tag">${escapeHtml(i.category)}</span>
        ${i.available ? "" : '<span class="tag">Unavailable</span>'}
      </div>
    </article>`).join("");
}

// ---------- Track order ----------
async function trackOrder(e) {
  e.preventDefault();
  const id = document.getElementById("orderId").value.trim();
  const box = document.getElementById("trackResult");
  const { ok, data } = await api("GET", `/api/orders/${encodeURIComponent(id)}`);
  box.hidden = false;
  box.className = "result" + (ok ? "" : " err");
  box.innerHTML = ok
    ? `<b>Order #${data.id}</b> · ${escapeHtml(data.items)}<br>Status: <b>${data.status.replaceAll("_", " ")}</b>` +
      (data.eta_minutes ? ` · ETA ${data.eta_minutes} min` : "") + ` · Total Rs ${data.total}`
    : escapeHtml(data.message || data.error);
}

// ---------- Book a table ----------
async function bookTable(e) {
  e.preventDefault();
  const form = new FormData(e.target);
  const payload = Object.fromEntries(form.entries());
  payload.party_size = Number(payload.party_size);
  const box = document.getElementById("bookResult");
  const { ok, data } = await api("POST", "/api/bookings", payload);
  box.hidden = false;
  box.className = "result" + (ok ? "" : " err");
  box.innerHTML = ok
    ? `Confirmed! Booking <b>#${data.booking_id}</b> for ${data.party_size} on ${data.date} at ${data.time}.`
    : escapeHtml(data.error);
}

// ---------- Chat widget (talks to the AI agent) ----------
const Chat = {
  history: [], // [{role, content}] - only text; the backend owns the system prompt & tools

  open() { document.getElementById("chat").hidden = false; document.getElementById("chatText").focus(); if (!this.history.length) this.greet(); },
  toggle() { const c = document.getElementById("chat"); c.hidden ? this.open() : (c.hidden = true); },
  reset() { this.history = []; document.getElementById("chatBody").innerHTML = ""; this.greet(); },
  greet() { this.addMsg("bot", "Hi! I'm Nila, Cafe Nilgiri's assistant. Ask me about the menu, your order, or book a table."); },

  addMsg(who, text) {
    const div = document.createElement("div");
    div.className = "msg " + who;
    div.textContent = text;
    document.getElementById("chatBody").appendChild(div);
    div.scrollIntoView({ block: "end" });
    return div;
  },

  addTrace(trace, mode, ms) {
    const labels = { thought: "Think", tool_call: "Act · tool call", tool_result: "Observe · tool result", answer: "Answer", error: "Error" };
    const d = document.createElement("details");
    d.className = "trace";
    d.open = true;
    const toolCount = trace.filter(s => s.type === "tool_call").length;
    d.innerHTML = `<summary>Agent trace · ${toolCount} tool call(s) · ${mode} · ${Math.round(ms)} ms</summary>` +
      trace.map(s => {
        let body = "";
        if (s.type === "tool_call") body = `<pre>${escapeHtml(s.tool)}(${escapeHtml(JSON.stringify(s.args, null, 1))})</pre>`;
        else if (s.type === "tool_result") body = `<pre>${escapeHtml(JSON.stringify(s.result, null, 1))}</pre>`;
        else body = `<div>${escapeHtml(s.text || "")}</div>`;
        return `<div class="step ${s.type}"><b>${labels[s.type] || s.type}</b>${s.ms ? ` <span class="muted">(${s.ms} ms LLM)</span>` : ""}${body}</div>`;
      }).join("");
    document.getElementById("chatBody").appendChild(d);
  },

  async send(text) {
    text = text.trim();
    if (!text) return;
    this.addMsg("user", text);
    this.history.push({ role: "user", content: text });
    const typing = this.addMsg("bot typing", "Nila is thinking…");
    const t0 = performance.now();
    try {
      const { ok, data } = await api("POST", "/api/chat", { messages: this.history });
      typing.remove();
      if (!ok) throw new Error(data.error);
      this.addTrace(data.trace, data.mode, performance.now() - t0);
      this.addMsg("bot", data.reply);
      this.history.push({ role: "assistant", content: data.reply });
    } catch (err) {
      typing.remove();
      this.addMsg("bot", "Sorry, something went wrong: " + err.message);
    }
  },
};

document.getElementById("chatForm").addEventListener("submit", e => {
  e.preventDefault();
  const input = document.getElementById("chatText");
  Chat.send(input.value);
  input.value = "";
});
document.getElementById("chips").addEventListener("click", e => {
  if (e.target.tagName === "BUTTON") Chat.send(e.target.textContent);
});
document.getElementById("traceToggle").addEventListener("change", e => {
  document.getElementById("chat").classList.toggle("hide-trace", !e.target.checked);
});

document.getElementById("menuForm").addEventListener("submit", loadMenu);
document.getElementById("trackForm").addEventListener("submit", trackOrder);
document.getElementById("bookForm").addEventListener("submit", bookTable);
document.querySelector('#bookForm input[name="date"]').valueAsDate = new Date(Date.now() + 86400000);

loadHealth();
loadMenu();
