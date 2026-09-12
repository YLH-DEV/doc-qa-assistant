# -*- coding: utf-8 -*-
"""
app.py — 星野考研资料问答 · 本地网页版

用法：python app.py
然后浏览器打开 http://127.0.0.1:8090
手机连同一个 WiFi，打开 http://<电脑局域网IP>:8090

复用 kb_local.py 的资料读取、检索与 DeepSeek 调用逻辑。
"""
import json
import os
import socket
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = BASE
sys.path.insert(0, ROOT)

import kb_local as kb  # noqa: E402

PORT = 8090

# 启动时读一次资料（3 个文件很小，秒级）
CHUNKS = []
for _f in kb.FILES:
    CHUNKS.extend(kb.extract_chunks(_f))

SYSTEM_PROMPT = (
    "你是星野考研的客服助手。必须遵守以下五条规则：\n"
    "1. 只依据下方【资料】中提供的内容回答，不得使用资料以外的任何知识。\n"
    "2. 每条回答末尾必须附出处，格式为文件名+段落位置。\n"
    "3. 如果资料里没有相关信息，直接回答“资料里没有相关信息”，不要推测。\n"
    "4. 如果问题包含多个子问题，必须逐个分别回答，不得遗漏任何一个。\n"
    "5. 回答必须覆盖【资料】中与问题相关的全部要点，包括条件、备注、适用范围等细节。\n"
    "回答要简洁、口语化，像客服在跟学员说话。"
)

PAGE = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>星野考研 · 资料问答助手</title>
<style>
*{box-sizing:border-box}
body{margin:0;background:#12151a;color:#e8e8e8;font-family:"Microsoft YaHei",system-ui,sans-serif;
     display:flex;flex-direction:column;height:100vh}
