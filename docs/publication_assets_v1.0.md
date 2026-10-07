# Publication Assets v1.0

This package contains seven paper tables and five vector figures generated only from frozen experimental, held-out, paired-statistical, and structural-error results. All percentages in the figures use proportions stored in the corresponding frozen JSON packages.

## Tables

1. Dataset and split summary
2. Frozen experimental configuration
3. Retrieval performance overall and by language
4. Structured decision performance by language
5. Paired omnibus statistical tests
6. Contract and reliability measures
7. Structural error indicators

CSV values are intentionally unrounded so paper-formatting software can apply consistent precision. Rates should normally be displayed as percentages with two decimal places; MRR and p-values should normally use four significant decimal places, except very small p-values.

## Figures

1. Frozen experimental and evaluation pipeline
2. Retrieval Hit@1, Hit@3, and Hit@5 by language
3. Structured decision accuracy with 95% Wilson confidence intervals
4. False-abstention rate with 95% Wilson confidence intervals
5. Overlapping structural error indicators

Figures are SVG vector graphics suitable for conversion or placement in the paper workflow. EN, MY, and MIX use a consistent color mapping. Every statistical figure includes its denominator context in the title or associated table.

## Required Captions and Boundaries

- Figure 2: Retrieval metrics are calculated only for 180 answerable variants, 60 per language.
- Figure 3: Accuracy concerns the structured `ANSWER`/`ABSTAIN` decision, not semantic answer correctness.
- Figure 4: False abstention means an answerable benchmark label paired with structured `ABSTAIN`.
- Figure 5: Categories overlap and must not be summed as a unique-error total.
- Gold-page Hit@5 is page-intersection retrieval scoring, not proof of semantic evidence sufficiency.
- Semantic answer correctness, groundedness, hallucination, and claim-level citation support remain `NOT_EVALUATED`.

Do not edit values manually. Regenerate the package with `python -m src.build_publication_assets` after verifying the frozen source hashes. Do not use held-out figures to tune any experimental component.
