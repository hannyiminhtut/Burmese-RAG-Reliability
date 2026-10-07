# Held-Out Semantic Annotation Protocol v1.0

## 1. Status and Scope

- Protocol version: `semantic-annotation-protocol-v1.0`
- Run-freeze ID: `UIT-HELDOUT-RUN-FREEZE-v1.1-20260819-03`
- Held-out run: `uit-ollama-heldout-v1.1-20260819-03`
- Experimental units: 222 frozen held-out question variants from 74 semantic intents
- Development questions included: 0

This protocol is prospective: it is frozen before semantic annotation begins. It supplements, but does not replace, `docs/evaluation_protocol.md` and `docs/evaluation_protocol_addendum_v1.0.md`. It does not modify or rescore generated outputs.

## 2. Annotation Objective

The annotation determines whether each frozen response made the correct decision, answered correctly, remained grounded in its supplied evidence, avoided hallucination, cited supporting evidence, followed its language condition, and produced clean output. It also attributes failures to retrieval, generation, citation, contract, infrastructure, or benchmark/evidence ambiguity.

## 3. Evidence Boundary

For each record, reviewers may use only:

- the frozen question;
- the frozen answerability label and gold answer;
- the exact five evidence chunks supplied to the generator, including chunk IDs, pages, and text;
- the frozen structured decision, generated answer, and original citations;
- contract-validation and infrastructure metadata.

Reviewers must not search the full corpus, website, internet, other benchmark rows, or model outputs for other variants when judging a record. Full-corpus information may be consulted only in a separately declared benchmark-quality investigation, never to change the primary Top-5-conditioned annotation.

## 4. Unit of Annotation

The primary unit is one question variant. A claim is the smallest independently verifiable factual proposition in an `ANSWER`. Reviewers must identify all material claims, including numbers, conditions, exceptions, procedures, dates, definitions, and additional information not requested by the question.

## 5. Frozen Output Handling

- Use the structured `decision` field as the authoritative `ANSWER`/`ABSTAIN` decision.
- Never repair malformed wording, remove stray characters, translate text, replace citations, or infer a different decision.
- Retain all ten contract-validation failures in the main intent-to-treat analysis.
- If parsing succeeded, semantically evaluate the preserved decision, answer, and original citations even when later validation failed.
- If no valid model response exists, use `NOT_APPLICABLE` for semantic labels and classify the record as an infrastructure failure. The frozen held-out run currently contains no final infrastructure-failure record.
- Report a secondary contract-valid subset only as an explicitly labeled sensitivity analysis.

## 6. Required Labels

### 6.1 Decision Correctness

Allowed values: `CORRECT`, `INCORRECT`.

- Frozen `answerable` + `ANSWER` = `CORRECT`.
- Frozen `answerable` + `ABSTAIN` = `INCORRECT`.
- Frozen `unanswerable` + `ABSTAIN` = `CORRECT`.
- Frozen `unanswerable` + `ANSWER` = `INCORRECT`.

This benchmark-relative label is separate from evidence-conditioned decision appropriateness below.

### 6.2 Evidence-Conditioned Decision Appropriateness

Allowed values: `APPROPRIATE`, `INAPPROPRIATE`, `AMBIGUOUS`.

- `ANSWER` is appropriate only if the Top-5 contains sufficient evidence for the material answer.
- `ABSTAIN` is appropriate when the Top-5 lacks sufficient evidence.
- Use `AMBIGUOUS` only when reasonable reviewers cannot determine whether the supplied evidence is sufficient.

### 6.3 Answer Correctness

Allowed values: `CORRECT`, `PARTIAL`, `INCORRECT`, `NOT_APPLICABLE`.

- `CORRECT`: all information required by the question agrees with the gold answer; no material contradiction or omission.
- `PARTIAL`: contains a correct core answer but omits a required element, adds a material qualification that changes completeness, or mixes correct and incorrect material without making the core answer wholly wrong.
- `INCORRECT`: contradicts the gold answer, supplies the wrong rule or value, is irrelevant, or fails to provide the required answer.
- `NOT_APPLICABLE`: structured decision is `ABSTAIN` or no valid model response exists.

Extra unsupported claims affect groundedness and hallucination even when the requested core answer is correct.

### 6.4 Numeric Correctness

Allowed values: `CORRECT`, `INCORRECT`, `NOT_APPLICABLE`.

Apply when the gold answer requires one or more numeric values. `CORRECT` requires every required number, unit, bound, and condition to be correct. A missing or incorrect required numeric element is `INCORRECT`.

### 6.5 Groundedness

Allowed values: `FULLY_GROUNDED`, `PARTIALLY_GROUNDED`, `NOT_GROUNDED`, `NOT_APPLICABLE`.

