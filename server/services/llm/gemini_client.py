"""
Base LLM Client interface and implementations for Gemini, Groq, and Ollama.

Error taxonomy used throughout:
  RateLimitError      — per-minute 429, short cooldown (60 s), worth retrying soon
  QuotaExhaustedError — daily/monthly quota gone, long cooldown (1 h), no point retrying
  ProviderError       — other connectivity/server error, medium cooldown (3 min)
  ParseError          — model returned unparseable JSON; NOT a provider issue,
                        never triggers the circuit breaker
"""
import json
import re
import asyncio
import logging
import time
from typing import Optional, Union, Any, Protocol
from google import genai
from google.genai import types as genai_types
from groq import Groq
from config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Typed exceptions — let CompositeLLMClient set appropriate cooldowns
# ---------------------------------------------------------------------------

class RateLimitError(RuntimeError):
    """429 / per-minute rate limit. Retry after ~60 s."""
    pass

class QuotaExhaustedError(RuntimeError):
    """Daily or monthly quota gone. Don't retry for hours."""
    pass

class ProviderError(RuntimeError):
    """Generic provider failure (5xx, network, auth). Medium cooldown."""
    pass

class ParseError(ValueError):
    """Model returned invalid JSON. NOT a provider issue — no circuit breaker."""
    pass


def _classify_gemini_error(err_str: str) -> type:
    """Map a Gemini error string to the right exception class."""
    lower = err_str.lower()
    # Network / connectivity errors — NOT quota, use short cooldown so retries happen soon
    if any(kw in lower for kw in (
        "nameresolutionerror", "failed to resolve", "nodename nor servname",
        "connection refused", "connection reset", "connectionerror",
        "max retries exceeded", "timed out", "timeout", "ssl",
    )):
        return ProviderError
    # Model retired / not found — long cooldown, no point retrying
    if "404" in err_str or "not found" in lower or "is not found" in lower:
        return QuotaExhaustedError
    # Daily/monthly quota exhausted — ResourceExhausted with billing language
    if "resource_exhausted" in lower or ("quota" in lower and "daily" in lower):
        return QuotaExhaustedError
    # Per-minute rate limit
    if "429" in err_str or "rate_limit" in lower or "too many requests" in lower:
        return RateLimitError
    return ProviderError


def _classify_groq_error(err_str: str) -> type:
    lower = err_str.lower()
    # Daily/monthly token budget exhausted — long cooldown, don't retry for hours.
    # Groq TPD errors contain "tokens per day", "tpd", or "need more tokens".
    # Must check BEFORE the generic "429" check because TPD errors are also 429s.
    if any(kw in lower for kw in (
        "tokens per day", "tpd", "org tokens per day", "need more tokens",
        "token per day", "tokens/day",
    )):
        return QuotaExhaustedError
    if "quota" in lower or "billing" in lower:
        return QuotaExhaustedError
    # Per-minute rate limit — short cooldown, worth retrying soon
    if "429" in err_str or "rate_limit" in lower or "too many requests" in lower:
        return RateLimitError
    return ProviderError


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

class LLMClient(Protocol):
    async def generate(
        self,
        system: str,
        user: str,
        temperature: float = 0.7,
        response_schema: Optional[Any] = None,
    ) -> str: ...

    async def generate_json(
        self,
        system: str,
        user: str,
        temperature: float = 0.7,
        response_schema: Optional[Any] = None,
    ) -> Union[dict, list]: ...


# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------

