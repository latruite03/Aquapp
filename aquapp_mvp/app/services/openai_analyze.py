from __future__ import annotations

import base64
import logging
import os
from functools import lru_cache
from dataclasses import dataclass
from pathlib import Path

from openai import OpenAI
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parents[2]

SYSTEM_PROMPT = (
    "Tu es un assistant d'observation d'aquarium. Sois prudent, "
    "n'invente pas, et ne fais aucun diagnostic médical pour les poissons. "
    "Propose des conseils pratiques et des questions utiles. "
    "Si la qualité de l'image est trop faible, demande une photo meilleure."
)

USER_PROMPT = (
    "Réponds en français avec un texte continu (2 à 4 paragraphes) "
    "dans un ton bienveillant et clair. N'inclus pas de JSON ni de code. "
    "Base-toi sur la photo, le commentaire éventuel, le profil de l'aquarium "
    "et l'historique fourni pour garder le contexte général."
    "Base-toi sur la photo, le commentaire éventuel, et l'historique fourni "
    "pour garder le contexte général de l'aquarium."
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


def analyze_image(
    image_path: Path,
    filename: str,
    comment: str | None = None,
    history: list[str] | None = None,
    profile_summary: str | None = None,
) -> AnalysisResult:
    env_path = _ensure_env_loaded()
    if env_path:
        logger.info("Loaded env from %s", env_path)
    else:
        logger.warning("No .env found in %s or %s", BASE_DIR, BASE_DIR.parent)
    api_key = os.getenv("OPENAI_API_KEY")
    logger.info("OPENAI_API_KEY loaded: %s", "yes" if api_key else "no")
    if not api_key:
        message = "Configurez OPENAI_API_KEY pour activer l'analyse."
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
        content: list[dict[str, object]] = [{"type": "text", "text": USER_PROMPT}]
        if comment and comment.strip():
            content.append(
                {"type": "text", "text": f"Commentaire/question: {comment.strip()}"}
            )
        if profile_summary:
            content.append(
                {
                    "type": "text",
                    "text": "Profil de l'aquarium:\n" + profile_summary,
                }
            )
        if history:
            history_text = "\n\n".join(history)
            content.append(
                {
                    "type": "text",
                    "text": "Historique récent de l'aquarium:\n" + history_text,
                }
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
        return AnalysisResult(model=model, json_text=None, raw_text=raw_text, success=True)
    except Exception as exc:  # noqa: BLE001
        logger.exception("OpenAI analysis failed")
        return AnalysisResult(
            model=model,
            json_text=None,
            raw_text=str(exc),
            success=False,
            error_message="Analyse échouée. Veuillez réessayer plus tard.",
        )
