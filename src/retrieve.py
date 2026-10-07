"""Load and query the existing UIT academic-credits FAISS index."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import faiss
import numpy as np
import yaml


LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "experiment_config.yaml"


def _artifact_paths(config: Dict[str, Any], project_root: Path) -> Dict[str, Path]:
    """Resolve configured artifacts or discover the matching legacy manifest."""
    index_config = config.get("index")
    if index_config is None:
        models_dir = project_root / "models"
        candidates = []
        for manifest_path in models_dir.glob("*_manifest.json"):
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if (
                manifest.get("corpus_version") == config["corpus"]["corpus_version"]
                and manifest.get("embedding_model")
                == config["retrieval"]["embedding_model"]
                and manifest.get("experiment_id") == config.get("experiment_id")
            ):
                candidates.append((manifest_path, manifest))
        if len(candidates) != 1:
            raise ValueError(
                "Legacy configuration must match exactly one index manifest; "
                f"found {len(candidates)}"
            )
        manifest_path, manifest = candidates[0]
        return {
            "index": models_dir / manifest["index_filename"],
            "metadata": models_dir / manifest["metadata_filename"],
            "manifest": manifest_path,
        }
    try:
        return {
            "index": project_root / Path(index_config["index_file"]),
            "metadata": project_root / Path(index_config["metadata_file"]),
            "manifest": project_root / Path(index_config["manifest_file"]),
        }
    except KeyError as exc:
        raise ValueError(f"Missing index configuration value: {exc.args[0]}") from exc


def validate_index_metadata(index: Any, metadata: List[Dict[str, Any]]) -> None:
    if index.ntotal != len(metadata):
        raise ValueError(
            f"FAISS/metadata length mismatch: {index.ntotal} index rows, "
            f"{len(metadata)} metadata rows"
        )
    for row, item in enumerate(metadata):
        if item.get("faiss_row") != row:
            raise ValueError(f"Metadata row mapping mismatch at FAISS row {row}")


def encode_queries(
    model: Any, questions: List[str], query_prefix: str = "query: "
) -> np.ndarray:
    """Encode unmodified questions in one normalized float32 batch."""
    if not questions:
        raise ValueError("At least one query is required")
    embedding = model.encode(
        [query_prefix + question for question in questions],
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    embedding = np.ascontiguousarray(embedding, dtype=np.float32)
    if (
        embedding.ndim != 2
        or embedding.shape[0] != len(questions)
        or embedding.shape[1] == 0
    ):
        raise ValueError(f"Query embedding has invalid shape: {embedding.shape}")
    if np.any(np.linalg.norm(embedding, axis=1) == 0):
        raise ValueError("One or more query embeddings are zero vectors")
    faiss.normalize_L2(embedding)
    return embedding


def encode_query(model: Any, question: str, query_prefix: str = "query: ") -> np.ndarray:
    """Encode one unmodified question with the required E5 query prefix."""
    return encode_queries(model, [question], query_prefix)


def search_index(
    index: Any,
    metadata: List[Dict[str, Any]],
    query_embedding: np.ndarray,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    validate_index_metadata(index, metadata)
    if top_k <= 0 or top_k > index.ntotal:
        raise ValueError(f"top_k must be between 1 and {index.ntotal}")
    scores, rows = index.search(query_embedding, top_k)
    results: List[Dict[str, Any]] = []
    for rank, (row, score) in enumerate(zip(rows[0], scores[0]), start=1):
        if row < 0 or row >= len(metadata):
            raise ValueError(f"FAISS returned invalid metadata row: {row}")
        item = metadata[int(row)]
        page_sets = item.get("pages")
        if page_sets is None:
            page_sets = [item["page"]]
        if not isinstance(page_sets, list) or not page_sets:
            raise ValueError(f"Metadata pages must be a non-empty list at row {row}")
        results.append(
            {
                "rank": rank,
                "chunk_id": item["chunk_id"],
                "page": item["page"],
                "pages": page_sets,
                "section": item["section"],
                "similarity_score": float(score),
            }
        )
    return results


def search_index_batch(
    index: Any,
    metadata: List[Dict[str, Any]],
    query_embeddings: np.ndarray,
    top_k: int = 5,
) -> List[List[Dict[str, Any]]]:
    """Search multiple query vectors while preserving their input order."""
    validate_index_metadata(index, metadata)
    if top_k <= 0 or top_k > index.ntotal:
        raise ValueError(f"top_k must be between 1 and {index.ntotal}")
    scores, rows = index.search(query_embeddings, top_k)
    batches: List[List[Dict[str, Any]]] = []
    for query_scores, query_rows in zip(scores, rows):
        results: List[Dict[str, Any]] = []
        for rank, (row, score) in enumerate(zip(query_rows, query_scores), start=1):
            if row < 0 or row >= len(metadata):
                raise ValueError(f"FAISS returned invalid metadata row: {row}")
            item = metadata[int(row)]
            pages = item.get("pages")
            if pages is None:
                pages = [item["page"]]
            if not isinstance(pages, list) or not pages:
                raise ValueError(f"Metadata pages must be a non-empty list at row {row}")
            results.append(
                {
                    "rank": rank,
                    "chunk_id": item["chunk_id"],
                    "page": item["page"],
                    "pages": pages,
                    "section": item["section"],
                    "similarity_score": float(score),
                }
            )
        batches.append(results)
    return batches


class Retriever:
    """Small auditable wrapper around the frozen FAISS index and E5 model."""

    def __init__(
        self,
        config_path: Path = DEFAULT_CONFIG_PATH,
        index_path: Optional[Path] = None,
        metadata_path: Optional[Path] = None,
        manifest_path: Optional[Path] = None,
        model_factory: Optional[Callable[[str], Any]] = None,
    ) -> None:
        with config_path.open("r", encoding="utf-8") as stream:
            config = yaml.safe_load(stream)
        project_root = config_path.resolve().parent.parent
        configured_paths = _artifact_paths(config, project_root)
        index_path = index_path or configured_paths["index"]
        metadata_path = metadata_path or configured_paths["metadata"]
        manifest_path = manifest_path or configured_paths["manifest"]
        self.query_prefix = config["retrieval"]["query_prefix"]
        if self.query_prefix != "query: ":
            raise ValueError('Configured query_prefix must be exactly "query: "')

        self.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        self.index = faiss.read_index(str(index_path))
        validate_index_metadata(self.index, self.metadata)
        if len(self.metadata) != self.manifest["chunk_count"]:
            raise ValueError("Metadata length does not match manifest chunk_count")
        if self.manifest["corpus_version"] != config["corpus"]["corpus_version"]:
            raise ValueError("Manifest corpus_version does not match the configuration")
        if self.manifest["embedding_model"] != config["retrieval"]["embedding_model"]:
            raise ValueError("Manifest embedding_model does not match the configuration")
        if Path(self.manifest["index_filename"]).name != index_path.name:
            raise ValueError("Selected index filename does not match the configuration")
        if Path(self.manifest["metadata_filename"]).name != metadata_path.name:
            raise ValueError("Selected metadata filename does not match the configuration")
        if self.index.d != self.manifest["vector_dimension"]:
            raise ValueError("FAISS vector dimension does not match the index manifest")
        if self.index.ntotal != self.manifest["chunk_count"]:
            raise ValueError("FAISS row count does not match the index manifest")

        if model_factory is None:
            from sentence_transformers import SentenceTransformer

            model_factory = SentenceTransformer
        model_name = self.manifest["embedding_model"]
        top_k_values = config["retrieval"]["top_k"]
        if not isinstance(top_k_values, list) or not top_k_values:
            raise ValueError("Configured retrieval.top_k must be a non-empty list")
        self.top_k = max(top_k_values)
        LOGGER.info("Loading embedding model %s", model_name)
        self.model = model_factory(model_name)

    def retrieve(self, question: str, top_k: Optional[int] = None) -> List[Dict[str, Any]]:
        top_k = self.top_k if top_k is None else top_k
        query_embedding = encode_query(self.model, question, self.query_prefix)
        if query_embedding.shape[1] != self.index.d:
            raise ValueError("Query embedding dimension does not match the FAISS index")
        return search_index(self.index, self.metadata, query_embedding, top_k)

    def retrieve_many(
        self, questions: List[str], top_k: Optional[int] = None
    ) -> List[List[Dict[str, Any]]]:
        top_k = self.top_k if top_k is None else top_k
        embeddings = encode_queries(self.model, questions, self.query_prefix)
        if embeddings.shape[1] != self.index.d:
            raise ValueError("Query embedding dimension does not match the FAISS index")
        return search_index_batch(self.index, self.metadata, embeddings, top_k)