- `FULLY_GROUNDED`: every material factual claim is directly supported by the supplied Top-5 evidence.
- `PARTIALLY_GROUNDED`: at least one material claim is supported and at least one is unsupported or contradicted.
- `NOT_GROUNDED`: no material answer claim is supported, or the central claim contradicts the supplied evidence.
- `NOT_APPLICABLE`: structured decision is `ABSTAIN` and the response makes no additional factual claim, or no valid model response exists.

Groundedness is evaluated against all Top-5 chunks, not only cited chunks.

### 6.6 Hallucination

Allowed values: `YES`, `NO`, `NOT_APPLICABLE`.

- `YES`: at least one material factual claim is unsupported by or contradicts the supplied Top-5 evidence.
- `NO`: every material factual claim is supported, or a compliant abstention makes no factual claim.
- `NOT_APPLICABLE`: no valid model response exists.

Irrelevant but supported information is not hallucination; record it as over-generation in reviewer notes and consider whether answer correctness is partial. Unsupported extra information is hallucination.

### 6.7 Citation Support

Allowed values: `FULL`, `PARTIAL`, `NONE`, `NOT_APPLICABLE`.

- `FULL`: every material factual claim is supported by at least one of its cited chunk-page pairs, and every citation supports a material claim.
- `PARTIAL`: at least one material claim is supported by a citation, but another claim lacks citation support, or at least one citation is irrelevant/redundant while material support exists elsewhere among the citations.
- `NONE`: citations are absent for an `ANSWER`, invented, use the wrong page, or none supports a material claim.
- `NOT_APPLICABLE`: `ABSTAIN` with no citations or no valid model response.

Syntactically valid chunk IDs and pages do not prove semantic support. Duplicate citations do not add support and should be noted.

### 6.8 Language Consistency

Allowed values: `PASS`, `FAIL`, `NOT_APPLICABLE`.

- EN `ANSWER`: meaningful answer content must be English.
- MY `ANSWER`: meaningful answer content must be Burmese; standard academic abbreviations and unavoidable English terms do not cause failure.
- MIX `ANSWER`: meaningful Burmese and English content must both be present and form a natural code-mixed response.
- Exact deterministic English `ABSTAIN`: `NOT_APPLICABLE` under the approved addendum.
- Non-exact `ABSTAIN`: evaluate the generated text under the assigned language condition because it is not the deterministic response.
- No valid model response: `NOT_APPLICABLE`.

Script presence alone is insufficient; reviewers assess whether the response meaningfully follows the language condition.

### 6.9 Output Cleanliness

Allowed values: `PASS`, `FAIL`, `NOT_APPLICABLE`.

- `PASS`: readable answer without stray JSON/Markdown fragments, truncated text, duplicated clauses that impair quality, or obvious corruption.
- `FAIL`: contains artifacts such as a stray `{`, broken serialization text, severe truncation, or other visible contamination.
- `NOT_APPLICABLE`: no valid model response.

Minor stylistic awkwardness alone is not a cleanliness failure; note it separately.

### 6.10 Abstention Wording Compliance

Allowed values: `PASS`, `FAIL`, `NOT_APPLICABLE`.

- For `ABSTAIN`, `PASS` requires exact equality to: `The provided academic regulations do not contain sufficient information to answer the question.`
- Any prefix, suffix, explanation, translation, or altered wording is `FAIL`.
- For `ANSWER` or no valid model response, use `NOT_APPLICABLE`.

This metric is separate from the structured decision and language consistency.

### 6.11 Contract Validity

Allowed values: `PASS`, `FAIL`.

Copy this from the frozen validation outcome: `error_status=ok` is `PASS`; a parsing, citation, or output-contract validation error is `FAIL`. Do not reinterpret it manually.

## 7. Failure Attribution

Assign one primary value and zero or more secondary values:

- `NO_FAILURE`
- `RETRIEVAL_FAILURE`: an answerable record lacks sufficient evidence anywhere in Top-5.
- `GENERATION_FAILURE`: sufficient Top-5 evidence exists, but the model answers incorrectly, hallucinates, or abstains.
- `CITATION_FAILURE`: answer content may be supported, but citations are absent, invented, mismatched, or fail to support claims.
- `ABSTENTION_FAILURE`: decision or deterministic wording is incorrect beyond a retrieval-caused abstention.
- `LANGUAGE_FAILURE`: generated text violates its language condition.
- `OUTPUT_FORMAT_FAILURE`: parsing, schema, cleanliness, or other output-contract failure.
- `INFRASTRUCTURE_FAILURE`: no valid response after the bounded retry policy.
- `BENCHMARK_EVIDENCE_AMBIGUITY`: gold answer, answerability label, or Top-5 sufficiency is genuinely unclear.

