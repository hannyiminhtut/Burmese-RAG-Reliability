import json
import os
import tempfile
import unittest
from unittest import mock
from argparse import Namespace
from pathlib import Path

from src.generate_pilot import (
    ABSTENTION_RESPONSE, OUTPUT_SCHEMA, build_prompt, generate_one,
    classify_infrastructure_error, parse_generation, run, validate_citations,
)
from src.ollama_client import OllamaModelError, OllamaResponseError


def sample_item(language="MY"):
    return {
        "benchmark": {"intent_id": "Q001", "variant_id": f"Q001-{language}",
                      "language_condition": language, "answerability": "answerable",
                      "question": "တက္ကသိုလ် GPA rule ကဘာလဲ?"},
        "retrieval": {},
        "chunks": [{"chunk_id": f"C{i}", "source_id": "UIT-SRC-025", "page": i,
                    "pages": [i, i + 1], "text": f"မြန်မာ evidence {i}"}
                   for i in range(1, 6)],
    }


def output(decision="ANSWER", answer="GPA အဖြေ", citations=None):
    return {"decision": decision, "answer": answer,
            "citations": [{"chunk_id": "C1", "page": 1}] if citations is None else citations}


class FakeGenerationClient:
    def __init__(self, model_output, **envelope):
        self.model_output, self.envelope, self.schema = model_output, envelope, None

    def generate(self, _prompt, _settings, schema):
        self.schema = schema
        return {"response": self.model_output, **self.envelope}


