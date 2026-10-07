# Evaluation Protocol Addendum v1.0

## Status

This prospective addendum was approved after development pilot `uit-ollama-pilot-v1.1-20260818-05` and before held-out generation. It does not modify or retrospectively rescore any development-pilot output. The original `docs/evaluation_protocol.md` remains unchanged.

## Deterministic Abstention and Language Consistency

- The structured `decision` field is the authoritative source for classifying an output as `ANSWER` or `ABSTAIN`.
- Exact reproduction of the configured English deterministic-abstention response is evaluated as a separate contract-compliance metric.
- Language consistency is `NOT_APPLICABLE` when `decision` is `ABSTAIN` and the deterministic response is used.
- Language consistency is evaluated normally for every `ANSWER` output under its EN, MY, or MIX condition.
- Generated response text is never silently translated, replaced, or rescored to satisfy this policy.

## Version

- Addendum version: `evaluation-protocol-addendum-v1.0`
- Scope: frozen v1.1 held-out generation and subsequent evaluation
