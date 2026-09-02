# T-0015: Phase 1 - Real Semantic Core

**Status:** active
**Priority:** p0
**Created:** 2026-09-02T00:00:00Z
**Completed:** —
**Depends On:** 
**Tags:** v7-upgrade, phase-1, semantic-search

## Description

Implement vector-based retrieval system for `semantic_search.py` that replaces fragile keyword matching with:
- Vector embeddings support (cosine similarity, simple embeddings or dense vectors)
- Metadata filters for structured queries
- Explainable scoring (returns reason for matches)
- Filesystem remains source of truth

## Acceptance Criteria

- [ ] Implement `SemanticSearchIndex` with embedding support
- [ ] Replace keyword-based search with vector similarity
- [ ] Add metadata filtering layer
- [ ] Return structured results with match reasons
- [ ] Maintain filesystem integrity (no breaking changes to storage)
- [ ] Add type hints and error handling
- [ ] Tests pass (vector search accuracy)

## Implementation Notes

**File Target:** `src/keeli/semantic_search.py`

**Key Changes:**
1. Replace `_calculate_relevance()` with vector similarity
2. Add `EmbeddingModel` abstraction (supports external APIs)
3. Implement `MetadataFilter` for structured queries
4. Return `SearchResult` objects with `reason` field

**Architecture:**
- Lightweight, no external LLM dependency
- Embeddings can be computed or cached
- Metadata filters applied before ranking
