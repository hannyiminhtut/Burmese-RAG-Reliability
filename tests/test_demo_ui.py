from src.demo_ui import DemoService, detect_language


class FakeRetriever:
    def __init__(self):
        self.metadata = [
            {
                "chunk_id": f"CH-{index}", "page": index, "pages": [index],
                "section": "section", "text": f"မြန်မာ evidence {index}",
            }
            for index in range(1, 7)
        ]

    def retrieve(self, question, top_k):
        assert question == "credit requirement?"
        assert top_k == 5
        return [
            {
                "rank": index, "chunk_id": f"CH-{index}", "page": index,
                "pages": [index], "section": "section",
                "similarity_score": 1.0 / index,
            }
            for index in range(1, 6)
        ]


class FakeClient:
    def require_model(self):
        return "fake"

    def generate(self, prompt, settings, output_schema):
        assert "credit requirement?" in prompt
        assert prompt.count("EVIDENCE_") >= 10  # start and end markers for five blocks
        return {
            "response": '{"decision":"ANSWER","answer":"Supported.",'
            '"citations":[{"chunk_id":"CH-1","page":1}]}'
        }


def test_language_detection_preserves_three_demo_conditions():
    assert detect_language("What credits are required?") == "EN"
    assert detect_language("ခရက်ဒစ် ဘယ်လောက်လိုပါသလဲ") == "MY"
    assert detect_language("credit ဘယ်လောက်လိုပါသလဲ") == "MIX"


def test_demo_uses_exactly_top_five_and_returns_evidence_without_persistence():
    service = DemoService(retriever=FakeRetriever(), client=FakeClient())
    result = service.answer("credit requirement?", "EN")
    assert result["decision"] == "ANSWER"
    assert result["citations"] == [{"chunk_id": "CH-1", "page": 1}]
    assert len(result["evidence"]) == 5
    assert result["testing_only"] is True


def test_demo_rejects_empty_question_and_invalid_language():
    service = DemoService(retriever=FakeRetriever(), client=FakeClient())
    for question, language in ((" ", "EN"), ("question", "XX")):
        try:
            service.answer(question, language)
        except ValueError:
            pass
        else:
            raise AssertionError("Expected ValueError")
