"""Explanation pipeline: Select -> Fill -> Adapt -> Validate -> Log.

Guarantees:
- Numbers come only from structured slots.
- LLM only rephrases/translates approved templates.
- Strict validator catches number drift, missing disclaimers, or banned phrases.
- Instant fallback to pre-approved template if validation fails or LLM is unavailable.
"""

import hashlib
import json
import os
import uuid
from typing import Dict, Any, Optional
import httpx
from explain.templates.catalog import TEMPLATES, CLINICAL_SIGNOFF_TAG
from explain.validator import validator, ExplanationValidator
from backend.database import Database, db


class LLMAdapter:
    """Base interface for LLM adapters."""
    def adapt(self, filled_text: str, language: str, reading_level: str) -> str:
        raise NotImplementedError


class TemplateOnlyAdapter(LLMAdapter):
    """Deterministic, local-only adapter. Returns approved clinician text directly."""
    def adapt(self, filled_text: str, language: str, reading_level: str) -> str:
        return filled_text


class OllamaAdapter(LLMAdapter):
    """Calls local Ollama endpoint if configured."""
    def __init__(self, base_url: Optional[str] = None, model: str = "qwen2.5:7b"):
        self.base_url = base_url or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        self.model = os.environ.get("OLLAMA_MODEL", model)

    def adapt(self, filled_text: str, language: str, reading_level: str) -> str:
        prompt = (
            f"You are a medical copy editor. Rephrase the following clinical screening text for a patient at a {reading_level} "
            f"reading level in {language}. You MUST preserve all numbers, percentages, and fractions exactly. "
            f"You MUST keep the exact phrases 'This is a screening result, not a diagnosis' and '[{CLINICAL_SIGNOFF_TAG}]'. "
            f"Never advise for or against marriage or pregnancy.\n\nSource text:\n{filled_text}"
        )
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.post(
                    f"{self.base_url}/api/generate",
                    json={"model": self.model, "prompt": prompt, "stream": False},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("response", filled_text).strip()
        except Exception:
            pass
        return filled_text


class GeminiAdapter(LLMAdapter):
    """Calls Google Gemini free tier if GEMINI_API_KEY is present."""
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")

    def adapt(self, filled_text: str, language: str, reading_level: str) -> str:
        if not self.api_key:
            return filled_text
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.api_key}"
            prompt = (
                f"You are an empathetic medical editor. Rephrase this clinical screening text at a {reading_level} reading level in {language}. "
                f"Preserve all numbers and disclaimers exactly.\nText:\n{filled_text}"
            )
            with httpx.Client(timeout=5.0) as client:
                res = client.post(url, json={"contents": [{"parts": [{"text": prompt}]}]})
                if res.status_code == 200:
                    data = res.json()
                    return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception:
            pass
        return filled_text


def get_adapter(mode: Optional[str] = None) -> LLMAdapter:
    selected = mode or os.environ.get("LLM_MODE", "template_only").lower()
    if selected == "ollama":
        return OllamaAdapter()
    elif selected == "gemini":
        return GeminiAdapter()
    return TemplateOnlyAdapter()


class ExplanationPipeline:
    """End-to-end explanation generation and validation pipeline."""

    def __init__(self, database: Optional[Database] = None, val: Optional[ExplanationValidator] = None):
        self.db = database or db
        self.validator = val or validator

    def select(self, template_key: str, language: str = "ar", reading_level: str = "standard") -> str:
        """Step 1: Select approved template."""
        if template_key not in TEMPLATES:
            raise KeyError(f"Template key '{template_key}' not found in approved catalog.")
        lang_dict = TEMPLATES[template_key].get(language, TEMPLATES[template_key]["en"])
        return lang_dict.get(reading_level, lang_dict["standard"])

    def fill(self, raw_template: str, slots: Dict[str, Any]) -> str:
        """Step 2: Fill template slots strictly from structured data."""
        # Clean formatting
        safe_slots = {k: str(v) for k, v in slots.items()}
        try:
            return raw_template.format(**safe_slots)
        except KeyError:
            # Fallback for missing optional slots
            return raw_template

    def generate_explanation(
        self,
        template_key: str,
        slots: Dict[str, Any],
        person_id: str,
        language: str = "ar",
        reading_level: str = "standard",
        llm_mode: Optional[str] = None,
        injected_llm_output: Optional[str] = None,  # For testing adversarial/bad LLM responses
    ) -> Dict[str, Any]:
        """Full pipeline: Select -> Fill -> Adapt -> Validate -> Log."""
        # 1. Select
        raw_tmpl = self.select(template_key, language, reading_level)

        # 2. Fill
        filled_source = self.fill(raw_tmpl, slots)

        # 3. Adapt
        if injected_llm_output is not None:
            adapted_text = injected_llm_output
        else:
            adapter = get_adapter(llm_mode)
            adapted_text = adapter.adapt(filled_source, language, reading_level)

        # 4. Validate
        is_valid, errors, meta = self.validator.validate(
            candidate_text=adapted_text,
            source_template=filled_source,
            language=language,
            reading_level=reading_level,
        )

        fallback_used = False
        if is_valid:
            final_text = adapted_text
        else:
            # Safety Fallback: revert to approved clinician-filled template!
            final_text = filled_source
            fallback_used = True

        # 5. Log in database
        final_hash = hashlib.sha256(final_text.encode("utf-8")).hexdigest()
        log_id = f"log_{uuid.uuid4().hex[:16]}"
        conn = self.db.get_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO explanation_log (id, person_id, template_ids, final_text_hash, raw_content, validator_result)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            log_id,
            person_id,
            json.dumps([template_key]),
            final_hash,
            final_text,
            json.dumps({"is_valid": is_valid, "errors": errors, "fallback_used": fallback_used, "meta": meta}),
        ))
        conn.commit()
        conn.close()

        return {
            "template_id": template_key,
            "final_text": final_text,
            "language": language,
            "reading_level": reading_level,
            "is_valid": is_valid,
            "fallback_used": fallback_used,
            "validation_errors": errors,
            "text_hash": final_hash,
        }


pipeline = ExplanationPipeline()
