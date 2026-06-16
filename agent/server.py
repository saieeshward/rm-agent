"""
Deployable web app for the Revenue Manager agent.

  uvicorn agent.server:app --host 0.0.0.0 --port 8000

- GET  /health  : JSON proof fields computed from the LIVE DB (no model/key needed),
                  for the reviewer to confirm the deployed DB matches LOAD_PROOF.json.
- GET  /        : chat page (HTTP basic auth) that STREAMS tool + skill calls live.
- POST /chat    : run the agent, server-sent events (tool/skill/answer/interrupt).
- POST /resume  : approve/reject the get_as_of_otb human-in-the-loop interrupt.

Model comes from MODEL (.env); the agent is built lazily so /health works with no key.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import time

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from langchain_core.messages import AIMessage, ToolMessage

from tools.db import query, query_one

app = FastAPI(title="Revenue Manager Agent")
security = HTTPBasic()
USER = os.environ.get("BASIC_AUTH_USER", "gm")
PASSWORD = os.environ.get("BASIC_AUTH_PASS", "hackathon")

# One agent per model spec, all sharing the same checkpointer + store so the
# conversation (thread) memory survives a mid-session model switch.
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

_CHECKPOINTER = MemorySaver()
_STORE = InMemoryStore()
_agents: dict[str, object] = {}

DEFAULT_MODEL = os.environ.get("MODEL", "openrouter:openai/gpt-oss-120b:free")

# Models the UI may offer, with friendly labels. Only those whose API key is
# actually configured are shown — so the picker never lists an option that 500s.
# All openrouter:* free entries require tool-calling support (this is a tool-using
# deep agent) — verified against OpenRouter's catalog. Free-tier quality varies;
# the switcher lets the GM compare. Extend via the EXTRA_MODELS env var (see below).
# All openrouter:* free entries require tool-calling support (this is a tool-using
# deep agent) — verified against OpenRouter's catalog. Free-tier quality/availability
# varies (gpt-oss can produce loose briefings; the big Nemotrons can be slow / 429),
# so the GM can switch. Gemini is the default; add more via EXTRA_MODELS (below).
# Spread across providers so a quota wall on one still leaves working options.
# NOTE: Groq's free tier is intentionally absent — its per-minute token cap
# (6-12k TPM) is below this agent's ~9-14k-token request, so every call 413s.
# The groq: provider is still wired (build.py) for a paid/Dev-tier key via
# EXTRA_MODELS. Viable free providers here are Google + OpenRouter (daily caps).
_MODEL_LABELS = {
    "google_genai:gemini-2.5-flash": "Gemini 2.5 Flash · Google",
    "openrouter:openai/gpt-oss-120b:free": "gpt-oss-120B · OpenRouter",
    "openrouter:meta-llama/llama-3.3-70b-instruct:free": "Llama 3.3 70B · OpenRouter",
    "openrouter:qwen/qwen3-next-80b-a3b-instruct:free": "Qwen3 Next 80B · OpenRouter",
    "openrouter:nvidia/nemotron-3-ultra-550b-a55b:free": "Nemotron 3 Ultra 550B · OpenRouter",
    "openrouter:nvidia/nemotron-3-super-120b-a12b:free": "Nemotron 3 Super 120B · OpenRouter",
    "openrouter:google/gemma-4-31b-it:free": "Gemma 4 31B · OpenRouter",
    "anthropic:claude-sonnet-4-6": "Claude Sonnet 4.6 · Anthropic",
}

# Optional: append models without a code change. Comma-separated "spec|Label"
# (or just "spec"); e.g. EXTRA_MODELS="openrouter:mistralai/...:free|Mistral · free"
for _entry in (os.environ.get("EXTRA_MODELS") or "").split(","):
    _entry = _entry.strip()
    if not _entry:
        continue
    _spec, _, _lbl = _entry.partition("|")
    _MODEL_LABELS.setdefault(_spec.strip(), (_lbl.strip() or _spec.strip().split(":", 1)[-1]))


def _key_present(spec: str) -> bool:
    if spec.startswith("openrouter:"):
        return bool(os.environ.get("OPENROUTER_API_KEY"))
    if spec.startswith("groq:"):
        return bool(os.environ.get("GROQ_API_KEY"))
    if spec.startswith("google_genai:"):
        return bool(os.environ.get("GOOGLE_API_KEY"))
    if spec.startswith("anthropic:"):
        return bool(os.environ.get("ANTHROPIC_API_KEY"))
    if spec.startswith("openai:"):
        return bool(os.environ.get("OPENAI_API_KEY"))
    return True  # ollama / local


def available_models() -> list[dict]:
    """Default model first, then any other known candidate whose key is set."""
    specs, seen, out = [DEFAULT_MODEL, *_MODEL_LABELS], set(), []
    for spec in specs:
        if spec in seen or not _key_present(spec):
            continue
        seen.add(spec)
        out.append({"spec": spec, "label": _MODEL_LABELS.get(spec, spec.split(":", 1)[-1])})
    return out


def get_agent(model: str | None = None):
    valid = {m["spec"] for m in available_models()}
    spec = model if model in valid else DEFAULT_MODEL
    if spec not in _agents:
        from agent.build import build_agent
        _agents[spec] = build_agent(model=spec, checkpointer=_CHECKPOINTER, store=_STORE)
    return _agents[spec]


@app.get("/models")
def models():
    return JSONResponse({"default": DEFAULT_MODEL, "options": available_models()})


def require_auth(creds: HTTPBasicCredentials = Depends(security)) -> str:
    ok = secrets.compare_digest(creds.username, USER) and secrets.compare_digest(creds.password, PASSWORD)
    if not ok:
        raise HTTPException(status_code=401, detail="Unauthorized",
                            headers={"WWW-Authenticate": "Basic"})
    return creds.username


# --------------------------------------------------------------------------- #
# /health — computed from the live DB; matches etl/LOAD_PROOF.json on a fresh load
# --------------------------------------------------------------------------- #
@app.get("/health")
def health():
    rows = query("select reservation_id, stay_date::text, financial_status "
                 "from public.reservations_hackathon "
                 "order by reservation_id, stay_date, financial_status")
    sha = hashlib.sha256(
        "\n".join(f"{r['reservation_id']}|{r['stay_date']}|{r['financial_status']}" for r in rows).encode()
    ).hexdigest()
    man = query_one("select dataset_revision, row_hash from public.load_manifest "
                    "order by load_id desc limit 1") or {}
    posted = query_one("select count(*) n from public.reservations_hackathon "
                       "where reservation_status <> 'Cancelled' and financial_status = 'Posted'") or {}
    return JSONResponse({
        "db_fingerprint": sha,
        "dataset_revision": man.get("dataset_revision"),
        "row_hash": man.get("row_hash"),
        "financial_status_posted_only_rows": int(posted.get("n", 0)),
    })


# --------------------------------------------------------------------------- #
# streaming helpers
# --------------------------------------------------------------------------- #
def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


_SKILL_PATH = re.compile(r"skills/([^/]+)/SKILL", re.IGNORECASE)


def _events(chunk: dict, pending: dict):
    """Yield SSE events for a stream chunk. `pending` carries per-tool-call start
    times across chunks so each result reports how long that call (incl. a whole
    subagent delegation) took."""
    now = time.monotonic()
    for _node, update in chunk.items():
        msgs = (update or {}).get("messages", []) if isinstance(update, dict) else []
        for msg in msgs:
            if isinstance(msg, AIMessage):
                for tc in (msg.tool_calls or []):
                    name = tc["name"]
                    args = tc.get("args", {}) or {}
                    if name == "task":
                        # delegation to a subagent — credit the subagent by name,
                        # not the generic "task" tool. Its result time == subagent time.
                        kind = "subagent"
                        name = args.get("subagent_type") or "segment-analyst"
                    elif name in ("read_file", "ls", "glob", "grep"):
                        kind = "skill"
                        # surface the actual skill name (skills/<name>/SKILL.md),
                        # so the work tape credits the skill, not a generic read_file
                        path = str(args.get("file_path") or args.get("path") or "")
                        m = _SKILL_PATH.search(path)
                        if m:
                            name = m.group(1)
                    else:
                        kind = "tool"
                    if tc.get("id"):
                        pending[tc["id"]] = (name, kind, now)
                    yield {"type": kind, "name": name, "args": args}
            elif isinstance(msg, ToolMessage):
                label, _kind, start = pending.pop(
                    getattr(msg, "tool_call_id", None), (msg.name, "tool", None))
                ev = {"type": "result", "name": label,
                      "preview": str(msg.content)[:200].replace("\n", " ")}
                if start is not None:
                    ev["ms"] = int((now - start) * 1000)
                yield ev


def _final_text(state) -> str:
    msg = state.values["messages"][-1]
    content = getattr(msg, "content", "")
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content
                         if isinstance(b, dict) and b.get("type") == "text") or str(content)
    return content


def _stream(payload, thread: str, model: str | None = None):
    agent = get_agent(model)
    cfg = {"configurable": {"thread_id": thread}, "recursion_limit": 50}
    pending: dict = {}
    try:
        for chunk in agent.stream(payload, config=cfg, stream_mode="updates"):
            for ev in _events(chunk, pending):
                yield _sse(ev)
        state = agent.get_state(cfg)
        if state.next:
            yield _sse({"type": "interrupt", "tool": "get_as_of_otb",
                        "message": "Point-in-time rebuild needs approval."})
        else:
            yield _sse({"type": "answer", "text": _final_text(state)})
    except Exception as exc:  # surface model/rate-limit errors instead of hanging
        msg = str(exc)
        low = msg.lower()
        if "resource_exhausted" in low or "429" in msg or "rate" in low:
            msg = "Model rate limit / quota exceeded — retry shortly or use a model with more capacity."
        elif "'messages'" in msg or msg.strip() in ("", "None"):
            # the provider returned a malformed/error payload (seen under concurrent
            # bursts on gpt-4o-mini) instead of a completion — present it cleanly.
            msg = "The model returned an unexpected response (likely a transient rate-limit). Please retry."
        yield _sse({"type": "error", "message": msg[:400]})
    yield _sse({"type": "done"})


@app.post("/chat")
async def chat(request: Request, user: str = Depends(require_auth)):
    body = await request.json()
    thread = body.get("thread", "web")
    # Pin "today" to the dataset anchor (the data is locked to this load), so the
    # agent never drifts to a wrong month over the 7-day window or guesses a past year.
    primer = ("(Context: treat today as 2026-06-16 — the dataset anchor. Stay months "
              "are 'YYYY-MM'; if a month isn't specified, use the upcoming month "
              "2026-07. STLY = same month, year minus one.)\n\n")
    payload = {"messages": [{"role": "user", "content": primer + body["message"]}]}
    return StreamingResponse(_stream(payload, thread, body.get("model")), media_type="text/event-stream")


@app.post("/resume")
async def resume(request: Request, user: str = Depends(require_auth)):
    from langgraph.types import Command
    body = await request.json()
    thread = body.get("thread", "web")
    approve = bool(body.get("approve"))
    decision = {"type": "approve"} if approve else {"type": "reject", "message": "Not approved by GM."}
    payload = Command(resume={"decisions": [decision]})
    return StreamingResponse(_stream(payload, thread, body.get("model")), media_type="text/event-stream")


# --------------------------------------------------------------------------- #
# minimal chat UI (streams tool/skill calls; approve/reject on interrupt)
# --------------------------------------------------------------------------- #
PAGE = """<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Grand Harbour Hotel — Revenue Desk</title>
<link rel=preconnect href="https://fonts.googleapis.com">
<link rel=preconnect href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600&family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;1,6..72,400&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel=stylesheet>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<style>
:root{
 --paper:#F6F4EF;--card:#FFFFFF;--ink:#1B2430;--soft:#5C6976;--faint:#909AA5;
 --line:#E7E1D5;--teal:#0E6E5B;--teal-deep:#0A4C40;--teal-tint:#E6F1ED;
 --gold:#A87C2F;--gold-tint:#F3E9D4;--amber:#8A5E10;--amber-bg:#FAEFD6;
 --red:#9F352A;--red-bg:#F7E7E4;--mono:'IBM Plex Mono',ui-monospace,monospace;
 --sans:'IBM Plex Sans',system-ui,sans-serif;--serif:'Newsreader',Georgia,serif;
 --display:'Fraunces','Newsreader',serif;
}
*{box-sizing:border-box}
html,body{margin:0;height:100%}
body{background:var(--paper);color:var(--ink);font-family:var(--sans);
 font-size:15.5px;line-height:1.55;display:flex;flex-direction:column;min-height:100vh;
 -webkit-font-smoothing:antialiased}
