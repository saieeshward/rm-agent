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

import datetime
import hashlib
import json
import os
import secrets

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from langchain_core.messages import AIMessage, ToolMessage

from tools.db import query, query_one

app = FastAPI(title="Revenue Manager Agent")
security = HTTPBasic()
USER = os.environ.get("BASIC_AUTH_USER", "gm")
PASSWORD = os.environ.get("BASIC_AUTH_PASS", "hackathon")

_agent = None


def get_agent():
    global _agent
    if _agent is None:
        from agent.build import build_agent
        _agent = build_agent()
    return _agent


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


def _events(chunk: dict):
    for _node, update in chunk.items():
        msgs = (update or {}).get("messages", []) if isinstance(update, dict) else []
        for msg in msgs:
            if isinstance(msg, AIMessage):
                for tc in (msg.tool_calls or []):
                    name = tc["name"]
                    kind = "skill" if name in ("read_file", "ls", "glob", "grep") else "tool"
                    yield {"type": kind, "name": name, "args": tc.get("args", {})}
            elif isinstance(msg, ToolMessage):
                yield {"type": "result", "name": msg.name,
                       "preview": str(msg.content)[:200].replace("\n", " ")}


def _final_text(state) -> str:
    msg = state.values["messages"][-1]
    content = getattr(msg, "content", "")
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content
                         if isinstance(b, dict) and b.get("type") == "text") or str(content)
    return content


def _stream(payload, thread: str):
    cfg = {"configurable": {"thread_id": thread}, "recursion_limit": 50}
    try:
        for chunk in get_agent().stream(payload, config=cfg, stream_mode="updates"):
            for ev in _events(chunk):
                yield _sse(ev)
        state = get_agent().get_state(cfg)
        if state.next:
            yield _sse({"type": "interrupt", "tool": "get_as_of_otb",
                        "message": "Point-in-time rebuild needs approval."})
        else:
            yield _sse({"type": "answer", "text": _final_text(state)})
    except Exception as exc:  # surface model/rate-limit errors instead of hanging
        msg = str(exc)
        if "RESOURCE_EXHAUSTED" in msg or "429" in msg or "rate" in msg.lower():
            msg = "Model rate limit / quota exceeded — retry shortly or use a model with more capacity."
        yield _sse({"type": "error", "message": msg[:400]})
    yield _sse({"type": "done"})


@app.post("/chat")
async def chat(request: Request, user: str = Depends(require_auth)):
    body = await request.json()
    thread = body.get("thread", "web")
    today = datetime.date.today().isoformat()
    primer = (f"(Context: today is {today}; dataset anchor ~2026-06-16; stay months "
              f"are 'YYYY-MM', STLY = year minus one.)\n\n")
    payload = {"messages": [{"role": "user", "content": primer + body["message"]}]}
    return StreamingResponse(_stream(payload, thread), media_type="text/event-stream")


@app.post("/resume")
async def resume(request: Request, user: str = Depends(require_auth)):
    from langgraph.types import Command
    body = await request.json()
    thread = body.get("thread", "web")
    approve = bool(body.get("approve"))
    decision = {"type": "approve"} if approve else {"type": "reject", "message": "Not approved by GM."}
    payload = Command(resume={"decisions": [decision]})
    return StreamingResponse(_stream(payload, thread), media_type="text/event-stream")


# --------------------------------------------------------------------------- #
# minimal chat UI (streams tool/skill calls; approve/reject on interrupt)
# --------------------------------------------------------------------------- #
PAGE = """<!doctype html><html><head><meta charset=utf-8><title>Revenue Manager</title>
<style>body{font:15px system-ui;margin:0;background:#0f1117;color:#e6e6e6}
header{padding:14px 20px;background:#161922;font-weight:600}
#log{padding:16px 20px;max-width:820px;margin:auto}
.ev{font:12px ui-monospace;color:#8aa;margin:2px 0}.res{color:#6a6}
.answer{white-space:pre-wrap;background:#161922;padding:14px;border-radius:8px;margin:10px 0;border-left:3px solid #6366f1}
.you{color:#9ab;margin-top:18px}#bar{display:flex;gap:8px;padding:16px 20px;max-width:820px;margin:auto}
input{flex:1;padding:10px;border-radius:8px;border:1px solid #333;background:#0b0d12;color:#eee}
button{padding:10px 16px;border:0;border-radius:8px;background:#6366f1;color:#fff;cursor:pointer}
#hitl{display:none;gap:8px;margin:8px 0}.warn{background:#3a2a00;border-left-color:#fb0}</style></head>
<body><header>Revenue Manager Agent — show-your-work</header>
<div id=log></div>
<div id=hitl><span class=ev>get_as_of_otb needs approval</span>
<button onclick=decide(true)>Approve</button><button onclick=decide(false)>Reject</button></div>
<div id=bar><input id=q placeholder="What's driving July? Are we too dependent on OTA?" autofocus>
<button onclick=send()>Ask</button></div>
<script>
const thread = 'web-' + Math.random().toString(36).slice(2);
const log = document.getElementById('log'), hitl = document.getElementById('hitl');
function add(html,cls){const d=document.createElement('div');d.className=cls;d.innerHTML=html;log.appendChild(d);window.scrollTo(0,document.body.scrollHeight);return d;}
async function stream(url,payload){
  const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  const rd=r.body.getReader(),dec=new TextDecoder();let buf='';
  while(true){const{done,value}=await rd.read();if(done)break;buf+=dec.decode(value,{stream:true});
    let i;while((i=buf.indexOf('\\n\\n'))>=0){const line=buf.slice(0,i).replace(/^data: /,'');buf=buf.slice(i+2);
      if(!line)continue;const e=JSON.parse(line);
      if(e.type==='tool')add('→ tool: '+e.name+' '+JSON.stringify(e.args),'ev');
      else if(e.type==='skill')add('→ skill: '+e.name+' '+JSON.stringify(e.args),'ev');
      else if(e.type==='result')add('  ↳ '+e.name+': '+e.preview,'ev res');
      else if(e.type==='interrupt'){hitl.style.display='flex';}
      else if(e.type==='error')add('⚠ '+e.message,'answer warn');
      else if(e.type==='answer')add(e.text,'answer');
    }}}
function send(){const q=document.getElementById('q');if(!q.value)return;add('You: '+q.value,'you');stream('/chat',{message:q.value,thread});q.value='';}
function decide(approve){hitl.style.display='none';stream('/resume',{approve,thread});}
document.getElementById('q').addEventListener('keydown',e=>{if(e.key==='Enter')send();});
</script></body></html>"""


@app.get("/", response_class=HTMLResponse)
def index(user: str = Depends(require_auth)):
    return PAGE
