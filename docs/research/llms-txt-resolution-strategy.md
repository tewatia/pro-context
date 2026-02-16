# llms.txt Resolution Strategy for Pro-Context

**Date:** 2026-02-17
**Status:** Approved for Implementation
**Purpose:** Define the strategy for discovering and resolving library names to llms.txt documentation sources

---

## Executive Summary

Based on comprehensive research of 70+ popular libraries (see `llms-txt-deployment-patterns.md`), this document outlines Pro-Context's strategy for resolving library names to llms.txt documentation URLs.

**Key Findings:**
- 60% of surveyed libraries have adopted llms.txt (100% of AI/ML libraries)
- No single standard URL pattern exists
- Multi-variant libraries use "hub-and-spoke" models
- Content validation is critical (many URLs return HTML 200s)
- Registry-first approach with smart fallback solves 95%+ of cases

---

## Problem Statement

When a user queries Pro-Context for library documentation (e.g., "langchain", "nextjs@14", "supabase python sdk"), we need to:

1. **Resolve** the library name to a valid llms.txt URL
2. **Handle** multi-variant libraries (language, version, product variants)
3. **Validate** that the URL returns actual llms.txt content (not HTML error pages)
4. **Cache** results for fast subsequent lookups
5. **Maintain** accuracy as libraries evolve

---

## Solution: Registry-First with Smart Fallback

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ User Query: "langchain python docs"                         │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
        ┌──────────────────────────────┐
        │ Parse Query                   │
        │ - Extract: name, language,    │
        │   version, variant            │
        │ - Normalize: lowercase, etc.  │
        └──────────────┬───────────────┘
                       │
                       ▼
        ┌──────────────────────────────┐
        │ Step 1: Check Registry        │
        │ (SQLite lookup by normalized  │
        │  name, language, version)     │
        └──────────┬──────────┬────────┘
                   │          │
           Found   │          │  Not Found
                   │          │
                   ▼          ▼
        ┌──────────────┐  ┌──────────────────────────┐
        │ Return URL   │  │ Step 2: Try URL Patterns │
        │ from registry│  │ (10 common patterns)      │
        └──────────────┘  └──────────┬───────────────┘
                                      │
                              Found   │   Not Found
                                      │
                                      ▼
                          ┌──────────────────────────────┐
                          │ Step 3: Package Manager      │
                          │ Query → Extract docs URL     │
                          │ → Try patterns               │
                          └──────────┬──────────────────┘
                                     │
                             Found   │   Not Found
                                     │
                                     ▼
                          ┌──────────────────────────┐
                          │ Step 4: Hub Detection    │
                          │ Parse variants if hub    │
                          └──────────┬───────────────┘
                                     │
                                     ▼
                          ┌──────────────────────────┐
                          │ Step 5: Cache & Return   │
                          │ Add to registry          │
                          └──────────────────────────┘
                                     │
                                     ▼
                          ┌──────────────────────────┐
                          │ If still not found:      │
                          │ Fall back to other       │
                          │ adapters (HTML scraping) │
                          └──────────────────────────┘
```

---

## Step 0: Query Parsing

**Extract context from user query:**

Parse user query to extract:
- Library name
- Language/platform (if specified)
- Version (if specified)
- Variant/product (if specified)

**Examples:**
- `"langchain"` → name: "langchain", language: null, version: null
- `"langchain python"` → name: "langchain", language: "python"
- `"nextjs@14"` → name: "nextjs", version: "14"
- `"supabase js sdk"` → name: "supabase", language: "javascript", variant: "sdk"
- `"tensorflow lite"` → name: "tensorflow", variant: "lite"

**Extraction logic:**

1. **Version extraction**: If query contains `@`, split on it to extract version
   - `"nextjs@14"` → name: "nextjs", version: "14"

2. **Language detection**: Check query for language keywords
   - Python: "python", "py", "pypi"
   - JavaScript: "javascript", "js", "npm", "node"
   - TypeScript: "typescript", "ts"
   - Rust: "rust", "cargo"
   - Go: "go", "golang"
   - Ruby: "ruby", "gem"
   - Swift: "swift", "ios"
   - Kotlin: "kotlin", "android"

3. **Variant detection**: Check for variant keywords
   - "lite", "full", "core", "mini", "sdk"

4. **Normalization**: Convert to lowercase, remove special characters (-_.) for matching
```

