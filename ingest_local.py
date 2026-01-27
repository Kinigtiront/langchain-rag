from __future__ import annotations

import argparse
from pathlib import Path

from kb import KnowledgeBase


def main() -> None:
    """命令行入口：将本地目录入库。"""
    parser = argparse.ArgumentParser(description="Ingest local files into the knowledge base.")
    parser.add_argument("--data-dir", default="data", help="Directory with .txt/.md files")
    parser.add_argument(
        "--persist-dir", default="chroma_db", help="Directory to store the vector index"
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    persist_dir = Path(args.persist_dir)
    persist_dir.mkdir(parents=True, exist_ok=True)

    kb = KnowledgeBase(persist_dir)
    count = kb.ingest_local_dir(data_dir)
    if count == 0:
        raise ValueError(f"No supported files found in {data_dir}")
    print(f"Ingested {count} chunks from {data_dir} into {persist_dir}")


if __name__ == "__main__":
    main()
