"""One-shot retrieval worker for the RAM-constrained interactive demo."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from src.retrieve import Retriever


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Retrieve one demo question")
    parser.add_argument("--config", type=Path, required=True)
    return parser.parse_args(argv)


def main() -> None:
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    payload = json.loads(sys.stdin.read())
    question = payload.get("question")
    top_k = payload.get("top_k")
    if not isinstance(question, str) or not question.strip():
        raise ValueError("Worker question must be a non-empty string")
    if not isinstance(top_k, int):
        raise ValueError("Worker top_k must be an integer")

    retriever = Retriever(config_path=args.config)
    metadata = {row["chunk_id"]: row for row in retriever.metadata}
    hits = retriever.retrieve(question, top_k=top_k)
    enriched = [
        {**hit, "text": metadata[hit["chunk_id"]]["text"]}
        for hit in hits
    ]
    sys.stdout.write(json.dumps({"hits": enriched}, ensure_ascii=False))


if __name__ == "__main__":
    main()
