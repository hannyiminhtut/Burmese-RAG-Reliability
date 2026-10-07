# Verified Literature Review v1.0

## Purpose

This record documents the sources admitted during Step 10. Bibliographic details were checked against the original paper record or the ACL Anthology. The list supports the manuscript's background and methodological positioning; it does not establish novelty.

## Source-Screening Rules

- Prefer the original paper and its publisher or archival record.
- Admit a source only when its title, authors, year, venue, and persistent URL can be verified.
- Use a source only for claims supported by its stated scope.
- Do not infer Burmese-specific results from multilingual studies that did not evaluate Burmese.
- Do not use citations to imply that the present study measured semantic hallucination.

## Audited Sources

| Ref. | Topic | Verified source | Claim supported in this study |
|---|---|---|---|
| [1] | Foundational RAG | P. Lewis et al., “Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks,” NeurIPS, 2020. https://arxiv.org/abs/2005.11401 | RAG combines parametric generation with retrieved non-parametric evidence. |
| [2] | Multilingual embeddings | L. Wang et al., “Multilingual E5 Text Embeddings: A Technical Report,” arXiv:2402.05672, 2024. https://arxiv.org/abs/2402.05672 | Multilingual E5 is a multilingual embedding family with small, base, and large variants. |
| [3] | RAG evaluation | S. Es et al., “RAGAs: Automated Evaluation of Retrieval Augmented Generation,” EACL System Demonstrations, 2024, pp. 150–158. https://doi.org/10.18653/v1/2024.eacl-demo.16 | Retrieval quality, faithful context use, and generation quality are distinct evaluation dimensions. |
| [4] | Code-mixed retrieval | J. Do, J. Lee, and S.-w. Hwang, “ContrastiveMix: Overcoming Code-Mixing Dilemma in Cross-Lingual Transfer for Information Retrieval,” NAACL-HLT, 2024, pp. 197–204. https://doi.org/10.18653/v1/2024.naacl-short.17 | Code mixing can affect cross-lingual representation alignment and retrieval objectives. |
| [5] | Multilingual RAG | J. Park and H. Lee, “Investigating Language Preference of Multilingual RAG Systems,” Findings of ACL, 2025, pp. 5647–5675. https://doi.org/10.18653/v1/2025.findings-acl.295 | Retriever and generator behavior can vary with query and evidence language; retrieval success need not translate directly into generation success. |
| [6] | LLM abstention | B. Wen et al., “Know Your Limits: A Survey of Abstention in Large Language Models,” TACL, vol. 13, pp. 529–556, 2025. https://doi.org/10.1162/tacl_a_00754 | Abstention is a distinct reliability behavior with methods, benchmarks, and evaluation measures. |
| [7] | Selective abstention | L. Huang et al., “Alleviating Hallucinations from Knowledge Misalignment in Large Language Models via Selective Abstention Learning,” ACL, 2025, pp. 24564–24579. https://doi.org/10.18653/v1/2025.acl-long.1199 | Selective refusal has been studied as a mechanism for responding to insufficient or misaligned knowledge. |
| [8] | RAG hallucination errors | T. A. Chang et al., “Detecting Hallucination and Coverage Errors in Retrieval Augmented Generation for Controversial Topics,” LREC-COLING, 2024, pp. 4729–4743. https://aclanthology.org/2024.lrec-main.423/ | Hallucination and coverage errors require explicit detection or semantic evaluation and are not established by structural validation alone. |

## ICAIT 2026 Requirements Check

The official University of Information Technology conference page and call-for-papers brochure were checked on 20 August 2026:

- Conference: 7th International Conference on Advanced Information Technologies (ICAIT 2026)
- Date and place: 5 November 2026, Yangon, Myanmar
- Relevant track: Artificial Intelligence and Data Science, including Natural Language Processing
- Submission deadline: 30 August 2026
- Acceptance notification: 30 September 2026
- Camera-ready deadline: 15 October 2026
- Format constraint: no more than six pages, two columns
- Submission condition: original and not previously published
- Submission route: `icait@uit.edu.mm`
- Publication wording: accepted papers are published in the conference proceedings and submitted for possible inclusion in IEEE Xplore
- Official page: https://uit.edu.mm/icait-2026/
- Official CFP: https://uit.edu.mm/app/uploads/2026/04/icait2026CFP.pdf

The website's current instructions must be checked again immediately before submission because conference dates and instructions can change.

## Unresolved Literature Boundary

No verified source in this audit is used to claim that the study is the first Burmese RAG benchmark. Burmese-specific prior work and authoritative evidence about Zawgyi conversion effects remain a literature-coverage gap. The manuscript therefore limits its positioning to a focused Burmese university-domain RAG reliability study.
