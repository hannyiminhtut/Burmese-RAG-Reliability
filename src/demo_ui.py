"""Local, testing-only web UI for interactive UIT RAG questions.

This module is deliberately separate from the frozen evaluation CLIs. It does
not read benchmark questions, write experimental results, or calculate metrics.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.generate_pilot import (
    GENERATION_SETTINGS,
    OUTPUT_SCHEMA,
    build_prompt,
    parse_generation,
    validate_citations,
)
from src.ollama_client import OllamaClient


LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "experiment_config_v1.1.yaml"
MAX_QUESTION_CHARACTERS = 2000
# The interactive UI is outside the frozen experiment.  Loading the retriever
# and Gemma 3 together can leave too little contiguous CPU memory for Ollama's
# default prompt-processing batch.  Keep the evaluated settings untouched and
# use a smaller batch/context only for this non-persistent demonstration.
DEMO_GENERATION_SETTINGS = {
    **GENERATION_SETTINGS,
    "num_ctx": 3072,
    "num_predict": 384,
    "num_batch": 64,
}
DEMO_LANGUAGE_INSTRUCTIONS = (
    "For ANSWER text, use fluent, grammatically correct Unicode Burmese when "
    "the requested language is MY or MIX. Copy established Burmese academic "
    "terms from the supplied evidence instead of inventing Burmese spellings "
    "or phonetic transliterations. English terms such as Academic Year and "
    "Semester may be retained in parentheses. State the answer directly; do "
    "not mention EVIDENCE_1, EVIDENCE_2, or other evidence-block labels in the "
    "answer because citations are returned separately.\n"
)


class IsolatedDemoRetriever:
    """Run E5 retrieval in an expendable process to release RAM before generation."""

    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path

    def retrieve(self, question: str, top_k: int) -> List[Dict[str, Any]]:
        payload = json.dumps(
            {"question": question, "top_k": top_k}, ensure_ascii=False
        )
        worker_environment = os.environ.copy()
        worker_environment["HF_HUB_OFFLINE"] = "1"
        worker_environment["TRANSFORMERS_OFFLINE"] = "1"
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "src.demo_retrieval_worker",
                "--config",
                str(self.config_path),
            ],
            input=payload,
            text=True,
            encoding="utf-8",
            capture_output=True,
            env=worker_environment,
            timeout=300,
            check=False,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(f"Isolated retrieval failed: {detail}")
        try:
            document = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Isolated retrieval returned malformed JSON") from exc
        if not isinstance(document, dict) or not isinstance(document.get("hits"), list):
            raise RuntimeError("Isolated retrieval response is missing hits")
        return document["hits"]


HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>UIT Academic Regulations — RAG Demo</title>
  <style>
    :root{font-family:Inter,"Noto Sans Myanmar","Myanmar Text",system-ui,sans-serif;color:#172033;background:#eef3f9}
    *{box-sizing:border-box} body{margin:0} main{max-width:960px;margin:auto;padding:32px 18px 60px}
    header{background:linear-gradient(135deg,#123c69,#176b87);color:white;padding:28px;border-radius:18px;box-shadow:0 12px 30px #173f6730}
    h1{font-size:clamp(1.5rem,4vw,2.25rem);margin:0 0 8px} header p{margin:0;opacity:.88}
    .notice{margin:18px 0;padding:12px 16px;background:#fff5cf;border-left:5px solid #e0a400;border-radius:8px}
    .card{background:white;border-radius:16px;padding:22px;margin-top:18px;box-shadow:0 6px 22px #173f6715}
    label{font-weight:700;display:block;margin-bottom:8px} textarea{width:100%;min-height:120px;resize:vertical;border:1px solid #b8c5d6;border-radius:10px;padding:14px;font:inherit;line-height:1.6}
    .controls{display:flex;gap:12px;align-items:end;margin-top:12px;flex-wrap:wrap} select,button{font:inherit;border-radius:9px;padding:10px 14px}
    select{border:1px solid #b8c5d6;background:white} button{border:0;background:#176b87;color:white;font-weight:700;cursor:pointer} button:disabled{opacity:.55;cursor:wait}
    .hidden{display:none}.meta{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px}.pill{background:#e7f3f6;color:#11546a;border-radius:999px;padding:5px 10px;font-size:.9rem}
    #answer{white-space:pre-wrap;line-height:1.7}.error{color:#9c1c1c;background:#fff0f0;padding:12px;border-radius:8px}
    details{border-top:1px solid #dce4ed;padding:12px 0} summary{cursor:pointer;font-weight:700}.chunk{white-space:pre-wrap;line-height:1.55;color:#344156;margin-top:9px}.score{font-variant-numeric:tabular-nums;color:#53657a}
    footer{color:#65748a;text-align:center;margin-top:24px;font-size:.88rem}
  </style>
</head>
<body><main>
  <header><h1>UIT Academic Regulations RAG Demo</h1><p>မြန်မာ၊ English နှင့် code-mixed မေးခွန်းများကို စမ်းသပ်နိုင်ပါသည်။</p></header>
  <div class="notice"><strong>Testing demo only.</strong> This is not an official UIT advisory service and is outside the frozen research evaluation. Verify consequential information against the official regulation.</div>
  <section class="card">
    <label for="question">Ask a question / မေးခွန်းမေးရန်</label>
    <textarea id="question" maxlength="2000" placeholder="ဥပမာ — ဘွဲ့ရဖို့ credit ဘယ်လောက်လိုပါသလဲ။"></textarea>
    <div class="controls"><div><label for="language">Answer language</label><select id="language"><option value="AUTO">Auto detect</option><option value="MY">မြန်မာ</option><option value="EN">English</option><option value="MIX">မြန်မာ-English Mix</option></select></div><button id="ask">Ask / မေးမည်</button></div>
  </section>
  <section id="result" class="card hidden"><div id="error"></div><div id="content"><div class="meta"><span id="decision" class="pill"></span><span id="runtime" class="pill"></span></div><h2>Answer</h2><div id="answer"></div><h3>Citations</h3><div id="citations"></div><h3>Retrieved Top-5 Evidence</h3><div id="evidence"></div></div></section>
  <footer>Local CPU-only demo · No benchmark selection · No evaluation results are saved</footer>
</main><script>
const q=document.querySelector('#question'), ask=document.querySelector('#ask'), result=document.querySelector('#result');
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
ask.onclick=async()=>{const question=q.value.trim();if(!question){q.focus();return}ask.disabled=true;ask.textContent='Working…';result.classList.remove('hidden');document.querySelector('#error').innerHTML='';document.querySelector('#content').classList.add('hidden');
try{const r=await fetch('/api/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question,language:document.querySelector('#language').value})});const d=await r.json();if(!r.ok)throw new Error(d.error||'Request failed');
document.querySelector('#decision').textContent=d.decision;document.querySelector('#runtime').textContent=d.runtime_seconds.toFixed(1)+' s';document.querySelector('#answer').textContent=d.answer;
document.querySelector('#citations').innerHTML=d.citations.length?d.citations.map(c=>`<span class="pill">${esc(c.chunk_id)} · page ${esc(c.page)}</span>`).join(' '):'<em>No citations (abstention)</em>';
document.querySelector('#evidence').innerHTML=d.evidence.map(e=>`<details><summary>#${e.rank} ${esc(e.chunk_id)} · page ${esc(e.pages.join(', '))} <span class="score">score ${e.similarity_score.toFixed(4)}</span></summary><div class="chunk">${esc(e.text)}</div></details>`).join('');document.querySelector('#content').classList.remove('hidden');
}catch(e){document.querySelector('#error').innerHTML=`<div class="error">${esc(e.message)}</div>`}finally{ask.disabled=false;ask.textContent='Ask / မေးမည်'}};
q.addEventListener('keydown',e=>{if(e.ctrlKey&&e.key==='Enter')ask.click()});
</script></body></html>"""


