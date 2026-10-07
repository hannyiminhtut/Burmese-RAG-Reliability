"""Offline verification for the immutable held-out experiment freeze."""

from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path
from typing import Any, Dict

from src.generate_pilot import (
    GENERATION_SETTINGS,
    PARSER_VERSION,
    PROMPT_VERSION,
    RESOURCE_PROFILE_VERSION,
    build_prompt,
    parse_generation,
)
from src.ollama_client import canonical_sha256_digest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FREEZE = (
    PROJECT_ROOT / "freezes" / "uit-rag-freeze-v1.1-20260819" / "experiment_freeze.json"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def implementation_sha256(function: Any) -> str:
    return hashlib.sha256(inspect.getsource(function).encode("utf-8")).hexdigest()


def load_freeze(path: Path = DEFAULT_FREEZE) -> Dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("Freeze manifest must be a JSON object")
    return document


def verify_freeze(
    path: Path = DEFAULT_FREEZE, root: Path = None
) -> Dict[str, Any]:
    manifest = load_freeze(path)
    root = root.resolve() if root is not None else path.resolve().parents[2]
    errors = []
    for name, artifact in manifest["artifacts"].items():
        artifact_path = root / artifact["path"]
        if not artifact_path.is_file():
            errors.append(f"{name}: missing {artifact['path']}")
            continue
        observed = sha256_file(artifact_path)
        if observed != artifact["sha256"]:
            errors.append(f"{name}: SHA-256 mismatch")
    runtime = manifest["generation"]
    try:
        frozen_model_digest = canonical_sha256_digest(
            runtime["ollama_model_manifest_digest"]
        )
        if frozen_model_digest != runtime["ollama_model_manifest_digest_canonical"]:
            errors.append("ollama_model_manifest_digest_canonical: frozen value differs")
    except (KeyError, ValueError) as exc:
        errors.append(f"ollama_model_manifest_digest: {exc}")
    comparisons = {
        "prompt_version": (PROMPT_VERSION, runtime["prompt_version"]),
        "parser_version": (PARSER_VERSION, runtime["parser_version"]),
        "resource_profile_version": (
            RESOURCE_PROFILE_VERSION, runtime["resource_profile_version"]
        ),
        "settings": (GENERATION_SETTINGS, runtime["settings"]),
        "prompt_implementation_sha256": (
            implementation_sha256(build_prompt), runtime["prompt_implementation_sha256"]
        ),
        "parser_implementation_sha256": (
            implementation_sha256(parse_generation), runtime["parser_implementation_sha256"]
        ),
    }
    for name, (observed, expected) in comparisons.items():
        if observed != expected:
            errors.append(f"{name}: frozen value differs")
    if errors:
        raise ValueError("Frozen configuration verification failed: " + "; ".join(errors))
    return manifest
