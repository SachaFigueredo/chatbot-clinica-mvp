"""Unit tests for the FAQ search engine (Jaccard similarity, stop words, caching).

Tests cover the pure functions in ``app.application.faq.answer``:
- ``_clean_text`` — accent stripping, lowercase, punctuation removal
- ``_tokenize`` — stop-word and single-char filtering
- ``_jaccard_similarity`` — intersection / union
- ``_score_faq`` — combined question + answer scoring
- ``search_faqs`` — end-to-end search with cached and uncached paths
- ``generate_faq_response`` — LLM response generation with fallback
"""

from __future__ import annotations

import time

import pytest

from app.application.faq.answer import (
    _clean_text,
    _tokenize,
    _jaccard_similarity,
    _score_faq,
    _make_cache_key,
    clear_faq_search_cache,
    search_faqs,
    generate_faq_response,
    CACHE_TTL_SECONDS,
    SIMILARITY_THRESHOLD,
)


# ---------------------------------------------------------------------------
# _clean_text
# ---------------------------------------------------------------------------


class TestCleanText:
    def test_lowercase(self):
        assert _clean_text("Hola Mundo") == "hola mundo"

    def test_remove_accents(self):
        assert _clean_text("canción médica") == "cancion medica"

    def test_remove_punctuation(self):
        assert _clean_text("¿Cómo estás?") == "como estas"

    def test_collapse_whitespace(self):
        assert _clean_text("  mucho   espacio ") == "mucho espacio"

    def test_empty_string(self):
        assert _clean_text("") == ""

    def test_numbers_are_kept(self):
        assert _clean_text("Turno a las 15:30") == "turno a las 15 30"


# ---------------------------------------------------------------------------
# _tokenize
# ---------------------------------------------------------------------------


class TestTokenize:
    def test_removes_stop_words(self):
        """Common Spanish stop words are removed."""
        tokens = _tokenize("Hola, quiero un turno por favor")
        assert "un" not in tokens
        assert "por" not in tokens
        assert "quiero" in tokens
        assert "turno" in tokens

    def test_removes_single_chars(self):
        """Single-character tokens are removed."""
        tokens = _tokenize("a b c")
        assert tokens == set()

    def test_normalizes_accents(self):
        """Accented words are normalized before tokenization."""
        tokens = _tokenize("médico")
        assert "medico" in tokens

    def test_empty_input(self):
        assert _tokenize("") == set()

    def test_only_stop_words(self):
        assert _tokenize("de la y el") == set()


# ---------------------------------------------------------------------------
# _jaccard_similarity
# ---------------------------------------------------------------------------


class TestJaccardSimilarity:
    def test_identical_sets(self):
        assert _jaccard_similarity({"a", "b"}, {"a", "b"}) == 1.0

    def test_no_overlap(self):
        assert _jaccard_similarity({"a"}, {"b"}) == 0.0

    def test_partial_overlap(self):
        sim = _jaccard_similarity({"a", "b", "c"}, {"a", "d", "e"})
        assert sim == 1 / 5  # intersection: {a}, union: {a,b,c,d,e}

    def test_one_empty(self):
        assert _jaccard_similarity(set(), {"a", "b"}) == 0.0

    def test_both_empty(self):
        assert _jaccard_similarity(set(), set()) == 0.0


# ---------------------------------------------------------------------------
# _score_faq
# ---------------------------------------------------------------------------


class TestScoreFAQ:
    def test_question_match(self):
        """Direct question match gives a high score."""
        score = _score_faq(
            {"horario", "atencion"},
            "¿Cuáles son los horarios de atención?",
            "Respuesta genérica",
        )
        assert score >= SIMILARITY_THRESHOLD

    def test_answer_match(self):
        """Match against the answer (weighted 0.7) contributes."""
        score = _score_faq(
            {"lunes", "viernes"},
            "Pregunta no relacionada",
            "Lunes a viernes de 8 a 18",
        )
        # Answer match is weighted at 0.7
        assert score > 0
        assert score < 0.8


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


