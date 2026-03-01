"""Library resolution algorithm.

Pure business logic — receives RegistryIndexes, returns LibraryMatch results.
No knowledge of AppState, MCP, or I/O.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Literal

from rapidfuzz import fuzz, process

from procontext.models.registry import LibraryMatch

if TYPE_CHECKING:
    from procontext.models.registry import RegistryEntry, RegistryIndexes


def normalise_query(raw: str) -> str:
    """Normalise a raw query string for resolution.

    Steps (order matters):
      1. Strip pip extras:     "package[extra1,extra2]" → "package"
      2. Strip version specs:  "package>=1.0,<2.0" → "package"
      3. Lowercase
      4. Trim whitespace
    """
    query = re.sub(r"\[.*?\]", "", raw)
    query = re.sub(r"[><=!~^].+", "", query)
    query = query.lower()
    query = query.strip()
    return query


def resolve_library(
    query: str,
    indexes: RegistryIndexes,
    *,
    fuzzy_score_cutoff: int = 70,
    fuzzy_max_results: int = 5,
) -> list[LibraryMatch]:
    """Resolve a query to matching libraries using the 5-step algorithm.

    Returns on first hit for steps 1-3 (exact matches).
    Step 4 (fuzzy) may return multiple results.
    Result is always sorted by relevance descending (contract guarantee).
    """
    normalised = normalise_query(query)
    if not normalised:
        return []

    # Step 1: Exact package name match
    library_id = indexes.by_package.get(normalised)
    if library_id is not None:
        entry = indexes.by_id[library_id]
        return [_match_from_entry(entry, matched_via="package_name", relevance=1.0)]

    # Step 2: Exact ID match
    entry = indexes.by_id.get(normalised)
    if entry is not None:
        return [_match_from_entry(entry, matched_via="library_id", relevance=1.0)]

    # Step 3: Alias match
    library_id = indexes.by_alias.get(normalised)
    if library_id is not None:
        entry = indexes.by_id[library_id]
        return [_match_from_entry(entry, matched_via="alias", relevance=1.0)]

    # Step 4: Fuzzy match
    matches = _fuzzy_search(
        normalised,
        indexes.fuzzy_corpus,
        indexes.by_id,
        limit=fuzzy_max_results,
        score_cutoff=fuzzy_score_cutoff,
    )
    if matches:
        return matches

    # Step 5: No match
    return []


def _match_from_entry(
    entry: RegistryEntry,
    *,
    matched_via: Literal["package_name", "library_id", "alias", "fuzzy"],
    relevance: float,
) -> LibraryMatch:
    """Build a LibraryMatch from a RegistryEntry."""
    return LibraryMatch(
        library_id=entry.id,
        name=entry.name,
        languages=entry.languages,
        docs_url=entry.docs_url,
        matched_via=matched_via,
        relevance=relevance,
    )


def _fuzzy_search(
    query: str,
    corpus: list[tuple[str, str]],
    by_id: dict[str, RegistryEntry],
    limit: int = 5,
    score_cutoff: int = 70,
) -> list[LibraryMatch]:
    """Fuzzy match against the corpus using Levenshtein distance.

    Deduplicates by library_id (one result per library).
    Returns matches sorted by relevance descending.
    """
    terms = [term for term, _ in corpus]
    results = process.extract(
        query,
        terms,
        scorer=fuzz.ratio,
        limit=limit,
        score_cutoff=score_cutoff,
    )

    seen: set[str] = set()
    matches: list[LibraryMatch] = []

    for _term, score, idx in results:
        _, library_id = corpus[idx]
        if library_id in seen:
            continue
        seen.add(library_id)
        entry = by_id[library_id]
        matches.append(
            _match_from_entry(
                entry,
                matched_via="fuzzy",
                relevance=round(score / 100, 2),
            )
        )

    return sorted(matches, key=lambda m: m.relevance, reverse=True)
