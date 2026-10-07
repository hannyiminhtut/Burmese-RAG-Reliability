import csv
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

import yaml

from src.evaluate_retrieval import (
    load_benchmark,
    load_pilot_intents,
    parse_evidence_pages,
    relevance_metrics,
    run_heldout,
    run_pilot,
    select_fixed_pilot,
    select_heldout_rows,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class MockRetriever:
    manifest = {
        "embedding_model": "mock-model", "chunk_count": 148,
        "input_sha256": "abc123",
    }

    def retrieve(self, question, top_k=5):
        return [
            {
                "rank": rank,
                "chunk_id": f"C{rank}",
                "page": rank,
                "pages": [rank, rank + 10] if rank == 2 else [rank],
                "section": f"S{rank}",
                "similarity_score": 1.0 - rank / 10,
            }
            for rank in range(1, top_k + 1)
        ]

    def retrieve_many(self, questions, top_k=5):
        return [self.retrieve(question, top_k) for question in questions]


class EvaluateRetrievalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.benchmark = load_benchmark(
            PROJECT_ROOT / "data" / "evaluation" / "question_benchmark.csv"
        )

    def test_hit_metrics_and_reciprocal_rank(self):
        metrics = relevance_metrics([8, 10, 12, 14, 16], {10, 11})
        self.assertEqual(metrics["hit_at_1"], 0)
        self.assertEqual(metrics["hit_at_3"], 1)
        self.assertEqual(metrics["hit_at_5"], 1)
        self.assertEqual(metrics["first_relevant_rank"], 2)
        self.assertEqual(metrics["reciprocal_rank"], 0.5)
        self.assertEqual(parse_evidence_pages("8-9, 12;14"), {8, 9, 12, 14})

    def test_cross_page_evidence_match(self):
        metrics = relevance_metrics([[4], [5, 6], [7]], {6})
        self.assertEqual(metrics["first_relevant_rank"], 2)
        self.assertEqual(metrics["hit_at_3"], 1)

    def test_fixed_pilot_loading_and_distributions(self):
        ids1 = load_pilot_intents(PROJECT_ROOT / "results" / "pilot_intents.json")
        ids2 = load_pilot_intents(PROJECT_ROOT / "results" / "pilot_intents.json")
        rows1 = select_fixed_pilot(self.benchmark, ids1)
        rows2 = select_fixed_pilot(self.benchmark, ids2)
        self.assertEqual(ids1, ids2)
        self.assertEqual([r["variant_id"] for r in rows1], [r["variant_id"] for r in rows2])
        self.assertEqual(len(ids1), 5)
        self.assertEqual(len(rows1), 15)
        self.assertEqual(Counter(r["language_condition"] for r in rows1), {"EN": 5, "MY": 5, "MIX": 5})
        self.assertEqual(Counter(r["answerability"] for r in rows1), {"answerable": 9, "unanswerable": 6})

    def test_exact_pilot_exclusion_and_heldout_counts(self):
        pilot_ids = load_pilot_intents(PROJECT_ROOT / "results" / "pilot_intents.json")
        heldout = select_heldout_rows(self.benchmark, pilot_ids)
        heldout_ids = {row["intent_id"] for row in heldout}
        self.assertFalse(heldout_ids & set(pilot_ids))
        self.assertEqual(len(heldout_ids), 74)
        self.assertEqual(len(heldout), 222)
        self.assertEqual(
            Counter(row["answerability"] for row in heldout),
            {"answerable": 180, "unanswerable": 42},
        )
        self.assertEqual(
            Counter(row["language_condition"] for row in heldout),
            {"EN": 74, "MY": 74, "MIX": 74},
        )

    def test_heldout_unanswerable_metrics_blank(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_dir = root / "configs"; data_dir = root / "data" / "evaluation"
            config_dir.mkdir(parents=True); data_dir.mkdir(parents=True)
            benchmark_path = data_dir / "benchmark.csv"
            with benchmark_path.open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(self.benchmark[0]))
                writer.writeheader(); writer.writerows(self.benchmark)
            config_path = config_dir / "config.yaml"
            config_path.write_text(yaml.safe_dump({
                "experiment_id": "heldout-test",
                "corpus": {"corpus_version": "v1.1"},
                "benchmark": {"file": "data/evaluation/benchmark.csv"},
                "reproducibility": {"random_seed": 42},
            }), encoding="utf-8")
            intents_path = root / "intents.json"
            intents_path.write_text(
                (PROJECT_ROOT / "results" / "pilot_intents.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            results_path = root / "heldout.csv"; summary_path = root / "heldout.json"
            run_heldout(
                config_path, intents_path, results_path, summary_path,
                retriever=MockRetriever(),
            )
            with results_path.open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 222)
            self.assertTrue(all(row["split_label"] == "heldout_test" for row in rows))
            for row in rows:
                if row["answerability"] == "unanswerable":
                    self.assertTrue(all(
                        row[field] == "" for field in (
                            "hit_at_1", "hit_at_3", "hit_at_5",
                            "first_relevant_rank", "reciprocal_rank",
                        )
                    ))

    def test_unanswerable_metrics_blank_and_csv_arrays_valid(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_dir = root / "configs"
            data_dir = root / "data" / "evaluation"
            output_dir = root / "results"
            config_dir.mkdir(parents=True)
            data_dir.mkdir(parents=True)

            benchmark_path = data_dir / "benchmark.csv"
            fieldnames = list(self.benchmark[0])
            with benchmark_path.open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(self.benchmark)
            config = {
                "experiment_id": "test-run",
                "corpus": {"corpus_version": "test-v1"},
                "benchmark": {"file": "data/evaluation/benchmark.csv"},
                "reproducibility": {"random_seed": 42},
            }
            config_path = config_dir / "experiment_config.yaml"
            config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
            intents_path = root / "pilot_intents.json"
            source_intents = json.loads(
                (PROJECT_ROOT / "results" / "pilot_intents.json").read_text(encoding="utf-8")
            )
            intents_path.write_text(json.dumps(source_intents), encoding="utf-8")

            results_path = output_dir / "results.csv"
            summary_path = output_dir / "summary.json"
            run_pilot(
                config_path, pilot_intents_path=intents_path,
                output_results=results_path, output_summary=summary_path,
                retriever=MockRetriever(),
            )
            with results_path.open(
                encoding="utf-8-sig", newline=""
            ) as stream:
                rows = list(csv.DictReader(stream))
            for row in rows:
                self.assertIsInstance(json.loads(row["retrieved_chunk_ids"]), list)
                self.assertIsInstance(json.loads(row["retrieved_pages"]), list)
                self.assertTrue(all(isinstance(x, list) for x in json.loads(row["retrieved_page_sets"])))
                self.assertIsInstance(json.loads(row["retrieved_scores"]), list)
                if row["answerability"] == "unanswerable":
                    for field in (
                        "hit_at_1", "hit_at_3", "hit_at_5",
                        "first_relevant_rank", "reciprocal_rank",
                    ):
                        self.assertEqual(row[field], "")

    def test_v1_results_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_dir = root / "configs"; data_dir = root / "data" / "evaluation"
            config_dir.mkdir(parents=True); data_dir.mkdir(parents=True)
            benchmark_path = data_dir / "benchmark.csv"
            with benchmark_path.open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(self.benchmark[0]))
                writer.writeheader(); writer.writerows(self.benchmark)
            config_path = config_dir / "config.yaml"
            config_path.write_text(yaml.safe_dump({
                "experiment_id": "test", "corpus": {"corpus_version": "v"},
                "benchmark": {"file": "data/evaluation/benchmark.csv"},
                "reproducibility": {"random_seed": 42},
            }), encoding="utf-8")
            intents_path = root / "intents.json"
            intents_path.write_text((PROJECT_ROOT / "results" / "pilot_intents.json").read_text(encoding="utf-8"), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "protected v1.0"):
                run_pilot(
                    config_path, intents_path,
                    root / "pilot_retrieval_results_v1.0.csv",
                    root / "safe-summary.json", retriever=MockRetriever(),
                )


if __name__ == "__main__":
    unittest.main()
