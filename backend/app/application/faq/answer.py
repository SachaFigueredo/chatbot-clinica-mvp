from __future__ import annotations

import hashlib
import logging
import re
import time
import unicodedata
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.interfaces.llm import LLMProvider
from app.infrastructure.database.models.faq import FAQ
from app.infrastructure.llm.prompts import FAQ_RESPONSE_PROMPT_TEMPLATE

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FAQ_SEARCH_LIMIT = 5
"""Maximum number of FAQ results to include in the LLM context."""

SIMILARITY_THRESHOLD = 0.2
"""Minimum Jaccard similarity score for a FAQ to be considered a match."""

CACHE_TTL_SECONDS = 300
"""Default TTL for the in-memory search cache (5 minutes)."""

CACHE_MAX_SIZE = 256
"""Maximum number of entries in the in-memory search cache."""

# ---------------------------------------------------------------------------
# Spanish stop words
# ---------------------------------------------------------------------------

_STOP_WORDS: set[str] = {
    "a", "al", "ante", "aquel", "aquella", "aquellos", "aquellas",
    "aqui", "ahi", "allí", "asi", "aunque",
    "bajo", "bastante",
    "cabe", "cada", "casi", "cierta", "ciertas", "cierto", "ciertos",
    "como", "con", "conmigo", "contigo", "consigo", "cual", "cuales",
    "cualquier", "cualquiera", "cuan", "cuando", "cuanta", "cuantas",
    "cuanto", "cuantos", "cuya", "cuyas", "cuyo", "cuyos",
    "da", "dado", "dan", "dar", "de", "del", "demas", "demasiada",
    "demasiadas", "demasiado", "demasiados", "desde", "dicha", "dichas",
    "dicho", "dichos", "donde", "dos",
    "e", "el", "ella", "ellas", "ello", "ellos", "en", "entre", "era",
    "erais", "eramos", "eran", "eras", "eres", "es", "esa", "esas",
    "ese", "eso", "esos", "esta", "estaba", "estabais", "estabamos",
    "estaban", "estabas", "estad", "estada", "estadas", "estado",
    "estados", "estais", "estamos", "estan", "estando", "estar",
    "estara", "estaran", "estaras", "estare", "estareis", "estaremos",
    "estaria", "estariais", "estariamos", "estarian", "estarias",
    "estas", "este", "estemos", "esto", "estos", "estoy", "etc",
    "fue", "fuera", "fuerais", "fueramos", "fueran", "fueras",
    "fueron", "fuese", "fueseis", "fuesemos", "fuesen", "fueses",
    "fui", "fuimos", "fuiste", "fuisteis",
    "ha", "habeis", "haber", "habia", "habiais", "habiamos", "habian",
    "habias", "habida", "habidas", "habido", "habidos", "habiendo",
    "habra", "habran", "habras", "habre", "habreis", "habremos",
    "habria", "habriais", "habriamos", "habrian", "habrias", "han",
    "has", "hasta", "hay", "haya", "hayais", "hayamos", "hayan",
    "hayas", "he", "hemos", "hube", "hubiera", "hubierais",
    "hubieramos", "hubieran", "hubieras", "hubieron", "hubiese",
    "hubieseis", "hubiesemos", "hubiesen", "hubieses", "hubimos",
    "hubiste", "hubisteis", "hubo",
    "la", "las", "le", "les", "lo", "los",
    "mas", "me", "menos", "mi", "mia", "mias", "mio", "mios", "mis",
    "misma", "mismas", "mismo", "mismos", "mucho", "mucha", "muchas",
    "muchos", "muy",
    "nada", "ni", "ningun", "ninguna", "ningunas", "ninguno", "ningunos",
    "no", "nos", "nosotras", "nosotros", "nuestra", "nuestras",
    "nuestro", "nuestros", "nunca",
    "o", "os", "otra", "otras", "otro", "otros",
    "para", "pero", "poca", "pocas", "poco", "pocos", "por", "porque",
    "que", "quien", "quienes", "qué",
    "se", "sea", "seais", "seamos", "sean", "seas", "segun", "ser",
    "sera", "seran", "seras", "sere", "sereis", "seremos", "seria",
    "seriais", "seriamos", "serian", "serias", "si", "sido", "siendo",
    "sin", "sino", "sobre", "sois", "somos", "son", "soy", "sr", "sra",
    "su", "sus", "suya", "suyas", "suyo", "suyos",
    "tal", "tambien", "tan", "tanta", "tantas", "tanto", "tantos",
    "te", "teneis", "tenemos", "tener", "tenga", "tengais", "tengamos",
    "tengan", "tengas", "tengo", "tengo", "tenia", "teniais",
    "teniamos", "tenian", "tenias", "tiene", "tienen", "tienes",
    "todo", "toda", "todas", "todos", "tras", "tres",
    "tu", "tus", "tuya", "tuyas", "tuyo", "tuyos",
    "un", "una", "unas", "uno", "unos", "usted", "ustedes",
    "varias", "varios", "vosotras", "vosotros", "vuestra", "vuestras",
    "vuestro", "vuestros",
    "y", "ya", "yo",
}

