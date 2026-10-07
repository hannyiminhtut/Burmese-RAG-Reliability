# Language-Conditioned Abstention in Burmese-English RAG: Retrieval–Decision Divergence Across Query Languages

[![Paper](https://img.shields.io/badge/Paper-PDF-red.svg)](docs/26042.pdf)
[![Conference](https://img.shields.io/badge/ICAIT-2026-blue.svg)](http://icait.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/)

This repository contains the official evaluation pipeline, benchmark dataset, frozen artifacts, and experimental reproduction code for the research paper:

> **Language-Conditioned Abstention in Burmese-English RAG: Retrieval–Decision Divergence Across Query Languages**  
> *Han Nyi Min Htut, Thet Thet Zin*  
> University of Information Technology (UIT), Yangon, Myanmar  
> Accepted at **ICAIT 2026** (IEEE conference proceedings).

---

## 📌 Abstract

Retrieval-augmented generation (RAG) systems for university regulations must answer supported questions and abstain when evidence is unavailable. This paper reports a controlled structural and decision-level evaluation of a local RAG configuration over a frozen University of Information Technology academic-regulation document, comparing **English (EN)**, **Burmese (MY)**, and **Burmese-English code-mixed (MIX)** queries. 

The benchmark features **79 paired semantic intents and 237 query variants** (222 held-out). Retrieval utilizes `intfloat/multilingual-e5-small` with normalized FAISS inner-product search, feeding the Top-5 chunks into `gemma3:4b-it-q4_K_M`. 

### Key Findings
* **Retrieval Hit@5:** Reached **87.22%** overall with no statistically significant divergence across languages ($p = 0.0990$).
* **Decision Accuracy:** Reached **73.42%** overall. However, Burmese (MY) decision accuracy was significantly lower at **60.81%**, compared with **79.73%** for both EN and MIX ($Q(2) = 10.595, p = 0.0050$).
* **False Abstention Disparity:** The divergence stems from false abstention: **45.00% for MY** versus **20.00% for EN** and **16.67% for MIX** ($p = 0.00031$). In 13 cases, the model falsely abstained on Burmese queries despite retrieving the gold evidence at Rank 1.
* **Output Contract Validity:** **95.50%** of outputs complied with structural JSON contracts and chunk–page citation bindings.

---

## 🏗️ Architecture & Pipeline

```text
┌─────────────────┐       ┌──────────────────────┐       ┌──────────────────────┐
│  Query Variants │  ──►  │    Multilingual E5   │  ──►  │      FAISS IP        │
│  (EN, MY, MIX)  │       │  multilingual-e5-sm  │       │     Top-5 Chunks     │
└─────────────────┘       └──────────────────────┘       └──────────┬───────────┘
                                                                    │
                                                                    ▼
┌─────────────────┐       ┌──────────────────────┐       ┌──────────────────────┐
│ Frozen Analysis │  ◄──  │    Output Parser     │  ◄──  │     Gemma 3:4B       │
│ & Reliability   │       │ Chunk–Page Citations │       │ gemma3:4b-it-q4_K_M  │
└─────────────────┘       └──────────────────────┘       └──────────────────────┘
```

The evaluation explicitly separates three distinct measurement levels:
1. **Retrieval-level:** Page intersection with gold evidence (Hit@$k$, MRR).
2. **Decision-level:** Agreement of the structured `ANSWER` vs. `ABSTAIN` choice against the benchmark label.
3. **Contract-level:** Structural compliance, valid JSON syntax, and chunk–page citation bindings.

---

## 📊 Summary of Results

### 1. Retrieval Performance (Answerable Held-out, $n=60$ per language)

| Language Condition | Hit@1 | Hit@3 | Hit@5 | MRR |
| :--- | :---: | :---: | :---: | :---: |
| **Overall** | 52.78% | 77.22% | 87.22% | 0.6577 |
| **English (EN)** | 51.67% | 75.00% | 86.67% | 0.6444 |
| **Burmese (MY)** | 46.67% | 75.00% | 81.67% | 0.6039 |
| **Code-mixed (MIX)** | 60.00% | 81.67% | 93.33% | 0.7247 |
| *Significance* | \multicolumn{4}{c|}{Not statistically significant (closest Hit@5, $p=0.0990$)} |

### 2. Decision Performance (Not Answer Correctness)

| Language Condition | Decision Accuracy ($n=74$) | False Abstention ($n=60$) | False Answer ($n=14$) |
| :--- | :---: | :---: | :---: |
| **English (EN)** | 59 (79.73%) | 12 (20.00%) | 3 (21.43%) |
| **Burmese (MY)** | 45 (60.81%) | 27 (45.00%) | 2 (14.29%) |
| **Code-mixed (MIX)** | 59 (79.73%) | 10 (16.67%) | 5 (35.71%) |
| *Omnibus / Paired Test* | $Q(2) = 10.595, p = 0.0050$ | $Q(2) = 16.188, p = 0.00031$ | $p = 0.2466$ (underpowered) |

---

## 📂 Repository Structure

```text
├── configs/                  # Configuration files for retrieval and inference profiles
├── data/
│   ├── processed/            # 148 frozen corpus chunks & raw academic credit regulations
│   └── evaluation/           # 237-variant paired benchmark dataset (EN, MY, MIX)
├── docs/                     # Paper sources, protocols, 26042.pdf & editable 26042.docx
│   ├── 26042.pdf             # Compiled 6-page IEEE conference paper
│   ├── 26042.docx            # Editable IEEE-formatted Word document
│   └── paper_draft_v1.1_revised.tex # Full LaTeX source
├── freezes/                  # Immutable cryptographic SHA-256 manifests of datasets & runs
├── models/                   # Pre-indexed FAISS search indices and metadata
├── results/                  # Complete held-out generation JSONL, CSVs, and statistical logs
│   ├── publication_assets_v1.0/ # Publication-grade SVG and PNG figures
│   └── paired_statistical_analysis_v1.0/ # Exact McNemar & Cochran's Q outputs
├── src/                      # Source code for indexing, retrieval, inference & evaluation
├── requirements-lock.txt     # Pinned Python package dependencies
└── README.md
```

---

## 🚀 Quickstart & Reproduction

### 1. Prerequisites
* Python 3.9+
* [Ollama](https://ollama.com/) with `gemma3:4b-it-q4_K_M` pulled:
  ```bash
  ollama pull gemma3:4b-it-q4_K_M
  ```

### 2. Environment Setup
```bash
# Clone the repository
git clone https://github.com/hannyiminhtut/Burmese-RAG-Reliability.git
cd Burmese-RAG-Reliability

# Create and activate virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements-lock.txt
```

### 3. Build Vector Index
```bash
python src/build_index.py
```

### 4. Evaluate Retrieval Performance
```bash
python src/evaluate_retrieval.py
```

### 5. Run Held-out Generation & Decision Evaluation
```bash
python src/generate_heldout.py
python src/analyze_heldout_automated.py
```

### 6. Run Paired Statistical Tests
```bash
python src/analyze_paired_statistics.py
```

---

## 📄 Citation

If you find this benchmark or study useful in your research, please cite:

```bibtex
@inproceedings{htut2026language,
  author    = {Htut, Han Nyi Min and Zin, Thet Thet},
  title     = {Language-Conditioned Abstention in Burmese-English RAG: Retrieval--Decision Divergence Across Query Languages},
  booktitle = {Proceedings of the 2026 International Conference on Advanced Information Technologies (ICAIT)},
  year      = {2026},
  pages     = {1--6},
  address   = {Yangon, Myanmar}
}
```

---

## ⚖️ Ethical & Transparency Notes
* **Boundaries:** This study evaluates decision-level correctness and structural contracts. Semantic correctness and claim-level hallucinations were not evaluated due to lack of independent annotators.
* **Corpus Scope:** The dataset covers the official 24-page *Undergraduate Academic Regulations (4 Years Program)* from the University of Information Technology (UIT). It does not represent authoritative legal advice.
