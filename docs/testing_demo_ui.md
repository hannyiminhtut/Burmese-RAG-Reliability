# Testing-Only RAG Demo UI

## Boundary

This local interface is provided only so a professor can interactively test the existing RAG system. It is outside the frozen research experiment. It does not select benchmark questions, calculate metrics, write generation records, or change any frozen artifact. Its outputs must not be reported as held-out results.

## Behavior

- Accepts an arbitrary English, Burmese, or Burmese-English mixed question.
- Retrieves exactly five chunks from the existing v1.1 FAISS index.
- Uses the existing generation prompt, structured schema, parser, citation validation, and model, with the demo-only memory overrides described below.
- Uses a demo-only low-memory request profile (`num_ctx=3072`, `num_predict=384`, and `num_batch=64`) so the retriever and Ollama model can coexist on CPU-constrained machines. This does not alter the frozen experiment or any reported result.
- Runs E5 query retrieval in a short-lived worker process. The worker exits and releases the embedding-model memory before Ollama starts Gemma 3. A first request can therefore take longer while retrieval loads.
- Adds a demo-only language instruction requiring standard Unicode Burmese terms copied from the evidence and preventing internal `EVIDENCE_n` labels from appearing in the displayed answer.
- Shows the structured decision, answer, validated citations, and supplied Top-5 evidence.
- Does not persist questions or answers.
- Binds to `127.0.0.1` by default, so it is available only on the same computer.

## Windows PowerShell

Start Ollama with the CPU-safe environment settings in the first PowerShell window:

```powershell
$env:OLLAMA_NUM_PARALLEL = "1"
$env:OLLAMA_MAX_LOADED_MODELS = "1"
ollama serve
```

In a second PowerShell window, start the UI from the project root:

```powershell
.\.venv\Scripts\Activate.ps1
python -m src.demo_ui
```

Open `http://127.0.0.1:8000` in a browser. Press `Ctrl+C` in the second terminal to stop the UI.

If Ollama previously reported an out-of-memory startup error, stop both processes, close other memory-heavy applications, and restart `ollama serve` before restarting the UI. The demo-only smaller prompt batch substantially reduces the temporary CPU compute-buffer allocation.

## Interpretation

The interface is not an official UIT advisory service. Answers should be checked against the displayed source evidence and the official academic regulation before any consequential decision.
