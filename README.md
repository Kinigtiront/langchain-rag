# localfirst-rag-demo

## 总体架构（分层说明）

- **入口层**：`run.py` 负责问答流程编排（本地检索 → 低命中回退 → 生成报告）。
- **知识库层**：`kb.py` 负责切块、稳定 `source_id`、向量入库与检索。
- **检索增强层**：`web_fallback.py` 负责网页搜索与正文抽取（占位实现，可替换）。
- **数据结构层**：`schema.py` 定义报告 JSON 的结构与校验。

## 模块协作与数据流（接口如何串起来）

下面用“完全不了解 LLM 的读者也能看懂”的方式，说明这些接口如何协作。

**你可以把它理解为三步（与模块对应关系）：**

1. 把本地资料切成小块并存进“向量知识库”。（`ingest_local.py` + `kb.py`）
2. 提问时先从本地找相关内容，不够再去网上补。（`run.py` + `web_fallback.py` + `kb.py`）
3. 把找到的内容交给模型生成“带引用”的结构化答案。（`run.py` + `schema.py`）

**入库路径（准备知识库）**

1. `ingest_local.py` → `KnowledgeBase.ingest_local_dir(data_dir)`
2. `kb.py` 内部：`build_documents()` → `chunk_text()` → `build_source_id()`
3. `KnowledgeBase.add_documents()` 调用 `QianfanClient.embed()` 得到向量
4. `chromadb` 持久化保存向量与元数据

**问答路径（本地优先 + 回退）**

1. `run.py` 调用 `KnowledgeBase.search(question, top_k)`：先把问题转成向量并检索本地向量库。
2. `kb.py` 内部：`QianfanClient.embed()` 生成“问题向量”，`chromadb.query()` 返回最相近的文本块。
3. `run.py` 调用 `should_fallback()`：判断命中数量是否过少或距离是否过大（说明相关性不足）。
4. 若需回退：`web_fallback.search_and_extract()` 搜索网页并抽取正文 → `KnowledgeBase.ingest_web_pages()` 入库。
5. 再次 `KnowledgeBase.search()`：用同样的问题重新检索，得到更丰富的 evidence。
6. `run.py` 组装证据：`build_sources()` 把每个文本块变成包含 `source_id + snippet` 的 evidence。
7. `run.py` 生成提示词：`build_prompt()` 把问题与 evidence 拼成“只准引用这些来源”的指令。
8. `QianfanClient.chat()` 生成结构化 JSON（summary + claims + sources）。
9. `parse_report()` 校验 JSON 格式与 `source_ids` 合法性 → `render_markdown()` 输出 `report.json` + `report.md`。

**问答路径背后的原理（为什么要这么做）**

- **为什么先向量检索？** 因为模型本身不会“记住”你的本地资料，必须先把相关内容检索出来作为证据。
- **为什么需要回退？** 当本地资料缺失或相关度不足时，允许临时拉取网页内容补足证据。
- **为什么要稳定 `source_id`？** 让每条结论都能对应到具体文本块，避免“凭空生成”。
- **为什么要结构化 JSON？** 统一输出格式，便于程序检查“是否有引用、引用是否有效”。

**核心接口速查（谁调用谁）**

- `ingest_local.py` 只调用：`KnowledgeBase.ingest_local_dir()`
- `run.py` 调用：`KnowledgeBase.search()`、`search_and_extract()`、`KnowledgeBase.ingest_web_pages()`、`QianfanClient.chat()`
- `kb.py` 内部调用链：`build_documents()`/`build_web_documents()` → `add_documents()` → `QianfanClient.embed()` → `chromadb.upsert()`

**每个文件负责什么（新手版）**

- `ingest_local.py`：只做一件事——把 `data/` 里的文本资料“入库”。它不会生成答案。
- `kb.py`：
  - `chunk_text()`：把长文本切成小块，方便检索。
  - `build_source_id()`：给每个小块一个稳定编号，后面引用会用到。
  - `QianfanClient.embed()`：把文本变成“向量”，用于相似度检索。
  - `KnowledgeBase.search()`：根据问题从向量库找出最相关的文本块。
- `web_fallback.py`：当本地找不到时，去网上搜索并抽取正文（占位实现，可替换）。
- `run.py`：把上述步骤串起来，最后生成 `report.json` + `report.md`。
- `schema.py`：规定报告的固定格式（summary/claims/sources），避免输出结构混乱。

**为什么要这样组织？**

这样拆分可以让你很容易替换某一部分：比如你只想换网页搜索，就改 `web_fallback.py`；
想换模型或 embedding，就改 `kb.py` 的 `QianfanClient`。核心流程不变。

## 依赖安装

```bash
pip install chromadb pydantic requests
```

## 千帆环境变量配置

```bash
export QIANFAN_API_KEY=your_api_key
export QIANFAN_SECRET_KEY=your_secret_key
export QIANFAN_CHAT_MODEL=ernie-lite-8k
export QIANFAN_EMBEDDING_MODEL=embedding-v1
```

可选：网页搜索（使用 Tavily + Jina Reader 占位实现）

```bash
export TAVILY_API_KEY=your_tavily_key
```

## 本地入库

```bash
python ingest_local.py --data-dir data --persist-dir chroma_db
```

## 运行示例

```bash
python run.py "RAG 的基本流程是什么？" --persist-dir chroma_db
```
