# Cafe Nilgiri: AI Agents and Backend Integration for Websites

Hands-on starter kit for the workshop at **Nehru Arts and Science College, Coimbatore** (29 September 2026).
Resource person: **Dr. Amogh Deshmukh**, School of Technology, Woxsen University.

You get a small café website with a **real backend** (Python and SQLite) and an **AI agent** ("Nila")
that answers customers by calling the same backend through **tools**.

> **Nothing to install except Python 3.9 or newer.** No pip, no npm, no API key needed to start.

---

## 1. Run it (about 60 seconds)

| Your laptop | Do this |
|---|---|
| **Windows** | Double-click `run_windows.bat`, **or** open a terminal in this folder and type `python server.py` |
| **Mac / Linux** | Open a terminal in this folder and type `python3 server.py` |

Then open **http://localhost:8000** in your browser.
The interactive **Agent Lab** (API playground, agent-loop simulator, tool designer, guardrail arena, quiz) is at **http://localhost:8000/lab.html**. It works offline too.

- Port 8000 busy? Set `PORT=8001` in `.env` (see below), or on Mac/Linux run `PORT=8001 python3 server.py`
- `python` not found? On Windows try `py server.py`.
- To reset all data: `python db.py --reset`

## 2. What you are looking at

```
 Browser (public/)            Backend (server.py)                 Data and AI
 ┌─────────────────┐  fetch   ┌──────────────────────┐   SQL    ┌──────────────┐
 │ index.html      │ ───────► │ REST API  /api/...   │ ───────► │ SQLite       │
 │ app.js          │ ◄─────── │                      │          │ cafe.db      │
 │ chat widget     │   JSON   │ /api/chat ─► agent.py│          └──────────────┘
 └─────────────────┘          │      │   ▲           │  HTTPS   ┌──────────────┐
                              │      ▼   │ tool calls│ ───────► │ LLM API      │
                              │   tools.py           │ ◄─────── │ (Gemini etc.)│
                              └──────────────────────┘          └──────────────┘
```

| File | What it does |
|---|---|
| `server.py` | Web server and REST API. Serves the website and routes `/api/...` requests. |
| `tools.py` | Business logic **and** the agent's tools. The same functions serve both the website and the agent. |
| `agent.py` | The agent loop: LLM ⇄ tools, until a final answer. Also a **mock brain** for use without an API key. |
| `db.py` | Creates the SQLite database with menu, orders and bookings. |
| `public/` | The website: HTML, CSS and plain JavaScript. Includes the chat widget with the **agent trace** view, and `lab.html` (Agent Lab). |
| `exercises/EXERCISES.md` | Today's lab tasks. |

## 3. The REST API

| Method | URL | Try it |
|---|---|---|
| GET | `/api/health` | http://localhost:8000/api/health |
| GET | `/api/menu?q=&veg=1&max_price=` | http://localhost:8000/api/menu?veg=1&max_price=100 |
| GET | `/api/orders/<id>` | http://localhost:8000/api/orders/1022 |
| GET | `/api/availability?date=&time=&party_size=` | http://localhost:8000/api/availability?date=tomorrow&time=20:00&party_size=2 |
| GET | `/api/bookings` | http://localhost:8000/api/bookings |
| GET | `/api/tools` | http://localhost:8000/api/tools (what the LLM sees) |
| POST | `/api/bookings` | JSON body: `name, phone, date, time, party_size` |
| POST | `/api/chat` | JSON body: `{"messages":[{"role":"user","content":"hi"}]}` |

POST from a terminal:

```bash
curl -X POST http://localhost:8000/api/chat -H "Content-Type: application/json" -d "{\"messages\":[{\"role\":\"user\",\"content\":\"Where is order 1022?\"}]}"
```

## 4. Mock mode vs real LLM mode

- **Mock mode** (default): a rule-based brain picks tools from keywords. You see the full *think → act → observe → answer* loop, but it only understands simple phrasing.
- **LLM mode**: copy `.env.example` to `.env` and paste a free API key (Gemini, Groq, or a local Ollama model). Restart the server. The badge at the top right shows the mode.

The API key lives **only on the server**. The browser never sees it. That is one of the main reasons a backend exists.

If the LLM call fails (network, wrong key, wrong model name), the server automatically falls back to mock mode and shows the error in the trace, so your demo never breaks.

## 5. How the agent loop works (agent.py)

```python
messages = [system_prompt] + chat_history
for step in range(MAX_STEPS):                        # safety limit
    reply = call_llm(messages, tools=TOOL_SCHEMAS)
    if no tool_calls in reply:
        return reply.content                          # final answer
    for call in reply.tool_calls:                     # LLM asked for tools
        result = run_tool(call.name, call.arguments)  # WE run them, with validation
        messages.append(tool_result)                  # LLM sees the observation
```

## 6. Security rules to remember

1. API keys stay on the server (in `.env`), never in front-end JavaScript and never on GitHub.
2. The backend validates every tool input. The LLM is not trusted any more than a browser is.
3. Authorisation goes in code, not in the prompt (see Exercise 3).
4. The browser can only send `user`/`assistant` text. It can never send a `system` message.
5. Limit the loop (`MAX_STEPS`), the history length and the request size.
6. Give tools the least power they need. The agent has no "run any SQL" tool, and there is a reason for that.

---
Café Nilgiri is a fictional business created for teaching.