class GeminiClient:
    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        key = api_key or settings.gemini_api_key
        if not key:
            raise ValueError("GEMINI_API_KEY is required")
        self.client = genai.Client(api_key=key)
        self.model_name = model_name or settings.gemini_model

    @property
    def is_local(self) -> bool:
        return False

    async def generate(
        self,
        system: str,
        user: str,
        temperature: float = 0.7,
        response_schema: Optional[Any] = None,
    ) -> str:
        gen_config_kwargs: dict = {
            "temperature": temperature,
            "max_output_tokens": 32768,  # Long chapters need room; 8192 truncates mid-JSON
        }
        if response_schema:
            gen_config_kwargs["response_mime_type"] = "application/json"
            gen_config_kwargs["response_schema"] = response_schema
        if system:
            gen_config_kwargs["system_instruction"] = system

        # Per-minute retries only — quota exhaustion is raised immediately
        max_retries = 3
        for attempt in range(max_retries):
            try:
                config = genai_types.GenerateContentConfig(**gen_config_kwargs)
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: self.client.models.generate_content(
                        model=self.model_name,
                        contents=user,
                        config=config,
                    ),
                )
                logger.debug(f"Gemini response (first 200): {response.text[:200]}")
                return response.text

            except Exception as e:
                err_str = str(e)

                # Schema rejected by Gemini — retry once without schema enforcement
                if ("Schema" in err_str or "default" in err_str) and response_schema:
                    logger.warning(f"Gemini schema rejected, retrying schema-free: {err_str[:120]}")
                    gen_config_kwargs.pop("response_schema", None)
                    gen_config_kwargs.pop("response_mime_type", None)
                    user += "\n\nIMPORTANT: Return the response in valid JSON format."
                    response_schema = None
                    continue

                exc_class = _classify_gemini_error(err_str)

                if exc_class is QuotaExhaustedError:
                    # No point retrying — raise immediately so failover kicks in
                    logger.error(f"Gemini quota exhausted ({self.model_name}): {err_str[:120]}")
                    raise QuotaExhaustedError(f"Gemini quota exhausted: {err_str}")

                if exc_class is RateLimitError:
                    if attempt < max_retries - 1:
                        wait = (2 ** attempt) + 2   # 3 s, 6 s
                        logger.warning(f"Gemini rate limited, retrying in {wait}s (attempt {attempt+1})")
                        await asyncio.sleep(wait)
                        continue
                    raise RateLimitError(f"Gemini rate limited after {max_retries} attempts: {err_str}")

                raise ProviderError(f"Gemini error ({self.model_name}): {err_str}")

    async def generate_json(
        self,
        system: str,
        user: str,
        temperature: float = 0.7,
        response_schema: Optional[Any] = None,
    ) -> Union[dict, list]:
        raw = await self.generate(system, user, temperature, response_schema=response_schema)
        try:
            if response_schema:
                return json.loads(raw)
            return parse_llm_json(raw)
        except (json.JSONDecodeError, ValueError) as e:
            # Try the more forgiving parser before giving up
            try:
                return parse_llm_json(raw)
            except ValueError:
                raise ParseError(f"Gemini returned unparseable JSON: {raw[:300]}") from e


# ---------------------------------------------------------------------------
# Groq
# ---------------------------------------------------------------------------

class GroqClient:
    def __init__(self, api_key: Optional[str] = None, model_name: str = "llama-3.3-70b-versatile"):
        key = api_key or settings.groq_api_key
        if not key:
            raise ValueError("GROQ_API_KEY is required")
        self.client = Groq(api_key=key)
        self.model_name = model_name

    @property
    def is_local(self) -> bool:
        return False

    async def generate(
        self,
        system: str,
        user: str,
        temperature: float = 0.7,
        response_schema: Optional[Any] = None,
    ) -> str:
        if response_schema and "json" not in (system + user).lower():
            user += "\n\nIMPORTANT: Respond in valid JSON format."

        max_retries = 3
        for attempt in range(max_retries):
            try:
                loop = asyncio.get_event_loop()
                completion = await loop.run_in_executor(
                    None,
                    lambda: self.client.chat.completions.create(
                        messages=[
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        model=self.model_name,
                        temperature=temperature,
                        response_format={"type": "json_object"} if response_schema else None,
                    ),
                )
                logger.debug(f"Groq response (first 200): {completion.choices[0].message.content[:200]}")
                return completion.choices[0].message.content

            except Exception as e:
                err_str = str(e)
                exc_class = _classify_groq_error(err_str)

                if exc_class is QuotaExhaustedError:
                    logger.error(f"Groq quota exhausted: {err_str[:120]}")
                    raise QuotaExhaustedError(f"Groq quota exhausted: {err_str}")

                if exc_class is RateLimitError:
                    if attempt < max_retries - 1:
                        wait = (2 ** attempt) + 1   # 2 s, 5 s
                        logger.warning(f"Groq rate limited, retrying in {wait}s (attempt {attempt+1})")
                        await asyncio.sleep(wait)
                        continue
                    raise RateLimitError(f"Groq rate limited after {max_retries} attempts: {err_str}")

                raise ProviderError(f"Groq error: {err_str}")

    async def generate_json(
        self,
        system: str,
        user: str,
        temperature: float = 0.7,
        response_schema: Optional[Any] = None,
    ) -> Union[dict, list]:
        raw = await self.generate(system, user, temperature, response_schema=response_schema)
        try:
            return parse_llm_json(raw)
        except ValueError as e:
            raise ParseError(f"Groq returned unparseable JSON: {raw[:300]}") from e


# ---------------------------------------------------------------------------
# Ollama (local)
# ---------------------------------------------------------------------------

class OllamaClient:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        model_name: str = "llama3.2:3b",
        num_ctx: int = 32768,
    ):
        self.base_url = base_url
        self.model_name = model_name
        self.num_ctx = num_ctx
        try:
            import ollama
            logger.info(f"Ollama AsyncClient → {base_url}")
            self.client = ollama.AsyncClient(host=base_url)
        except ImportError:
            logger.error("ollama library not found — run 'pip install ollama'")
            self.client = None

    @property
    def is_local(self) -> bool:
        return True

    async def generate(
        self,
        system: str,
        user: str,
        temperature: float = 0.7,
        response_schema: Optional[Any] = None,
    ) -> str:
        if not self.client:
            raise ProviderError("Ollama library not installed. Run 'pip install ollama'")
        try:
            logger.info(f"Ollama: model={self.model_name} ctx={self.num_ctx}")
            response = await self.client.chat(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user + "\n\nIMPORTANT: Respond with valid JSON only. Match the exact structure requested above."},
                ],
                options={
                    "temperature": temperature,
                    "num_ctx": self.num_ctx,
                    "num_predict": 4096,
                },
                format="json",
            )
            content = response["message"]["content"]
            logger.debug(f"Ollama response (first 200): {content[:200]}")
            return content
        except Exception as e:
            err_str = str(e)
            if "connection" in err_str.lower() or "connect" in err_str.lower():
                raise ProviderError(f"Ollama not reachable at {self.base_url}. Is it running?")
            if "404" in err_str:
                raise ProviderError(f"Ollama model '{self.model_name}' not found. Run: ollama pull {self.model_name}")
            raise ProviderError(f"Ollama error ({self.model_name}): {err_str}")

    async def generate_json(
        self,
        system: str,
        user: str,
        temperature: float = 0.7,
        response_schema: Optional[Any] = None,
    ) -> Union[dict, list]:
        raw = await self.generate(system, user, temperature, response_schema=response_schema)
        try:
            return parse_llm_json(raw)
        except ValueError as e:
            raise ParseError(f"Ollama returned unparseable JSON: {raw[:300]}") from e