---

## Step 1: Registry Lookup

**Check pre-built registry first (fastest path)**

**Registry Lookup Algorithm:**

Query registry for matching entry with priority order:

1. **Exact match** (name + language + version)
   - Search by normalized_name AND language AND version
   - If found, return immediately

2. **Name + language match** (any version)
   - Search by normalized_name AND language (ignore version)
   - Returns latest/default version
   - If found, return

3. **Name-only match** (default variant)
   - Search by normalized_name only
   - Returns default language/version
   - If found, return

4. **Alias match**
   - Search aliases field for normalized_name
   - If found, return

5. **Not found**
   - Proceed to next resolution step

**Variant URL Selection:**

When registry entry has multiple URLs, select best match:

1. **Language filter** (if language specified in context)
   - Find URL where variant matches requested language
   - Return if found

2. **Version filter** (if version specified in context)
   - Find URL where version appears in URL path
   - Return if found

3. **Canonical URL**
   - Return URL marked as canonical
   - Return if exists

4. **Default**
   - Return first URL in list

**Registry Data Structure:**

Each registry entry contains:
- `library_name`: Display name
- `normalized_name`: Lowercase, no special characters (for matching)
- `aliases`: List of alternative names
- `canonical_url`: Primary llms.txt URL
- `all_urls`: List of URL objects containing:
  - `url`: Full llms.txt URL
  - `variant`: language/version/package identifier
  - `type`: "index", "hub", or variant type
  - `validated_at`: Last check timestamp
  - `canonical`: boolean flag
- `is_hub`: Boolean indicating hub-and-spoke structure
- `hub_variants`: List of variant objects (if hub)
- `language`: List of supported languages
- `version`: Version string or null
- `doc_platform`: Platform identifier (mintlify, vitepress, custom, etc.)
- `last_validated`: Timestamp of last URL check
- `validation_status`: "active", "stale", or "dead"
- `discovered_from`: Source (llms-txt-hub, manual, automated)
- `created_at`: Creation timestamp
- `metadata`: Extensibility field for additional data

**Expected Performance:**
- Database lookup: <10ms
- Covers 80% of queries (top 200-300 libraries in registry)

---

## Step 2: URL Pattern Discovery

**If not in registry, try standard URL patterns**

Based on research of 70+ libraries, these patterns cover 95% of llms.txt deployments.

**Pattern Priority Order** (by adoption frequency):

**If language specified in context, prepend:**
- `https://{language}.{name}.com/llms.txt` (e.g., python.langchain.com)
- `https://{name}.com/llms/{language}.txt` (e.g., supabase.com/llms/python.txt)
- `https://docs.{name}.com/{language}/llms.txt`

**If version specified in context, prepend:**
- `https://{name}.org/docs/{version}/llms.txt` (Next.js pattern)
- `https://docs.{name}.com/en/{version}/llms.txt`
- `https://docs.{name}.com/{version}/llms.txt`

**Standard patterns (ordered by frequency):**

1. **Docs subdomain** (30% of cases)
   - `https://docs.{name}.com/llms.txt`
   - `https://docs.{name}.dev/llms.txt`
   - `https://docs.{name}.io/llms.txt`

2. **Modern .dev domain** (popular with JS frameworks)
   - `https://{name}.dev/llms.txt`

3. **Root-level on .com** (25% of cases)
   - `https://{name}.com/llms.txt`
   - `https://www.{name}.com/llms.txt`

4. **.io domain** (15% of cases)
   - `https://{name}.io/llms.txt`
   - `https://www.{name}.io/llms.txt`

5. **Docs path** (OpenAI pattern)
   - `https://{name}.com/docs/llms.txt`
   - `https://www.{name}.com/docs/llms.txt`

6. **Locale path** (Anthropic pattern)
   - `https://docs.{name}.com/en/llms.txt`

