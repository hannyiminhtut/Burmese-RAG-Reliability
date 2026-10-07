"""Build reproducible FAISS indexes for the UIT academic-credits corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import faiss
import numpy as np
import yaml


LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "experiment_config.yaml"

# Retained for compatibility with the original v1.0 tests and imports.
REQUIRED_FIELDS = (
    "chunk_id",
    "source_id",
    "corpus_id",
    "corpus_version",
    "page",
    "section",
    "language",
    "content_type",
    "text",
)
EXPECTED_IDS = [f"UIT-AC-CH-{number:03d}" for number in range(4, 26)]

V1_1_REQUIRED_FIELDS = (
    "chunk_id",
    "source_id",
    "corpus_id",
    "corpus_version",
    "page",
    "pages",
    "section_id",
    "section",
    "language",
    "content_type",
    "retrieval_eligible",
    "text",
)


class CorpusValidationError(ValueError):
    """Raised when a retrieval corpus fails reproducibility checks."""


def load_config(config_path: Path) -> dict[str, Any]:
    """Load a YAML experiment configuration."""
    try:
        with config_path.open("r", encoding="utf-8") as stream:
            config = yaml.safe_load(stream)
    except OSError as exc:
        raise ValueError(f"Could not read configuration {config_path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"Malformed YAML in {config_path}: {exc}") from exc

    if not isinstance(config, dict):
        raise ValueError(f"Configuration must contain a YAML mapping: {config_path}")
    return config


def sha256_file(file_path: Path) -> str:
    """Return the lowercase SHA-256 digest of a file."""
    digest = hashlib.sha256()
    try:
        with file_path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise CorpusValidationError(
            f"Could not read input corpus {file_path}: {exc}"
        ) from exc
    return digest.hexdigest()


def _required_config_value(config: dict[str, Any], *keys: str) -> Any:
    value: Any = config
    try:
        for key in keys:
            value = value[key]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"Missing configuration value: {'.'.join(keys)}") from exc
    return value


def _resolve_project_path(project_root: Path, configured_path: str | Path) -> Path:
    path = Path(configured_path)
    return path if path.is_absolute() else project_root / path


def _is_int_not_bool(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _expected_chunk_count(corpus_config: dict[str, Any]) -> int:
    value = corpus_config.get(
        "expected_chunk_count",
        corpus_config.get("retrieval_chunk_count"),
    )
    if not _is_int_not_bool(value) or value <= 0:
        raise CorpusValidationError(
            "corpus.expected_chunk_count or corpus.retrieval_chunk_count "
            "must be a positive integer"
        )
    return value


def _expected_ids(corpus_config: dict[str, Any], count: int) -> list[str]:
    prefix = corpus_config.get("chunk_id_prefix")
    if prefix is not None:
        if not isinstance(prefix, str) or not prefix:
            raise CorpusValidationError("corpus.chunk_id_prefix must be non-empty")
        ids = [f"{prefix}{number:03d}" for number in range(1, count + 1)]
    elif count == len(EXPECTED_IDS):
        ids = list(EXPECTED_IDS)
    else:
        raise CorpusValidationError(
            "corpus.chunk_id_prefix is required for a non-legacy corpus"
        )

    configured_first = corpus_config.get("expected_first_chunk_id")
    configured_last = corpus_config.get("expected_last_chunk_id")
    if configured_first is not None and configured_first != ids[0]:
        raise CorpusValidationError(
            f"Configured first chunk ID {configured_first!r} conflicts with {ids[0]!r}"
        )
    if configured_last is not None and configured_last != ids[-1]:
        raise CorpusValidationError(
            f"Configured last chunk ID {configured_last!r} conflicts with {ids[-1]!r}"
        )
    return ids


def _validate_pages(
    chunk: dict[str, Any],
    *,
    chunk_id: str,
    minimum_page: int | None,
    maximum_page: int | None,
    require_pages: bool,
) -> None:
    page = chunk["page"]
    if not _is_int_not_bool(page):
        raise CorpusValidationError(f"{chunk_id}: page must be an integer")

    if "pages" not in chunk:
        if require_pages:
            raise CorpusValidationError(f"{chunk_id}: missing required field pages")
        pages = [page]
    else:
        pages = chunk["pages"]
        if (
            not isinstance(pages, list)
            or not pages
            or not all(_is_int_not_bool(item) for item in pages)
        ):
            raise CorpusValidationError(
                f"{chunk_id}: pages must be a non-empty list of integers"
            )
        if pages != sorted(set(pages)):
            raise CorpusValidationError(
                f"{chunk_id}: pages must be unique and ascending"
            )
        if page != pages[0]:
            raise CorpusValidationError(
                f"{chunk_id}: page must equal the first value in pages"
            )

    if minimum_page is not None and any(item < minimum_page for item in pages):
        raise CorpusValidationError(
            f"{chunk_id}: page is below configured minimum {minimum_page}"
        )
    if maximum_page is not None and any(item > maximum_page for item in pages):
        raise CorpusValidationError(
            f"{chunk_id}: page is above configured maximum {maximum_page}"
        )


def load_chunks(
    input_path: Path,
    corpus_config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Load and validate a configured corpus.

    Calling ``load_chunks(path)`` without configuration preserves the original
    v1.0 validation contract of 22 ordered IDs from UIT-AC-CH-004 to -025.
    """
    if corpus_config is None:
        corpus_config = {
            "corpus_id": "UIT-AC",
            "corpus_version": "UIT-AC-v1.0",
            "source_id": "UIT-SRC-025",
            "retrieval_chunk_count": 22,
        }
        legacy_mode = True
    else:
        legacy_mode = "chunk_id_prefix" not in corpus_config

    expected_count = _expected_chunk_count(corpus_config)
    expected_ids = _expected_ids(corpus_config, expected_count)
    expected_version = corpus_config.get("corpus_version")
    expected_source_id = corpus_config.get("source_id")
    expected_corpus_id = corpus_config.get("corpus_id")
    minimum_page = corpus_config.get("minimum_page")
    maximum_page = corpus_config.get("maximum_page")

    for label, value in (
        ("minimum_page", minimum_page),
        ("maximum_page", maximum_page),
    ):
        if value is not None and not _is_int_not_bool(value):
            raise CorpusValidationError(f"corpus.{label} must be an integer")
    if (
        minimum_page is not None
        and maximum_page is not None
        and minimum_page > maximum_page
    ):
        raise CorpusValidationError("corpus.minimum_page exceeds maximum_page")

    expected_sha = corpus_config.get("input_sha256")
    if expected_sha is not None:
        if not isinstance(expected_sha, str) or not re.fullmatch(
            r"[0-9a-fA-F]{64}", expected_sha
        ):
            raise CorpusValidationError(
                "corpus.input_sha256 must contain 64 hexadecimal characters"
            )
        actual_sha = sha256_file(input_path)
        if actual_sha != expected_sha.lower():
            raise CorpusValidationError(
                f"Corpus SHA-256 mismatch: expected {expected_sha.lower()}, "
                f"got {actual_sha}"
            )

    required_fields = REQUIRED_FIELDS if legacy_mode else V1_1_REQUIRED_FIELDS
    chunks: list[dict[str, Any]] = []
    try:
        with input_path.open("r", encoding="utf-8-sig") as stream:
            for line_number, raw_line in enumerate(stream, start=1):
                if not raw_line.strip():
                    raise CorpusValidationError(
                        f"Empty JSONL record at line {line_number}"
                    )
                try:
                    chunk = json.loads(raw_line)
                except json.JSONDecodeError as exc:
                    raise CorpusValidationError(
                        f"Malformed JSON at line {line_number}: {exc.msg}"
                    ) from exc
                if not isinstance(chunk, dict):
                    raise CorpusValidationError(
                        f"JSONL record at line {line_number} must be an object"
                    )

                missing = [field for field in required_fields if field not in chunk]
                if missing:
                    raise CorpusValidationError(
                        f"Missing required field(s) at line {line_number}: "
                        + ", ".join(missing)
                    )

                chunk_id = chunk["chunk_id"]
                if not isinstance(chunk_id, str) or not chunk_id:
                    raise CorpusValidationError(
                        f"Invalid chunk_id at line {line_number}"
                    )
                text = chunk["text"]
                if not isinstance(text, str) or not text.strip():
                    raise CorpusValidationError(f"Empty text at line {line_number}")
                if "\ufffd" in text:
                    raise CorpusValidationError(
                        f"{chunk_id}: Unicode replacement character found in text"
                    )

                for field in ("section", "language", "content_type"):
                    if not isinstance(chunk[field], str) or not chunk[field].strip():
                        raise CorpusValidationError(
                            f"{chunk_id}: {field} must be a non-empty string"
                        )

                if not legacy_mode:
                    if (
                        not isinstance(chunk["section_id"], str)
                        or not chunk["section_id"].strip()
                    ):
                        raise CorpusValidationError(
                            f"{chunk_id}: section_id must be a non-empty string"
                        )
                    if chunk["retrieval_eligible"] is not True:
                        raise CorpusValidationError(
                            f"{chunk_id}: retrieval_eligible must be exactly true"
                        )

                _validate_pages(
                    chunk,
                    chunk_id=chunk_id,
                    minimum_page=minimum_page,
                    maximum_page=maximum_page,
                    require_pages=not legacy_mode,
                )
                chunks.append(chunk)
    except UnicodeDecodeError as exc:
        raise CorpusValidationError(
            f"Input corpus is not valid UTF-8: {input_path}"
        ) from exc
    except OSError as exc:
        raise CorpusValidationError(
            f"Could not read input corpus {input_path}: {exc}"
        ) from exc

    if len(chunks) != expected_count:
        raise CorpusValidationError(
            f"Expected {expected_count} chunks, found {len(chunks)}"
        )

    chunk_ids = [chunk["chunk_id"] for chunk in chunks]
    duplicates = sorted(
        chunk_id for chunk_id in set(chunk_ids) if chunk_ids.count(chunk_id) > 1
    )
    if duplicates:
        raise CorpusValidationError(f"Duplicate chunk ID(s): {', '.join(duplicates)}")
    if chunk_ids != expected_ids:
        raise CorpusValidationError(
            f"Chunk IDs must be sequential and ordered from {expected_ids[0]} "
            f"through {expected_ids[-1]}"
        )

    for chunk in chunks:
        chunk_id = chunk["chunk_id"]
        if expected_version is not None and chunk["corpus_version"] != expected_version:
            raise CorpusValidationError(
                f"{chunk_id}: corpus_version must be {expected_version!r}"
            )
        if expected_source_id is not None and chunk["source_id"] != expected_source_id:
            raise CorpusValidationError(
                f"{chunk_id}: source_id must be {expected_source_id!r}"
            )
        if expected_corpus_id is not None and chunk["corpus_id"] != expected_corpus_id:
            raise CorpusValidationError(
                f"{chunk_id}: corpus_id must be {expected_corpus_id!r}"
            )
        if not legacy_mode and chunk["language"] != "my-en":
            raise CorpusValidationError(
                f"{chunk_id}: language must be 'my-en'"
            )

    return chunks