# ---------------------------------------------------------------------------
# CompositeLLMClient — failover with typed circuit breaker
# ---------------------------------------------------------------------------

# Cooldown seconds per error type
_COOLDOWNS = {
    RateLimitError:     60,    # Per-minute limit resets in ~60 s — try again soon
    QuotaExhaustedError: 3600, # Daily quota gone — don't hammer the API for an hour
    ProviderError:      180,   # Generic error — 3 min cooldown
    # ParseError is intentionally absent — never triggers circuit breaker
}

class CompositeLLMClient:
    """
    Tries each provider in order, skipping ones whose circuit breaker is active.

    Circuit breaker cooldown depends on WHY the provider failed:
      - Per-minute rate limit  →  60 s
      - Daily quota exhausted  →  1 h
      - Other provider error   →  3 min
      - JSON parse failure     →  (no circuit breaker — provider is still healthy)
    """

    def __init__(self, clients: list):
        self.clients = [c for c in clients if c is not None]
        self._breakers: dict[int, float] = {}   # client id → expiry timestamp

    @property
    def is_local(self) -> bool:
        active = [c for c in self.clients if not self._is_broken(c)]
        return all(c.is_local for c in active) if active else True

    def _is_broken(self, client) -> bool:
        cid = id(client)
        if cid in self._breakers:
            if time.monotonic() < self._breakers[cid]:
                return True
            del self._breakers[cid]
        return False

    def _trip(self, client, exc: Exception):
        """Trip the circuit breaker with the right cooldown for this error type."""
        cooldown = _COOLDOWNS.get(type(exc), 180)
        self._breakers[id(client)] = time.monotonic() + cooldown
        remaining = cooldown
        unit = "s" if cooldown < 120 else f"{cooldown // 60} min"
        logger.warning(
            f"⚡ Circuit breaker: {type(client).__name__} offline for {unit} "
            f"[{type(exc).__name__}]"
        )

    async def generate(
        self,
        system: str,
        user: str,
        temperature: float = 0.7,
        response_schema: Optional[Any] = None,
    ) -> str:
        last_error: Optional[Exception] = None
        for client in self.clients:
            if self._is_broken(client):
                logger.debug(f"Skipping {type(client).__name__} (circuit open)")
                continue
            try:
                return await client.generate(system, user, temperature, response_schema)
            except ParseError as e:
                # Parse failures don't mean the provider is down — don't trip breaker
                logger.warning(f"{type(client).__name__} parse error (no breaker): {e}")
                last_error = e
                continue
            except Exception as e:
                logger.warning(f"{type(client).__name__} failed: {e}")
                self._trip(client, e)
                last_error = e
                continue
        raise last_error or ProviderError("All LLM providers failed or are rate-limited")

    async def generate_json(
        self,
        system: str,
        user: str,
        temperature: float = 0.7,
        response_schema: Optional[Any] = None,
    ) -> Union[dict, list]:
        last_error: Optional[Exception] = None
        for client in self.clients:
            if self._is_broken(client):
                logger.debug(f"Skipping {type(client).__name__} (circuit open)")
                continue
            try:
                return await client.generate_json(system, user, temperature, response_schema)
            except ParseError as e:
                logger.warning(f"{type(client).__name__} parse error (no breaker): {e}")
                last_error = e
                continue
            except Exception as e:
                logger.warning(f"{type(client).__name__} failed (JSON): {e}")
                self._trip(client, e)
                last_error = e
                continue
        raise last_error or ProviderError("All LLM providers failed or are rate-limited")


