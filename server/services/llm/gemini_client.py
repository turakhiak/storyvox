"""
Google Gemini client for the Director and Character Detection roles.
Also serves as Writer fallback.
"""
import json
import re
import google.generativeai as genai
from typing import Optional
from config import settings


class GeminiClient:
    def __init__(self, api_key: Optional[str] = None):
        key = api_key or settings.gemini_api_key
        if not key:
            raise ValueError("GEMINI_API_KEY is required")
        genai.configure(api_key=key)
        self.model = genai.GenerativeModel("gemini-1.5-flash")

    async def generate(self, system: str, user: str, temperature: float = 0.7) -> str:
        """Generate a response from Gemini."""
        try:
            response = self.model.generate_content(
                f"{system}\n\n{user}",
                generation_config=genai.types.GenerationConfig(
                    temperature=temperature,
                    max_output_tokens=8192,
                ),
            )
            return response.text
        except Exception as e:
            raise RuntimeError(f"Gemini API error: {e}")

    async def generate_json(self, system: str, user: str, temperature: float = 0.7) -> dict | list:
        """Generate and parse JSON response."""
        raw = await self.generate(system, user, temperature)
        return parse_llm_json(raw)


def parse_llm_json(raw: str) -> dict | list:
    """Extract JSON from LLM response, handling markdown fences and preamble."""
    cleaned = raw.strip()

    # Remove markdown fences
    if "```json" in cleaned:
        cleaned = cleaned.split("```json", 1)[1]
        cleaned = cleaned.rsplit("```", 1)[0]
    elif "```" in cleaned:
        cleaned = cleaned.split("```", 1)[1]
        cleaned = cleaned.rsplit("```", 1)[0]

    cleaned = cleaned.strip()

    # Try direct parse
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Try to find JSON object or array in the text
    for pattern in [
        r'(\{[\s\S]*\})',  # Find JSON object
        r'(\[[\s\S]*\])',  # Find JSON array
    ]:
        match = re.search(pattern, cleaned)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                continue

    # Last resort: try fixing common issues
    cleaned = cleaned.replace("'", '"')
    cleaned = re.sub(r',\s*([}\]])', r'\1', cleaned)  # Remove trailing commas

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse LLM JSON response: {e}\nRaw: {raw[:500]}")
