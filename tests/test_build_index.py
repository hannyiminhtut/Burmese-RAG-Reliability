import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import yaml

from src.build_index import EXPECTED_IDS, build_index, load_chunks


REQUIRED_RECORD = {
    "source_id": "UIT-SRC-025",
    "corpus_id": "UIT-AC",
    "corpus_version": "UIT-AC-v1.0",
    "page": 1,
    "section": "Test section",
    "language": "my",
    "content_type": "regulation",
    "text": "စမ်းသပ်စာသား",
}


class MockEmbeddingModel:
    def __init__(self, model_name):
        self.model_name = model_name

    def encode(self, texts, **kwargs):
        return np.array(
            [[row + 1.0, 1.0, 0.5] for row in range(len(texts))], dtype=np.float64
        )


class BuildIndexTests(unittest.TestCase):
    def make_rows(self):
        return [dict(REQUIRED_RECORD, chunk_id=chunk_id) for chunk_id in EXPECTED_IDS]

    def write_jsonl(self, path, rows):
        path.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )

    def test_valid_jsonl_loading(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "chunks.jsonl"
            self.write_jsonl(path, self.make_rows())
            self.assertEqual([row["chunk_id"] for row in load_chunks(path)], EXPECTED_IDS)

    def test_malformed_json_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "chunks.jsonl"
            path.write_text('{"chunk_id": invalid}\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Malformed JSON at line 1"):
                load_chunks(path)

    def test_duplicate_chunk_id_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "chunks.jsonl"
            rows = self.make_rows()
            rows[1]["chunk_id"] = rows[0]["chunk_id"]
            self.write_jsonl(path, rows)
            with self.assertRaisesRegex(ValueError, "Duplicate chunk ID"):
                load_chunks(path)

    def test_missing_required_field_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "chunks.jsonl"
            rows = self.make_rows()
            del rows[0]["section"]
            self.write_jsonl(path, rows)
            with self.assertRaisesRegex(ValueError, "Missing required field.*section"):
                load_chunks(path)

    def test_empty_text_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "chunks.jsonl"
            rows = self.make_rows()
            rows[0]["text"] = "   "
            self.write_jsonl(path, rows)
            with self.assertRaisesRegex(ValueError, "Empty text at line 1"):
                load_chunks(path)

    def test_correct_row_to_chunk_metadata_order(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            corpus_dir = root / "data" / "processed"
            config_dir = root / "configs"
            corpus_dir.mkdir(parents=True)
            config_dir.mkdir()
            corpus_path = corpus_dir / "chunks.jsonl"
            self.write_jsonl(corpus_path, self.make_rows())
            config = {
                "experiment_id": "test",
                "corpus": {
                    "corpus_version": "UIT-AC-v1.0",
                    "retrieval_file": "data/processed/chunks.jsonl",
                    "retrieval_chunk_count": 22,
                },
                "retrieval": {
                    "embedding_model": "mock-model",
                    "similarity_metric": "cosine",
                    "document_prefix": "passage: ",
                },
                "reproducibility": {"random_seed": 42},
            }
            config_path = config_dir / "experiment_config.yaml"
            config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

            build_index(config_path, model_factory=MockEmbeddingModel)

            metadata = json.loads(
                (root / "models" / "uit_academic_credits_v1_metadata.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual([item["faiss_row"] for item in metadata], list(range(22)))
            self.assertEqual([item["chunk_id"] for item in metadata], EXPECTED_IDS)


if __name__ == "__main__":
    unittest.main()