# ---------------------------------------------------------------------------
# JSON parser
# ---------------------------------------------------------------------------

def parse_llm_json(raw: str) -> Union[dict, list]:
    cleaned = raw.strip()

    # Strip markdown fences
    if "```json" in cleaned:
        cleaned = cleaned.split("```json", 1)[1].rsplit("```", 1)[0]
    elif "```" in cleaned:
        cleaned = cleaned.split("```", 1)[1].rsplit("```", 1)[0]
    cleaned = cleaned.strip()

    def _sanitize(s: str) -> str:
        return re.sub(r",\s*([\]}])", r"\1", s)

    # Direct parse
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Trailing-comma-tolerant parse
    try:
        return json.loads(_sanitize(cleaned))
    except json.JSONDecodeError:
        pass

    # Regex extraction fallback
    for pattern in [r"(\{[\s\S]*\})", r"(\[[\s\S]*\])"]:
        match = re.search(pattern, cleaned)
        if match:
            inner = match.group(1)
            for candidate in [inner, _sanitize(inner)]:
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    continue

    raise ParseError(f"Failed to parse LLM JSON response: {raw[:500]}")


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------

def get_llm_client(role: str = "general") -> LLMClient:
    """
    Build a client (or CompositeLLMClient) for the given role.

    Priority order per role:
      writer             → Groq (fast, very high RPM) → Gemini → Ollama
      director           → Gemini (best analytical)   → Groq   → Ollama
      character_detection→ Gemini (best JSON schema)  → Groq   → Ollama
      general            → primary_provider → fallback → Ollama
    """
    clients = []

    def make(provider: str, model: Optional[str] = None):
        try:
            if provider == "gemini" and settings.gemini_api_key:
                return GeminiClient(model_name=model or settings.gemini_model)
            if provider == "groq" and settings.groq_api_key:
                return GroqClient(model_name=model or settings.groq_model)
            if provider == "ollama":
                return OllamaClient(
                    base_url=getattr(settings, "ollama_base_url", "http://127.0.0.1:11434"),
                    model_name=getattr(settings, "ollama_model", "llama3.2:3b"),
                    num_ctx=getattr(settings, "ollama_num_ctx", 32768),
                )
        except Exception as e:
            logger.warning(f"Could not create {provider} client: {e}")
        return None

    # Role-specific preferred order and model selection
    # Creative roles (writer/director) use the quality model (gemini-2.5-flash)
    # Simple roles (character_detection, general) use the fast model (gemini-1.5-flash)
    use_quality_model = role in ("writer", "director")

    if role == "writer":
        order = ["groq", "gemini", "ollama"]
    elif role == "director":
        order = ["gemini", "groq", "ollama"]
    elif role == "character_detection":
        order = ["gemini", "groq", "ollama"]
    else:
        primary = settings.primary_provider.lower()
        fallback = "groq" if primary == "gemini" else "gemini"
        order = [primary, fallback, "ollama"]

    gemini_model_for_role = (
        getattr(settings, "gemini_model_quality", settings.gemini_model)
        if use_quality_model else settings.gemini_model
    )
    logger.info(f"get_llm_client(role={role}): order={order}, gemini_model={gemini_model_for_role}")

    seen: set[str] = set()
    for provider in order:
        if provider not in seen:
            seen.add(provider)
            # Pass the quality model name for creative roles using Gemini
            model_override = None
            if provider == "gemini" and use_quality_model:
                model_override = getattr(settings, "gemini_model_quality", None)
            c = make(provider, model=model_override)
            if c:
                clients.append(c)

    if not clients:
        raise ValueError("No LLM providers configured. Add at least one API key or run Ollama.")

    if len(clients) == 1:
        return clients[0]

    return CompositeLLMClient(clients)