class TestCache:
    def setup_method(self):
        clear_faq_search_cache()

    def test_cache_key_is_deterministic(self):
        key1 = _make_cache_key("Hola mundo")
        key2 = _make_cache_key("Hola mundo")
        assert key1 == key2

    def test_different_questions_have_different_keys(self):
        key1 = _make_cache_key(_clean_text("horarios"))
        key2 = _make_cache_key(_clean_text("precios"))
        assert key1 != key2

    def test_clear_cache(self):
        clear_faq_search_cache()
        # After clear, internal cache should be empty
        from app.application.faq.answer import _search_cache

        assert len(_search_cache) == 0


# ---------------------------------------------------------------------------
# search_faqs — integration-light (needs a real DB session)
# ---------------------------------------------------------------------------


class TestSearchFAQs:
    """Requires a DB with FAQ data (see integration tests for full coverage).

    These smoke tests verify the search function works end-to-end with
    a real session but use the **conftest test_tenant + test_faqs** fixtures.
    """

    @pytest.mark.asyncio
    async def test_search_returns_matches(
        self, db_session, test_tenant, test_faqs
    ):
        """Searching for a relevant question returns matching FAQs."""
        # "horarios de atención" → tokens {horarios, atencion}
        # Known to match FAQ #1 "¿Cuáles son los horarios de atención?" via Jaccard
        results = await search_faqs(
            db_session, str(test_tenant.id), "horarios de atención"
        )
        assert len(results) >= 1
        first = results[0]
        assert "question" in first
        assert "answer" in first
        assert "score" in first
        # The top result should be about hours
        assert "horario" in first["question"].lower() or "lunes" in first["answer"].lower()

    @pytest.mark.asyncio
    async def test_search_no_match(self, db_session, test_tenant):
        """A completely unrelated query returns an empty list."""
        results = await search_faqs(
            db_session, str(test_tenant.id), "zyxwvutsrqponmlkjihgfedcba"
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_search_inactive_faqs_excluded(
        self, db_session, test_tenant, test_faqs
    ):
        """Soft-deleted (is_active=False) FAQs are never returned."""
        results = await search_faqs(
            db_session, str(test_tenant.id), "Inactive"
        )
        for r in results:
            assert r["question"] != "Inactive FAQ"

    @pytest.mark.asyncio
    async def test_search_empty_question(self, db_session, test_tenant):
        """An empty question returns no results (not an error)."""
        results = await search_faqs(db_session, str(test_tenant.id), "")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_cache_hits(self, db_session, test_tenant, test_faqs):
        """Repeated searches hit the cache."""
        # First call — populate cache
        results1 = await search_faqs(
            db_session, str(test_tenant.id), "horarios de atención"
        )
        # Second call — should be cached
        results2 = await search_faqs(
            db_session, str(test_tenant.id), "horarios de atención"
        )
        assert len(results1) == len(results2)
        assert results1 == results2


# ---------------------------------------------------------------------------
# generate_faq_response
# ---------------------------------------------------------------------------


class TestGenerateFAQResponse:
    async def test_no_results_returns_none(self, mock_llm_provider):
        """No FAQ results yields None (no answer)."""
        result = await generate_faq_response(
            mock_llm_provider, [], "¿alguna pregunta?"
        )
        assert result is None

    async def test_with_results_returns_string(self, mock_llm_provider):
        """FAQ results produce a response via the LLM."""
        mock_llm_provider.chat.return_value = (
            "Nuestros horarios son de lunes a viernes de 8 a 18hs."
        )
        faq_results = [
            {
                "question": "¿Horarios?",
                "answer": "Lunes a viernes de 8 a 18hs.",
                "category": "horarios",
                "score": 0.8,
            }
        ]
        result = await generate_faq_response(
            mock_llm_provider, faq_results, "¿Cuándo atienden?"
        )
        assert isinstance(result, str)
        assert "horarios" in result.lower() or "lunes" in result.lower()

    async def test_llm_failure_falls_back_to_first_answer(self, mock_llm_provider):
        """When the LLM call fails, we return the first FAQ answer directly."""
        mock_llm_provider.chat.side_effect = ConnectionError("network error")
        faq_results = [
            {
                "question": "¿Horarios?",
                "answer": "Lunes a viernes de 8 a 18hs.",
                "category": "horarios",
                "score": 0.8,
            }
        ]
        result = await generate_faq_response(
            mock_llm_provider, faq_results, "¿Cuándo atienden?"
        )
        assert result == "Lunes a viernes de 8 a 18hs."