7. **ReadTheDocs** (low success rate but worth trying)
   - `https://{name}.readthedocs.io/llms.txt`
   - `https://{name}.readthedocs.io/en/latest/llms.txt`

**Algorithm:**
- For each pattern in order, construct URL and validate
- Return first valid llms.txt URL found
- If none found, return null

**Expected Performance:**
- 10 patterns × 5s timeout = max 50s (parallelizable to ~10s)
- Success rate: 60% of libraries not in registry

---

## Step 3: Content Validation (Critical)

**Many URLs return HTTP 200 but serve HTML error pages**

Research found 4+ cases where valid URLs return HTML:
- `docs.anthropic.com/en/llms.txt` → HTML 404 page
- `kit.svelte.dev/llms.txt` → HTML page
- `docs.sqlalchemy.org/llms.txt` → HTML page

**Validation Algorithm:**

For each candidate URL, perform these checks:

1. **HTTP Status Check**
   - Make HEAD request to URL with timeout (5s)
   - Follow redirects if any
   - Must return HTTP 200 status
   - If not 200, URL is invalid

2. **Content-Type Header Check**
   - Examine Content-Type response header
   - Should be `text/plain` or `text/markdown`
   - If contains "html", URL is invalid (likely error page)

3. **Content Validation** (fetch first 1KB only)
   - Make GET request, read first 1024 bytes
   - Check for HTML indicators:
     - `<!DOCTYPE`
     - `<html` or `<HTML>`
     - `<head>`
     - `<body>`
   - If any HTML tags found, URL is invalid (HTML error page despite 200 status)

4. **Markdown Format Check**
   - Extract first line of content
   - Must start with `#` (markdown header)
   - If not markdown, URL is invalid

5. **Error Handling**
   - Network errors, timeouts → URL is invalid
   - Return false on any exception

**Result:** URL is valid only if all checks pass

**Performance:**
- HEAD request: ~500ms
- GET 1KB: ~800ms
- Total per URL: ~1.3s
- Parallelize to test multiple patterns simultaneously

---

## Step 4: Hub Detection

**Multi-variant libraries use hub-and-spoke model**

Examples from research:
- **Svelte**: 7 files (main + 3 sizes + 4 packages)
- **Supabase**: 9 files (main + 7 language SDKs + CLI)
- **TanStack**: 5 files (main + 4 libraries)

**Detection Algorithm:**

Hub files contain multiple links to other llms.txt files.

**Detection Steps:**

1. **Extract Markdown Links**
   - Parse llms.txt content for markdown link pattern: `[Label](URL)`
   - Extract all links with `.txt` extension

2. **Filter for llms.txt Variants**
   - Keep only URLs containing "llms" in path
   - For each link, extract:
     - Label (link text)
     - URL
     - Inferred variant type

3. **Hub Threshold Check**
   - If >2 llms.txt links found → classify as hub
   - Otherwise → regular llms.txt file

**Variant Type Inference:**

For each variant, infer type from label and URL:

**Language variant** - contains language keywords:
- Python, JavaScript, TypeScript, Rust, Go, Swift, Kotlin, etc.
- Example: "Python SDK" or URL contains `/python/`

**Size variant** - contains size keywords:
- full, medium, small, lite
- Example: "Full Documentation" or `llms-full.txt`

**Version variant** - contains version number:
- Pattern: v14, v15, version 2.0, etc.
- Example: "Version 14" or URL contains `/14/`

**Package variant** - default for others:
- kit, router, query, form, cli, etc.
- Example: "SvelteKit" or URL contains `/kit/`

**Hub Type Classification:**
- Count variant types across all variants
- Hub type = most common variant type
- Example: If 5 language variants and 2 package variants → "language" hub

**User Experience:**

When hub detected with multiple variants:
```
Found LangChain documentation with multiple variants:
1. Python SDK (https://python.langchain.com/llms.txt)
2. JavaScript SDK (https://js.langchain.com/llms.txt)
3. Main Documentation (https://docs.langchain.com/llms.txt)

Which would you like? [default: Python SDK]
```

---

## Step 5: Package Manager Integration

**If URL patterns fail, query package manager for docs URL**

