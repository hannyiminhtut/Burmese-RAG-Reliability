import json
import re
from pathlib import Path


DRAFT = Path(__file__).resolve().parents[1] / "docs" / "paper_draft_v1.0.md"
LITERATURE_AUDIT = DRAFT.with_name("literature_review_v1.0.md")
STATUS = DRAFT.with_name("paper_draft_status_v1.0.json")


def test_title_matches_the_evaluated_outcomes():
    first_line = DRAFT.read_text(encoding="utf-8").splitlines()[0]
    assert first_line == (
        "# Evaluating Retrieval and Abstention across Burmese, English, and "
        "Code-Mixed Queries in RAG for University Academic Regulations"
    )
    assert "Hallucination and Abstention" not in first_line


def test_draft_contains_frozen_population_and_primary_results():
    text = DRAFT.read_text(encoding="utf-8")
    for required in ("222", "180", "42", "87.22%", "73.42%", "60.81%", "79.73%"):
        assert required in text


def test_draft_preserves_semantic_evaluation_boundary():
    text = DRAFT.read_text(encoding="utf-8")
    assert "hallucination, and claim-level citation support were not evaluated" in text
    assert "does not report held-out hallucination" in text


def test_draft_has_only_resolved_numbered_citations():
    text = DRAFT.read_text(encoding="utf-8")
    for forbidden in ("(Author, Year)", "TODO citation", "citation needed", "Verified references will be added"):
        assert forbidden not in text
    body, references = text.split("## References", maxsplit=1)
    cited = {int(value) for value in re.findall(r"\[(\d+)\]", body)}
    defined = {int(value) for value in re.findall(r"(?m)^\[(\d+)\] ", references)}
    assert cited == defined == set(range(1, 9))


def test_literature_audit_and_conference_requirements_are_recorded():
    audit = LITERATURE_AUDIT.read_text(encoding="utf-8")
    status = json.loads(STATUS.read_text(encoding="utf-8"))
    assert "https://uit.edu.mm/icait-2026/" in audit
    assert "https://uit.edu.mm/app/uploads/2026/04/icait2026CFP.pdf" in audit
    assert status["citation_status"]["verified_references_added"] == 8
    assert status["citation_status"]["related_work_ready"] is True
    assert status["conference_status"]["maximum_pages"] == 6
    assert status["conference_status"]["submission_deadline"] == "2026-08-30"


def test_draft_references_frozen_publication_figures():
    text = DRAFT.read_text(encoding="utf-8")
    assert text.count("../results/publication_assets_v1.0/figures/") == 4
