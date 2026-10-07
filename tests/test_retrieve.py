import json
import tempfile
import unittest
from pathlib import Path

import faiss
import numpy as np
import yaml

from src.retrieve import Retriever, encode_query, search_index, validate_index_metadata


class MockModel:
    def __init__(self, model_name=None):
        self.model_name = model_name
        self.texts = None
        self.kwargs = None

    def encode(self, texts, **kwargs):
        self.texts = texts
        self.kwargs = kwargs
        return np.array([[3.0, 4.0]], dtype=np.float64)


class MockIndex:
    def __init__(self, scores=None, rows=None, ntotal=3):
        self.ntotal = ntotal
        self.scores = np.array([scores or [0.9, 0.7, 0.2]], dtype=np.float32)
        self.rows = np.array([rows or [2, 0, 1]], dtype=np.int64)
        self.received = None

    def search(self, query, top_k):
        self.received = query
        return self.scores[:, :top_k], self.rows[:, :top_k]


class RetrieveTests(unittest.TestCase):
    def setUp(self):
        self.metadata = [
            {"faiss_row": i, "chunk_id": f"C{i}", "page": i + 1, "section": f"S{i}"}
            for i in range(3)
        ]

    def test_correct_query_prefix_and_normalized_float32_embedding(self):
        model = MockModel()
        embedding = encode_query(model, "မူရင်း question")
        self.assertEqual(model.texts, ["query: မူရင်း question"])
        self.assertTrue(model.kwargs["normalize_embeddings"])
        self.assertEqual(embedding.dtype, np.float32)
        self.assertAlmostEqual(float(np.linalg.norm(embedding[0])), 1.0, places=6)

    def test_top_k_result_ordering(self):
        index = MockIndex()
        query = np.array([[1.0, 0.0]], dtype=np.float32)
        results = search_index(index, self.metadata, query, top_k=3)
        self.assertEqual([item["chunk_id"] for item in results], ["C2", "C0", "C1"])
        self.assertEqual([item["rank"] for item in results], [1, 2, 3])
        self.assertEqual(index.received.dtype, np.float32)

    def test_v1_single_page_fallback(self):
        results = search_index(
            MockIndex(), self.metadata, np.array([[1.0, 0.0]], dtype=np.float32), 3
        )
        self.assertEqual(results[0]["pages"], [3])

    def test_faiss_metadata_length_mismatch_rejection(self):
        with self.assertRaisesRegex(ValueError, "FAISS/metadata length mismatch"):
            validate_index_metadata(MockIndex(ntotal=4), self.metadata)

    def test_config_based_artifact_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "configs").mkdir()
            (root / "custom").mkdir()
            index_path = root / "custom" / "chosen.faiss"
            metadata_path = root / "custom" / "chosen_metadata.json"
            manifest_path = root / "custom" / "chosen_manifest.json"
            index = faiss.IndexFlatIP(2)
            index.add(np.array([[1.0, 0.0]], dtype=np.float32))
            faiss.write_index(index, str(index_path))
            metadata_path.write_text(
                json.dumps([{
                    "faiss_row": 0, "chunk_id": "X", "page": 4,
                    "pages": [4, 5], "section": "S",
                }]), encoding="utf-8"
            )
            manifest_path.write_text(json.dumps({
                "corpus_version": "v1.1", "embedding_model": "mock-model",
                "vector_dimension": 2, "chunk_count": 1,
                "index_filename": index_path.name,
                "metadata_filename": metadata_path.name,
            }), encoding="utf-8")
            config = {
                "corpus": {"corpus_version": "v1.1"},
                "retrieval": {
                    "query_prefix": "query: ", "embedding_model": "mock-model",
                    "top_k": [1],
                },
                "index": {
                    "index_file": "custom/chosen.faiss",
                    "metadata_file": "custom/chosen_metadata.json",
                    "manifest_file": "custom/chosen_manifest.json",
                },
            }
            config_path = root / "configs" / "experiment.yaml"
            config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
            retriever = Retriever(config_path=config_path, model_factory=MockModel)
            self.assertEqual(retriever.index.ntotal, 1)
            self.assertEqual(retriever.metadata[0]["pages"], [4, 5])
            self.assertEqual(retriever.model.model_name, "mock-model")


if __name__ == "__main__":
    unittest.main()