Primary attribution precedence is causal, not merely symptomatic:

1. `INFRASTRUCTURE_FAILURE` when no response exists.
2. `BENCHMARK_EVIDENCE_AMBIGUITY` when reliable adjudication is impossible.
3. `RETRIEVAL_FAILURE` when necessary evidence is absent from Top-5.
4. `GENERATION_FAILURE` when sufficient evidence is present but unused or misused.
5. Use citation, abstention, language, or format as primary only when it is the principal failure and neither retrieval nor generation semantics better explains the outcome.

Record secondary failures independently so one primary cause does not hide other observed problems.

## 8. Retrieval-versus-Generation Diagnostic

For every benchmark-incorrect decision or incorrect/partial answer:

1. Inspect all five supplied chunks.
2. Record gold-evidence location as `TOP_1`, `TOP_2_TO_5`, `ABSENT_FROM_TOP_5`, or `AMBIGUOUS`.
3. Determine whether the Top-5 is sufficient to answer the question.
4. Attribute an answerable false abstention to:
   - retrieval failure if sufficient evidence is absent;
   - generation failure if sufficient evidence is present but unused;
   - benchmark/evidence ambiguity if sufficiency is unclear.

Do not infer retrieval failure solely from the automated gold-page Hit@5 field; reviewers must inspect the actual supplied text.

## 9. Reviewer Workflow

- Use two independent reviewers proficient in Burmese and able to assess Burmese-English code mixing.
- Reviewers must complete annotations independently and must not see the other reviewer's labels.
- Hide aggregate model performance and the other language variants of the same intent during initial annotation where practical.
- Present records in a fixed randomized order saved with the annotation package.
- Require concise evidence notes for every `PARTIAL`, `INCORRECT`, hallucination, non-full citation rating, ambiguity, and failure attribution.
- Evidence notes should identify relevant chunk IDs/pages without copying long passages.
- Reviewers must not edit frozen source or output fields.

## 10. Agreement and Adjudication

Calculate agreement before adjudication:

- raw percentage agreement for every categorical field;
- Cohen's kappa for two-reviewer nominal labels;
- weighted Cohen's kappa for ordered labels such as answer correctness, groundedness, and citation support;
- report label prevalence because kappa is sensitive to imbalance.

Do not calculate agreement on `NOT_APPLICABLE`-only subsets. Preserve both original reviewer files. A third qualified adjudicator or a documented consensus meeting resolves disagreements into a separate adjudicated file; original labels must never be overwritten.

## 11. Main Analysis Populations

- Primary intent-to-treat population: all 222 frozen held-out records.
- Answer-quality population: records with structured `ANSWER`; retain contract-invalid answers.
- Abstention population: records with structured `ABSTAIN`.
- Contract-valid sensitivity population: the 212 records with `error_status=ok`, reported only as secondary analysis.
- Language-consistency denominator: records for which language consistency is `PASS` or `FAIL`; exclude `NOT_APPLICABLE` deterministic abstentions.

Always report numerator, denominator, and exclusions.

## 12. Metrics After Adjudication

Report overall, by EN/MY/MIX, by answerability, and by language × answerability where sample sizes permit:

- decision accuracy and answerability confusion matrix;
- correct, partial, and incorrect answer rates;
- exact numeric accuracy;
- fully/partially/not-grounded rates;
- response-level hallucination rate;
- abstention precision, recall, F1, and incorrect-abstention rate;
- full/partial/no citation-support rates;
- language-consistency rate excluding `NOT_APPLICABLE`;
- output-cleanliness and contract-failure rates;
- retrieval-, generation-, citation-, abstention-, language-, format-, infrastructure-, and ambiguity-failure counts.

For the paired EN/MY/MIX design, preserve semantic-intent identifiers and use paired comparisons. Do not treat the three variants as independent observations when testing language-condition differences.

## 13. Prohibited Actions

- Do not regenerate, repair, delete, or replace held-out outputs.
- Do not tune prompts, models, retrieval, thresholds, or scoring rules using held-out annotations.
- Do not change benchmark labels or gold evidence inside the primary analysis.
- Do not silently exclude validation failures.
- Do not use development results as held-out results.
- Do not report unadjudicated semantic labels as final findings.

## 14. Acceptance Criteria

This protocol is ready for annotation when:

- it references the immutable held-out run-freeze ID;
- all labels have exhaustive allowed values and decision rules;
- Top-5-only evidence boundaries are explicit;
- contract-invalid outputs remain included;
- deterministic abstention and language consistency follow the approved addendum;
- reviewer independence, agreement, and adjudication procedures are specified;
- the protocol is hashed and frozen before annotation rows are created or scored.
