# Blinded Semantic Annotation Package v1.0

## Use

This package contains two independent reviewer copies for the 222 frozen held-out records. Reviewers must read `docs/semantic_annotation_protocol_v1.0.md` before annotation.

- Assign `reviewer_1_annotation.csv` to Reviewer 1.
- Assign `reviewer_2_annotation.csv` to Reviewer 2.
- Do not give reviewers `blinded_id_key.csv`; retain it for reconciliation and paired analysis.
- Reviewers must not compare labels until both copies are complete.
- Never edit frozen source columns. Enter judgments only in the empty columns beginning with `reviewer_id`.

## Blinding

Rows use reproducibly shuffled identifiers `UIT-ANN-001` through `UIT-ANN-222`. Reviewer files omit the original intent ID, variant ID, run ID, model name, retrieval scores, aggregate performance, and the other language variants' identities. The separate key restores identifiers after independent review.

## Allowed Annotation Values

- `decision_correctness`: `CORRECT`, `INCORRECT`
- `evidence_conditioned_decision_appropriateness`: `APPROPRIATE`, `INAPPROPRIATE`, `AMBIGUOUS`
- `answer_correctness`: `CORRECT`, `PARTIAL`, `INCORRECT`, `NOT_APPLICABLE`
- `numeric_correctness`: `CORRECT`, `INCORRECT`, `NOT_APPLICABLE`
- `groundedness`: `FULLY_GROUNDED`, `PARTIALLY_GROUNDED`, `NOT_GROUNDED`, `NOT_APPLICABLE`
- `hallucination`: `YES`, `NO`, `NOT_APPLICABLE`
- `citation_support`: `FULL`, `PARTIAL`, `NONE`, `NOT_APPLICABLE`
- `language_consistency`: `PASS`, `FAIL`, `NOT_APPLICABLE`
- `output_cleanliness`: `PASS`, `FAIL`, `NOT_APPLICABLE`
- `abstention_wording_compliance`: `PASS`, `FAIL`, `NOT_APPLICABLE`
- `contract_validity_confirmation`: `PASS`, `FAIL`
- `gold_evidence_location`: `TOP_1`, `TOP_2_TO_5`, `ABSENT_FROM_TOP_5`, `AMBIGUOUS`, `NOT_APPLICABLE`
- `primary_failure_attribution`: `NO_FAILURE`, `RETRIEVAL_FAILURE`, `GENERATION_FAILURE`, `CITATION_FAILURE`, `ABSTENTION_FAILURE`, `LANGUAGE_FAILURE`, `OUTPUT_FORMAT_FAILURE`, `INFRASTRUCTURE_FAILURE`, `BENCHMARK_EVIDENCE_AMBIGUITY`
- `secondary_failure_attributions`: zero or more failure values separated by `|`
- `reviewer_evidence_notes`: concise evidence-based notes, including chunk IDs/pages where required
- `annotation_complete`: `YES` only after every applicable field has been reviewed

Do not use values outside this codebook. Use UTF-8-capable spreadsheet software and preserve CSV encoding when saving.