def _output_paths(
    config: dict[str, Any], project_root: Path
) -> tuple[Path, Path, Path]:
    index_config = config.get("index")
    if index_config is None:
        models_dir = project_root / "models"
        return (
            models_dir / "uit_academic_credits_v1.faiss",
            models_dir / "uit_academic_credits_v1_metadata.json",
            models_dir / "uit_academic_credits_v1_manifest.json",
        )
    if not isinstance(index_config, dict):
        raise ValueError("Configuration index value must be a mapping")
    return tuple(
        _resolve_project_path(project_root, _required_config_value(config, "index", key))
        for key in ("index_file", "metadata_file", "manifest_file")
    )


def build_index(
    config_path: Path = DEFAULT_CONFIG_PATH,
    model_factory: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    """Validate the corpus, encode passages, and persist aligned artifacts."""
    config_path = config_path.resolve()
    project_root = config_path.parent.parent
    config = load_config(config_path)

    corpus_config = _required_config_value(config, "corpus")
    if not isinstance(corpus_config, dict):
        raise ValueError("Configuration corpus value must be a mapping")

    input_path = _resolve_project_path(
        project_root,
        _required_config_value(config, "corpus", "retrieval_file"),
    )
    chunks = load_chunks(input_path, corpus_config)

    model_name = _required_config_value(config, "retrieval", "embedding_model")
    passage_prefix = _required_config_value(config, "retrieval", "document_prefix")
    retrieval_config = _required_config_value(config, "retrieval")
    if not isinstance(retrieval_config, dict):
        raise ValueError("Configuration retrieval value must be a mapping")
    normalize_embeddings = retrieval_config.get(
    "normalize_embeddings",
    True,)
    if not isinstance(normalize_embeddings, bool):
        raise ValueError(
        "retrieval.normalize_embeddings must be true or false")
    similarity_metric = _required_config_value(
        config, "retrieval", "similarity_metric"
    )
    if passage_prefix != "passage: ":
        raise ValueError('Configured document_prefix must be exactly "passage: "')
    if similarity_metric != "cosine":
        raise ValueError("This index builder currently requires cosine similarity")
    if not normalize_embeddings:
        raise ValueError("Cosine retrieval requires normalize_embeddings: true")

    if model_factory is None:
        from sentence_transformers import SentenceTransformer

        model_factory = SentenceTransformer

    LOGGER.info("Loading embedding model %s", model_name)
    model = model_factory(model_name)
    passages = [passage_prefix + chunk["text"] for chunk in chunks]
    LOGGER.info("Encoding %d passages", len(passages))
    embeddings = model.encode(
        passages,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=True,
    )
    embeddings = np.ascontiguousarray(embeddings, dtype=np.float32)
    if embeddings.ndim != 2 or embeddings.shape[0] != len(chunks):
        raise ValueError(
            f"Embedding model returned shape {embeddings.shape}; "
            f"expected {len(chunks)} rows"
        )
    if embeddings.shape[1] == 0:
        raise ValueError("Embedding model returned zero-dimensional vectors")
    if not np.all(np.isfinite(embeddings)):
        raise ValueError("Embedding model returned non-finite values")
    norms = np.linalg.norm(embeddings, axis=1)
    if np.any(norms == 0):
        raise ValueError("Embedding model returned one or more zero vectors")
    faiss.normalize_L2(embeddings)

    vector_dimension = int(embeddings.shape[1])
    index = faiss.IndexFlatIP(vector_dimension)
    index.add(embeddings)
    if index.ntotal != len(chunks):
        raise ValueError(
            f"FAISS index contains {index.ntotal} rows; expected {len(chunks)}"
        )

    index_path, metadata_path, manifest_path = _output_paths(config, project_root)
    for output_path in (index_path, metadata_path, manifest_path):
        output_path.parent.mkdir(parents=True, exist_ok=True)

    metadata: list[dict[str, Any]] = []
    for row, chunk in enumerate(chunks):
        item = dict(chunk)
        item.setdefault("pages", [item["page"]])
        metadata.append({"faiss_row": row, **item})

    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    faiss.write_index(index, str(index_path))

    input_sha256 = sha256_file(input_path)
    manifest = {
        "experiment_id": _required_config_value(config, "experiment_id"),
        "corpus_id": corpus_config.get("corpus_id"),
        "corpus_version": corpus_config.get("corpus_version"),
        "source_id": corpus_config.get("source_id"),
        "embedding_model": model_name,
        "similarity_metric": similarity_metric,
        "normalize_embeddings": normalize_embeddings,
        "document_prefix": passage_prefix,
        "vector_dimension": vector_dimension,
        "chunk_count": len(chunks),
        "creation_timestamp": datetime.now(timezone.utc).isoformat().replace(
            "+00:00", "Z"
        ),
        "selected_config": str(config_path.relative_to(project_root)),
        "input_filename": input_path.name,
        "input_path": str(input_path.relative_to(project_root)),
        "input_sha256": input_sha256,
        "expected_chunk_count": _expected_chunk_count(corpus_config),
        "expected_first_chunk_id": chunks[0]["chunk_id"],
        "expected_last_chunk_id": chunks[-1]["chunk_id"],
        "index_filename": index_path.name,
        "metadata_filename": metadata_path.name,
        "manifest_filename": manifest_path.name,
        "random_seed": _required_config_value(
            config, "reproducibility", "random_seed"
        ),
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    LOGGER.info(
        "Saved FAISS index, metadata, and manifest for %d chunks", len(chunks)
    )
    return manifest


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a UIT academic-regulation FAISS index."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Experiment YAML path (default: configs/experiment_config.yaml)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args(argv)
    manifest = build_index(config_path=args.config)
    LOGGER.info(
        "Completed experiment %s with %d chunks and %d-dimensional vectors",
        manifest["experiment_id"],
        manifest["chunk_count"],
        manifest["vector_dimension"],
    )


if __name__ == "__main__":
    main()