# ---------------------------------------------------------------------------
# In-memory search cache
# ---------------------------------------------------------------------------

_search_cache: dict[str, tuple[list[dict[str, Any]], float]] = {}
"""Cache for FAQ search results.

Map: ``cache_key -> (results, expiry_timestamp)``
The ``cache_key`` is an MD5 hash of the cleaned question.
"""


def _make_cache_key(cleaned_question: str) -> str:
    """Generate a deterministic cache key from the cleaned question."""
    return hashlib.md5(cleaned_question.encode("utf-8")).hexdigest()


def _get_cached(key: str) -> list[dict[str, Any]] | None:
    """Retrieve cached results if they exist and are still fresh."""
    entry = _search_cache.get(key)
    if entry is None:
        return None
    results, expiry = entry
    if time.monotonic() < expiry:
        return results
    # Expired — remove and return None.
    del _search_cache[key]
    return None


def _set_cache(key: str, results: list[dict[str, Any]]) -> None:
    """Store results in the cache, evicting oldest entries if full."""
    # Evict if at capacity (LRU-style: removes first inserted).
    if len(_search_cache) >= CACHE_MAX_SIZE:
        try:
            oldest = next(iter(_search_cache))
            del _search_cache[oldest]
        except StopIteration:
            pass

    _search_cache[key] = (results, time.monotonic() + CACHE_TTL_SECONDS)


def clear_faq_search_cache() -> None:
    """Clear the entire FAQ search cache.

    Call this from CRUD endpoints when FAQs are created, updated, or
    deleted so that subsequent searches reflect the latest data.
    """
    _search_cache.clear()
    logger.debug("FAQ search cache cleared")


# ---------------------------------------------------------------------------
# Text cleaning and similarity
# ---------------------------------------------------------------------------


def _clean_text(text: str) -> str:
    """Clean text for comparison.

    Steps:
    1. Lowercase
    2. Remove accents (Unicode NFKD normalization)
    3. Remove punctuation and non-alphanumeric characters
    4. Collapse whitespace
    """
    text = text.lower()
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9áéíóúñü\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _tokenize(text: str) -> set[str]:
    """Split cleaned text into a set of meaningful tokens.

    Removes stop words and single-character tokens.
    """
    cleaned = _clean_text(text)
    words = cleaned.split()
    return {w for w in words if w not in _STOP_WORDS and len(w) > 1}


def _jaccard_similarity(tokens_a: set[str], tokens_b: set[str]) -> float:
    """Compute the Jaccard similarity between two token sets.

    Returns a float in [0.0, 1.0], where 1.0 means identical sets.
    """
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


