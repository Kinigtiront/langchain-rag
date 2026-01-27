from __future__ import annotations

import os
from typing import List

import requests


def search_web(query: str, top_k: int = 3) -> List[dict]:
    """网页搜索占位实现（Tavily）。"""
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return []
    response = requests.post(
        "https://api.tavily.com/search",
        json={"api_key": api_key, "query": query, "max_results": top_k},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    return data.get("results", [])


def extract_page(url: str) -> dict | None:
    """正文抽取占位实现（Jina Reader）。"""
    try:
        response = requests.get(f"https://r.jina.ai/{url}", timeout=30)
        response.raise_for_status()
    except requests.RequestException:
        return None
    content = response.text
    return {"url": url, "title": url, "content": content}


def search_and_extract(query: str, top_k: int = 3) -> List[dict]:
    """搜索并抽取网页正文，返回可入库页面。"""
    results = search_web(query, top_k=top_k)
    pages: List[dict] = []
    for item in results:
        url = item.get("url")
        if not url:
            continue
        page = extract_page(url)
        if page:
            page["title"] = item.get("title") or url
            pages.append(page)
    return pages