class GeneratePilotTests(unittest.TestCase):
    def test_integer_page_answer_accepted(self):
        result = parse_generation(json.dumps(output(), ensure_ascii=False))
        validate_citations(result, sample_item()["chunks"])
        self.assertEqual(result["citations"], [{"chunk_id": "C1", "page": 1}])
        self.assertEqual(result["citation_normalizations"], [])

    def test_digit_only_page_string_is_explicitly_normalized(self):
        result = parse_generation(json.dumps(output(citations=[{"chunk_id": "C1", "page": "1"}])))
        validate_citations(result, sample_item()["chunks"])
        self.assertEqual(result["citations"][0]["page"], 1)
        self.assertEqual(result["citation_normalizations"][0]["original_page_value"], "1")
        self.assertEqual(result["citation_normalizations"][0]["normalized_page_value"], 1)

    def test_nonnumeric_page_rejected(self):
        with self.assertRaisesRegex(OllamaResponseError, "digit-only"):
            parse_generation(json.dumps(output(citations=[{"chunk_id": "C1", "page": "page 1"}])))

    def test_page_range_rejected(self):
        with self.assertRaisesRegex(OllamaResponseError, "digit-only"):
            parse_generation(json.dumps(output(citations=[{"chunk_id": "C1", "page": "1-2"}])))

    def test_invented_chunk_rejected(self):
        result = parse_generation(json.dumps(output(citations=[{"chunk_id": "INVENTED", "page": 1}])))
        with self.assertRaisesRegex(ValueError, "Invented"):
            validate_citations(result, sample_item()["chunks"])

    def test_correct_chunk_wrong_page_rejected(self):
        result = parse_generation(json.dumps(output(citations=[{"chunk_id": "C1", "page": 99}])))
        with self.assertRaisesRegex(ValueError, "does not match"):
            validate_citations(result, sample_item()["chunks"])

    def test_chunk_id_paired_with_another_chunks_page_rejected(self):
        result = parse_generation(json.dumps(output(citations=[{"chunk_id": "C1", "page": 3}])))
        with self.assertRaisesRegex(ValueError, "does not match"):
            validate_citations(result, sample_item()["chunks"])

    def test_answer_requires_a_citation(self):
        result = parse_generation(json.dumps(output(citations=[])))
        with self.assertRaisesRegex(ValueError, "at least one citation"):
            validate_citations(result, sample_item()["chunks"])

    def test_abstain_with_no_citation(self):
        result = parse_generation(json.dumps(output(decision="ABSTAIN", answer=ABSTENTION_RESPONSE,
                                                      citations=[])))
        validate_citations(result, sample_item()["chunks"])

    def test_abstain_with_extra_explanation_rejected_but_decision_preserved(self):
        text = ABSTENTION_RESPONSE + " Extra explanation."
        raw = json.dumps(output(decision="ABSTAIN", answer=text, citations=[]))
        record = generate_one(FakeGenerationClient(raw, total_duration=10), "test", sample_item())
        self.assertTrue(record["abstention_decision"])
        self.assertFalse(record["abstention_wording_compliant"])
        self.assertEqual(record["decision"], "ABSTAIN")
        self.assertEqual(record["generated_answer"], text)
        self.assertEqual(record["validation_stage"], "citation_and_contract_validation")
        self.assertIn("deterministic response", record["validation_error"])
        self.assertEqual(record["parsed_response"]["answer"], text)

    def test_failure_evidence_and_timing_retained_after_validation_failure(self):
        raw = json.dumps(output(citations=[{"chunk_id": "C1", "page": 99}]))
        client = FakeGenerationClient(raw, total_duration=10, load_duration=2,
                                      prompt_eval_duration=3, eval_duration=5)
        record = generate_one(client, "test", sample_item())
        self.assertEqual(record["raw_model_response"], raw)
        self.assertEqual(record["raw_response"], raw)
        self.assertEqual(record["original_citations"], [{"chunk_id": "C1", "page": 99}])
        self.assertEqual(record["parsed_model_output"]["citations"][0]["page"], 99)
        self.assertEqual(record["decision"], "ANSWER")
        self.assertEqual(record["ollama_total_duration_ns"], 10)
        self.assertEqual(record["eval_duration_ns"], 5)
        self.assertEqual(record["validation_stage"], "citation_and_contract_validation")
        self.assertEqual(client.schema, OUTPUT_SCHEMA)

    def test_raw_response_retained_after_parsing_failure(self):
        raw = "not-json"
        record = generate_one(FakeGenerationClient(raw, total_duration=10), "test", sample_item())
        self.assertEqual(record["raw_model_response"], raw)
        self.assertIn(raw, record["raw_ollama_response"])
        self.assertEqual(record["error_status"], "OllamaResponseError")

    def test_parsed_but_invalid_schema_output_retained(self):
        raw_document = output(citations=[{"chunk_id": "C1", "page": "page 1"}])
        record = generate_one(FakeGenerationClient(json.dumps(raw_document), total_duration=10),
                              "test", sample_item())
        self.assertEqual(record["parsed_model_output"], raw_document)

    def test_utf8_preserved_for_english_myanmar_and_mix(self):
        self.assertIn("Answer in English", build_prompt(sample_item("EN")))
        self.assertIn("Answer in Myanmar", build_prompt(sample_item("MY")))
        self.assertIn("Burmese-English mixed", build_prompt(sample_item("MIX")))
        self.assertIn("တက္ကသိုလ်", build_prompt(sample_item("MY")))
        parsed = parse_generation(json.dumps(output(answer="မြန်မာ GPA answer"), ensure_ascii=False))
        self.assertEqual(parsed["answer"], "မြန်မာ GPA answer")

    def test_prompt_uses_unambiguous_evidence_blocks(self):
        prompt = build_prompt(sample_item("MIX"))
        self.assertIn("EVIDENCE_1\nchunk_id: C1\npage: 1\ntext:", prompt)
        self.assertIn("chunk_id and page are an inseparable pair", prompt)
        self.assertIn("no explanation, prefix, suffix, translation, or citation", prompt)

    def test_http_500_runner_stop_and_bad_alloc_classification(self):
        stopped = OllamaModelError(
            "Ollama HTTP 500: model runner has unexpectedly stopped",
            status_code=500,
        )
        allocation = OllamaModelError(
            "Ollama HTTP 500: std::bad_alloc GGML_ASSERT failed",
            status_code=500,
        )
        self.assertEqual(classify_infrastructure_error(stopped), "model_runner_unexpected_stop")
        self.assertEqual(
            classify_infrastructure_error(allocation),
            "model_runner_memory_allocation_failure",
        )

    def test_bounded_retry_and_attempt_history_preservation(self):
        class CrashClient:
            calls = 0
            def generate(self, _prompt, _settings, _schema):
                self.calls += 1
                raise OllamaModelError(
                    "Ollama HTTP 500: std::bad_alloc GGML_ASSERT failed",
                    status_code=500,
                )
        client = CrashClient()
        cooldowns = []
        record = generate_one(client, "test", sample_item(), sleep_func=cooldowns.append)
        self.assertEqual(client.calls, 2)
        self.assertEqual(cooldowns, [5.0])
        self.assertEqual(record["attempt_count"], 2)
        self.assertEqual(len(record["attempt_history"]), 2)
        self.assertTrue(all(attempt["infrastructure_error"] for attempt in record["attempt_history"]))

    def test_validation_error_is_not_retried(self):
        client = FakeGenerationClient(json.dumps(output(citations=[{"chunk_id": "C1", "page": 99}])))
        record = generate_one(client, "test", sample_item(), sleep_func=lambda _seconds: self.fail("retried"))
        self.assertEqual(record["attempt_count"], 1)
        self.assertFalse(record["infrastructure_error"])
        self.assertEqual(len(record["attempt_history"]), 1)

    @mock.patch.dict(os.environ, {"OLLAMA_NUM_PARALLEL": "1", "OLLAMA_MAX_LOADED_MODELS": "1"})
    def test_runner_checkpoints_and_resumes_without_repeating_questions(self):
        class FakeClient:
            generation_calls = 0
            def __init__(self, **_kwargs): pass
            def version(self): return "test-version"
            def require_model(self): return "gemma3:4b-it-q4_K_M"
            def generate(self, _prompt, _settings, _schema):
                FakeClient.generation_calls += 1
                return {"response": json.dumps(output(decision="ABSTAIN",
                                                       answer=ABSTENTION_RESPONSE, citations=[])),
                        "total_duration": 1}

        with tempfile.TemporaryDirectory() as temporary_directory:
            output_root = Path(temporary_directory)
            args = Namespace(config=Path("configs/experiment_config_v1.1.yaml"),
                             pilot_intents=Path("results/pilot_intents.json"),
                             retrieval_results=Path("results/pilot_retrieval_results_v1.1.csv"),
                             output_root=output_root, base_url="http://localhost:11434",
                             model="gemma3:4b-it-q4_K_M", timeout_seconds=600.0,
                             run_id="mocked-pilot", dry_run=False, resume=False)
            run(args, client_factory=FakeClient)
            jsonl_path = output_root / "mocked-pilot" / "mocked-pilot.jsonl"
            self.assertEqual(len(jsonl_path.read_text(encoding="utf-8").splitlines()), 15)
            self.assertEqual(FakeClient.generation_calls, 15)
            manifest_path = output_root / "mocked-pilot" / "mocked-pilot_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["resource_profile_version"], "uit-cpu-safe-v1")
            self.assertEqual(manifest["resource_profile"]["required_ollama_environment"], {
                "OLLAMA_NUM_PARALLEL": "1", "OLLAMA_MAX_LOADED_MODELS": "1"
            })
            args.resume = True
            run(args, client_factory=FakeClient)
            self.assertEqual(FakeClient.generation_calls, 15)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["prompt_version"] = "uit-context-only-json-v1"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "prompt/parser contract changed"):
                run(args, client_factory=FakeClient)
            args.resume = False
            with self.assertRaisesRegex(FileExistsError, "will not be overwritten"):
                run(args, client_factory=FakeClient)


if __name__ == "__main__":
    unittest.main()