def _score_faq(
    patient_tokens: set[str],
    faq_question: str,
    faq_answer: str,
) -> float:
    """Compute a combined similarity score between a question and a FAQ.

    The score is the **maximum** of:
    - Jaccard similarity between the patient's tokens and the FAQ question tokens
    - Jaccard similarity between the patient's tokens and the FAQ answer tokens
      (weighted at 0.7 to prioritise question matching)

    This allows matching both direct question-to-question and cases where
    the patient's keywords appear in the answer.
    """
    question_tokens = _tokenize(faq_question)
    answer_tokens = _tokenize(faq_answer)

    question_score = _jaccard_similarity(patient_tokens, question_tokens)
    answer_score = _jaccard_similarity(patient_tokens, answer_tokens) * 0.7

    return max(question_score, answer_score)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def search_faqs(
    db: AsyncSession,
    tenant_id: str,
    question: str,
) -> list[dict[str, str]]:
    """Search the FAQ database for entries matching the patient's question.

    Uses Jaccard similarity on tokenized words (with Spanish stop word
    removal and accent normalisation) to find the best-matching entries.
    Results are cached in-memory for ``CACHE_TTL_SECONDS`` (default 5 min).

    Args:
        db: Database session.
        tenant_id: The tenant UUID string.
        question: The patient's question text.

    Returns:
        List of dicts with ``question``, ``answer``, ``category``, and
        ``score`` keys, sorted by score descending.  Empty list if no
        matches exceed the ``SIMILARITY_THRESHOLD`` (default 0.2).
    """
    # --- Clean the incoming question ---
    cleaned_question = _clean_text(question)
    patient_tokens = _tokenize(question)

    # --- Short-circuit: nothing to match ---
    if not patient_tokens:
        logger.debug("No tokens extracted from question: %.80s", question)
        return []

    # --- Check the cache ---
    cache_key = _make_cache_key(cleaned_question)
    cached = _get_cached(cache_key)
    if cached is not None:
        logger.debug("FAQ search cache hit for: %.80s", question)
        return cached

    # --- Load active FAQs for the tenant ---
    stmt = (
        select(FAQ)
        .where(
            FAQ.tenant_id == tenant_id,
            FAQ.is_active.is_(True),
        )
        .order_by(FAQ.sort_order)
    )
    result = await db.execute(stmt)
    all_faqs: list[FAQ] = list(result.scalars().all())

    if not all_faqs:
        logger.debug("No active FAQs found for tenant %s", tenant_id)
        return []

    # --- Score each FAQ ---
    scored: list[tuple[float, FAQ]] = []
    for faq in all_faqs:
        score = _score_faq(patient_tokens, faq.question, faq.answer)
        if score >= SIMILARITY_THRESHOLD:
            scored.append((score, faq))

    # --- Sort by score descending, then sort_order ascending (stable) ---
    scored.sort(key=lambda t: (-t[0], t[1].sort_order))

    # --- Build the result list ---
    results = [
        {
            "question": faq.question,
            "answer": faq.answer,
            "category": faq.category,
            "score": round(score, 4),
        }
        for score, faq in scored[:FAQ_SEARCH_LIMIT]
    ]

    # --- Cache and return ---
    _set_cache(cache_key, results)
    logger.debug(
        "FAQ search: %d / %d FAQs matched for: %.80s",
        len(results), len(all_faqs), question,
    )
    return results


async def generate_faq_response(
    llm_provider: LLMProvider,
    faq_results: list[dict[str, str]],
    question: str,
    clinic_name: str = "la clínica",
) -> str | None:
    """Generate a natural-language FAQ response using the LLM.

    Args:
        llm_provider: LLM provider for response generation.
        faq_results: List of FAQ entries from ``search_faqs``.
        question: The patient's original question.
        clinic_name: The clinic name for context.

    Returns:
        A natural language response string, or ``None`` if no FAQ
        context was found and the question cannot be answered.
    """
    if not faq_results:
        return None

    # Build FAQ context string.
    faq_lines = []
    for i, faq in enumerate(faq_results, 1):
        faq_lines.append(
            f"{i}. Pregunta: {faq['question']}\n   Respuesta: {faq['answer']}"
        )
    faq_context = "\n\n".join(faq_lines)

    prompt = FAQ_RESPONSE_PROMPT_TEMPLATE.format(
        clinic_name=clinic_name,
        question=question,
        faq_context=faq_context,
    )

    messages: list[dict[str, str]] = [
        {"role": "user", "content": prompt}
    ]

    try:
        response = await llm_provider.chat(messages, temperature=0.3)
        return response.strip()
    except (ConnectionError, TimeoutError) as exc:
        logger.error("LLM call failed for FAQ response: %s", exc)
        # Fallback: return the first FAQ answer directly.
        if faq_results:
            return faq_results[0]["answer"]
        return None
