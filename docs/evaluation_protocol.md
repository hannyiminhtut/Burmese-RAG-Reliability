# Evaluation Protocol

## 1. Study Objective

This evaluation measures retrieval performance, answer correctness,
hallucination, abstention, and language consistency in a
retrieval-augmented generation system for university academic regulations.

## 2. Evaluation Dataset

- Corpus ID: UIT-AC
- Corpus Version: UIT-AC-v1.0
- Source ID: UIT-SRC-025
- Domain: University Academic Regulations
- Language conditions:
  - EN: English question and English answer
  - MY: Burmese question and Burmese answer
  - MIX: Burmese-English code-mixed question and answer
- Total benchmark rows: 237
- Answerable rows: 189
- Unanswerable rows: 48
- Semantic intents: 79
- Variants per intent: 3

## 3. Experimental Unit

Each benchmark row represents one experimental query.

Each query must be executed independently using the same:

- Corpus version
- Chunking configuration
- Embedding model
- Retriever configuration
- Top-k value
- Generator model
- Generation prompt
- Temperature
- Maximum output length
- Abstention threshold

## 4. Retrieval Metrics

### 4.1 Hit Rate at k

Hit@k equals 1 when at least one relevant evidence chunk appears within
the top-k retrieved chunks. Otherwise, it equals 0.

Hit@k = Queries with relevant evidence in top-k / Total answerable queries

Report:

- Hit@1
- Hit@3
- Hit@5

### 4.2 Recall at k

Recall@k measures how much of the relevant evidence is retrieved within
the top-k results.

Recall@k = Retrieved relevant chunks in top-k / Total relevant chunks

Report:

- Recall@1
- Recall@3
- Recall@5

### 4.3 Mean Reciprocal Rank

MRR measures how highly the first relevant evidence chunk is ranked.

MRR = (1/N) × Σ(1/rank of first relevant chunk)

Calculate MRR using answerable questions only.

## 5. Answer Correctness Metrics

### 5.1 Exact Numeric Accuracy

Use this metric for answers containing:

- Marks
- Percentages
- Credit units
- Grade points
- GPA or CGPA thresholds
- Semester counts
- Time limits

A response receives:

- 1: All required numeric values are correct
- 0: At least one required numeric value is incorrect or missing

Exact Numeric Accuracy =
Correct numeric answers / Numeric answer questions

### 5.2 Semantic Correctness

Semantic correctness measures whether the generated answer has the same
meaning as the gold answer.

Scoring rubric:

- 2: Correct and complete
- 1: Partially correct or incomplete
- 0: Incorrect, contradictory, or irrelevant

Report the mean semantic-correctness score for each language condition.

## 6. Groundedness and Hallucination

### 6.1 Supported Claim

A claim is supported when it can be directly verified from the retrieved
UIT academic-regulation evidence.

### 6.2 Hallucinated Claim

A claim is hallucinated when it:

- Is not supported by the retrieved evidence
- Contradicts the evidence
- Invents a rule, number, date, fee, person, or procedure
- Presents unavailable information as fact

### 6.3 Hallucination Rate

Response-level Hallucination Rate =
Responses containing at least one unsupported claim / Total responses

Report hallucination rates separately for:

- Answerable questions
- Unanswerable questions
- EN questions
- MY questions
- MIX questions

## 7. Abstention Metrics

A correct abstention states that the provided academic regulations do not
contain sufficient information to answer the question.

### 7.1 Abstention Decision

Record:

- 1: The system abstained
- 0: The system attempted to answer

### 7.2 Abstention Precision

Abstention Precision =
Correct abstentions / All abstentions

### 7.3 Abstention Recall

Abstention Recall =
Correct abstentions / Total unanswerable questions

### 7.4 Abstention F1

Abstention F1 =
2 × Precision × Recall / (Precision + Recall)

### 7.5 Incorrect Abstention Rate

Incorrect Abstention Rate =
Answerable questions incorrectly refused / Total answerable questions

## 8. Language-Consistency Metric

A response is language-consistent when it follows the required output
language.

Rules:

- EN: Answer should be in English.
- MY: Answer should be in Burmese.
- MIX: Answer should contain meaningful Burmese and English content.

Language-Consistency Rate =
Language-consistent responses / Total responses

Official symbols and values such as A+, GPA, CGPA, LMS, 75%, and 4.0
should not automatically be treated as language violations.

## 9. Citation and Evidence Accuracy

Citation Accuracy =
Responses citing the correct source page or section / Responses containing citations

A citation is correct when:

- Source ID is UIT-SRC-025
- The cited page contains the supporting information
- The cited section is relevant to the answer

## 10. Evaluation Labels

Use the following labels for each generated response:

- retrieval_hit
- first_relevant_rank
- numeric_correct
- semantic_correctness
- hallucination_present
- abstained
- abstention_correct
- language_consistent
- citation_correct
- reviewer_notes

## 11. Results File

Store experimental results in:

data/evaluation/evaluation_results.csv

Recommended columns:

run_id,variant_id,language_condition,answerability,question,gold_answer,
generated_answer,retrieved_chunk_ids,retrieved_pages,retrieval_hit_at_1,
retrieval_hit_at_3,retrieval_hit_at_5,first_relevant_rank,numeric_correct,
semantic_correctness,hallucination_present,abstained,abstention_correct,
language_consistent,citation_correct,latency_ms,reviewer,reviewer_notes

## 12. Reporting Strategy

Report results:

1. Overall
2. By language condition: EN, MY, and MIX
3. By answerability: answerable and unanswerable
4. By language condition and answerability
5. By question type:
   - Definition
   - Numeric
   - Rule or procedure
   - Grade classification
   - Unanswerable