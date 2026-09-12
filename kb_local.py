# -*- coding: utf-8 -*-
"""
kb_local.py — 星野考研 · 本地最小知识库问答（无需任何账号/云端API）
- 读取 01/02/03 三个文件提取纯文本（docx 用 python-docx，xlsx 用 openpyxl）
- 按段落切块，用标准库做关键词/字符bigram检索（不装重型依赖）
- 取最相关若干块拼进提示词，调用本机 Ollama（qwen3:8b）

用法：
    python kb_local.py "我开课后第10天想退课，能退多少？"
"""
import os
import sys
import json
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FILES = ["samples/01-退费与转班规则-V3.docx", "samples/02-2027全程班-课程价格表.xlsx", "samples/03-学员高频问题FAQ.docx"]

OLLAMA_URL = "http://127.0.0.1:11434/v1/chat/completions"
OLLAMA_MODEL = "qwen3:8b"
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-flash"
TIMEOUT = 300          # 秒，模型调用较慢
TOP_K = 4              # 取最相关块数

# ===================== 文本提取 =====================
def extract_chunks(filename):
    """返回 [(text, source)]，source 为 文件名+段落位置。"""
    path = os.path.join(BASE_DIR, filename)
    chunks = []
    if filename.endswith(".docx"):
        from docx import Document
        doc = Document(path)
        for i, p in enumerate(doc.paragraphs):
            t = p.text.strip()
            if t:
                chunks.append((t, f"{filename}·第{i}段"))
    elif filename.endswith(".xlsx"):
        from openpyxl import load_workbook
        wb = load_workbook(path, data_only=True)
        for ws in wb.worksheets:
            for ridx, row in enumerate(ws.iter_rows(values_only=True), start=1):
                vals = [str(c) for c in row if c is not None and str(c).strip()]
                if vals:
                    chunks.append(("；".join(vals), f"{filename}·第{ridx}行·工作表{ws.title}"))
    return chunks

# ===================== 检索（纯标准库） =====================
def _clean(s):
    return "".join(ch for ch in s.lower() if not ch.isspace())

def _bigrams(s):
    return {s[i:i+2] for i in range(len(s) - 1)}

def score(qclean, cclean):
    qc = set(qclean); cc = set(cclean)
    qbg = _bigrams(qclean); cbg = _bigrams(cclean)
    bigram_hit = len(qbg & cbg)
    char_hit = len(qc & cc)
    return bigram_hit * 2 + char_hit

def retrieve(chunks, question, k=TOP_K):
    qclean = _clean(question)
    scored = sorted(((score(qclean, _clean(t)), t, src) for t, src in chunks),
                    key=lambda x: x[0], reverse=True)
    hit = [x for x in scored if x[0] > 0]
    best = hit if hit else scored
    return best[:k]

# ===================== 模型调用（DeepSeek 主 + Ollama 兜底） =====================
def _post(url, headers, payload):
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))

def _parse(data):
    return data["choices"][0]["message"]["content"], data.get("usage", {})

def read_api_key():
    key = os.environ.get("DEEPSEEK_API_KEY", "") or ""
    if key:
        return key.strip()
    envfile = os.path.join(BASE_DIR, ".env")
    if os.path.isfile(envfile):
        with open(envfile, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("DEEPSEEK_API_KEY="):
                    return line.split("=", 1)[1].strip().strip("\"'")
    return ""

def _price_multiplier():
    from datetime import datetime
    now = datetime.now()
    if now.weekday() < 5 and (9 <= now.hour < 12 or 14 <= now.hour < 18):
        return 2
    return 1

def deepseek_stats(usage):
    """返回 (输入token, 输出token, 估算费用元)。工作日 9-12 / 14-18 费用翻倍。"""
    prompt = usage.get("prompt_tokens", 0)
    cached = (usage.get("prompt_tokens_details", {}) or {}).get("cached_tokens", 0)
    miss = max(prompt - cached, 0)
    completion = usage.get("completion_tokens", 0)
    mult = _price_multiplier()
    cost = (miss * 1.0 + cached * 0.02) / 1_000_000 * mult + (completion * 4.0) / 1_000_000 * mult
    return prompt, completion, cost

def ask_deepseek(messages):
    """优先 DeepSeek。无 key 或调用失败 → 返回 (None, None)。"""
    key = read_api_key()
    if not key:
        return None, None
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {key}"}
    payload = {"model": DEEPSEEK_MODEL, "messages": messages, "stream": False}
    try:
        return _parse(_post(DEEPSEEK_URL, headers, payload))
    except Exception:
        return None, None

def ask_ollama(messages):
    """本机 Ollama 兜底，免费。"""
    headers = {"Content-Type": "application/json"}
    payload = {"model": OLLAMA_MODEL, "messages": messages, "stream": False}
    return _parse(_post(OLLAMA_URL, headers, payload))

def main():
    if len(sys.argv) < 2:
        print("用法: python kb_local.py \"你的问题\"")
        sys.exit(1)
    question = sys.argv[1]

    chunks = []
    for f in FILES:
        chunks.extend(extract_chunks(f))
    if not chunks:
        print("未能读到任何资料，请检查文件是否存在。")
        sys.exit(1)

    top = retrieve(chunks, question)
    context = "\n".join(f"[{src}] {t}" for _, t, src in top)

    system_prompt = (
        "你是星野考研的客服助手。必须遵守以下五条规则：\n"
        "1. 只依据下方【资料】中提供的内容回答，不得使用资料以外的任何知识。\n"
        "2. 每条回答末尾必须附出处，格式为文件名+段落位置。\n"
        "3. 如果资料里没有相关信息，直接回答“资料里没有相关信息”，不要推测。\n"
        "4. 如果问题包含多个子问题，必须逐个分别回答，不得遗漏任何一个。\n"
        "5. 回答必须覆盖【资料】中与问题相关的全部要点，包括条件、备注、适用范围等细节。"
    )
    user_prompt = f"[资料]\n{context}\n\n[问题]\n{question}"
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    # 优先 DeepSeek，失败回退本机 Ollama
    model_id = OLLAMA_MODEL
    model_display = "Ollama 本机(兜底)"
    try:
        answer, usage = ask_deepseek(messages)
        if answer is not None:
            model_id = DEEPSEEK_MODEL
            model_display = "DeepSeek API"
        else:
            answer, usage = ask_ollama(messages)
    except Exception as e:
        print(f"DeepSeek 调用异常，回退 Ollama：{e}")
        answer, usage = ask_ollama(messages)

    if answer is None:
        print("两次调用均失败，无法回答。")
        sys.exit(1)

    # 用量与估算费用
    x_in = usage.get("prompt_tokens", 0)
    x_out = usage.get("completion_tokens", 0)
    if model_id == DEEPSEEK_MODEL:
        _, _, cost = deepseek_stats(usage)
        cost_str = f"≈¥{cost:.4f}"
    else:
        cost_str = "¥0（本机免费）"

    print(f"\n当前使用模型：{model_display}")
    print(f"使用模型：{model_id} | 输入token：{x_in} | 输出token：{x_out} | 估算费用：{cost_str}")

    print("== 命中资料 ==")
    for _, t, src in top:
        print(f"- [{src}] {t}")
    print("\n== 回答 ==")
    print(answer)

if __name__ == "__main__":
    main()