header{padding:14px 18px;background:#1b1e21;border-bottom:1px solid #2a2f33;display:flex;align-items:center;gap:12px}
.dot{width:38px;height:38px;border-radius:50%;background:#3ba55d;display:flex;align-items:center;
     justify-content:center;font-weight:bold;font-size:20px;color:#fff}
.name{font-weight:bold;font-size:17px}
.sub{font-size:12px;color:#9aa0a6;margin-top:2px}
#log{flex:1;overflow-y:auto;padding:18px 14px}
.row{display:flex;margin:10px 0}
.row.me{justify-content:flex-end}
.bub{max-width:82%;padding:12px 16px;border-radius:16px;line-height:1.7;font-size:15px;white-space:pre-wrap}
.me .bub{background:#95ec69;color:#0e1a0c}
.ai .bub{background:#26292c;color:#f0f0f0}
.cite{margin-top:8px;font-size:12px;color:#9aa0a6;border-top:1px dashed #3a3f44;padding-top:8px}
.hits{margin-top:6px;font-size:12px;color:#8b949e;display:none}
.hits.show{display:block}
.hits div{opacity:.85;margin-top:2px}
footer{padding:12px 14px;background:#1b1e21;border-top:1px solid #2a2f33;display:flex;gap:10px}
input{flex:1;padding:13px 16px;border-radius:22px;border:none;background:#26292c;color:#e8e8e8;font-size:15px;outline:none}
button{width:52px;border:none;border-radius:50%;background:#95ec69;color:#0e1a0c;font-size:20px;font-weight:bold;cursor:pointer}
button:disabled{opacity:.5}
.tip{font-size:12px;color:#6e7681;text-align:center;padding:6px}
</style></head><body>
<header>
  <div class="dot">星</div>
  <div><div class="name">星野考研 · 资料问答助手</div>
  <div class="sub">在线 · 已加载 3 份资料 · 回答带出处</div></div>
</header>
<div id="log"><div class="tip">问我：我开课后第10天想退课，能退多少？</div></div>
<footer>
  <input id="q" placeholder="输入你的问题…" autocomplete="off">
  <button id="send">↑</button>
</footer>
<script>
const log=document.getElementById('log'),q=document.getElementById('q'),btn=document.getElementById('send');
function add(cls,text,cite,hits){
  const row=document.createElement('div');row.className='row '+cls;
  const b=document.createElement('div');b.className='bub';b.textContent=text;
  if(cite){const c=document.createElement('div');c.className='cite';c.textContent='出处：'+cite;b.appendChild(c);}
  if(hits&&hits.length){
    const h=document.createElement('div');h.className='hits';
    hits.forEach(x=>{const d=document.createElement('div');d.textContent='· '+x;h.appendChild(d);});
    const t=document.createElement('div');t.style.cursor='pointer';t.style.marginTop='6px';
    t.textContent='▸ 查看命中的资料';t.onclick=()=>h.classList.toggle('show');
    b.appendChild(t);b.appendChild(h);
  }
  row.appendChild(b);log.appendChild(row);log.scrollTop=log.scrollHeight;
}
async function ask(){
  const v=q.value.trim();if(!v)return;
  q.value='';btn.disabled=true;
  add('me',v);
  const ai=document.createElement('div');ai.className='row ai';
  const b=document.createElement('div');b.className='bub';b.textContent='正在查资料…';
  ai.appendChild(b);log.appendChild(ai);log.scrollTop=log.scrollHeight;
  try{
    const r=await fetch('/ask',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({q:v})});
    const d=await r.json();
    ai.remove();add('ai',d.answer,d.cite,d.hits);
  }catch(e){ai.remove();add('ai','出错了：'+e);}
  btn.disabled=false;q.focus();
}
btn.onclick=ask;
q.addEventListener('keydown',e=>{if(e.key==='Enter')ask();});
q.focus();
</script></body></html>"""


def build_answer(question):
    hits = kb.retrieve(CHUNKS, question)
    context = "\n".join(f"[{src}] {t}" for _, t, src in hits)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"[资料]\n{context}\n\n[问题]\n{question}"},
    ]
    answer, usage = kb.ask_deepseek(messages)
    model = "DeepSeek"
    if answer is None:
        answer, usage = kb.ask_ollama(messages)
        model = "本机模型"
    cite = ""
    lines = [l.strip() for l in (answer or "").splitlines() if l.strip()]
    if lines and ("出处" in lines[-1] or "来源" in lines[-1]):
        cite = lines[-1].split("：", 1)[-1].split(":", 1)[-1].strip()
        answer = "\n".join(lines[:-1])
    return {
        "answer": answer or "（没有拿到回答）",
        "cite": cite,
        "hits": [f"[{src}] {t[:60]}" for _, t, src in hits[:4]],
        "model": model,
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, code, body, ctype):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, PAGE, "text/html; charset=utf-8")
        else:
            self._send(404, "not found", "text/plain; charset=utf-8")

    def do_POST(self):
        if self.path != "/ask":
            self._send(404, "not found", "text/plain; charset=utf-8")
            return
        try:
            n = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(n).decode("utf-8"))
            question = (payload.get("q") or "").strip()
            if not question:
                self._send(400, json.dumps({"answer": "请输入问题"}), "application/json")
                return
            result = build_answer(question)
            self._send(200, json.dumps(result, ensure_ascii=False), "application/json; charset=utf-8")
        except Exception as exc:  # noqa: BLE001
            self._send(500, json.dumps({"answer": f"服务出错：{exc}"}, ensure_ascii=False),
                       "application/json; charset=utf-8")


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("223.5.5.5", 80))
        return s.getsockname()[0]
    except Exception:  # noqa: BLE001
        return "127.0.0.1"
    finally:
        s.close()


if __name__ == "__main__":
    print("=" * 52)
    print("  星野考研 · 资料问答助手（本地网页版）")
    print("=" * 52)
    print(f"  已加载资料：{len(CHUNKS)} 段")
    print(f"  电脑上打开：http://127.0.0.1:{PORT}")
    print(f"  手机上打开：http://{lan_ip()}:{PORT}   （需同一个 WiFi）")
    print("  停止服务：按 Ctrl + C")
    print("=" * 52)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
