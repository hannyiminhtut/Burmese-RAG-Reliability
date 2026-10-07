# Paired Statistical Results v1.0

## Design

The analysis preserves the paired EN/MY/MIX design at the semantic-intent level. It includes 74 held-out intents: 60 answerable and 14 unanswerable. Development records are excluded. Binary proportions use 95% Wilson intervals; omnibus comparisons use Cochran's Q; pairwise comparisons use two-sided exact McNemar tests with Holm correction within each outcome.

These are automated non-semantic outcomes. Semantic answer correctness, groundedness, hallucination, and claim-level citation support remain `NOT_EVALUATED`.

## Structured Decision Correctness

| Language | Correct / N | Accuracy | 95% Wilson CI |
|---|---:|---:|---:|
| EN | 59/74 | 79.73% | 69.21%–87.31% |
| MY | 45/74 | 60.81% | 49.42%–71.14% |
| MIX | 59/74 | 79.73% | 69.21%–87.31% |

Cochran's Q showed a language-condition difference, `Q(2) = 10.595`, `p = 0.0050`; the maximum observed accuracy difference was 18.92 percentage points.

Holm-adjusted exact McNemar comparisons found:

- EN versus MY: paired difference 18.92 percentage points, matched odds ratio 3.00, adjusted `p = 0.0376`;
- MY versus MIX: paired difference −18.92 percentage points for MY relative to MIX, matched odds ratio 0.33, adjusted `p = 0.0376`;
- EN versus MIX: no observed accuracy difference, adjusted `p = 1.0000`.

Thus, MY had lower structured decision correctness than both EN and MIX in this frozen paired evaluation. This does not establish lower semantic answer quality.

## Retrieval Outcomes Among Answerable Intents

| Outcome | EN | MY | MIX | Cochran's Q p-value |
|---|---:|---:|---:|---:|
| Hit@1 | 31/60 (51.67%) | 28/60 (46.67%) | 36/60 (60.00%) | 0.2564 |
| Hit@3 | 45/60 (75.00%) | 45/60 (75.00%) | 49/60 (81.67%) | 0.5529 |
| Hit@5 | 52/60 (86.67%) | 49/60 (81.67%) | 56/60 (93.33%) | 0.0990 |

No retrieval Hit@k omnibus comparison reached the prespecified 0.05 threshold. No pairwise retrieval difference remained significant after Holm correction. MIX had the highest observed Hit@1, Hit@3, and Hit@5 values, but these descriptive differences are not statistically conclusive in this sample.

## False Abstention Among Answerable Intents

| Language | False abstentions / N | Rate | 95% Wilson CI |
|---|---:|---:|---:|
| EN | 12/60 | 20.00% | 11.83%–31.78% |
| MY | 27/60 | 45.00% | 33.09%–57.51% |
| MIX | 10/60 | 16.67% | 9.31%–28.03% |

The omnibus comparison was significant, `Q(2) = 16.188`, `p = 0.00031`.

- MY versus EN: MY was 25.00 percentage points higher; adjusted `p = 0.01185`.
- MY versus MIX: MY was 28.33 percentage points higher; adjusted `p = 0.00146`.
- EN versus MIX: difference 3.33 percentage points; adjusted `p = 0.7905`.

The structured decision difference is therefore primarily associated with a higher observed false-abstention rate for MY questions.

## False Answers Among Unanswerable Intents

| Language | False answers / N | Rate | 95% Wilson CI |
|---|---:|---:|---:|
| EN | 3/14 | 21.43% | 7.57%–47.59% |
| MY | 2/14 | 14.29% | 4.01%–39.94% |
| MIX | 5/14 | 35.71% | 16.34%–61.24% |

The language comparison was not statistically significant, `Q(2) = 2.800`, `p = 0.2466`; all Holm-adjusted pairwise p-values were 1.0. The wide intervals reflect the small unanswerable sample of 14 paired intents, so absence of significance must not be interpreted as equivalence.

## Interpretation for the Paper

The paired analysis provides evidence of a language-condition difference in structured answer-versus-abstain decision correctness, driven by more false abstentions for MY. In contrast, paired retrieval Hit@1, Hit@3, and Hit@5 differences were not statistically significant. This pattern is consistent with a downstream decision-behavior difference, but the absence of human semantic evaluation prevents attribution to translation quality, prompt interpretation, evidence sufficiency, answer correctness, or hallucination.

No experimental component may be tuned using these held-out findings. Results should be presented with exact denominators, confidence intervals, adjusted p-values, effect sizes, and the semantic-evaluation limitation.
