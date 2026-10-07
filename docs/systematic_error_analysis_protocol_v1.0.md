# Systematic Structural Error-Analysis Protocol v1.0

## Scope

This protocol governs a reproducible structural analysis of the frozen held-out retrieval and generation records. It retains all 222 question variants and excludes all five development intents. No model output, benchmark label, retrieval result, or experimental component may be changed.

## Permitted Classifications

The following labels are mechanically derivable:

- `false_abstention`: frozen label is answerable and structured decision is `ABSTAIN`;
- `false_answer`: frozen label is unanswerable and structured decision is `ANSWER`;
- `gold_page_hit_at_5` or `gold_page_miss_at_5`: copied from the frozen retrieval evaluation for answerable questions;
- `contract_invalid`: frozen `error_status` is not `ok`;
- `infrastructure_event_recorded`: frozen infrastructure-error flag is true;
- `language_decision_disagreement`: paired EN/MY/MIX decisions for an intent are not identical;
- paired correctness and false-abstention patterns derived from the frozen decisions.

Gold-page Hit@5 is an automated page-intersection measure. It must not be called proof that the supplied text was semantically sufficient. Conversely, a miss must not be called proof that no useful evidence existed.

## Required Analyses

- record-level inventory of every record with at least one structural flag;
- counts by language and answerability;
- answerable Hit@5 × structured-decision contingency tables;
- contract and infrastructure-event tables;
- intent-level EN/MY/MIX decision disagreement table;
- MY false-abstention patterns relative to paired EN and MIX variants;
- explicit overlap counts because one record may carry multiple flags.

## Prohibited Semantic Inferences

Do not assign or infer:

- semantic answer correctness or numeric correctness;
- hallucination or groundedness;
- claim-level citation support;
- translation error;
- evidence sufficiency;
- retrieval-versus-generation causal attribution;
- benchmark ambiguity.

These fields remain `NOT_EVALUATED` unless a future, separately approved human-review protocol is completed.

## Reproducibility and Reporting

- Verify all frozen source hashes before analysis.
- Require exactly 222 unique variants, 74 paired intents, 180 answerable and 42 unanswerable variants, and 74 EN/MY/MIX variants each.
- Require one EN, MY, and MIX variant with consistent answerability for every intent.
- Preserve exact identifiers for auditing; do not publish the inventory as new annotation.
- Report denominators and clarify overlapping categories.
- Freeze the implementation and outputs after the complete test suite and count reconciliation pass.
