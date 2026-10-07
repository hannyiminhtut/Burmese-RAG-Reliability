# Local Ollama Pilot Generation

This command processes only the frozen 15-question development/pilot split. It uses the existing v1.1 Top-5 retrieval results and does not select or execute held-out questions.

## Instrument Version

The active generation contract is `uit-context-only-json-v3` with parser `uit-citation-object-parser-v3`. It uses citation objects shaped as `{"chunk_id":"<id>","page":<integer>}` and sends an explicit JSON schema to Ollama.

The change was required because run `uit-ollama-pilot-v1.1-20260818-01` produced 12 parsed ANSWER attempts with non-integer citation pages, while v1 instrumentation discarded the raw model responses and timings on validation failure. Run 01 is therefore a failed pilot/instrumentation run and must not be used as evaluation data.

The parser accepts JSON integer pages directly. A digit-only string such as `"8"` is normalized explicitly and recorded with `citation_type_normalized`, `original_page_value`, `normalized_page_value`, and `citation_normalizations`. Other strings, ranges, floats, booleans, and null are rejected. Raw response bodies, parsed-but-invalid output, and available Ollama timings are retained on every post-API failure.

Run `uit-ollama-pilot-v1.1-20260818-03` is a development pilot with three contract failures. Its Q008-MIX response copied the schematic page `8` from the v2 output example while citing a chunk whose actual page was `11`. Two MIX abstentions appended explanations to the exact deterministic response. V3 removes that misleading numeric example from the contract area, renders each Top-5 chunk as a labeled evidence block, declares the chunk/page pair inseparable, and gives explicit ANSWER and exact ABSTAIN examples. It also persists the aliases `raw_response` and `parsed_response`, original citations, separate abstention-decision and wording-compliance fields, and the precise validation stage and error.

## CPU-Safe Resource Profile

The active resource profile is `uit-cpu-safe-v1`. It does not change prompt or parser semantics. Run `uit-ollama-pilot-v1.1-20260818-04` is recorded as a development pilot with 13 valid generations and two infrastructure failures (`Q008-MY` and `Q057-MY`): HTTP 500 runner termination and `std::bad_alloc`/GGML assertion failure.

The profile uses `num_ctx=4096`, `num_predict=512`, temperature 0, top-p 0.9, top-k 40, seed 42, sequential requests, `OLLAMA_NUM_PARALLEL=1`, and `OLLAMA_MAX_LOADED_MODELS=1`. It permits at most two attempts, with one five-second cooldown, only for classified transient infrastructure failures. Validation failures are never retried, and every attempt is retained.

Run 04 returned exact Ollama token counts for 13 prompts: minimum 752, maximum 1469, and mean 1079.54. The two crash-before-response requests had no tokenizer count. Pre-request counts for all 15 use the documented calibrated heuristic `ceil((UTF-8 bytes / 4) × 1.10)` and are replaced by `prompt_eval_count` after a valid response. The all-prompt estimate is checked against the context budget with a 1024-token safety margin.

## Activate the Environment

```powershell
Set-Location "D:\Projects\Burmese-RAG-Reliability"
.\.venv\Scripts\Activate.ps1
```

## Check Ollama and the Model

```powershell
$ollamaVersion = Invoke-RestMethod -Method Get -Uri "http://localhost:11434/api/version" -TimeoutSec 10
$ollamaVersion | ConvertTo-Json

$ollamaModels = (Invoke-RestMethod -Method Get -Uri "http://localhost:11434/api/tags" -TimeoutSec 10).models.name
$ollamaModels
if ($ollamaModels -notcontains "gemma3:4b-it-q4_K_M") { throw "Required model is unavailable: gemma3:4b-it-q4_K_M" }
```

## Confirm the Frozen Selection Without Generation

```powershell
python -m src.generate_pilot --dry-run
```

The confirmation must include:

```text
selected questions = 15
held-out questions = 0
```

## Run the Live Pilot

Choose a new, stable run ID. An existing run directory is never overwritten.

```powershell
$runId = "uit-ollama-pilot-v1.1-20260818-05"
python -m src.generate_pilot --run-id $runId
```

## Resume an Interrupted Pilot

Use the exact same run ID and add `--resume`. Completed question variants are skipped after the saved manifest and input hashes are validated.

```powershell
python -m src.generate_pilot --run-id $runId --resume
```

## Locate Outputs

```powershell
$runDir = Join-Path "results\ollama_pilot" $runId
Get-Item -LiteralPath (Join-Path $runDir "$runId.jsonl")
Get-Item -LiteralPath (Join-Path $runDir "${runId}_summary.csv")
Get-Item -LiteralPath (Join-Path $runDir "${runId}_manifest.json")
```