.eyebrow{font-family:var(--mono);font-size:10.5px;letter-spacing:.18em;
 text-transform:uppercase;color:var(--faint)}

/* masthead */
header{position:sticky;top:0;z-index:5;background:rgba(246,244,239,.9);
 backdrop-filter:blur(8px);border-bottom:2px solid var(--gold)}
.mast{max-width:880px;margin:auto;padding:15px 22px;display:flex;align-items:baseline;
 justify-content:space-between;gap:16px}
.brand{display:flex;align-items:baseline;gap:11px}
.brand .mark{width:11px;height:11px;background:var(--teal);transform:rotate(45deg);
 align-self:center;flex:none}
.brand h1{font-family:var(--display);font-weight:600;font-size:23px;margin:0;
 letter-spacing:-.01em;line-height:1}
.brand .sub{font-family:var(--mono);font-size:10.5px;letter-spacing:.14em;
 text-transform:uppercase;color:var(--soft)}
.chip{font-family:var(--mono);font-size:11px;color:var(--soft);text-align:right;
 display:flex;align-items:center;gap:7px;white-space:nowrap}
.chip .dot{width:7px;height:7px;border-radius:50%;background:var(--teal);flex:none;
 box-shadow:0 0 0 0 rgba(14,110,91,.5);animation:beat 2.4s infinite}