**Package Manager Query Algorithm:**

1. **Select Package Manager** (based on language context)
   - JavaScript/TypeScript/null → query npm
   - Python/null → query PyPI
   - Rust → query crates.io
   - (Future: add more package managers)

2. **Query Package Registry API**

   **For npm:**
   - GET `https://registry.npmjs.org/{package_name}`
   - Extract `homepage` field or `repository.url` field
   - Return as docs_url

   **For PyPI:**
   - GET `https://pypi.org/pypi/{package_name}/json`
   - Extract `project_urls.Documentation` or `project_urls.Homepage`
   - Return as docs_url

   **For crates.io:**
   - GET `https://crates.io/api/v1/crates/{package_name}`
   - Extract `homepage` or `repository` field
   - Return as docs_url

3. **Try llms.txt Patterns on Discovered URL**
   - `{docs_url}/llms.txt`
   - `{docs_url}/en/llms.txt`
   - `{docs_url}/docs/llms.txt`

4. **Validate Each Pattern**
   - Use same validation algorithm as Step 3
   - Return first valid llms.txt URL

5. **Handle Errors**
   - API errors, timeouts → return null
   - Continue to next package manager if available

**Expected Performance:**
- npm/PyPI API call: ~500ms
- Pattern testing on result: ~3s
- Success rate: 30-40% of remaining cases

---

## Step 6: Caching Strategy

**Store discovered URLs in registry for future queries**

**Caching Algorithm:**

1. **Prepare Registry Entry**
   - library_name: Original query name
   - normalized_name: Normalized version for matching
   - aliases: Empty list (can be enriched later)
   - canonical_url: Discovered llms.txt URL
   - all_urls: List containing single URL object:
     - url: Discovered URL
     - variant: Language from context (if any)
     - type: "index"
     - validated_at: Current timestamp
     - canonical: true
   - is_hub: Whether hub structure detected
   - hub_variants: Variant list if hub, null otherwise
   - language: List with language from context (if any)
   - version: Version from context (if any)
   - doc_platform: Platform identifier (see detection below)
   - last_validated: Current timestamp
   - validation_status: "active"
   - discovered_from: "automated"
   - created_at: Current timestamp
   - metadata: Empty extensibility field

2. **Detect Documentation Platform** (from URL patterns)
   - Contains "mintlify" → "mintlify"
   - Contains "readthedocs.io" → "readthedocs"
   - Contains "github.io" → "github-pages"
   - Contains "gitbook" → "gitbook"
   - Domain ends with ".dev" → "vitepress" (common pattern)
   - Otherwise → "custom"

3. **Store in Registry**
   - Insert entry into registry database
   - Entry now available for future lookups

**Cache TTL:**
- Active entries: Re-validate after 30 days
- Stale entries: Re-validate on next access
- Dead entries: Try rediscovery after 90 days

---

## Registry Maintenance

### Initial Registry Build

**Phase 1: Curated Sources (Week 1)**

1. **Scrape llms-txt-hub**
   - ~100+ verified entries
   - High confidence, community-maintained

2. **Add manually verified popular libraries**
   - All AI/ML libraries (100% adoption)
   - Top 50 JS frameworks
   - Top 50 developer platforms

3. **Validate all URLs**
   - Run validation against each URL
   - Detect hubs and extract variants
   - Store in registry

**Target:** 200-300 verified entries

**Phase 2: Package Ecosystem Coverage (Week 2-3)**

1. **npm top 500 packages**
   - Extract homepage from package.json
   - Try URL patterns
   - Add successful discoveries

2. **PyPI top 500 packages**
   - Extract project_urls from metadata
   - Try URL patterns
   - Add successful discoveries

**Target:** +100-200 additional entries

### Ongoing Maintenance

**Weekly Automated Tasks:**

Schedule: Every Sunday (or weekly interval)

Tasks to perform:
1. Scrape llms-txt-hub repository for updates
2. Check GitHub topics tagged "llms-txt"
3. Re-validate registry entries older than 30 days
4. Detect and mark dead links (404/500 responses)
5. Try rediscovery for stale entries (new URL patterns)
6. Generate report of changes for review

