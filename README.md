# localfirst-rag-demo

## 总体架构（分层说明）

- **入口层**：`run.py` 负责问答流程编排（本地检索 → 低命中回退 → 生成报告）。
- **知识库层**：`kb.py` 负责切块、稳定 `source_id`、向量入库与检索。
- **检索增强层**：`web_fallback.py` 负责网页搜索与正文抽取（占位实现，可替换）。
- **数据结构层**：`schema.py` 定义报告 JSON 的结构与校验。

## 模块协作与数据流（接口如何串起来）

**入库路径（准备知识库）**

1. `ingest_local.py` → `KnowledgeBase.ingest_local_dir(data_dir)`
2. `kb.py` 内部：`build_documents()` → `chunk_text()` → `build_source_id()`
3. `KnowledgeBase.add_documents()` 调用 `QianfanClient.embed()` 得到向量
4. `chromadb` 持久化保存向量与元数据

**问答路径（本地优先 + 回退）**

1. `run.py` → `KnowledgeBase.search(question, top_k)`
2. `kb.py`：`QianfanClient.embed()` 生成查询向量 → `chromadb.query()` 取回 chunks
3. `run.py`：`should_fallback()` 判断命中不足
4. 若需回退：`web_fallback.search_and_extract()` → `KnowledgeBase.ingest_web_pages()`
5. 再次 `KnowledgeBase.search()` 得到最终 evidence
6. `run.py`：`build_sources()` → `build_prompt()` → `QianfanClient.chat()`
7. `parse_report()` 校验 JSON → `render_markdown()` 输出 `report.json` + `report.md`

**核心接口速查（谁调用谁）**

- `ingest_local.py` 只调用：`KnowledgeBase.ingest_local_dir()`
- `run.py` 调用：`KnowledgeBase.search()`、`search_and_extract()`、`KnowledgeBase.ingest_web_pages()`、`QianfanClient.chat()`
- `kb.py` 内部调用链：`build_documents()`/`build_web_documents()` → `add_documents()` → `QianfanClient.embed()` → `chromadb.upsert()`

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
