"""
scraper/discovery.py — Company URL discovery from permitted public sources.

Currently supports:
1. Seed CSV file of manually approved URLs (primary source for the MVP)
2. Extensible base class for future directory scrapers

Discovery design:
- Each source is a separate class implementing DiscoverySource.
- The seed CSV is the only active source for the one-day MVP.
- Future sources (e.g., IndiaMart, Justdial permitted feeds) are
  placeholders with clear NOT_IMPLEMENTED markers.

Important: no search-engine scraping, no platform ToS violations.
"""

import csv
import logging
import pathlib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterator

logger = logging.getLogger(__name__)

DEFAULT_SEED_PATH = pathlib.Path(__file__).parent.parent / "data" / "seed_urls.csv"

ALLOWED_CATEGORIES = {"architecture", "interior", "other"}


@dataclass
class DiscoveredURL:
    url: str
    category: str   # architecture | interior | other
    source: str     # which discovery source produced this


class DiscoverySource(ABC):
    """Base class for company URL discovery sources."""

    @abstractmethod
    def discover(self) -> Iterator[DiscoveredURL]:
        """Yield DiscoveredURL objects from this source."""


class SeedCSVSource(DiscoverySource):
    """
    Read approved company URLs from a local CSV file.

    Expected CSV columns (order-independent, header required):
        url      — the company website URL
        category — architecture | interior | other
        notes    — optional human-readable notes (ignored)

    Any row with an invalid or missing URL is skipped with a warning.
    """

    def __init__(self, path: pathlib.Path | str | None = None) -> None:
        self.path = pathlib.Path(path) if path else DEFAULT_SEED_PATH

    def discover(self) -> Iterator[DiscoveredURL]:
        if not self.path.exists():
            logger.warning("Seed CSV not found at %s", self.path)
            return

        with open(self.path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                logger.error("Seed CSV has no header row.")
                return

            fieldnames_lower = [fn.strip().lower() for fn in reader.fieldnames]
            if "url" not in fieldnames_lower:
                logger.error("Seed CSV missing required 'url' column. Found: %s", reader.fieldnames)
                return

            for i, row in enumerate(reader, start=2):
                url = row.get("url", "").strip()
                if not url:
                    logger.debug("Row %d: empty URL, skipping.", i)
                    continue

                raw_category = row.get("category", "architecture").strip().lower()
                category = raw_category if raw_category in ALLOWED_CATEGORIES else "other"

                yield DiscoveredURL(url=url, category=category, source="seed_csv")


class DiscoveryEngine:
    """
    Orchestrates multiple discovery sources and deduplicates by URL.
    """

    def __init__(self, sources: list[DiscoverySource] | None = None) -> None:
        self.sources = sources or [SeedCSVSource()]

    def discover_all(self) -> list[DiscoveredURL]:
        seen: set[str] = set()
        results: list[DiscoveredURL] = []
        for source in self.sources:
            for item in source.discover():
                if item.url not in seen:
                    seen.add(item.url)
                    results.append(item)
        logger.info("Discovery complete: %d unique URLs from %d source(s).", len(results), len(self.sources))
        return results