**Community Contributions:**

Issue template for adding libraries to registry:

Fields to provide:
- Library name
- llms.txt URL
- Language/variants (if applicable)
- Additional information

Verification checklist:
- [ ] URL is accessible (returns HTTP 200)
- [ ] Content is valid llms.txt format (not HTML error page)

**Validation Process:**

For entries older than 30 days:

1. **Test Current URL**
   - Validate canonical_url using validation algorithm
   - Check if URL still returns valid llms.txt

2. **If Valid**
   - Update last_validated timestamp to current time
   - Keep validation_status as "active"

3. **If Invalid**
   - Update validation_status to "stale"
   - Attempt rediscovery using URL pattern algorithm

4. **Rediscovery Attempt**
   - Try all URL patterns for library name
   - If new valid URL found:
     - Update canonical_url to new URL
     - Update validation_status to "active"
     - Update last_validated timestamp
   - If no valid URL found:
     - Update validation_status to "dead"
     - Entry marked for manual review

---

## Coverage & Performance Estimates

### Expected Coverage

| Library Category | Registry Coverage | Pattern Discovery | Total Coverage |
|------------------|------------------|-------------------|----------------|
| AI/ML libraries | 100% | N/A | **100%** |
| Top 100 JS frameworks | 80% | 15% | **95%** |
| Top 100 Python libraries | 50% | 20% | **70%** |
| Developer platforms | 90% | 5% | **95%** |
| Database/ORMs | 75% | 10% | **85%** |
| Testing tools | 40% | 20% | **60%** |
| ReadTheDocs libraries | 0% | 0% | **0%** (fallback to other adapters) |
| **Overall popular libraries** | **80%** | **15%** | **95%+** |

### Performance Characteristics

| Resolution Path | Latency | Success Rate | % of Queries |
|----------------|---------|--------------|--------------|
| Registry hit (Step 1) | <10ms | 100% | 80% |
| Pattern discovery (Step 2) | 5-10s | 60% | 15% |
| Package manager (Step 3) | 3-5s | 40% | 3% |
| Fall back to other adapters | Varies | Varies | 2% |
| **Average** | **<1s** | **95%+** | **100%** |

### Optimization Opportunities

1. **Parallel pattern testing**
   - Test 10 patterns concurrently
   - Reduces latency from 50s to ~5s

2. **CDN caching**
   - Cache llms.txt content at edge
   - Serve from cache for repeated queries

3. **Predictive caching**
   - Pre-fetch llms.txt for trending libraries
   - Warm cache proactively

4. **Background validation**
   - Re-validate stale entries in background
   - Don't block user queries

---

## Integration Points

### With Library Resolution Algorithm

This strategy becomes **Step 0** in Pro-Context's library resolution:

```
Current Resolution Flow (05-library-resolution.md):
1. Check cache
2. Normalize library name
3. Query package managers
4. Try heuristics (GitHub, docs patterns)
5. Fall back to search

Updated Flow with llms.txt:
0. Try llms.txt resolution (THIS STRATEGY)
   ↓ (if found, return immediately)
   ↓ (if not found, continue to existing flow)
1. Check cache
2. Normalize library name
3. Query package managers
4. Try heuristics
5. Fall back to search
```

### With Adapter Chain

New adapter: `LLMsTxtAdapter` (Priority 0 - highest)

```javascript
class LLMsTxtAdapter extends DocumentationAdapter {
  priority = 0;

  async resolve(libraryName, context) {
    // Step 1: Parse query
    const libContext = parseLibraryQuery(libraryName);

    // Step 2: Check registry
    const registryEntry = await lookupRegistry(libContext);
    if (registryEntry) {
      return {
        url: selectVariantUrl(registryEntry, libContext),
        type: 'llms-txt',
        metadata: registryEntry
      };
    }

    // Step 3: Try URL patterns
    const url = await tryUrlPatterns(libContext);
    if (url) {
      // Cache for future
      await cacheDiscoveredUrl(libContext, url, null);
      return { url, type: 'llms-txt' };
    }

    // Step 4: Package manager fallback
    const pmUrl = await queryPackageManager(libContext);
    if (pmUrl) {
      await cacheDiscoveredUrl(libContext, pmUrl, null);
      return { url: pmUrl, type: 'llms-txt' };
    }

    // Not found, let next adapter try
    return null;
  }
}
```

