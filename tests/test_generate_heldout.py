import json
import os
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock

from src.experiment_freeze import DEFAULT_FREEZE, PROJECT_ROOT, load_freeze, verify_freeze
from src.generate_heldout import (
    language_consistency, load_heldout_inputs, run, verify_live_ollama,
)
from src.generate_pilot import ABSTENTION_RESPONSE


class HeldoutGenerationTests(unittest.TestCase):
    def test_live_preflight_accepts_observed_unprefixed_digest(self):
        manifest = load_freeze(DEFAULT_FREEZE)
        class Client:
            def version(self): return "0.32.13"
            def model_info(self):
                return {
                    "name": "gemma3:4b-it-q4_K_M",
                    "digest": "a2af6cc3eb7fa8be8504abaf9b04e88f17a119ec3f04a3addf55f92841195f5a",
                }
        audit = verify_live_ollama(Client(), manifest)
        self.assertTrue(audit["digest_match"])
        self.assertEqual(audit["raw_api_digest"], Client().model_info()["digest"])
        self.assertEqual(audit["frozen_digest"], manifest["generation"]["ollama_model_manifest_digest"])

    def test_live_preflight_rejects_genuinely_different_digest(self):
        manifest = load_freeze(DEFAULT_FREEZE)
        class Client:
            def version(self): return "0.32.13"
            def model_info(self):
                return {"name": "gemma3:4b-it-q4_K_M", "digest": "b" * 64}
        with self.assertRaisesRegex(ValueError, "digest differs"):
            verify_live_ollama(Client(), manifest)
    def test_freeze_hash_verification(self):
        manifest = verify_freeze(DEFAULT_FREEZE)
        self.assertEqual(manifest["freeze_id"], "UIT-RAG-FREEZE-v1.1-20260819")

    def test_altered_input_refusal(self):
        manifest = load_freeze(DEFAULT_FREEZE)
        manifest["artifacts"]["benchmark"]["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as temporary_directory:
            altered = Path(temporary_directory) / "altered.json"
            altered.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "benchmark: SHA-256 mismatch"):
                verify_freeze(altered, root=PROJECT_ROOT)

    def test_exact_heldout_and_development_counts(self):
        manifest = verify_freeze(DEFAULT_FREEZE)
        selected = load_heldout_inputs(manifest, PROJECT_ROOT)
        self.assertEqual(len(selected["inputs"]), 222)
        self.assertEqual(
            sum(row["benchmark"]["intent_id"] in selected["pilot_ids"] for row in selected["inputs"]),
            0,
        )

    def test_abstention_language_is_not_applicable(self):
        for language in ("EN", "MY", "MIX"):
            self.assertEqual(
                language_consistency("ABSTAIN", language, ABSTENTION_RESPONSE),
                "NOT_APPLICABLE",
            )

    def test_answer_language_is_evaluated_normally(self):
        self.assertEqual(language_consistency("ANSWER", "EN", "English answer"), "PASS")
        self.assertEqual(language_consistency("ANSWER", "EN", "မြန်မာ answer"), "FAIL")
        self.assertEqual(language_consistency("ANSWER", "MY", "မြန်မာအဖြေ"), "PASS")
        self.assertEqual(language_consistency("ANSWER", "MIX", "မြန်မာ answer"), "PASS")
        self.assertEqual(language_consistency("ANSWER", "MIX", "English only"), "FAIL")

    @mock.patch.dict(os.environ, {"OLLAMA_NUM_PARALLEL": "1", "OLLAMA_MAX_LOADED_MODELS": "1"})
    def test_checkpoint_resume_and_no_overwrite(self):
        frozen = load_freeze(DEFAULT_FREEZE)

        class FakeClient:
            calls = 0
            def __init__(self, **_kwargs): pass
            def version(self): return frozen["generation"]["ollama_version"]
            def model_info(self):
                return {
                    "name": frozen["generation"]["ollama_model"],
                    "digest": frozen["generation"]["ollama_model_manifest_digest"],
                }
            def generate(self, _prompt, _settings, _schema):
                self.__class__.calls += 1
                return {
                    "response": json.dumps({
                        "decision": "ABSTAIN", "answer": ABSTENTION_RESPONSE,
                        "citations": [],
                    }),
                    "prompt_eval_count": 100,
                    "total_duration": 1,
                }

        with tempfile.TemporaryDirectory() as temporary_directory:
            args = Namespace(
                freeze=DEFAULT_FREEZE, output_root=Path(temporary_directory),
                base_url="http://localhost:11434", run_id="mock-heldout",
                dry_run=False, resume=False,
            )
            run(args, client_factory=FakeClient)
            jsonl = Path(temporary_directory) / "mock-heldout" / "mock-heldout.jsonl"
            self.assertEqual(len(jsonl.read_text(encoding="utf-8").splitlines()), 222)
            self.assertEqual(FakeClient.calls, 222)
            args.resume = True
            run(args, client_factory=FakeClient)
            self.assertEqual(FakeClient.calls, 222)
            args.resume = False
            with self.assertRaisesRegex(FileExistsError, "will not be overwritten"):
                run(args, client_factory=FakeClient)


if __name__ == "__main__":
    unittest.main()
