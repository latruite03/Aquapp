from __future__ import annotations

import base64
import json
import logging
import os
import re
from functools import lru_cache
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openai import OpenAI
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parents[2]

SYSTEM_PROMPT = (
    "You are an aquarium observation assistant. Be cautious. "
    "No medical diagnosis for fish. Provide practical suggestions. "
    "If image quality is too low, ask for a better photo."
)

USER_PROMPT = (
    "Return STRICT JSON only with this schema:\n"
    "{\n"
    "  \"observations\": [ ... ],\n"
    "  \"risks_or_concerns\": [ ... ],\n"
    "  \"suggestions\": [ ... ],\n"
    "  \"questions\": [ ... ],\n"
    "  \"confidence\": 0.0-1.0\n"
    "}\n"
    "Do not include any extra text."
)


@dataclass
class AnalysisResult:
    model: str
    json_text: str | None
    raw_text: str
    success: bool
    error_message: str | None = None


@lru_cache
def _ensure_env_loaded() -> Path | None:
    candidates = [BASE_DIR / ".env", BASE_DIR.parent / ".env"]
    for path in candidates:
        if path.is_file():
            load_dotenv(dotenv_path=path, override=False)
            return path
    return None


def _extract_json(text: str) -> dict[str, Any] | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None


def analyze_image(image_path: Path, filename: str, comment: str | None = None) -> AnalysisResult:
    env_path = _ensure_env_loaded()
    if env_path:
        logger.info("Loaded env from %s", env_path)
    else:
        logger.warning("No .env found in %s or %s", BASE_DIR, BASE_DIR.parent)
    api_key = os.getenv("OPENAI_API_KEY")
    logger.info("OPENAI_API_KEY loaded: %s", "yes" if api_key else "no")
    if not api_key:
        message = "Configure OPENAI_API_KEY to enable analysis."
        return AnalysisResult(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            json_text=None,
            raw_text=message,
            success=False,
            error_message=message,
        )

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    try:
        image_bytes = image_path.read_bytes()
        encoded = base64.b64encode(image_bytes).decode("utf-8")
        mime_type = "image/jpeg" if filename.lower().endswith((".jpg", ".jpeg")) else "image/png"
        client = OpenAI(api_key=api_key, timeout=20)
        logger.info("Sending image %s to OpenAI model %s", filename, model)
        content: list[dict[str, Any]] = [{"type": "text", "text": USER_PROMPT}]
        if comment and comment.strip():
            content.append(
                {"type": "text", "text": f"User comment/question: {comment.strip()}"}
            )
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
            }
        )
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": content,
                },
            ],
        )
        raw_text = response.choices[0].message.content or ""
        parsed = _extract_json(raw_text)
        if parsed is None:
            return AnalysisResult(
                model=model,
                json_text=None,
                raw_text=raw_text,
                success=False,
            )
        json_text = json.dumps(parsed, indent=2)
        return AnalysisResult(model=model, json_text=json_text, raw_text=raw_text, success=True)
    except Exception as exc:  # noqa: BLE001
        logger.exception("OpenAI analysis failed")
        return AnalysisResult(
            model=model,
            json_text=None,
            raw_text=str(exc),
            success=False,
            error_message="Analysis failed. Please try again later.",
        )
