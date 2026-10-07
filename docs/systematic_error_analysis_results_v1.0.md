# Systematic Structural Error Analysis Results v1.0

## Boundary

This analysis covers all 222 frozen held-out variants and zero development records. Categories are deterministic structural flags and may overlap. No semantic answer correctness, evidence sufficiency, groundedness, hallucination, translation error, or causal failure attribution was assessed.

## Structural Inventory

- False abstentions: 49
- False answers: 10
- Answerable gold-page misses at Hit@5: 23
- Contract-invalid records: 10
- Records with an infrastructure event recorded: 5
- Records with at least one structural flag: 77
- Records with multiple structural flags: 20

Because the flags overlap, their counts must not be added to obtain a total error count.

## Answerable Retrieval × Decision

| Gold-page Hit@5 | ANSWER | ABSTAIN | Total |
|---|---:|---:|---:|
| Hit | 123 | 34 | 157 |
| Miss | 8 | 15 | 23 |
| Total | 131 | 49 | 180 |

Of the 49 false abstentions, 34 occurred where the frozen retrieval evaluation recorded a gold-page intersection within Top-5 and 15 occurred where it did not. A gold-page intersection is not proof that the retrieved text was semantically sufficient, so these 34 cases cannot automatically be labelled generation failures. Similarly, the 15 misses cannot automatically be labelled retrieval failures.

### By Language

| Language | Hit + ANSWER | Hit + ABSTAIN | Miss + ANSWER | Miss + ABSTAIN |
|---|---:|---:|---:|---:|
| EN | 45 | 7 | 3 | 5 |
| MY | 30 | 19 | 3 | 8 |
| MIX | 48 | 8 | 2 | 2 |

MY had 19 false abstentions with a Top-5 gold-page hit, compared with 7 for EN and 8 for MIX. This is a retrieval-page/decision association only, not semantic causal attribution.

## Paired Language Disagreements

- Intents with nonidentical EN/MY/MIX decisions: 37/74
- Intents with identical decisions: 37/74
- MY false abstention while EN decision was correct: 21 intents
- MY false abstention while MIX decision was correct: 20 intents
- MY false abstention while both EN and MIX decisions were correct: 16 intents

Decision patterns among the 37 disagreement intents:

| EN | MY | MIX | Intents |
|---|---|---|---:|
| ABSTAIN | ABSTAIN | ANSWER | 7 |
| ABSTAIN | ANSWER | ABSTAIN | 2 |
| ABSTAIN | ANSWER | ANSWER | 4 |
| ANSWER | ABSTAIN | ABSTAIN | 5 |
| ANSWER | ABSTAIN | ANSWER | 17 |
| ANSWER | ANSWER | ABSTAIN | 2 |

The most common disagreement pattern was `ANSWER / ABSTAIN / ANSWER`, reinforcing the Step 6 finding that MY produced more false abstentions. This pattern does not identify why the model abstained.

## Contract and Infrastructure Boundary

Ten records failed deterministic citation/contract validation. Five records retain an infrastructure-event flag. These are preserved as separate structural dimensions; infrastructure events do not automatically imply missing final records, and all 222 records remain in the analysis.

## Paper-Ready Interpretation

Structural analysis found that 49 of 180 answerable variants received `ABSTAIN`, including 27 of 60 MY variants. Thirty-four false abstentions coincided with an automated Top-5 gold-page match, while 15 coincided with a miss. Across paired intents, 37 of 74 showed a language-dependent decision pattern, and the most frequent disagreement was EN=`ANSWER`, MY=`ABSTAIN`, MIX=`ANSWER` (17 intents). These findings localize the observed reliability difference to structured decision behavior, particularly MY abstention, but do not establish semantic evidence sufficiency, generation error, translation error, or hallucination.
