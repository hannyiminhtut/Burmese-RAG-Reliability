# Frozen Paired Statistical Analysis Protocol v1.0

## Scope

This protocol governs Step 6 statistical analysis of the frozen automated non-semantic held-out results. It applies to 74 semantic intents, each represented by paired EN, MY, and MIX variants. It does not authorize semantic annotation or experimental tuning.

## Analysis Populations

- All-intent population: 74 intents and 222 variants, used for structured decision correctness.
- Answerable population: 60 intents and 180 variants, used for retrieval Hit@1, Hit@3, Hit@5 and false-abstention comparisons.
- Unanswerable population: 14 intents and 42 variants, used for false-answer comparisons.
- Development intents `Q002`, `Q008`, `Q024`, `Q029`, and `Q057` are excluded.

The semantic intent is the paired unit. The three language variants must never be treated as independent observations in language-comparison hypothesis tests.

## Outcomes

Primary automated outcome:

- `decision_correct`: `ANSWER` for a frozen answerable label or `ABSTAIN` for a frozen unanswerable label.

Secondary automated outcomes:

- retrieval `Hit@1`, `Hit@3`, and `Hit@5` among answerable intents;
- `false_abstention` among answerable intents;
- `false_answer` among unanswerable intents.

All outcomes are binary. Human-dependent semantic outcomes remain `NOT_EVALUATED`.

## Descriptive Estimates

For each language condition, report the numerator, denominator, proportion, and two-sided 95% Wilson score confidence interval. Pooled totals may be shown descriptively but are not used as independent-observation language tests.

## Omnibus Paired Tests

For each outcome, compare EN, MY, and MIX using Cochran's Q test. Report the Q statistic, two degrees of freedom, p-value, paired-intent count, and an effect-size summary using the range between the highest and lowest observed language proportions.

## Pairwise Tests

Perform two-sided exact McNemar tests for:

- EN versus MY;
- EN versus MIX;
- MY versus MIX.

For each comparison report concordant and discordant cell counts, the exact unadjusted p-value, Holm-adjusted p-value within that outcome's three pairwise tests, paired risk difference, and matched odds ratio `b/c`. If either discordant cell is zero, report the raw matched odds ratio as undefined or infinite as appropriate and additionally report a continuity-corrected ratio `(b + 0.5)/(c + 0.5)`.

## Multiplicity and Significance

- Family-wise alpha: 0.05.
- Apply Holm correction separately to the three pairwise comparisons for each outcome.
- Statistical significance requires adjusted p-value below 0.05.
- Report effect sizes and confidence intervals regardless of significance.
- Do not use held-out p-values to alter the model, prompt, parser, retrieval, benchmark, or thresholds.

## Interpretation Boundary

Statistical differences characterize frozen retrieval and structured decision behavior only. They do not establish differences in semantic answer correctness, groundedness, hallucination, or citation support. Because some strata contain only 14 paired unanswerable intents, uncertainty and limited power must be stated.

## Reproducibility Requirements

- Verify SHA-256 hashes of the held-out run, generation JSONL, retrieval CSV, automated-analysis waiver, and Step 5 automated-analysis freeze before calculation.
- Fail if the population is not exactly 74 paired intents with one EN, MY, and MIX variant each.
- Fail if answerability differs across variants of the same intent.
- Export machine-readable JSON plus auditable UTF-8 CSV tables.
- Record Python, SciPy, input, implementation, and output hashes.
- Freeze the results after tests and independent integrity checks pass.
