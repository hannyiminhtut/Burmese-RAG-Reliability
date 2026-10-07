# Semantic Evaluation Waiver and Automated Analysis Addendum v1.0

## Status

- Version: `semantic-evaluation-waiver-v1.0`
- Applies prospectively to the frozen held-out run `uit-ollama-heldout-v1.1-20260819-03`.
- Reason: two qualified, independent human reviewers are not available.
- This addendum does not replace or rewrite the frozen semantic annotation protocol.

## Methodological Decision

The planned two-reviewer semantic annotation, inter-rater agreement, and adjudication are waived. The blank reviewer templates remain unannotated and must not be represented as completed human evaluation.

The study may report only reproducible measures derivable directly from frozen benchmark labels, retrieval outputs, structured model outputs, request metadata, and deterministic validators. No AI-generated labels will be inserted into the human-review fields.

## Permitted Automated Measures

- frozen population and language-condition counts;
- retrieval Hit@1, Hit@3, Hit@5, and MRR for answerable questions;
- structured `ANSWER` versus `ABSTAIN` confusion matrix against frozen answerability labels;
- decision accuracy;
- abstention precision, recall, and F1, treating `ABSTAIN` as the positive decision;
- false-abstention and false-answer counts;
- parser and output-contract validity;
- deterministic abstention-wording compliance;
- mechanically validated citation-contract outcomes;
- infrastructure-error counts and classifications;
- request-attempt, runtime, and Ollama duration summaries;
- results stratified by EN, MY, and MIX where the denominator is nonzero.

Every reported rate must include its numerator and denominator.

## Measures Not Evaluated

The following require semantic judgment and are recorded as `NOT_EVALUATED`:

- semantic answer correctness;
- numeric correctness beyond exact deterministic validation already frozen;
- groundedness of every generated claim;
- hallucination rate;
- claim-level citation support;
- nuanced language consistency beyond the frozen deterministic field;
- retrieval-versus-generation failure attribution requiring evidence interpretation;
- benchmark or evidence ambiguity.

These measures must not be inferred from valid JSON, valid citation syntax, citation-page matching, retrieval Hit@k, or agreement with the gold answer string.

## Reporting Rules

- Describe the resulting evaluation as an **automated non-semantic held-out analysis**.
- Do not call it human evaluation, semantic annotation, adjudication, or inter-rater agreement.
- Do not calculate Cohen's kappa from blank, duplicated, machine-generated, or proxy reviewer labels.
- Do not claim that contract-valid responses are semantically correct or non-hallucinatory.
- Preserve all 222 held-out records, including the ten frozen validation failures.
- Preserve the primary intent-to-treat population and report the contract-valid subset only as a sensitivity description.
- Do not tune any frozen experimental component from held-out observations.

## Relationship to Existing Frozen Materials

The following remain unchanged:

- `docs/semantic_annotation_protocol_v1.0.md`;
- `freezes/uit-semantic-annotation-protocol-v1.0/semantic_annotation_protocol_freeze.json`;
- the blinded annotation package and its empty reviewer labels;
- the held-out run, benchmark, retrieval results, corpus, index, prompt, parser, model, and split.

## Limitation for the Paper

Because qualified independent reviewers were unavailable, the study does not estimate semantic answer accuracy, groundedness, hallucination, or claim-level citation support on the held-out set. Automated results characterize retrieval performance, answer-versus-abstain decisions, deterministic contract compliance, and system reliability only. Conclusions must be limited accordingly.

## Acceptance Criteria

This addendum is ready for use when it is versioned and hashed before automated analysis, the analysis verifies all frozen inputs, all 222 held-out records are retained, no development record is included, and every human-dependent measure is explicitly marked `NOT_EVALUATED`.
