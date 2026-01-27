from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence

import chromadb
import requests

SUPPORTED_EXTENSIONS = {".txt", ".md"}


@dataclass
class RetrievedChunk:
    """检索结果的数据结构。"""
    source_id: str
    title: str
    snippet: str
    source_type: str
    path: str
    content: str
    score: float


class QianfanClient:
    """封装千帆鉴权、Embedding 与 Chat API。"""
    def __init__(self) -> None:
        self.api_key = os.getenv("QIANFAN_API_KEY")
        self.secret_key = os.getenv("QIANFAN_SECRET_KEY")
        if not self.api_key or not self.secret_key:
            raise ValueError("QIANFAN_API_KEY and QIANFAN_SECRET_KEY must be set")
        self._access_token: str | None = None

    def _get_access_token(self) -> str:
        """获取并缓存 access_token。"""
        if self._access_token:
            return self._access_token
        response = requests.post(
            "https://aip.baidubce.com/oauth/2.0/token",
            params={
                "grant_type": "client_credentials",
                "client_id": self.api_key,
                "client_secret": self.secret_key,
            },
            timeout=30,
        )
        response.raise_for_status()
        self._access_token = response.json()["access_token"]
        return self._access_token

    def embed(self, texts: Sequence[str], model: str | None = None) -> List[List[float]]:
        """调用千帆 Embedding API，返回向量列表。"""
        access_token = self._get_access_token()
        model_name = model or os.getenv("QIANFAN_EMBEDDING_MODEL", "embedding-v1")
        url = (
            "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/"
            f"embeddings/{model_name}?access_token={access_token}"
        )
        payload = {"input": texts}
        response = requests.post(url, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()
        return [item["embedding"] for item in data.get("data", [])]

    def chat(self, prompt: str, model: str | None = None) -> str:
        """调用千帆 Chat/Completions API，返回纯文本结果。"""
        access_token = self._get_access_token()
        model_name = model or os.getenv("QIANFAN_CHAT_MODEL", "ernie-lite-8k")
        url = (
            "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/"
            f"chat/completions?access_token={access_token}"
        )
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": "You are a helpful RAG assistant."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }
        response = requests.post(url, json=payload, timeout=90)
        response.raise_for_status()
        data = response.json()
        return data["result"]


def build_source_id(path: str, chunk_index: int) -> str:
    """生成稳定 source_id，保证可重复引用。"""
    payload = f"{path}::{chunk_index}".encode("utf-8")
    digest = hashlib.sha1(payload).hexdigest()
    return digest[:10]


def iter_source_files(data_dir: Path) -> Iterable[Path]:
    """遍历本地资料目录下的 .txt/.md 文件。"""
    for path in sorted(data_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            yield path


def chunk_text(text: str, chunk_size: int = 500, chunk_overlap: int = 80) -> List[str]:
    """按固定长度切块，带重叠以保留上下文。"""
    chunks: List[str] = []
    start = 0
    text_length = len(text)
    while start < text_length:
        end = min(start + chunk_size, text_length)
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk)
        start += chunk_size - chunk_overlap
    return chunks


def build_documents(data_dir: Path) -> List[dict]:
    """将本地文件构造成可入库的文档列表。"""
    documents: List[dict] = []
    for path in iter_source_files(data_dir):
        text = path.read_text(encoding="utf-8")
        chunks = chunk_text(text)
        for index, chunk in enumerate(chunks):
            source_id = build_source_id(str(path), index)
            documents.append(
                {
                    "id": source_id,
                    "text": chunk,
                    "metadata": {
                        "source_id": source_id,
                        "title": path.name,
                        "snippet": chunk[:200],
                        "source_type": "local",
                        "path": str(path),
                        "chunk_index": index,
                    },
                }
            )
    return documents


def build_web_documents(pages: Sequence[dict]) -> List[dict]:
    """将网页抽取内容构造成可入库的文档列表。"""
    documents: List[dict] = []
    for page in pages:
        content = page.get("content", "")
        chunks = chunk_text(content)
        for index, chunk in enumerate(chunks):
            source_id = build_source_id(page["url"], index)
            documents.append(
                {
                    "id": source_id,
                    "text": chunk,
                    "metadata": {
                        "source_id": source_id,
                        "title": page.get("title", page["url"]),
                        "snippet": chunk[:200],
                        "source_type": "web",
                        "path": page["url"],
                        "chunk_index": index,
                    },
                }
            )
    return documents


class KnowledgeBase:
    """封装本地向量库的入库与检索操作。"""
    def __init__(self, persist_dir: Path) -> None:
        self.persist_dir = persist_dir
        self.client = chromadb.PersistentClient(path=str(persist_dir))
        self.collection = self.client.get_or_create_collection("localfirst_rag")
        self.qianfan = QianfanClient()

    def add_documents(self, documents: Sequence[dict]) -> None:
        """写入向量库，自动完成 embedding。"""
        if not documents:
            return
        embeddings = self.qianfan.embed([doc["text"] for doc in documents])
        self.collection.upsert(
            ids=[doc["id"] for doc in documents],
            documents=[doc["text"] for doc in documents],
            metadatas=[doc["metadata"] for doc in documents],
            embeddings=embeddings,
        )

    def ingest_local_dir(self, data_dir: Path) -> int:
        """入库本地目录内容，返回写入的 chunk 数。"""
        documents = build_documents(data_dir)
        self.add_documents(documents)
        return len(documents)

    def ingest_web_pages(self, pages: Sequence[dict]) -> int:
        """入库网页抽取内容，返回写入的 chunk 数。"""
        documents = build_web_documents(pages)
        self.add_documents(documents)
        return len(documents)

    def search(self, query: str, top_k: int) -> List[RetrievedChunk]:
        """向量检索，返回 Top-K chunk。"""
        embeddings = self.qianfan.embed([query])
        results = self.collection.query(
            query_embeddings=embeddings,
            n_results=top_k,
            include=["documents", "metadatas", "distances", "ids"],
        )
        chunks: List[RetrievedChunk] = []
        if not results.get("ids"):
            return chunks
        for idx in range(len(results["ids"][0])):
            meta = results["metadatas"][0][idx]
            chunks.append(
                RetrievedChunk(
                    source_id=meta["source_id"],
                    title=meta["title"],
                    snippet=meta["snippet"],
                    source_type=meta["source_type"],
                    path=meta["path"],
                    content=results["documents"][0][idx],
                    score=results["distances"][0][idx],
                )
            )
        return chunks