@keyframes beat{0%{box-shadow:0 0 0 0 rgba(14,110,91,.45)}70%{box-shadow:0 0 0 6px rgba(14,110,91,0)}100%{box-shadow:0 0 0 0 rgba(14,110,91,0)}}

/* conversation */
main{flex:1;width:100%;max-width:880px;margin:auto;padding:26px 22px 30px}
.intro{font-family:var(--serif);font-size:18px;color:var(--soft);
 border-left:2px solid var(--line);padding:2px 0 2px 16px;margin:6px 0 30px}
.intro b{color:var(--ink);font-weight:500}
.turn{margin:0 0 34px}
.ask{margin:0 0 14px}
.ask .q{font-size:17px;font-weight:500;color:var(--ink);margin-top:3px}

/* work tape — the signature ledger */
.tape{border-left:1.5px solid var(--line);margin:0 0 4px;padding:2px 0 2px 0}
.step{position:relative;padding:7px 0 7px 22px;display:flex;gap:9px;
 align-items:flex-start;animation:rise .28s ease both}
.step::before{content:"";position:absolute;left:-5.5px;top:13px;width:9px;height:9px;
 border-radius:50%;background:var(--paper);border:1.5px solid var(--teal)}
.step.res::before{border-color:var(--line);background:var(--line)}
.step.appr::before{border-color:var(--gold);background:var(--gold-tint)}
@keyframes rise{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}
.badge{font-family:var(--mono);font-size:9.5px;letter-spacing:.12em;text-transform:uppercase;
 padding:3px 7px;border-radius:3px;flex:none;line-height:1.3;margin-top:1px}
