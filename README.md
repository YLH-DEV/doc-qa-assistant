# Document Q&A Assistant · 企业资料智能问答系统

把一堆 PDF / Word / Excel 变成"能直接问"的助手 ——
**每条回答都带原文出处，资料里没有的会直接说"没有"，不瞎编。**

[English ↓](#english)

---

## 为什么做这个

客服、HR、招生老师每天被同样的问题重复消耗（退费规则、价格政策、售后流程），
而且不同人回答的口径不一致 —— 一次答错就可能引发纠纷。

把资料整理成"能直接问"的助手，是成本最低的解法。

## 核心设计（三个关键决定）

**1. 分块保留出处坐标**
按段落切块，每块记录"出自哪份文件第几段"，回答必须附带这个坐标 —— 让答案可核对。

**2. 用三条硬规则控制幻觉**
① 只依据资料回答 ② 每条回答必须附出处 ③ 资料里没有的直接说"没有"，不许推测。

**3. 用验收集代替"感觉还行"**
5 题验收：3 题资料内（考准确率）+ 2 题资料外（考拒答）。
把"会不会瞎编"变成**可测指标**，而不是主观感受。

## 架构

```text
资料(PDF/Word/Excel) → 文本提取 → 按段切块(保留段号)
    → 字符 bigram 关键词检索(top-6) → 组装提示词(3 条规则)
    → DeepSeek API（或本机 Ollama 兜底） → 答案 + 出处 → Web 界面
```

## 项目结构

```text
.
├─ kb_local.py        # 命令行问答
├─ app.py             # Web 版问答界面（http://127.0.0.1:8090）
├─ requirements.txt
├─ .env.example       # 复制成 .env 并填入你的 API key
├─ samples/           # 演示资料（虚构的培训机构文档，可直接跑）
└─ docs/
   └─ evaluation.md   # 5 题验收记录 + 踩坑复盘 + 成本测算
```

## 快速开始

```bash
pip install -r requirements.txt

# 配置 API key（不配也能跑：会自动回退到本机 Ollama）
cp .env.example .env        # Windows: copy .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY=sk-xxxx

# 命令行问一句
python kb_local.py "开课后第10天想退课，能退多少？"

# 或起 Web 界面
python app.py               # 打开 http://127.0.0.1:8090
```

## 实测结果（用 `samples/` 里的资料）

| 问题 | 结果 |
|---|---|
| 开课后第10天退课能退多少？ | ✅ 「扣除已上课时费用后，退还剩余金额的 70%」+ 出处（第 11 段） |
| 二战特训营早鸟价多少？ | ✅ 「8800 元，需提供上一年准考证，且不可与联报优惠叠加」 |
| 报名要带什么材料？ | ✅ 材料三项齐全 |
| 你们支持花呗分期吗？（资料里没有） | ✅ 正确拒答「资料里没有相关信息」 |
| 退课时赠送的资料要不要扣钱？（规则未写明） | ✅ 正确拒答，未编造 |

完整验收记录见 [`docs/evaluation.md`](docs/evaluation.md)。

## 技术选型：为什么用关键词检索，不用向量库？

- 资料规模只有几十页，关键词召回的准确率已经够用
- **零依赖、零成本**（向量库要额外服务或本地推理）
- **可解释**：出问题能直接看到命中了哪一段，方便调试和向客户解释

什么时候该换向量检索：资料上百页、用户问法高度口语化、需要跨文档语义匹配时。
（那时还要配套做两阶段检索：粗召回 → 精排）

## 成本

| 项目 | 数值 |
|---|---|
| 单次问答 | 约 ¥0.0038 |
| 一千次问答 | 约 ¥3.8 |
| 每天 500 次（月） | 约 ¥57 |

优化手段（按效果排序）：缓存高频问答（实测缓存命中率 97.6%，命中价便宜 50 倍）、
缩小 TOP_K、模型分级、避开高峰时段（半价）、本机模型兜底。

## 已知边界（诚实说明）

- 只支持**电子版**文档；扫描件/拍照/影印版不支持（需要 OCR，识别错误会传导成答错）
- 适合几十页规模；上百页需要改造检索层（见上文）
- 没有做权限控制、多轮对话、审计日志
- 未做 Docker 化部署

## Roadmap

- [ ] 向量检索 + 两阶段粗排/精排（>100 页时）
- [ ] 多轮对话与追问
- [ ] 权限控制与审计日志
- [ ] Docker 化部署

---

## English

**Turn a pile of PDFs / Word / Excel files into a searchable Q&A assistant that always
cites its source — and says "not in the documents" instead of making things up.**

### Why

Support agents, HR and admissions staff answer the same questions all day (refund rules,
pricing, after-sales process) — and different people give different answers.
One wrong answer can escalate into a dispute.

### Three design decisions

1. **Chunks carry source coordinates** — every chunk records "file + paragraph index",
   and each answer must cite it, so answers are verifiable.
2. **Three hard rules against hallucination** — answer only from the documents,
   always cite, and say "not found" instead of guessing.
3. **An evaluation set instead of vibes** — 5 questions: 3 answerable (accuracy) and
   2 not in the documents (refusal). This turns hallucination into a measurable metric.

### Stack

Python · python-docx / openpyxl · character-bigram retrieval · DeepSeek API
(OpenAI-compatible) · optional local Ollama fallback · plain-stdlib HTTP server

### Results

5/5 evaluation passed: 3 accurate answers with citations, 2 correct refusals.
Cost: ~¥0.0038 per query (~$0.0005).

### Why keyword retrieval instead of a vector DB?

For a few dozen pages, keyword retrieval is accurate enough, has zero extra dependencies
and cost, and is fully explainable — you can see exactly which paragraph was matched.
A vector DB (and two-stage retrieve-then-rerank) becomes worth it beyond ~100 pages.
