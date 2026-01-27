from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List

from kb import KnowledgeBase, RetrievedChunk
from schema import Report, Source
from web_fallback import search_and_extract


def build_sources(chunks: List[RetrievedChunk]) -> List[Source]:
    """将检索结果转换为可输出的 sources 列表。"""
    sources: List[Source] = []
    for chunk in chunks:
        sources.append(
            Source(
                source_id=chunk.source_id,
                title=chunk.title,
                snippet=chunk.snippet,
                source_type=chunk.source_type,
                path=chunk.path,
            )
        )
    return sources


def build_prompt(question: str, sources: List[Source]) -> str:
    """构造给 LLM 的严格 JSON 输出提示词。"""
    sources_payload = json.dumps([source.model_dump() for source in sources], ensure_ascii=False)
    return (
        "You are a local-first RAG assistant. Answer the question using ONLY the sources.\n"
        "Return strict JSON only, no markdown.\n"
        "Required JSON schema:\n"
        "{\"summary\": string, \"claims\": [{\"text\": string, \"source_ids\": [string]}],"
        " \"sources\": [{\"source_id\": string, \"title\": string, \"snippet\": string,"
        " \"source_type\": string, \"path\": string}]}\n"
        "Each claim must cite source_ids from the provided sources only.\n"
        "Sources (must be reused as-is in output):\n"
        + sources_payload
        + "\nQuestion: "
        + question
        + "\nJSON:"
    )


def parse_report(raw: str) -> Report:
    """解析并校验 LLM 输出。"""
    data = json.loads(raw)
    report = Report.model_validate(data)
    report.validate_source_ids()
    return report


def retry_prompt(prompt: str) -> str:
    """校验失败时追加约束提示。"""
    return (
        prompt
        + "\nReminder: output JSON only. Every claim must include non-empty source_ids "
        "and you can ONLY reference source_id values listed in Sources.\n"
    )


def build_source_link(source: Source) -> str:
    """将 source 映射为可点击链接。"""
    if source.source_type == "web":
        return source.path
    return f"file://{Path(source.path).resolve()}"


def render_markdown(report: Report) -> str:
    """将结构化报告渲染为 Markdown。"""
    lines = ["# Report", "", "## Summary", report.summary, "", "## Claims"]
    source_lookup = {source.source_id: source for source in report.sources}
    for idx, claim in enumerate(report.claims, start=1):
        links = []
        for source_id in claim.source_ids:
            source = source_lookup.get(source_id)
            if source:
                link = build_source_link(source)
                links.append(f"[{source_id}]({link})")
            else:
                links.append(source_id)
        lines.append(f"{idx}. {claim.text} (sources: {', '.join(links)})")
    lines.append("")
    lines.append("## Sources")
    for source in report.sources:
        link = build_source_link(source)
        lines.append(f"- [{source.source_id}]({link}): {source.title}")
        lines.append(f"  - snippet: {source.snippet}")
    lines.append("")
    return "\n".join(lines)


def should_fallback(chunks: List[RetrievedChunk], min_sources: int, max_distance: float) -> bool:
    """命中不足或距离过大时触发网页回退。"""
    if len(chunks) < min_sources:
        return True
    if not chunks:
        return True
    return min(chunk.score for chunk in chunks) > max_distance


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local-first RAG demo with web fallback.")
    parser.add_argument("question", help="Question to answer")
    parser.add_argument("--top-k", type=int, default=4, help="Number of chunks to retrieve")
    parser.add_argument(
        "--persist-dir", default="chroma_db", help="Directory containing Chroma index"
    )
    parser.add_argument("--output-dir", default="outputs", help="Output directory")
    parser.add_argument("--min-sources", type=int, default=2, help="Minimum sources needed")
    parser.add_argument(
        "--max-distance",
        type=float,
        default=0.35,
        help="Fallback threshold for vector distance",
    )
    parser.add_argument("--web-top-k", type=int, default=3, help="Web pages to fetch")
    args = parser.parse_args()

    kb = KnowledgeBase(Path(args.persist_dir))
    chunks = kb.search(args.question, top_k=args.top_k)

    if should_fallback(chunks, args.min_sources, args.max_distance):
        pages = search_and_extract(args.question, top_k=args.web_top_k)
        if pages:
            kb.ingest_web_pages(pages)
            chunks = kb.search(args.question, top_k=args.top_k)

    sources = build_sources(chunks)
    prompt = build_prompt(args.question, sources)
    response = kb.qianfan.chat(prompt)

    try:
        report = parse_report(response)
    except (json.JSONDecodeError, ValueError):
        report = parse_report(kb.qianfan.chat(retry_prompt(prompt)))

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    report_path = output_dir / "report.json"
    report_path.write_text(report.model_dump_json(indent=2, ensure_ascii=False))

    markdown_path = output_dir / "report.md"
    markdown_path.write_text(render_markdown(report), encoding="utf-8")

    print(f"Wrote {report_path} and {markdown_path}")


if __name__ == "__main__":
    main()