def detect_language(question: str) -> str:
    """Choose the demo response language without changing the question text."""
    has_myanmar = bool(re.search(r"[\u1000-\u109f\uaa60-\uaa7f]", question))
    has_english = bool(re.search(r"[A-Za-z]", question))
    if has_myanmar and has_english:
        return "MIX"
    return "MY" if has_myanmar else "EN"


class DemoService:
    """Retrieve Top-5 evidence and generate one non-persistent demo answer."""

    def __init__(
        self,
        config_path: Path = DEFAULT_CONFIG,
        retriever: Optional[Any] = None,
        client: Optional[Any] = None,
    ) -> None:
        self.retriever = retriever or IsolatedDemoRetriever(config_path=config_path)
        self.client = client or OllamaClient()
        self.client.require_model()
        metadata = getattr(self.retriever, "metadata", [])
        self._metadata = {row["chunk_id"]: row for row in metadata}

    def answer(self, question: str, language: str = "AUTO") -> Dict[str, Any]:
        import time

        question = question.strip()
        if not question:
            raise ValueError("Question must not be empty")
        if len(question) > MAX_QUESTION_CHARACTERS:
            raise ValueError(f"Question exceeds {MAX_QUESTION_CHARACTERS} characters")
        if language == "AUTO":
            language = detect_language(question)
        if language not in {"EN", "MY", "MIX"}:
            raise ValueError("Language must be AUTO, EN, MY, or MIX")

        started = time.perf_counter()
        retrieved = self.retriever.retrieve(question, top_k=5)
        chunks: List[Dict[str, Any]] = []
        for hit in retrieved:
            if isinstance(hit.get("text"), str):
                chunks.append(hit)
            else:
                source = self._metadata[hit["chunk_id"]]
                chunks.append({**hit, "text": source["text"]})
        item = {
            "benchmark": {
                "question": question,
                "language_condition": language,
            },
            "chunks": chunks,
        }
        prompt = build_prompt(item)
        prompt = prompt.replace(
            "Return one JSON object only, with no Markdown or additional text.\n",
            DEMO_LANGUAGE_INSTRUCTIONS
            + "Return one JSON object only, with no Markdown or additional text.\n",
            1,
        )
        response = self.client.generate(prompt, DEMO_GENERATION_SETTINGS, OUTPUT_SCHEMA)
        parsed = parse_generation(response["response"])
        validate_citations(parsed, chunks)
        return {
            "question": question,
            "language": language,
            "decision": parsed["decision"],
            "answer": parsed["answer"],
            "citations": parsed["citations"],
            "evidence": chunks,
            "runtime_seconds": time.perf_counter() - started,
            "testing_only": True,
        }


def make_handler(service: DemoService) -> type:
    class DemoHandler(BaseHTTPRequestHandler):
        def _json(self, status: int, document: Dict[str, Any]) -> None:
            body = json.dumps(document, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if self.path != "/":
                self.send_error(404)
                return
            body = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/api/ask":
                self._json(404, {"error": "Not found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 16_384:
                    raise ValueError("Invalid request size")
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                if not isinstance(payload, dict) or not isinstance(payload.get("question"), str):
                    raise ValueError("Request must contain a string question")
                result = service.answer(payload["question"], payload.get("language", "AUTO"))
                self._json(200, result)
            except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
                self._json(400, {"error": str(exc)})
            except Exception as exc:  # local demo boundary; do not expose traceback
                LOGGER.exception("Demo request failed")
                self._json(500, {"error": f"RAG request failed: {exc}"})

        def log_message(self, fmt: str, *args: Any) -> None:
            LOGGER.info("%s - %s", self.address_string(), fmt % args)

    return DemoHandler


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the testing-only UIT RAG web UI")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    service = DemoService(config_path=args.config)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(service))
    LOGGER.info("Testing-only UIT RAG UI: http://%s:%d", args.host, args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        LOGGER.info("Stopping demo UI")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