### With Database Schema

Add to `03-technical-spec.md`:

```sql
-- llms.txt registry table
CREATE TABLE llms_txt_registry (
  id INTEGER PRIMARY KEY,
  library_name TEXT NOT NULL,
  normalized_name TEXT NOT NULL UNIQUE,
  aliases TEXT,
  canonical_url TEXT NOT NULL,
  all_urls TEXT,
  is_hub BOOLEAN DEFAULT FALSE,
  hub_variants TEXT,
  language TEXT,
  version TEXT,
  doc_platform TEXT,
  last_validated TEXT NOT NULL,
  validation_status TEXT NOT NULL,
  discovered_from TEXT,
  created_at TEXT NOT NULL,
  metadata TEXT
);

CREATE INDEX idx_normalized_name ON llms_txt_registry(normalized_name);
CREATE INDEX idx_validation_status ON llms_txt_registry(validation_status);
CREATE INDEX idx_last_validated ON llms_txt_registry(last_validated);
```

---

## Success Criteria

### Coverage Metrics
- ✅ 95%+ of top 200 popular libraries resolved
- ✅ 100% of AI/ML libraries covered
- ✅ 80%+ of modern JS frameworks covered

### Performance Metrics
- ✅ <10ms for registry hits (80% of queries)
- ✅ <5s for pattern discovery (15% of queries)
- ✅ <1s average resolution time

### Quality Metrics
- ✅ 0% HTML error pages returned
- ✅ >95% uptime for registry URLs
- ✅ <5% stale entries in registry

### Maintenance Metrics
- ✅ Weekly automated validation runs
- ✅ <7 day lag for new library additions
- ✅ Community contributions enabled

---

## Risks & Mitigations

### Risk 1: URL Pattern Changes
**Impact:** Libraries change documentation URLs
**Mitigation:**
- Weekly re-validation of registry entries
- Automatic rediscovery for stale URLs
- Community reporting mechanism

### Risk 2: Low Adoption Growth
**Impact:** llms.txt adoption doesn't grow as expected
**Mitigation:**
- Strategy still works with 60% current adoption
- Graceful fallback to other adapters
- Monitor adoption trends quarterly

### Risk 3: Hub Complexity
**Impact:** Hub-and-spoke patterns become more complex
**Mitigation:**
- Simple link extraction algorithm
- Manual curation for edge cases
- Clear user prompts when variants found

### Risk 4: Performance Degradation
**Impact:** Pattern testing becomes slow
**Mitigation:**
- Parallel pattern testing
- Timeout limits (5s per pattern)
- Registry growth reduces pattern testing frequency

---

## Future Enhancements

### Phase 2 (Post-Launch)
1. **Machine learning for URL prediction**
   - Train model on successful discoveries
   - Predict likely URL from library name

2. **Crowdsourced validation**
   - Let users flag incorrect/stale URLs
   - Community voting on variant preferences

3. **Integration with llms.txt hub**
   - Contribute discoveries back to llms-txt-hub
   - Auto-sync with hub updates

4. **llms.txt generator**
   - Tool for library maintainers
   - Generate llms.txt from existing docs

### Phase 3 (Long-term)
1. **llms.txt registry service**
   - Public API for llms.txt resolution
   - Shared across MCP servers

2. **Version-aware caching**
   - Store multiple versions per library
   - Smart version selection based on user needs

3. **Custom hub formats**
   - Support for structured hub metadata
   - Standardized variant naming

---

## References

- **Research:** `llms-txt-deployment-patterns.md` - Survey of 70+ libraries
- **Specification:** `05-library-resolution.md` - Library resolution algorithm
- **Database:** `03-technical-spec.md` - Database schema
- **Adapters:** `02-functional-spec.md` - Adapter chain design

---

## Changelog

- **2026-02-17:** Initial version based on research findings
