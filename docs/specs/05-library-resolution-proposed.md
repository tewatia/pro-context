# Pro-Context: Library Resolution Strategy

> **Document**: 05-library-resolution-proposed.md
> **Status**: Proposed
> **Last Updated**: 2026-02-17
> **Depends on**: 02-functional-spec.md (v3)
> **Research**: See `docs/research/llms-txt-deployment-patterns.md`

---

## Table of Contents

- [1. Problem](#1-problem)
- [2. Solution: Documentation Sources](#2-solution-documentation-sources)
- [3. Registry Schema](#3-registry-schema)
  - [3.1 Core Fields](#31-core-fields)
  - [3.2 llms.txt Support](#32-llmstxt-support)
  - [3.3 Example Entries](#33-example-entries)
- [4. Resolution Algorithm](#4-resolution-algorithm)
  - [4.1 Input Normalization](#41-input-normalization)
  - [4.2 Resolution Steps](#42-resolution-steps)
  - [4.3 llms.txt Discovery](#43-llmstxt-discovery)
- [5. Building the Registry](#5-building-the-registry)
  - [5.1 Data Sources](#51-data-sources)
  - [5.2 Package Grouping](#52-package-grouping)
  - [5.3 llms.txt Discovery](#53-llmstxt-discovery)
- [6. Version Handling](#6-version-handling)
- [7. Open Questions](#7-open-questions)

---

## 1. Problem

When an agent calls `resolve-library("langchain")`, Pro-Context must determine:
- Is "langchain" one library or multiple?
- Where does its documentation live?
- Does it have llms.txt support?
- Which package manager packages belong to it?

This is harder than it appears:

**Challenge 1: Packages ≠ Libraries**
- `langchain`, `langchain-openai`, `langchain-community`, `langchain-core` are 4 separate PyPI packages
- They all share one documentation site: `docs.langchain.com`
- They should resolve to **one** documentation source, not four

**Challenge 2: Multi-language Libraries**
- LangChain has separate docs for Python (`python.langchain.com`) and JavaScript (`js.langchain.com`)
- These are different documentation sources, not just language filters

**Challenge 3: Monorepo Sub-packages**
- TanStack publishes: `@tanstack/query`, `@tanstack/router`, `@tanstack/table`, `@tanstack/form`
- Each has separate docs under `tanstack.com/{library}/`
- These share a "hub" but are distinct documentation sources

**Challenge 4: Package Extras**
- `langchain[openai]` and `langchain[anthropic]` are pip extras (installation options)
- They're not separate packages and don't change which docs to use
- Must be normalized away

**Challenge 5: Version Variants**
- Some packages publish nightly/dev builds: `tensorflow`, `tf-nightly`, `tensorflow-gpu`
- These are distribution variants, not separate libraries
- All point to the same documentation

The core insight: **Pro-Context's registry models documentation sources, not packages.** Packages point to documentation sources.

---

## 2. Solution: Documentation Sources

A **Documentation Source** is a place where documentation lives. It has:
- A unique identifier (`id`)
- A documentation URL (`docsUrl`)
- A list of packages that point to it (`packages`)
- Optional llms.txt support (`llmsTxt`)

```
┌─────────────────────────────────────────┐
│  Documentation Source: "langchain"      │
│                                         │
│  docsUrl: https://docs.langchain.com    │
│  llmsTxt: https://python.langchain.com/llms.txt │
│                                         │
│  packages (pypi):                       │
│    - langchain                          │
│    - langchain-openai                   │
│    - langchain-community                │
│    - langchain-core                     │
│    - langchain-text-splitters           │
└─────────────────────────────────────────┘
```

When an agent queries "langchain-openai", the resolution algorithm:
1. Finds "langchain-openai" in the package-to-source mapping
2. Returns the "langchain" documentation source
3. The agent gets LangChain's full documentation, not a subset

**This is correct.** There is no separate "langchain-openai" documentation site. The OpenAI integration docs are sections within LangChain's main documentation.

---

## 3. Registry Schema

### 3.1 Core Fields

Each documentation source entry contains:

**Identity:**
- `id` (string, required): Unique identifier, human-readable (e.g., "langchain", "pydantic")
- `name` (string, required): Display name (e.g., "LangChain", "Pydantic")

**Documentation:**
- `docsUrl` (string, optional): Primary documentation site URL
- `repoUrl` (string, optional): GitHub repository URL

**Package Mappings:**
- `packages` (object): Package registry mappings
  - `pypi` (list of strings): PyPI package names
  - `npm` (list of strings): npm package names
  - `crates` (list of strings): crates.io names
  - (Future: add more package managers as needed)

**Metadata:**
- `languages` (list of strings): Languages this library supports (informational only)
- `aliases` (list of strings): Alternative names for fuzzy matching
- `versionPattern` (string, optional): Template for version-specific doc URLs
  - Example: `"https://docs.pydantic.dev/{version}/llms.txt"`

### 3.2 llms.txt Support

If the library publishes llms.txt files, the entry includes:

**llmsTxt object:**
- `url` (string, required): Main llms.txt URL (validated)
- `fullUrl` (string, optional): Full content variant URL (llms-full.txt if available)
- `isHub` (boolean, required): Whether this is a hub file linking to multiple variants
- `variants` (list, optional): If hub, list of variant objects:
  - `label` (string): Human-readable label (e.g., "Python SDK", "Version 14")
  - `url` (string): Variant llms.txt URL
  - `type` (string): "language", "version", "package", or "size"
- `platform` (string, optional): Documentation platform (e.g., "mintlify", "vitepress", "custom")
- `lastValidated` (string, required): ISO timestamp of last successful validation

**Why llms.txt?**
- **AI-optimized**: Content designed specifically for LLM consumption
- **Fast**: Direct URL, no HTML parsing
- **Structured**: Markdown format with clear sections and links
- **Growing adoption**: 60% of popular libraries (100% of AI/ML category)

**Research findings** (70+ libraries surveyed):
- AI/ML libraries: 100% adoption
- Developer platforms: 90% adoption
- JavaScript frameworks: 80% adoption
- Traditional Python libraries: 33% adoption
- ReadTheDocs libraries: 0% adoption (platform doesn't support it)

### 3.3 Example Entries

**Example 1: Simple library with llms.txt**
```json
{
  "id": "langchain",
  "name": "LangChain",
  "docsUrl": "https://docs.langchain.com",
  "repoUrl": "https://github.com/langchain-ai/langchain",
  "languages": ["python"],
  "packages": {
    "pypi": [
      "langchain",
      "langchain-openai",
      "langchain-anthropic",
      "langchain-community",
      "langchain-core",
      "langchain-text-splitters"
    ]
  },
  "aliases": ["lang-chain"],
  "llmsTxt": {
    "url": "https://python.langchain.com/llms.txt",
    "isHub": false,
    "platform": "mintlify",
    "lastValidated": "2026-02-17"
  }
}
```

**Example 2: Hub with multiple variants (Supabase)**
```json
{
  "id": "supabase",
  "name": "Supabase",
  "docsUrl": "https://supabase.com",
  "repoUrl": "https://github.com/supabase/supabase",
  "languages": ["javascript", "python", "dart", "swift", "kotlin"],
  "packages": {
    "npm": ["@supabase/supabase-js"],
    "pypi": ["supabase"]
  },
  "aliases": [],
  "llmsTxt": {
    "url": "https://supabase.com/llms.txt",
    "isHub": true,
    "variants": [
      {
        "label": "JavaScript SDK",
        "url": "https://supabase.com/llms/js.txt",
        "type": "language"
      },
      {
        "label": "Python SDK",
        "url": "https://supabase.com/llms/python.txt",
        "type": "language"
      },
      {
        "label": "Dart SDK",
        "url": "https://supabase.com/llms/dart.txt",
        "type": "language"
      }
    ],
    "platform": "custom",
    "lastValidated": "2026-02-17"
  }
}
```

**Example 3: Library without llms.txt**
```json
{
  "id": "tensorflow",
  "name": "TensorFlow",
  "docsUrl": "https://www.tensorflow.org",
  "repoUrl": "https://github.com/tensorflow/tensorflow",
  "languages": ["python", "javascript"],
  "packages": {
    "pypi": ["tensorflow", "tensorflow-gpu", "tensorflow-cpu", "tf-nightly", "keras"],
    "npm": ["@tensorflow/tfjs"]
  },
  "aliases": ["tf"]
}
```

---

## 4. Resolution Algorithm

### 4.1 Input Normalization

Before matching, normalize the query:

**Remove pip extras:**
- `"langchain[openai]"` → `"langchain"`
- `"fastapi[all]"` → `"fastapi"`

**Remove version specifiers:**
- `"langchain>=0.3"` → `"langchain"`
- `"pydantic==2.0.0"` → `"pydantic"`

**Lowercase:**
- `"LangChain"` → `"langchain"`

**Trim whitespace:**
- `" fastapi "` → `"fastapi"`

**Preserve hyphens/underscores:**
- `"langchain-openai"` stays `"langchain-openai"` (it's a real package name)

### 4.2 Resolution Steps

Given a normalized query (e.g., "langchain-openai"):

**Step 1: Check registry - Package name lookup**
- Search all `packages.pypi`, `packages.npm`, etc. across all documentation sources
- If "langchain-openai" found in a source's package list, return that source
- **Fast path:** Database index lookup, <10ms

**Step 2: Check registry - ID match**
- Search documentation source IDs
- If query matches an ID exactly, return that source
- Useful when agent already knows the canonical ID

**Step 3: Check registry - Alias match**
- Search aliases field across all sources
- If query matches an alias, return that source
- Handles common misspellings and alternative names

**Step 4: Fuzzy match**
- Use Levenshtein distance or similar
- Match against IDs, names, package names, aliases
- Return top matches if distance is acceptable (≤ 3 edits)
- All matches above threshold are returned, ranked by score

**Step 5: llms.txt URL discovery**
- Try common llms.txt URL patterns (see section 4.3)
- Validate each URL (HTTP 200 + content check)
- If valid llms.txt found:
  - Detect if hub (contains links to variants)
  - Create ephemeral documentation source
  - Cache for future queries
  - Return source

**Step 6: Package manager discovery**
- Query PyPI API: `GET https://pypi.org/pypi/{query}/json`
- Extract `project_urls.Documentation` or `project_urls.Homepage`
- Try llms.txt patterns on discovered URL
- If found, create ephemeral source and return

**Step 7: GitHub discovery**
- If query looks like "owner/repo" (contains `/`)
- Query GitHub API: `GET https://api.github.com/repos/{owner}/{repo}`
- Extract homepage URL
- Try llms.txt patterns on homepage
- If found, create ephemeral source and return

**Step 8: No match**
- Return empty results
- Functional spec indicates this is NOT an error
- Agent can try different queries or ask user for clarification

**Performance:**
- Steps 1-4: In-memory lookups, <10ms
- Step 5: Network calls (parallelizable), 5-10s
- Steps 6-7: API calls, ~500ms each
- **Registry hits (Steps 1-4) cover 80% of queries**

### 4.3 llms.txt Discovery

When Step 5 tries to discover llms.txt, test these URL patterns in order:

**If language context available** (from query like "langchain python"):
1. `https://{language}.{name}.com/llms.txt` (e.g., python.langchain.com)
2. `https://{name}.com/llms/{language}.txt` (e.g., supabase.com/llms/python.txt)

**If version context available** (from query like "nextjs@14"):
1. `https://{name}.org/docs/{version}/llms.txt`
2. `https://docs.{name}.com/{version}/llms.txt`

**Standard patterns** (by adoption frequency):
1. `https://docs.{name}.com/llms.txt` (30% of cases)
2. `https://{name}.dev/llms.txt` (popular with JS frameworks)
3. `https://{name}.com/llms.txt` (25% of cases)
4. `https://{name}.io/llms.txt` (15% of cases)
5. `https://www.{name}.com/llms.txt` (10% of cases)
6. `https://docs.{name}.dev/llms.txt` (Pydantic pattern)
7. `https://{name}.com/docs/llms.txt` (OpenAI pattern)
8. `https://docs.{name}.com/en/llms.txt` (Anthropic pattern)
9. `https://docs.{name}.io/llms.txt` (Pinecone pattern)
10. `https://{name}.readthedocs.io/llms.txt` (rarely works, but try)

**Validation** (critical - many URLs return HTML error pages with 200 status):

For each candidate URL:
1. **HTTP check**: Make HEAD request, must return 200
2. **Content-Type check**: Should be `text/plain` or `text/markdown`, NOT `text/html`
3. **Content check**: Fetch first 1KB, verify:
   - Does NOT contain HTML tags (`<!DOCTYPE`, `<html>`, `<head>`, `<body>`)
   - DOES start with `#` (markdown header)
4. Only if all checks pass is URL considered valid

**Hub detection** (for multi-variant libraries):

When valid llms.txt found, check if it's a hub:
1. Parse content for markdown links to other `.txt` files
2. Filter for links containing "llms" in URL
3. For each link, extract:
   - Label (link text)
   - URL
   - Inferred type (language/version/package/size based on label/URL keywords)
4. If >2 llms.txt links found → classify as hub
5. Store hub structure in documentation source

---

## 5. Building the Registry

### 5.1 Data Sources

The registry is built from multiple sources:

**Primary: PyPI Top Packages**
- Source: `hugovk/top-pypi-packages` dataset
- Coverage: Top 5,000 packages by monthly downloads
- API: `https://pypi.org/pypi/{package}/json` per package
- Extract: name, description, `project_urls`, repository

**Secondary: Curated Lists**
- llms-txt-hub repository (~100+ verified entries)
- Known Mintlify customers (~50+ sites)
- Community contributions

**Tertiary: Package Manager Feeds**
- npm top packages (future)
- crates.io popular crates (future)

### 5.2 Package Grouping

**Challenge:** Given 5,000 PyPI packages, determine which ones share documentation.

**Approach:** Three-tier grouping algorithm with manual overrides.

#### 5.2.1 Grouping Algorithm

**Step 1: Initialize**
- Each package starts as a potential documentation source
- Parse PyPI metadata for all packages:
  - Extract `project_urls.Documentation`
  - Extract `project_urls.Source` (GitHub repository)
  - Normalize URLs (strip trailing slashes, lowercase domains)

**Step 2: Apply Heuristic 1 (Shared Documentation URL)**
- Group packages with **identical** full documentation URLs
- **Strict matching:** URLs must match exactly (including paths)
  - `docs.langchain.com/integrations/openai` ≠ `docs.langchain.com/` → NOT grouped
  - `tanstack.com/query/` ≠ `tanstack.com/router/` → NOT grouped (correct: separate docs)
- **Minimum specificity requirement:** URL must include:
  - Subdomain (e.g., `docs.langchain.com`), OR
  - Path component (e.g., `example.com/docs/project`)
  - **Domain-only URLs are rejected** (e.g., `readthedocs.io` without subdomain)
- **Design rationale:** Prefer false negatives (missed grouping) over false positives (wrong merging)
  - Missed grouping → duplicate sources (minor issue, fixed by Heuristic 2 or manual overrides)
  - Wrong merging → agent gets incorrect documentation (severe issue)
- Example: All packages pointing to exact URL `docs.langchain.com` → one source
- Mark all grouped packages as "processed"
- **Result:** Catches ~70% of monorepo sub-packages with correct metadata

**Step 3: Apply Heuristic 2 (Prefix + Repository)**
- Only process packages with no docs URL or invalid docs URL (rejected in Step 2)
- For each unprocessed package P:
  1. Extract base name using delimiter rules:
     - `langchain-openai` → base: `langchain`, suffix: `openai`
     - `pydantic_core` → base: `pydantic`, suffix: `core`
     - Delimiters: hyphen, underscore
  2. Check if base name matches an existing documentation source ID
  3. If match found AND same GitHub organization:
     - Add P to that source's package list
     - Mark P as "processed"
- **Normalization:** Treat hyphens and underscores as equivalent
- **Result:** Catches packages where prefix matches but docs URL is missing/incomplete

**Step 4: Apply Heuristic 3 (Manual Overrides)**
- Load overrides from `registry-overrides.yaml`
- Override types:
  - **Force grouping:** Explicit package lists
    - Example: `["tensorflow", "tensorflow-gpu", "tf-nightly"]` → group all
  - **Force separation:** Prevent automated grouping
    - Example: Keep `pydantic` and `pydantic-ai` separate despite shared org
  - **ID correction:** Fix incorrect package-to-source mappings
- Overrides take precedence over automated heuristics
- **Result:** Handles edge cases and naming irregularities

**Step 5: Validation**
- Each package belongs to exactly ONE documentation source
- Flag ambiguous cases for manual review:
  - Package matched multiple sources in different heuristics
  - Docs URL exists but couldn't be validated
  - Prefix match found but different GitHub org

#### 5.2.2 Edge Case Handling

**Packages pointing to different paths on same domain:**
- `langchain` lists `docs.langchain.com`
- `langchain-openai` lists `docs.langchain.com/integrations/providers/openai`
- **Heuristic 1 does NOT group** (different URLs by design)
- **Heuristic 2 groups them:** Both have prefix `langchain` and same GitHub org `langchain-ai`
- **Result:** Correctly grouped without risk of wrongly merging unrelated products

**Version variants with different names:**
- `tensorflow`, `tf-nightly`, `tensorflow-gpu` don't share a common prefix
- **Solution:** Manual override file explicitly groups them
- Applies to: TensorFlow, PyTorch variants

**Multi-language packages with shared metadata:**
- LangChain Python and JavaScript might both reference parent `docs.langchain.com`
- **Solution:** Treat them as **separate sources** if:
  - They have language-specific subdomains (`python.langchain.com` vs `js.langchain.com`)
  - They list different languages in package classifiers
  - Override file explicitly separates them
- See: Challenge 2 in section 1, Q5 in section 7

**Related-but-separate projects:**
- `pydantic` and `pydantic-ai` share GitHub org but have different docs
- **Solution:** Heuristic 1 keeps them separate (different docs URLs: `docs.pydantic.dev` vs `ai.pydantic.dev`)
- **Safeguard:** Override file can prevent grouping even if heuristics suggest it

**Stale or incorrect PyPI metadata:**
- Docs URL points to 404 or redirects elsewhere
- **Solution:** Weekly validation job checks all URLs
- If URL fails validation, attempt llms.txt discovery (section 5.3)
- Flag for manual review if discovery also fails

**Conflicts between heuristics:**
- Package A and B grouped by H1 (same docs URL)
- Package A and C grouped by H2 (prefix + same repo)
- **Resolution:** Heuristic 1 takes precedence (more authoritative)
- If B and C should be in same source, use override file

#### 5.2.3 Grouping Statistics (Expected)

From top 5,000 PyPI packages:
- **Heuristic 1** (Shared docs URL):
  - ~3,500 packages share docs URLs → grouped into ~2,000 multi-package sources (70% of packages)
  - ~1,000 packages have unique docs URLs → 1,000 single-package sources (20% of packages)
- **Heuristic 2** (Prefix + repo): ~300 packages → added to existing sources (6% of packages)
- **Ungrouped** (no docs URL, no match): ~200 packages → 200 standalone sources (4% of packages)
- **Manual overrides**: ~200 adjustments (~4% of packages)

**Final result:** ~2,000 + 1,000 + 200 = ~3,200 unique documentation sources from 5,000 packages

**Grouping efficiency:** 3,500 packages collapsed into 2,000 sources (43% reduction via grouping)

### 5.3 llms.txt Discovery

For each unique documentation URL in the registry:

**Step 1: Try URL patterns**
- Test 10+ common patterns (see section 4.3)
- Validate each (HTTP 200 + content checks)

**Step 2: Parse and store**
- If valid llms.txt found:
  - Parse for hub structure (extract variant links)
  - Detect platform (mintlify, vitepress, custom, etc.)
  - Store in `llmsTxt` field with validation timestamp

**Step 3: Handle variants**
- If hub detected, store all variant URLs
- Each variant gets: label, URL, type
- Hub entry marked with `isHub: true`

**Platform detection** (from URL patterns):
- Contains "mintlify" → "mintlify"
- Contains "readthedocs.io" → "readthedocs"
- Contains "github.io" → "github-pages"
- Contains "gitbook" → "gitbook"
- Domain ends with ".dev" → "vitepress" (common pattern)
- Otherwise → "custom"

**Registry size estimates:**
- Top 1,000 packages → ~600-700 unique documentation sources
- Top 5,000 packages → ~3,000-3,500 unique sources
- With llms.txt data: adds ~30-40% to file size
- Expected registry size: ~200KB (top 1,000) to ~900KB (top 5,000)

**Maintenance:**
- **Monthly**: Full rebuild against latest top-pypi-packages
- **Weekly**: Re-validate llms.txt URLs (check if stale/dead)
- **On-demand**: Community PRs for additions/corrections

---

## 6. Version Handling

**Version variants** (distribution builds, not versions):

Some packages publish multiple distribution variants:
- `tensorflow`, `tensorflow-gpu`, `tensorflow-cpu`, `tf-nightly`
- `torch`, `torch-nightly`

These are **not separate libraries**. They're build variants sharing the same documentation.

**Registry approach:**
- List all variants in one source's `packages.pypi` array
- Example: `"pypi": ["tensorflow", "tensorflow-gpu", "tensorflow-cpu", "tf-nightly"]`
- When agent queries any variant, they resolve to the same source

**Version-specific documentation:**

Per functional spec section 10, version handling is:
- Explicit version (`version: "0.3.14"`): Use exact version
- Version range (`version: "0.3.x"`): Resolve to latest patch via package manager
- No version: Use latest stable
- Invalid version: Return error with available versions

**URL mapping patterns:**
- Version in path: `docs.pydantic.dev/2.10/llms.txt` (Pydantic)
- "latest" always current: `docs.langchain.com/llms.txt` (LangChain)
- No versioned docs: Single URL for all versions (many smaller libs)

**Registry field:**
- `versionPattern` (optional): Template for constructing version-specific URLs
- Example: `"https://docs.pydantic.dev/{version}/llms.txt"`
- If omitted, use base `docsUrl` or `llmsTxt.url` for all versions

---

## 7. Open Questions

### Q1: Should ephemeral discoveries be persisted?

When runtime discovery (Steps 5-7) finds a library not in the registry, should it:
- **Option A**: Cache in-memory for session only
- **Option B**: Persist to database with TTL (e.g., 7 days)

**Trade-offs:**
- Option A: Simpler, no database writes, but repeated queries re-discover
- Option B: Faster for repeated queries, but requires cleanup logic

**Recommendation:** Option B. If a library is queried once, it's likely to be queried again. Persist with 7-day TTL.

### Q2: How to handle duplicate documentation URLs?

If runtime discovery creates an ephemeral source for `tensorflow-lite` with `docs_url: tensorflow.org`, but registry already has `tensorflow` with same URL, we now have duplicates.

**Options:**
- Check if discovered URL matches existing source before creating ephemeral entry
- Let duplicates exist, deduplicate later during monthly rebuild
- Flag ephemeral entries for manual review

**Recommendation:** Check on creation. If `docsUrl` matches existing source, add package name to existing source instead of creating new one.

### Q3: Registry coverage target?

Should registry include:
- **Conservative**: Top 1,000 packages (fast builds, covers most use cases)
- **Moderate**: Top 5,000 packages (comprehensive for Python)
- **Aggressive**: All packages with llms.txt (~500+, regardless of popularity)

**Recommendation:** Start with top 5,000. Covers all commonly-used libraries. Runtime discovery handles long tail.

### Q4: Should we validate all registry URLs on every build?

Full validation (HTTP checks + content checks) for 5,000 sources takes significant time.

**Options:**
- Full validation on every build (thorough but slow)
- Full validation monthly, spot-checks weekly
- Lazy validation (check on first access)

**Recommendation:** Full validation monthly, incremental checks for recently-changed entries. Weekly re-validation for entries >30 days old.

### Q5: Multi-language registry structure?

Should LangChain Python and LangChain JavaScript be:
- **Option A**: Two separate documentation sources (`langchain-python`, `langchain-js`)
- **Option B**: One source with language-aware URL selection
- **Option C**: Two sources with shared parent ID

**Current approach**: Two separate sources. They have different docs sites, different package names, different documentation content. The `languages` field is informational metadata, not a routing mechanism.

**This aligns with functional spec 10.2:** Language is not a server-side routing concern.

### Q6: How to handle hub variant selection?

When hub detected with multiple variants, should resolution:
- Return hub URL + metadata (let agent choose variant)
- Use context (language from query) to auto-select variant
- Always return hub, agent calls `resolve-library` again with specific variant

**Recommendation:** If context matches exactly one variant (e.g., query contains "python" and hub has python variant), auto-select. Otherwise return hub with variant metadata.

---

**End of Document**
