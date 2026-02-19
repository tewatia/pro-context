# Pending Items and Open Questions

> **Document**: pending-items.md
> **Purpose**: Track pending decisions, missing components, and open questions during design phase
> **Last Updated**: 2026-02-19
> **Status**: Living document

---

## Table of Contents

- [1. Technology Stack Gaps](#1-technology-stack-gaps)
- [2. Registry Update Mechanism](#2-registry-update-mechanism)
- [3. FTS5 Sync Triggers](#3-fts5-sync-triggers)
- [4. Implementation Decisions](#4-implementation-decisions)
- [5. Future Enhancements](#5-future-enhancements)

---

## 1. Technology Stack Gaps

### 1.1 Markdown Parser (CRITICAL)

**Status**: Missing from tech stack
**Priority**: HIGH (needed for Phase 2/3)
**Context**: Specs mention "Parse markdown into AST (heading-aware)" for chunking and TOC extraction, but no parser is listed.

**Options:**
- `mistune` (>=3.0.0,<4.0.0) — Fast, AST support, well-maintained ✅ **Recommended**
- `markdown-it-py` — Python port of markdown-it, CommonMark compliant
- Regex-based — Simple but less robust

**Decision needed**: Which markdown parser to use?

**Action**: Add chosen parser to doc 03 (Technology Stack table)

---

### 1.2 CLI Framework (LOW PRIORITY)

**Status**: Missing from tech stack
**Priority**: LOW (Phase 4 decision)
**Context**: Admin CLI is specified (`pro-context-admin key create`) but no framework chosen.

**Options:**
- `argparse` (stdlib) — Zero dependencies, basic functionality
- `click` (>=8.1.0,<9.0.0) — Popular, mature, good UX
- `typer` — Modern, type-hint based, builds on click

**Decision needed**: Which CLI framework? Or defer to Phase 4?

**Action**: Revisit during Phase 4 implementation

---

### 1.3 Environment Variable Loading (OPTIONAL)

**Status**: Not specified
**Priority**: LOW (nice-to-have)
**Context**: Specs mention `config.yaml` but `.env` file support not addressed.

**Options:**
- `os.environ` (stdlib) — Works for env vars, no `.env` file support
- `python-dotenv` (>=1.0.0,<2.0.0) — `.env` file support for local dev

**Decision needed**: Do we need `.env` file support or is `os.environ` sufficient?

**Action**: Decide during Phase 1 (Foundation) implementation

---

## 2. Registry Update Mechanism

### 2.1 Registry Distribution Strategy

**Status**: ✅ **DOCUMENTED** in doc 03 Section 6
**Priority**: HIGH (foundational design decision)
**Context**: Registry should be independent from pro-context package version.

**Documented approach:**
- Host registry on GitHub Releases (separate from code releases)
- Date-based versioning: `registry-v2024-02-19`
- Local storage: `~/.local/share/pro-context/registry/`
- Bundled fallback: Ship with registry snapshot in package

**Action**: ✅ Complete (doc 03 Section 6.1-6.5)

---

### 2.2 Database Update Performance

**Status**: ✅ **DOCUMENTED** in doc 03 Section 6.4
**Priority**: MEDIUM (implementation detail)
**Context**: How to efficiently update local SQLite DB when registry changes.

**Documented approach:**
- Single `UPDATE` query with `WHERE IN (...)` (not N queries)
- SQLite WAL mode for concurrent reads during update
- Transaction ensures atomicity
- Performance: 10-30ms DB lock for typical updates (acceptable)
- Stale-while-revalidate pattern: serve old data, refresh in background

**Action**: ✅ Complete (doc 03 Section 6.4)

---

### 2.3 Open Questions - Registry Updates

**Decision needed:**

1. **stdio mode update timing**
   - Apply registry updates on startup, or defer to next restart?
   - **Trade-off**: Startup time (+50-100ms) vs freshness

2. **HTTP mode auto-update frequency**
   - Auto-update every 24 hours, or require manual trigger?
   - **Trade-off**: Convenience vs control

3. **Stale cache threshold**
   - After how many days should we force-refresh stale entries?
   - **Options**: 7 days, 14 days, 30 days
   - **Trade-off**: Freshness vs network usage

4. **Cache cleanup policy**
   - Should we ever delete entries not accessed in 90+ days?
   - **Trade-off**: Disk space vs performance (no re-fetching)

5. **Update check rate limiting**
   - Should we throttle GitHub API checks (max once per hour)?
   - **Trade-off**: Freshness vs API quota

6. **Registry compression**
   - Should we gzip the registry (1.2MB → 200KB)?
   - **Trade-off**: Bandwidth vs decompression CPU

7. **Offline fallback**
   - If GitHub is down for 24+ hours, what behavior?
   - **Options**: Warn user, silently continue, fail startup

---

### 2.4 Schema Additions Needed

**Status**: ✅ **DOCUMENTED** in doc 03 Section 15.1
**Priority**: HIGH (needed for registry update implementation)

**Documented schema changes:**

```sql
-- Added stale flag to all cache tables (doc_cache, page_cache, toc_cache)
stale INTEGER NOT NULL DEFAULT 0

-- Indexes for fast stale queries
CREATE INDEX IF NOT EXISTS idx_{table}_stale ON {table}(stale) WHERE stale = 1;

-- System metadata table for tracking registry version
CREATE TABLE IF NOT EXISTS system_metadata (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

**Action**: ✅ Complete (doc 03 Section 15.1)

---

## 3. FTS5 Sync Triggers

### 3.1 Search Index Synchronization

**Status**: Deferred by user ("we will discuss FTS 5 in detail once these updates are completed")
**Priority**: HIGH (potential showstopper if not implemented correctly)
**Context**: Doc 03 Section 14.1 mentions FTS5 table but doesn't specify how to keep it in sync with `search_chunks` table.

**The problem:**
- Content lives in `search_chunks` table
- FTS5 index lives in `search_chunks_fts` virtual table
- Need to keep them in sync when chunks are inserted/updated/deleted

**Solution options:**

**Option A: SQLite Triggers (automatic)**
```sql
CREATE TRIGGER IF NOT EXISTS search_chunks_ai AFTER INSERT ON search_chunks
BEGIN
  INSERT INTO search_chunks_fts(rowid, title, content, section_path)
  VALUES (new.rowid, new.title, new.content, new.section_path);
END;

CREATE TRIGGER IF NOT EXISTS search_chunks_ad AFTER DELETE ON search_chunks
BEGIN
  DELETE FROM search_chunks_fts WHERE rowid = old.rowid;
END;

CREATE TRIGGER IF NOT EXISTS search_chunks_au AFTER UPDATE ON search_chunks
BEGIN
  UPDATE search_chunks_fts
  SET title = new.title, content = new.content, section_path = new.section_path
  WHERE rowid = new.rowid;
END;
```
- ✅ Automatic, no application code needed
- ✅ Transaction-safe (triggers run in same transaction)
- ❌ Slight overhead on every write

**Option B: Application-level sync**
```python
async def index_chunk(chunk: DocChunk):
    async with db.transaction():
        # Insert into main table
        await db.execute(
            "INSERT INTO search_chunks (...) VALUES (...)",
            (...)
        )
        # Manually insert into FTS5
        await db.execute(
            "INSERT INTO search_chunks_fts (...) VALUES (...)",
            (...)
        )
```
- ✅ More control
- ❌ Easy to forget, risk of desync
- ❌ More code to maintain

**Recommendation**: Option A (SQLite triggers) - automatic, safe, standard pattern

**Open questions:**
1. Should we use `AFTER` or `BEFORE` triggers?
2. How to handle trigger failures (e.g., FTS5 insert fails)?
3. Should we support rebuild-index command for recovery?

**Action**: Discuss and document in doc 03 Section 14.1

---

## 4. Implementation Decisions

### 4.1 Deferred to Implementation Phase

These items are design decisions that can be finalized during implementation:

1. **Exact BM25 parameters** (k1, b values) — Phase 3, tune during testing
2. **Chunk size thresholds** (min 100, target 500, max 1000 tokens) — Phase 3, may need adjustment
3. **Cache memory limits** (LRU cache size) — Phase 2, tune based on testing
4. **Rate limiting defaults** (requests per minute) — Phase 4, tune based on usage
5. **Background refresh timing** (how soon to refresh stale entries) — Phase 2, tune based on latency tolerance
6. **Fuzzy match threshold** (relevance score cutoff) — Phase 1, tune based on user feedback
7. **Error retry logic** (exponential backoff parameters) — Phase 1, standard defaults OK

---

## 5. Future Enhancements

### 5.1 Deferred Features (Post-Phase 5)

Features explicitly deferred to future versions:

1. **HTML documentation support** (Phase 5+)
   - Dependencies: `beautifulsoup4`, `lxml`, `markdownify`
   - Requires HTML → markdown conversion with sanitization

2. **Vector search** (Phase 5+)
   - Alternative/complement to BM25 for semantic search
   - Requires embedding model and vector database

3. **Pre-warming tool** (Phase 5+)
   - `pro-context warm --libraries langchain,fastapi` command
   - Proactively fetch and index popular libraries

4. **Registry discovery improvements** (Post-Phase 5)
   - Improved PyPI metadata extraction
   - Better heuristics for documentation URL discovery

5. **Multi-language support** (Post-Phase 5)
   - npm (JavaScript/TypeScript)
   - RubyGems (Ruby)
   - crates.io (Rust)

6. **Collaborative filtering** (Post-Phase 5)
   - "Users who queried X also queried Y"
   - Requires usage analytics

---

## 6. Documentation Gaps

### 6.1 Missing Documentation

Documents that may be needed but don't exist yet:

1. **Operations Guide** (LOW priority, Phase 4+)
   - Deployment instructions
   - Monitoring and alerting
   - Backup and disaster recovery
   - Troubleshooting guide

2. **User Documentation** (MEDIUM priority, Phase 5)
   - End-user guide for MCP clients
   - Configuration examples
   - FAQ

3. **Security Specification** (HIGH priority, Phase 4)
   - Threat model
   - Security best practices
   - Incident response plan
   - Currently scattered across specs, should be consolidated

4. **API Reference** (MEDIUM priority, Phase 5)
   - Generated from code (Sphinx/mkdocs)
   - Internal API docs for developers

**Action**: Create these documents when needed during implementation

---

## 7. Questions to Revisit

### 7.1 Registry Seed Data Quality

**Question**: How do we handle conflicting information between curated registries (llms-txt-hub, Awesome-llms-txt)?

**Context**: Section 3.0 in doc 06 says "curated data wins on conflicts" but doesn't specify what to do when curated sources disagree.

**Options**:
- Priority order: llms-txt-hub > Awesome-llms-txt > PyPI discovery
- Manual review of conflicts during build
- Log conflicts and choose the one with most recent update

---

### 7.2 Version-Specific Documentation

**Question**: Should we ever support version-specific docs (e.g., "langchain v0.1.x docs")?

**Context**: Current design serves "latest" documentation only. Some users might need older versions.

**Trade-off**:
- ✅ Always fresh, simple
- ❌ Doesn't help with legacy code

**Decision**: Out of scope for Phase 0-5, revisit if users request

---

### 7.3 Private Documentation Sources

**Question**: How should users configure private/internal documentation that requires auth?

**Context**: Specs mention "custom sources config" but don't detail authentication mechanism.

**Options**:
- Environment variables for API tokens
- Config file with credentials (encrypted?)
- Use system keychain (macOS Keychain, Windows Credential Manager)

**Action**: Design during Phase 1 (config system)

---

## 8. Action Items Summary

### Immediate (Before Phase 1)

- [ ] **Add markdown parser to tech stack** (doc 03)
  - Recommendation: `mistune` >=3.0.0,<4.0.0

- [x] **Document registry update mechanism** (doc 03, doc 05) ✅ **COMPLETED**
  - ✅ Registry distribution strategy (Section 6.1)
  - ✅ Database update approach (Section 6.4)
  - ✅ Schema changes (Section 15.1: stale flag, system_metadata)
  - ✅ Local storage (Section 6.2)
  - ✅ Update detection and download (Section 6.3)
  - ✅ Configuration (Section 6.5)

- [ ] **Resolve FTS5 triggers design** (doc 03)
  - Choose trigger approach (Option A recommended)
  - Document trigger SQL
  - Add rebuild-index command spec

### Phase 1 Decisions

- [ ] CLI framework choice (argparse vs click vs typer)
- [ ] Environment variable loading (os.environ vs python-dotenv)
- [ ] Private docs authentication mechanism

### Phase 4+ Decisions

- [ ] Registry update timing (stdio vs HTTP mode)
- [ ] Stale cache threshold (7/14/30 days)
- [ ] Cache cleanup policy (90+ days)
- [ ] Update check rate limiting
- [ ] Registry compression
- [ ] Offline fallback behavior

---

## Document History

| Date | Change | Author |
|------|--------|--------|
| 2026-02-19 | Initial creation | Ankur + Claude |
