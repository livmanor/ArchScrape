"""
tests/test_firecrawl.py — Unit tests for firecrawl_client.py and directory fallback.
"""

from scraper.firecrawl_client import (
    SearchHit,
    is_available,
    search_local_directory,
    test_firecrawl_connection,
)


def test_test_firecrawl_connection_with_dummy_key():
    """Testing an invalid key should return (False, description)."""
    ok, msg = test_firecrawl_connection("invalid_test_key_xyz")
    assert ok is False
    assert "Invalid API key" in msg or "HTTP 401" in msg


def test_search_local_directory():
    """Curated directory search should find relevant matches in local CSV files."""
    hits = search_local_directory("delhi architecture", limit=5)
    assert len(hits) > 0
    assert all(isinstance(h, SearchHit) for h in hits)
    assert any("delhi" in h.description.lower() or "delhi" in h.title.lower() for h in hits)


def test_search_local_directory_bengaluru():
    hits = search_local_directory("bengaluru design studios", limit=5)
    assert len(hits) > 0
    assert any("bengaluru" in h.description.lower() or "bengaluru" in h.title.lower() for h in hits)
