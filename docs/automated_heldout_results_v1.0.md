# Automated Non-Semantic Held-Out Results v1.0

## Evaluation Boundary

These are held-out results for the 222 frozen question variants in `uit-ollama-heldout-v1.1-20260819-03`. The five development intents are excluded. No human semantic annotation or AI proxy annotation was performed.

Accordingly, these results evaluate retrieval, the structured `ANSWER`/`ABSTAIN` decision, deterministic output-contract compliance, and system reliability. They do not measure semantic answer correctness, groundedness, hallucination, or claim-level citation support.

## Population

- Semantic intents: 74
- Question variants: 222
- Answerable: 180
- Unanswerable: 42
- EN: 74
- MY: 74
- MIX: 74
- Structured decisions: 141 `ANSWER` and 81 `ABSTAIN`

## Frozen Retrieval Results

For the 180 answerable variants:

| Scope | Hit@1 | Hit@3 | Hit@5 | MRR |
|---|---:|---:|---:|---:|
| Overall | 52.78% | 77.22% | 87.22% | 0.6577 |
| EN | 51.67% | 75.00% | 86.67% | 0.6444 |
| MY | 46.67% | 75.00% | 81.67% | 0.6039 |
| MIX | 60.00% | 81.67% | 93.33% | 0.7247 |

## Structured Decision Results

`ABSTAIN` is treated as the positive decision.

| Frozen label / model decision | ANSWER | ABSTAIN |
|---|---:|---:|
| Answerable | 131 | 49 |
| Unanswerable | 10 | 32 |

- Decision accuracy: 163/222 = 73.42%
- Abstention precision: 32/81 = 39.51%
- Abstention recall: 32/42 = 76.19%
- Abstention F1: 64/123 = 52.03%
- False abstentions: 49/180 answerable variants
- False answers: 10/42 unanswerable variants

### Decision Results by Language

| Language | Accuracy | Abstention precision | Abstention recall | Abstention F1 |
|---|---:|---:|---:|---:|
| EN | 59/74 = 79.73% | 11/23 = 47.83% | 11/14 = 78.57% | 22/37 = 59.46% |
| MY | 45/74 = 60.81% | 12/39 = 30.77% | 12/14 = 85.71% | 24/53 = 45.28% |
| MIX | 59/74 = 79.73% | 9/19 = 47.37% | 9/14 = 64.29% | 18/33 = 54.55% |

The lower MY decision accuracy is an observed automated decision result. Without semantic annotation, it must not be interpreted as proof of lower Burmese answer quality or hallucination performance.

## Contract and Reliability Results

- Contract-valid records: 212/222 = 95.50%
- Frozen validation failures: 10/222 = 4.50%
- Exact abstention wording compliance: 78/81 = 96.30%
- Mechanically validated `ANSWER` outputs: 134/141 = 95.04%
- Records carrying an infrastructure-error flag: 5/222 = 2.25%
- Infrastructure classification observed: `model_runner_unexpected_stop`
- Validation failures observed: ten `ValueError` records at `citation_and_contract_validation`

An infrastructure-error flag records that an attempt encountered an infrastructure event; it does not by itself imply that the final record was missing. All 222 frozen records remain in the analysis.

## Runtime Description

- Mean total runtime per record: 69.06 seconds
- Median total runtime: 65.82 seconds
- Minimum–maximum total runtime: 32.56–127.55 seconds
- Total runtime across records: 15,331.29 seconds (approximately 4.26 hours)
- Mean prompt length: 1,142.38 tokens
- Prompt-token range: 731–1,795
- Mean attempts per record: 1.023; range 1–2

## Measures Not Evaluated

The following results are `NOT_EVALUATED`:

- semantic answer correctness and numeric correctness;
- groundedness and hallucination rate;
- claim-level citation support;
- semantic language consistency;
- semantic failure attribution;
- benchmark/evidence ambiguity;
- inter-rater agreement and adjudicated semantic metrics.

Contract validity must not be used as a substitute for any of these semantic measures.

## Paper-Ready Limitation Statement

Qualified independent reviewers were unavailable; therefore, the held-out study did not estimate semantic answer correctness, groundedness, hallucination, or claim-level citation support. The reported held-out results are limited to retrieval effectiveness, structured answer-versus-abstain decisions, deterministic contract compliance, and system reliability. This limitation prevents conclusions about end-to-end semantic answer quality and must be considered when interpreting language-condition differences.

## Reproducibility

The machine-readable JSON contains the complete aggregate result structure, while the CSV provides a compact paper-table representation with numerators, denominators, values, and evaluation status. Both are tied to the frozen held-out run and waiver by SHA-256 hashes in the analysis manifest and result freeze.