.badge.tool{background:var(--teal-tint);color:var(--teal-deep)}
.badge.skill{background:var(--gold-tint);color:var(--gold)}
.badge.subagent{background:var(--teal-deep);color:#fff}
.badge.res{background:#EEEAE0;color:var(--soft)}
.dur{font-family:var(--mono);font-size:10px;color:var(--faint);margin-left:8px;
 letter-spacing:.03em}
.step .body{min-width:0;flex:1}
.step .nm{font-family:var(--mono);font-size:13px;color:var(--ink);font-weight:500}
.step.res .nm{color:var(--soft);font-weight:400}
.args{font-family:var(--mono);font-size:11.5px;color:var(--soft);margin-top:2px;
 word-break:break-word}
.args .k{color:var(--faint)}
.preview{font-family:var(--mono);font-size:11.5px;color:var(--soft);margin-top:2px;
 word-break:break-word;line-height:1.4}

/* working pulse */
.work{display:flex;align-items:center;gap:9px;padding:9px 0 4px 22px;position:relative}
.work::before{content:"";position:absolute;left:-4px;top:13px;width:7px;height:7px;
 border-radius:50%;background:var(--teal);animation:blink 1s infinite}
@keyframes blink{50%{opacity:.25}}
.work span{font-family:var(--mono);font-size:11px;letter-spacing:.1em;
 text-transform:uppercase;color:var(--faint)}

/* briefing card */
.briefing{background:var(--card);border:1px solid var(--line);border-radius:10px;
 padding:20px 24px 4px;margin:14px 0 0;box-shadow:0 1px 0 rgba(27,36,48,.03),0 14px 30px -22px rgba(27,36,48,.35)}
.briefing .lbl{display:flex;align-items:center;gap:8px;margin-bottom:6px}
.briefing .lbl::before{content:"";width:9px;height:9px;background:var(--teal);
 transform:rotate(45deg)}
.doc{font-family:var(--serif);font-size:16.5px;line-height:1.62;color:var(--ink)}
.doc h1,.doc h2,.doc h3{font-family:var(--display);font-weight:600;line-height:1.25;
 margin:18px 0 6px}
.doc h1{font-size:22px}.doc h2{font-size:19px}.doc h3{font-size:16.5px}
.doc p{margin:10px 0}.doc strong{font-weight:600;color:var(--ink)}
.doc ul,.doc ol{margin:8px 0;padding-left:22px}.doc li{margin:5px 0}
.doc code{font-family:var(--mono);font-size:.86em;background:var(--paper);
 padding:1px 5px;border-radius:4px}
.doc em{color:var(--soft)}
.doc table{border-collapse:collapse;margin:12px 0;font-family:var(--sans);font-size:14px}
.doc th,.doc td{border:1px solid var(--line);padding:6px 11px;text-align:left}
.doc th{background:var(--paper);font-weight:600}

/* approval (HITL) */
.appr-card{background:var(--amber-bg);border:1px solid var(--gold);border-radius:9px;
 padding:14px 16px;margin:12px 0 2px}
.appr-card .t{font-weight:600;color:var(--amber);margin-bottom:3px}
.appr-card .d{font-family:var(--serif);font-size:14.5px;color:#6b4e12;margin-bottom:11px}
.appr-card .row{display:flex;gap:9px}
.btn{font-family:var(--sans);font-size:14px;font-weight:500;border:0;border-radius:7px;
 padding:9px 18px;cursor:pointer}
.btn.go{background:var(--teal);color:#fff}.btn.go:hover{background:var(--teal-deep)}
.btn.no{background:transparent;color:var(--amber);border:1px solid var(--gold)}
.btn.no:hover{background:var(--gold-tint)}

.err{background:var(--red-bg);border:1px solid #E3B7B0;border-radius:9px;
 padding:12px 15px;margin:12px 0 0;color:var(--red);font-size:14px}

/* composer */
footer{position:sticky;bottom:0;background:linear-gradient(180deg,rgba(246,244,239,0),var(--paper) 26%);
 padding-top:8px}
.dock{max-width:880px;margin:auto;padding:6px 22px 20px}
.chips{display:flex;gap:8px;overflow-x:auto;padding:4px 0 12px;scrollbar-width:none}
.chips::-webkit-scrollbar{display:none}
.chips button{flex:none;font-family:var(--sans);font-size:13px;color:var(--soft);
 background:var(--card);border:1px solid var(--line);border-radius:999px;
 padding:7px 14px;cursor:pointer;white-space:nowrap}
.chips button:hover{border-color:var(--teal);color:var(--teal-deep)}
.modelbar{display:flex;justify-content:flex-end;align-items:center;gap:7px;
 padding:0 2px 8px;font-family:var(--mono);font-size:10.5px;letter-spacing:.08em;
 text-transform:uppercase;color:var(--faint)}
.modelbar select{font-family:var(--mono);font-size:11px;letter-spacing:0;
 text-transform:none;color:var(--soft);background:var(--card);border:1px solid var(--line);
 border-radius:7px;padding:4px 9px;cursor:pointer}
.modelbar select:hover{border-color:var(--teal)}
.compose{display:flex;gap:10px;background:var(--card);border:1px solid var(--line);
 border-radius:12px;padding:7px 7px 7px 16px;box-shadow:0 10px 26px -20px rgba(27,36,48,.4)}
.compose:focus-within{border-color:var(--teal)}
#q{flex:1;border:0;outline:0;background:transparent;font-family:var(--sans);
 font-size:15.5px;color:var(--ink)}
#q::placeholder{color:var(--faint)}
.compose .btn.go{padding:10px 22px}
@media(max-width:560px){.brand .sub{display:none}.mast{padding:13px 16px}
 main{padding:20px 16px}.dock{padding:6px 16px 16px}}
</style></head>
<body>
<header><div class=mast>
 <div class=brand><span class=mark></span>
  <h1>Grand Harbour Hotel</h1><span class=sub>Revenue Desk · on-the-books intelligence</span></div>
 <div class=chip id=health><span class=dot></span><span>connecting…</span></div>
</div></header>

<main id=log>
 <p class=intro>Ask about <b>on-the-books revenue, pace, segments, or risk</b>.
  The desk shows its work — every tool and skill it consults — then writes the briefing.</p>
</main>

<footer><div class=dock>
 <div class=modelbar id=modelbar><span>Model</span><select id=model></select></div>
 <div class=chips id=chips></div>
 <div class=compose>
  <input id=q placeholder="What's driving July? Are we too dependent on OTA?" autofocus>
  <button class="btn go" onclick=send()>Ask</button>
 </div>
</div></footer>

<script>
marked.setOptions({breaks:true});
const thread='web-'+Math.random().toString(36).slice(2);
const log=document.getElementById('log');
let turn=null;

const SAMPLES=[
 "What's the July 2026 OTB summary?",
 "Which segments are driving July 2026?",
 "Are we too dependent on OTA?",
 "How does July 2026 compare to last year?",
 "As of 2026-05-01, how did July 2026 OTB look?"];
const chips=document.getElementById('chips');
SAMPLES.forEach(s=>{const b=document.createElement('button');b.textContent=s;
 b.onclick=()=>{document.getElementById('q').value=s;send();};chips.appendChild(b);});

const modelSel=document.getElementById('model');
fetch('/models').then(r=>r.json()).then(m=>{
 modelSel.innerHTML=m.options.map(o=>'<option value="'+esc(o.spec)+'"'+
  (o.spec===m.default?' selected':'')+'>'+esc(o.label)+'</option>').join('');
 if((m.options||[]).length<2)document.getElementById('modelbar').style.display='none';
}).catch(()=>{document.getElementById('modelbar').style.display='none';});
function curModel(){return modelSel.value||undefined;}

fetch('/health').then(r=>r.json()).then(h=>{
 const fp=(h.row_hash||h.db_fingerprint||'').slice(0,8);
 document.getElementById('health').innerHTML=
  '<span class=dot></span><span>rev '+(h.dataset_revision||'?')+' · '+
  (h.financial_status_posted_only_rows||0)+' posted rows · fp '+fp+'</span>';
}).catch(()=>{});

function el(tag,cls,html){const d=document.createElement(tag);if(cls)d.className=cls;
 if(html!=null)d.innerHTML=html;return d;}
function esc(s){return (s==null?'':String(s)).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
function fmtArgs(a){if(!a||!Object.keys(a).length)return '';
 return Object.entries(a).map(([k,v])=>'<span class=k>'+esc(k)+'</span> '+esc(v)).join('  ·  ');}
function scroll(){window.scrollTo({top:document.body.scrollHeight,behavior:'smooth'});}

function newTurn(q){
 const t=el('section','turn');
 t.appendChild(el('div','ask','<div class=eyebrow>You asked</div><div class=q>'+esc(q)+'</div>'));
 const tape=el('div','tape');tape.appendChild(el('div','eyebrow','&nbsp;Work tape'));
 t.appendChild(tape);log.appendChild(t);
 turn={root:t,tape:tape};working(true);scroll();
}
function working(on){
 if(!turn)return;let w=turn.tape.querySelector('.work');
 if(on){if(!w){w=el('div','work','<span>the desk is working</span>');turn.tape.appendChild(w);}}
 else if(w)w.remove();
}
function fmtMs(ms){return ms>=1000?(ms/1000).toFixed(ms>=10000?0:1)+'s':ms+'ms';}
function step(kind,name,args,preview,ms){
 const cls=kind==='result'?'step res':kind==='subagent'?'step sub':'step';
 const badge=kind==='skill'?'<span class="badge skill">skill</span>'
   :kind==='subagent'?'<span class="badge subagent">subagent</span>'
   :kind==='result'?'<span class="badge res">result</span>'
   :'<span class="badge tool">tool</span>';
 const dur=(ms!=null)?'<span class=dur>'+fmtMs(ms)+'</span>':'';
 let body='<div class=nm>'+esc(name)+dur+'</div>';
 if(kind==='result')body+='<div class=preview>'+esc(preview)+'</div>';
 else{const a=fmtArgs(args);if(a)body+='<div class=args>'+a+'</div>';}
 const s=el('div',cls,badge+'<div class=body>'+body+'</div>');
 const w=turn.tape.querySelector('.work');
 if(w)turn.tape.insertBefore(s,w);else turn.tape.appendChild(s);
 scroll();
}
function briefing(text){
 working(false);
 const c=el('div','briefing','<div class=lbl><span class=eyebrow>Briefing</span></div>'+
  '<div class=doc>'+marked.parse(text||'')+'</div>');
 turn.root.appendChild(c);scroll();
}
function approval(){
 working(false);
 const c=el('div','appr-card',
  '<div class=t>Approval required</div>'+
  '<div class=d>This is a point-in-time rebuild (<code>get_as_of_otb</code>) — '+
  'confirm the as-of snapshot before the desk runs it.</div>'+
  '<div class=row><button class="btn go">Approve</button>'+
  '<button class="btn no">Reject</button></div>');
 const s=el('div','step appr','<span class="badge skill">approval</span>'+
  '<div class=body></div>');
 s.querySelector('.body').appendChild(c);turn.tape.appendChild(s);
 c.querySelector('.go').onclick=()=>{s.remove();decide(true);};
 c.querySelector('.no').onclick=()=>{s.remove();decide(false);};
 scroll();
}

async function stream(url,payload){
 try{
  const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},
   body:JSON.stringify(payload)});
  const rd=r.body.getReader(),dec=new TextDecoder();let buf='';
  while(true){const{done,value}=await rd.read();if(done)break;
   buf+=dec.decode(value,{stream:true});
   let i;while((i=buf.indexOf('\\n\\n'))>=0){
    const line=buf.slice(0,i).replace(/^data: /,'');buf=buf.slice(i+2);
    if(!line)continue;const e=JSON.parse(line);
    if(e.type==='tool')step('tool',e.name,e.args);
    else if(e.type==='subagent')step('subagent',e.name,e.args);
    else if(e.type==='skill')step('skill',e.name,e.args);
    else if(e.type==='result')step('result',e.name,null,e.preview,e.ms);
    else if(e.type==='interrupt')approval();
    else if(e.type==='error'){working(false);turn.root.appendChild(el('div','err','⚠ '+esc(e.message)));scroll();}
    else if(e.type==='answer')briefing(e.text);
    else if(e.type==='done')working(false);
   }}
 }catch(err){working(false);if(turn)turn.root.appendChild(el('div','err','⚠ '+esc(err.message)));}
}
function send(){const q=document.getElementById('q');const v=q.value.trim();if(!v)return;
 newTurn(v);q.value='';stream('/chat',{message:v,thread,model:curModel()});}
function decide(approve){working(true);stream('/resume',{approve,thread,model:curModel()});}
document.getElementById('q').addEventListener('keydown',e=>{if(e.key==='Enter')send();});
</script></body></html>"""


@app.get("/", response_class=HTMLResponse)
def index(user: str = Depends(require_auth)):
    return PAGE
