# Pro-Context: Library Resolution Strategy

> **Document**: 05-library-resolution.md
> **Status**: Draft
> **Last Updated**: 2026-02-17
> **Depends on**: 02-functional-spec.md (v3)
> **Research**: See `docs/research/llms-txt-deployment-patterns.md` and `docs/research/llms-txt-resolution-strategy.md`

---

## Table of Contents

- [1. The Problem](#1-the-problem)
- [2. Core Model: Documentation Sources, Not Packages](#2-core-model-documentation-sources-not-packages)
- [3. Registry Schema](#3-registry-schema)
  - [3.1 Documentation Source Entry](#31-documentation-source-entry)
  - [3.2 llms.txt Support](#32-llmstxt-support)
  - [3.3 Example Entries](#33-example-entries)
- [4. Resolution Algorithm](#4-resolution-algorithm)
  - [4.1 Input Normalization](#41-input-normalization)
  - [4.2 Resolution Steps](#42-resolution-steps)
  - [4.3 Resolution Priority](#43-resolution-priority)
  - [4.4 What `resolve-library` Returns](#44-what-resolve-library-returns)
- [5. Handling Edge Cases](#5-handling-edge-cases)
  - [5.1 Pip Extras](#51-pip-extras)
  - [5.2 Sub-packages in Monorepos](#52-sub-packages-in-monorepos)
  - [5.3 Related but Separate Projects](#53-related-but-separate-projects)
  - [5.4 Multi-Language Libraries](#54-multi-language-libraries)
  - [5.5 GitHub-Only Libraries](#55-github-only-libraries)
  - [5.6 Version Variants](#56-version-variants)
- [6. Building the Registry](#6-building-the-registry)
  - [6.1 Data Sources](#61-data-sources)
  - [6.2 Build Script](#62-build-script)
  - [6.3 Package Grouping Heuristic](#63-package-grouping-heuristic)
  - [6.4 Registry Size Estimates](#64-registry-size-estimates)
  - [6.5 Registry Refresh Cadence](#65-registry-refresh-cadence)
- [7. Runtime Resolution Architecture](#7-runtime-resolution-architecture)
  - [7.1 In-Memory Index](#71-in-memory-index)
  - [7.2 Resolution Flow in Detail](#72-resolution-flow-in-detail)
  - [7.3 Query Normalization Rules](#73-query-normalization-rules)
- [8. Comparison: PyPI vs GitHub as Primary Source](#8-comparison-pypi-vs-github-as-primary-source)
- [9. Open Questions](#9-open-questions)

---

## 1. The Problem

When an agent calls `resolve-library("langchain")` or `get-docs([{libraryId: "langchain"}], "streaming")`, the server must figure out where to find documentation. This is harder than it sounds because:

1. **Packages are not libraries.** `langchain`, `langchain-openai`, `langchain-community`, and `langchain-core` are four separate PyPI packages, but they all share the same documentation site (docs.langchain.com). They should resolve to one documentation source, not four.

2. **Not everything is on PyPI.** Some libraries are GitHub-only (no PyPI package). Some are installed via conda. Some are internal/private.

3. **Extras are not separate libraries.** `langchain[openai]` and `langchain[vertexai]` are pip extras — they install additional dependencies but the core library is the same. They shouldn't create separate entries.

4. **Multi-language libraries exist.** `protobuf`, `grpc`, `tensorflow` exist across Python, JavaScript, Go, etc. Each language variant may have different docs or shared docs.

5. **Ecosystems have sub-projects.** Pydantic has `pydantic` (docs.pydantic.dev) and `pydantic-ai` (ai.pydantic.dev) — related but separate documentation sites.

The current spec hand-waves this with a "known-libraries registry." This document defines how that registry actually works.

---

## 2. Core Model: Documentation Sources, Not Packages

The fundamental unit in Pro-Context's registry is a **Documentation Source** — a place where documentation lives. Packages are secondary; they're pointers to documentation sources.

```
┌──────────────────────────────────────────────────────┐
│                  Documentation Source                  │
│                                                       │
│  id: "langchain"                                      │
│  name: "LangChain"                                    │
│  docsUrl: "https://docs.langchain.com"                │
│  repoUrl: "https://github.com/langchain-ai/langchain" │
│  languages: ["python"]                                │
│                                                       │
│  packages:                                            │
│    pypi: ["langchain", "langchain-openai",            │
│           "langchain-community", "langchain-core",    │
│           "langchain-text-splitters"]                  │
│                                                       │
│  aliases: ["lang-chain", "lang chain"]                │
│                                                       │
└──────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────┐
│                  Documentation Source                  │
│                                                       │
│  id: "langgraph"                                      │
│  name: "LangGraph"                                    │
│  docsUrl: "https://langchain-ai.github.io/langgraph"  │
│  repoUrl: "https://github.com/langchain-ai/langgraph" │
│  languages: ["python"]                                │
│                                                       │
│  packages:                                            │
│    pypi: ["langgraph", "langgraph-sdk",               │
│           "langgraph-checkpoint"]                      │
│                                                       │
└──────────────────────────────────────────────────────┘
```

**Key insight**: When the agent queries "langchain-openai", the server resolves it to the "langchain" documentation source. The agent gets LangChain's full TOC — not a separate "langchain-openai" documentation site, because one doesn't exist.

---

## 3. Registry Schema

### 3.1 Documentation Source Entry

A Documentation Source entry contains the following fields:

**Core Fields:**

- `id` (string, required): Unique identifier (human-readable, stable)
- `name` (string, required): Display name
- `docsUrl` (string or null): Documentation site URL (server tries {docsUrl}/llms.txt)
- `repoUrl` (string or null): Primary GitHub repository
- `languages` (list of strings): Languages this library supports

**Package Mappings:**

- `packages` (object): Package registry mappings — multiple packages can map to one source
  - `pypi` (list of strings, optional): PyPI package names
  - `npm` (list of strings, optional): npm package names (future)
  - `crates` (list of strings, optional): crates.io names (future)

**Matching Fields:**

- `aliases` (list of strings): Alternative names/spellings for fuzzy matching

**llms.txt Support:**

- `llmsTxtUrl` (string, required): URL to llms.txt file
  - **Builder guarantee**: Every entry in the registry has a valid llms.txt URL
  - **Sources**: Native llms.txt (library-published) or generated llms.txt (builder-created from GitHub)
  - **Hosting**: Native files served from original domains, generated files served from GitHub Pages
  - **Note**: Metadata like platform and validation timestamp are tracked by builder but not included in runtime registry (simplifies MCP server)

### 3.2 llms.txt Support

**What is llms.txt?** A proposed standard file (`/llms.txt`) that libraries publish at their documentation root to provide AI-optimized content. Research shows 60% adoption among surveyed libraries, with 100% adoption in AI/ML category.

**Why prioritize llms.txt?**

1. **AI-optimized content**: Designed specifically for LLM consumption
2. **Fast resolution**: Direct URL, no HTML parsing needed
3. **Structured format**: Markdown with clear sections and links
4. **Growing adoption**: Mintlify auto-generates for all hosted docs (1000+ sites)

**Discovery strategy**: Pro-Context uses a registry-first approach with fallback URL pattern testing (see `docs/research/llms-txt-resolution-strategy.md`).

**Hub files as build-time discovery aids**: Some documentation sites (Svelte, Supabase) publish a "hub" llms.txt at their root that links to multiple per-product or per-language llms.txt files. These hubs are useful during registry construction — the build script follows the links to discover individual llms.txt files and creates a separate DocSource for each one. Hubs do not exist in the runtime data model. Each individual llms.txt file found via a hub becomes its own DocSource.

**Content validation**: Not all URLs that return HTTP 200 serve valid llms.txt content. Some return HTML error pages. Pro-Context validates:

- Content-Type header (should be text/plain or text/markdown, not HTML)
- First 1KB doesn't contain HTML tags (`<!DOCTYPE`, `<html`, etc.)
- Starts with markdown header (`#`)

**URL patterns**: Based on research of 70+ libraries, common patterns include:

- `docs.{library}.com/llms.txt` (30% of cases)
- `{library}.dev/llms.txt` (popular with JS frameworks)
- `{library}.com/llms.txt` (25% of cases)
- `{library}.io/llms.txt` (15% of cases)
- `{library}.com/docs/llms.txt` (OpenAI pattern)
- `docs.{library}.com/en/llms.txt` (Anthropic pattern)

**Note on multi-product sites**: Some documentation sites host llms.txt files for multiple products under one domain (e.g., `svelte.dev/docs/svelte/llms.txt` and `svelte.dev/docs/kit/llms.txt`). Each distinct llms.txt file becomes its own DocSource. The shared domain is not a grouping signal — the individual llms.txt file is the unit of identity.

### 3.3 Example Entries

```json
[
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
    "aliases": ["lang-chain", "lang chain"],
    "llmsTxtUrl": "https://python.langchain.com/llms.txt"
  },
  {
    "id": "requests",
    "name": "Requests",
    "docsUrl": "https://requests.readthedocs.io",
    "repoUrl": "https://github.com/psf/requests",
    "languages": ["python"],
    "packages": {
      "pypi": ["requests"]
    },
    "aliases": [],
    "llmsTxtUrl": "https://pro-context.github.io/llms-txt/requests.txt"
  },
  {
    "id": "pydantic",
    "name": "Pydantic",
    "docsUrl": "https://docs.pydantic.dev/latest",
    "repoUrl": "https://github.com/pydantic/pydantic",
    "languages": ["python"],
    "packages": {
      "pypi": [
        "pydantic",
        "pydantic-core",
        "pydantic-settings",
        "pydantic-extra-types"
      ]
    },
    "aliases": [],
    "llmsTxtUrl": "https://docs.pydantic.dev/latest/llms.txt"
    "llmsTxt": {
      "url": "https://docs.pydantic.dev/latest/llms.txt",
      "platform": "custom",
      "lastValidated": "2026-02-17"
    }
  },
  {
    "id": "pydantic-ai",
    "name": "Pydantic AI",
    "docsUrl": "https://ai.pydantic.dev",
    "repoUrl": "https://github.com/pydantic/pydantic-ai",
    "languages": ["python"],
    "packages": {
      "pypi": ["pydantic-ai", "pydantic-ai-slim"]
    },
    "aliases": ["pydanticai"]
  },
  {
    "id": "fastapi",
    "name": "FastAPI",
    "docsUrl": "https://fastapi.tiangolo.com",
    "repoUrl": "https://github.com/tiangolo/fastapi",
    "languages": ["python"],
    "packages": {
      "pypi": ["fastapi"]
    },
    "aliases": ["fast-api", "fast api"]
  },
  {
    "id": "tensorflow",
    "name": "TensorFlow",
    "docsUrl": "https://www.tensorflow.org",
    "languages": ["python", "javascript"],
    "packages": {
      "pypi": ["tensorflow", "tensorflow-gpu", "tensorflow-cpu", "tf-nightly"],
      "npm": ["@tensorflow/tfjs"]
    },
    "aliases": ["tf"]
  },
  {
    "id": "supabase-python",
    "name": "Supabase Python SDK",
    "docsUrl": "https://supabase.com",
    "repoUrl": "https://github.com/supabase/supabase-py",
    "languages": ["python"],
    "packages": {
      "pypi": ["supabase"]
    },
    "aliases": ["supabase"],
    "llmsTxt": {
      "url": "https://supabase.com/llms/python.txt",
      "platform": "custom",
      "lastValidated": "2026-02-17"
    }
  },
  {
    "id": "supabase-js",
    "name": "Supabase JavaScript SDK",
    "docsUrl": "https://supabase.com",
    "repoUrl": "https://github.com/supabase/supabase-js",
    "languages": ["javascript"],
    "packages": {
      "npm": ["@supabase/supabase-js"]
    },
    "aliases": ["supabase"],
    "llmsTxt": {
      "url": "https://supabase.com/llms/js.txt",
      "platform": "custom",
      "lastValidated": "2026-02-17"
    }
  },
  {
    "id": "svelte",
    "name": "Svelte",
    "docsUrl": "https://svelte.dev",
    "repoUrl": "https://github.com/sveltejs/svelte",
    "languages": ["javascript"],
    "packages": {
      "npm": ["svelte"]
    },
    "aliases": [],
    "llmsTxt": {
      "url": "https://svelte.dev/docs/svelte/llms.txt",
      "platform": "custom",
      "lastValidated": "2026-02-17"
    }
  },
  {
    "id": "sveltekit",
    "name": "SvelteKit",
    "docsUrl": "https://svelte.dev",
    "repoUrl": "https://github.com/sveltejs/kit",
    "languages": ["javascript"],
    "packages": {
      "npm": ["@sveltejs/kit"]
    },
    "aliases": ["svelte-kit"],
    "llmsTxt": {
      "url": "https://svelte.dev/docs/kit/llms.txt",
      "platform": "custom",
      "lastValidated": "2026-02-17"
    }
  },
  {
    "id": "transformers",
    "name": "Transformers",
    "docsUrl": "https://huggingface.co/docs/transformers",
    "repoUrl": "https://github.com/huggingface/transformers",
    "languages": ["python"],
    "packages": {
      "pypi": ["transformers"]
    },
    "aliases": ["huggingface-transformers", "hf-transformers"],
    "llmsTxt": {
      "url": "https://huggingface.co/docs/transformers/llms.txt",
      "platform": "custom",
      "lastValidated": "2026-02-17"
    }
  }
]
```

---

## 4. Resolution Algorithm

### 4.1 Input Normalization

Before matching, normalize the input:

```
Input: "langchain[openai]"
  1. Strip pip extras: "langchain[openai]" → "langchain"
  2. Strip version specifiers: "langchain>=0.3" → "langchain"
  3. Lowercase: "LangChain" → "langchain"
  4. Strip whitespace: " langchain " → "langchain"

Input: "langchain-openai"
  → No stripping (this is a real package name, not an extra)
  → Lowercase: "langchain-openai"
```

### 4.2 Resolution Steps (Runtime)

**Runtime resolution searches ONLY the curated registry.** No network calls. No PyPI API. No llms.txt probing. Fast, reliable, offline-capable.

```
resolve-library(query: "langchain-openai", language?: "python")
  │
  ├─ Step 0: Parse and normalize query
  │    Extract: name, language from query
  │    Example: "langchain python" → {name: "langchain", language: "python"}
  │    Normalize: strip pip extras, version specs, lowercase
  │    "langchain[openai]>=0.3" → "langchain"
  │
  ├─ Step 1: Exact package match in registry
  │    Search packages.pypi across all DocSource entries
  │    "langchain-openai" found in DocSource "langchain"
  │    → MATCH: return DocSource "langchain"
  │    (The DocSource already contains llmsTxtUrl)
  │
  ├─ Step 2: Exact ID match (if step 1 fails)
  │    Search DocSource.id
  │    → No match for "langchain-openai"
  │
  ├─ Step 3: Alias match (if step 2 fails)
  │    Search DocSource.aliases
  │    → No match
  │
  ├─ Step 4: Fuzzy match (if step 3 fails)
  │    Levenshtein distance against all IDs, names, package names, aliases
  │    Max edit distance: 3
  │    Return all matches ranked by relevance score
  │    → Might match "langchain" with typo corrections
  │
  └─ Step 5: No match
       If no matches found in Steps 1-4: return empty results
       User gets: "Library not found in registry"
```

**If library not found**, user has two options:

1. **Wait for next registry update** (weekly automatic rebuild)
2. **Add via custom sources config** (immediate):
   ```yaml
   sources:
     custom:
       - name: "my-new-lib"
         library_id: "author/my-new-lib"
         type: "url"
         url: "https://docs.mynewlib.com/llms.txt"
   ```

See Section 6 (Building the Registry) for how libraries are discovered and added to the registry at build-time.

### 4.3 Resolution Priority

| Step | Source                    | Speed  | Coverage               | When Used                       |
| ---- | ------------------------- | ------ | ---------------------- | ------------------------------- |
| 0    | Query parsing             | <1ms   | All queries            | Extract context (language)      |
| 1    | Package exact match       | <1ms   | Registry packages only | Direct package name lookup      |
| 2    | DocSource ID exact match  | <1ms   | Registry libraries only | Agent uses known library IDs    |
| 3    | Alias match               | <1ms   | Registry libraries only | Typos, alternative names        |
| 4    | Fuzzy match (Levenshtein) | <10ms  | Registry libraries only | Misspellings (edit distance ≤3) |
| 5    | No match                  | <1ms   | —                      | Return empty results            |

**Key insights:**

- All steps are in-memory, fast (<10ms total)
- No network calls during resolution
- Registry quality directly determines coverage
- Unknown libraries require custom sources config or registry update

**Performance characteristics:**

- 95%+ queries resolve in <10ms (registry hit)
- 5% queries return "not found" (registry miss)
- Offline-capable: no external dependencies

### 4.4 What `resolve-library` Returns

`resolve-library` returns **DocSource** matches, not package matches. If "langchain-openai" resolves to the "langchain" DocSource, the response is:

```json
{
  "results": [
    {
      "libraryId": "langchain",
      "name": "LangChain",
      "description": "Build context-aware reasoning applications",
      "languages": ["python"],
      "relevance": 1.0,
      "matchedVia": "package:langchain-openai"
    }
  ]
}
```

The `matchedVia` field tells the agent how the match was found — useful for transparency.

---

## 5. Handling Edge Cases

### 5.1 Pip Extras

```
Input: "langchain[openai]"
Normalization: strip extras → "langchain"
Resolution: exact package match → DocSource "langchain"
```

The extras syntax (`[openai]`, `[vertexai]`, etc.) is stripped during normalization. The base package name is what gets resolved. This is correct because extras don't change which documentation site to use.

### 5.2 Sub-packages in Monorepos

LangChain's monorepo publishes multiple PyPI packages:

- `langchain` (main)
- `langchain-openai` (OpenAI integration)
- `langchain-anthropic` (Anthropic integration)
- `langchain-community` (community integrations)
- `langchain-core` (core abstractions)

All map to the same DocSource. The package-to-source mapping handles this — all five package names point to DocSource "langchain".

If the agent is specifically interested in the OpenAI integration docs, the TOC sections (from get-library-info) or search (from search-docs/get-docs) will surface the relevant pages.

### 5.3 Related but Separate Projects

Pydantic and Pydantic AI are related but have separate documentation sites:

- `pydantic` → docs.pydantic.dev
- `pydantic-ai` → ai.pydantic.dev

These are separate DocSource entries. The package-to-source mapping distinguishes them:

- PyPI package `pydantic` → DocSource "pydantic"
- PyPI package `pydantic-ai` → DocSource "pydantic-ai"

### 5.4 Multi-Language Libraries

Protocol Buffers exists in Python, JS, Go, Java, C++. How should we handle this?

**Approach: Language is not the server's problem — just use URLs.**

A single DocSource represents a single documentation site. The `languages` field is purely **informational metadata** — it tells the agent what languages the library supports, but the server does not validate, enforce, or route based on it.

- **Unified docs sites** (protobuf.dev, grpc.io): One DocSource, one URL. The TOC returned by `get-library-info` will contain language-specific sections (e.g., `/reference/python/`, `/reference/go/`). The agent — which knows what language it's working in — picks the relevant pages. This is consistent with Pro-Context's core architectural thesis: query understanding and navigation decisions belong to the agent's LLM, not the server.

- **Separate docs sites** (tensorflow.org for Python vs js.tensorflow.org for JS): These are naturally separate DocSources — not because of language, but because they are different documentation sites with different URLs. No special handling required.

This means:

- No `language` parameter on `get-library-info`, `get-docs`, or `search-docs`
- No `LANGUAGE_REQUIRED` error code
- No language in cache keys or session tracking
- `language` remains as an optional filter on `resolve-library` only, to narrow discovery results (e.g., agent can filter for DocSources that list `"python"` in their `languages` array)

**Why not per-language DocSources?** Splitting protobuf into `protobuf-python`, `protobuf-go`, etc. creates artificial entries that all point to the same docs site, would have overlapping TOCs (language-neutral content like the proto3 spec appears in all of them), and would produce duplicate search results.

**Why not require language as a parameter?** It adds a required parameter, a new error code, language-aware cache keys, and branching logic in every tool — all to solve a problem the agent already handles naturally by reading the TOC. Most libraries are single-language, so this machinery would almost never activate.

### 5.5 GitHub-Only Libraries

For libraries without a PyPI package:

- Add them manually via custom sources config:
  ```yaml
  sources:
    custom:
      - name: "some-lib"
        library_id: "some-org/some-lib"
        type: "github"
        url: "https://github.com/some-org/some-lib"
  ```
- Or submit a PR to add them to the registry via the manual overrides file
- The build script can discover llms.txt from GitHub repos just like PyPI packages

### 5.6 Distribution Variants

Some libraries publish separate PyPI packages for different release channels or build configurations:

| Stable package | Variant packages                                 | Relationship             |
| -------------- | ------------------------------------------------ | ------------------------ |
| `tensorflow`   | `tf-nightly`, `tensorflow-gpu`, `tensorflow-cpu` | Nightly / build variants |
| `torch`        | `torch-nightly`                                  | Nightly build            |

These are **not** separate libraries — they're distribution variants of the same project and share the same documentation. The registry handles this by listing all variants under a single DocSource's `packages.pypi` array:

```json
{
  "id": "tensorflow",
  "packages": {
    "pypi": ["tensorflow", "tensorflow-gpu", "tensorflow-cpu", "tf-nightly"]
  }
}
```

When an agent calls `resolve-library("tf-nightly")`, step 1 (exact package match) finds `"tf-nightly"` in the TensorFlow DocSource and returns it immediately. The agent never needs to know these are separate PyPI packages. Pro-Context always serves the latest available documentation regardless of which variant package was resolved.

---

## 6. Building the Registry

### 6.1 Data Sources

The registry is built from multiple sources, combined and deduplicated:

```
┌──────────────────────┐
│  Curated Registries  │  100-200 libraries with validated llms.txt
│  (seed data)         │  Sources: llms-txt-hub, Awesome-llms-txt
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  top-pypi-packages   │  15,000 packages ranked by downloads
│  (monthly snapshot)  │  Source: hugovk/top-pypi-packages
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  PyPI JSON API       │  Metadata per package: name, summary,
│  (per-package)       │  project_urls (Documentation, Source)
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  llms.txt probe      │  Try common URL patterns, validate content
│  (per docs URL)      │  HEAD + content check → exists & valid?
│                      │  Parse hub structure if detected
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Manual curation     │  Package grouping (langchain ecosystem),
│  (human review)      │  aliases, version patterns, corrections
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  known-libraries.json│  Final registry file shipped with
│  (output)            │  Pro-Context
└──────────────────────┘
```

**Curated Registries (Seed Data)**

Two community-maintained GitHub repositories provide a quick-start list of libraries with validated llms.txt files:

1. **llms-txt-hub** (`github.com/thedaviddias/llms-txt-hub`)
   - Largest community-maintained directory (100+ entries as of February 2026)
   - Organized by category: AI/ML, Developer Tools, Data & Analytics, Infrastructure, etc.
   - Regularly updated by community contributors
   - Provides immediate high-quality seed data for the registry

2. **Awesome-llms-txt** (`github.com/SecretiveShell/Awesome-llms-txt`)
   - Community-curated index of llms.txt files across the web
   - Good supplementary source for additional entries

These registries give Pro-Context a "quick win" — 100-200 validated entries immediately, covering major AI/ML libraries (LangChain, Anthropic, Pydantic AI, OpenAI) and popular developer tools. The build script starts with these, then enriches with PyPI data for broader coverage.

### 6.2 Build Script

A build script (not part of the runtime server) generates the registry. This is the ONLY place where PyPI API calls, llms.txt probing, and content validation happen.

```python
# scripts/build_registry.py

1. Fetch curated registries (seed data):
   a. Clone llms-txt-hub (github.com/thedaviddias/llms-txt-hub)
   b. Clone Awesome-llms-txt (github.com/SecretiveShell/Awesome-llms-txt)
   c. Parse entries: extract library name, docs URL, llms.txt URL
   d. Validate each llms.txt URL (HEAD request + content check)
   e. Create initial DocSource entries from validated entries

2. Fetch top-pypi-packages (community: top 1,000; enterprise: top 5,000)
   Source: hugovk/top-pypi-packages monthly snapshot

3. For each package:
   a. GET https://pypi.org/pypi/{name}/json
   b. Extract: name, summary, project_urls
   c. Determine docsUrl from project_urls.Documentation
   d. Determine repoUrl from project_urls.Source or project_urls.Repository
   e. Store package metadata for grouping step

4. Group packages by Repository URL (see section 6.3):
   Primary signal: same Repository URL → same DocSource
   Fallback signal: same Homepage URL (if no Repository URL)
   Example: langchain, langchain-openai, langchain-core all have
     Repository → github.com/langchain-ai/langchain → grouped into one DocSource

5. For each unique DocSource, discover llms.txt:
   a. Try docsUrl-relative patterns:
      1. {docsUrl}/llms.txt           (direct — works for LangChain)
      2. {docsUrl}/en/llms.txt        (locale prefix — works for Anthropic)
      3. {docsUrl}/latest/llms.txt    (version prefix — works for Pydantic)
      4. {domainRoot}/llms.txt        (if docsUrl has a path, try root)

   b. For each pattern, validate content (see section 6.2.1 below):
      - HTTP Status: HEAD request must return 200
      - Content-Type: Must be text/plain or text/markdown (not HTML)
      - First 1KB: Must not contain HTML tags (<!DOCTYPE, <html>, etc.)
      - First line: Must start with # (markdown header)

   c. If valid llms.txt found:
      - Check if it's a hub file (contains links to other llms.txt files)
      - If hub: follow links, validate each one, create separate DocSource per variant
      - If regular llms.txt: store URL in DocSource.llmsTxt
      - Extract platform hint (mintlify, vitepress, custom) from URL structure

   d. If no llms.txt found via docsUrl:
      - If repoUrl exists, try github.com/{owner}/{repo}/docs/ directory
      - Try llms.txt patterns on repoUrl

6. Apply manual overrides from overrides.yaml:
   - Force-group packages that automated rule missed
   - Force-separate packages that were incorrectly grouped
   - Add aliases for common misspellings/variations
   - Correct stale/wrong docsUrl from PyPI metadata
   - Add non-PyPI libraries (GitHub-only, private docs)
   - Merge with curated registry entries from step 1

7. Validate and output known-libraries.json:
   - Deduplicate DocSource IDs
   - Sort by popularity (download rank)
   - Validate all URLs are accessible
   - Generate SHA-256 hash for cache invalidation
```

#### 6.2.1 Content Validation (Build-time)

Many URLs return HTTP 200 but serve HTML error pages instead of llms.txt. The build script validates content before accepting a URL:

```python
async def validate_llms_txt(url: str) -> bool:
    """Validate that URL serves a real llms.txt file, not an error page"""

    # Step 1: HEAD request
    response = await http_client.head(url, follow_redirects=True)
    if response.status_code != 200:
        return False

    # Step 2: Content-Type check
    content_type = response.headers.get("Content-Type", "")
    if "html" in content_type.lower():
        return False  # Reject HTML responses

    # Step 3: Fetch first 1KB
    response = await http_client.get(url, headers={"Range": "bytes=0-1023"})
    content = response.text

    # Step 4: HTML detection
    html_indicators = ["<!DOCTYPE", "<html", "<head>", "<body>", "<HTML"]
    if any(indicator in content for indicator in html_indicators):
        return False

    # Step 5: Markdown header check
    if not content.strip().startswith("#"):
        return False

    return True
```

**Hub detection and resolution**: If the llms.txt file contains multiple links to other llms.txt files (e.g., `https://svelte.dev/docs/svelte/llms.txt`, `https://svelte.dev/docs/kit/llms.txt`), the build script:

1. Recognizes this as a hub
2. Follows each link
3. Validates each linked llms.txt
4. Creates a separate DocSource for each valid variant
5. Does NOT store the hub file itself in the registry

### 6.3 Package Grouping Rule

How do we know that `langchain-openai` belongs with `langchain`?

**The rule is simple: same GitHub repository URL = same DocSource.**

The build script extracts the Repository URL (or Source URL, or Homepage if it's a GitHub URL) from each package's PyPI metadata. Packages sharing the exact same Repository URL are grouped into one DocSource.

| Signal                 | Used for grouping? | Why                                                                                                                                                       |
| ---------------------- | ------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Same Repository URL    | **Yes (primary)**  | Monorepo sub-packages share a repo. Verified against LangChain, Pydantic, HuggingFace, TensorFlow ecosystems.                                             |
| Same Homepage URL      | **Yes (fallback)** | Only when Repository URL is missing. Catches packages like tensorflow/tensorflow-gpu/tf-nightly that have no repo but share `tensorflow.org` as Homepage. |
| Same Documentation URL | No                 | Every sub-package has a unique Documentation URL pointing to its specific page. Not useful for grouping.                                                  |
| Same GitHub org        | No                 | Too loose. HuggingFace packages share the `huggingface` org but are separate products with separate repos.                                                |
| Same domain            | No                 | Too loose. Multiple unrelated products can share a domain (e.g., `huggingface.co/docs/transformers/` vs `huggingface.co/docs/diffusers/`).                |

**Manual override.** For cases the automated rule misses, a manual override file specifies explicit groupings or separations.

### 6.4 Registry Size Estimates

| Filter                 | Packages | Unique DocSources | With llms.txt      | Registry File Size |
| ---------------------- | -------- | ----------------- | ------------------ | ------------------ |
| Top 1,000 by downloads | 1,000    | ~600-700          | ~400-500 (80%)     | ~150KB             |
| Top 5,000 by downloads | 5,000    | ~3,000-3,500      | ~2,000-2,500 (70%) | ~700KB             |

**Notes:**

- The package-to-source deduplication is significant — top 1,000 packages collapse to ~600-700 unique documentation sources because monorepo sub-packages share a Repository URL
- Expected llms.txt adoption: 80% of top 1,000, 70% of top 5,000 (based on research showing 60% overall, 100% for AI/ML, 90% for dev platforms)

### 6.5 Registry Refresh Cadence

- **Monthly**: Re-run build script against latest top-pypi-packages
  - Discover new packages that crossed popularity threshold
  - Re-probe all docsUrls for llms.txt (detect new adoptions)
  - Follow hub links to discover new per-product llms.txt files
  - Re-validate existing llms.txt URLs (detect moved/broken links)

- **Weekly** (automated, lightweight):
  - Re-validate llms.txt URLs that are >30 days old
  - Mark stale entries (HTTP 404/500)
  - Attempt rediscovery for stale entries (try new URL patterns)
  - Check curated lists (llms-txt-hub) for manual additions

- **On PR**: Community can submit PRs to add/correct entries in an overrides file
  - Add missing libraries (especially non-PyPI)
  - Correct package groupings
  - Add aliases and version patterns
  - Report broken llms.txt URLs

- **CI validation**: Build script runs in CI to verify the registry is valid
  - All URLs resolve (docsUrl, repoUrl, llms.txt URLs)
  - No duplicate DocSource IDs
  - llms.txt content validation passes
  - No stale llms.txt URLs

---

## 7. Runtime Resolution Architecture

### 7.1 In-Memory Index

At startup, the server loads `known-libraries.json` into memory and builds three lookup indexes:

**Index 1: DocSource by ID**

- Key: DocSource ID (string)
- Value: Complete DocSource entry
- Purpose: Fast lookup by known library ID

**Index 2: Package name to DocSource ID**

- Key: Package name (string)
- Value: DocSource ID (string)
- Purpose: Many-to-one mapping (multiple packages → one DocSource)

**Index 3: Fuzzy search corpus**

- List of searchable terms with their source IDs
- Includes: IDs, names, package names, aliases (all lowercased)
- Purpose: Fuzzy matching for typos/misspellings

### 7.2 Resolution Flow in Detail

**Input:** Query string (e.g., "langchain[openai]>=0.3") and optional language filter

**Normalization:**

- Strip pip extras: `"langchain[openai]"` → `"langchain"`
- Strip version specifiers: `"langchain>=0.3"` → `"langchain"`
- Lowercase: `"LangChain"` → `"langchain"`
- Trim whitespace: `" langchain "` → `"langchain"`

**Resolution Steps:**

**Step 1: Exact package match**

- Look up normalized query in package-to-ID index
- If found, retrieve DocSource by ID
- Return DocSource with all metadata (including llmsTxtUrl)
- If not found, continue to Step 2

**Step 2: Exact ID match**

- Look up normalized query in DocSource-by-ID index
- If found, return DocSource
- If not found, continue to Step 3

**Step 3: Alias match**

- Look up normalized query in alias index
- If found, retrieve DocSource by mapped ID
- Return DocSource
- If not found, continue to Step 4

**Step 4: Fuzzy match**

- Search normalized query against fuzzy corpus (all IDs, names, packages, aliases)
- Use Levenshtein distance algorithm (max edit distance: 3)
- If matches found with acceptable distance:
  - Rank by relevance score (lower distance = higher relevance)
  - Return all matching DocSources with relevance scores
- If not found, continue to Step 5

**Step 5: No match**

- Return empty result with suggestion to add via custom sources config

### 7.3 Query Normalization Rules

```
1. Strip pip extras:       "package[extra]" → "package"
2. Strip version specs:    "package>=1.0"   → "package"
                           "package==1.0.0" → "package"
                           "package~=1.0"   → "package"
3. Lowercase:              "FastAPI"        → "fastapi"
4. Trim whitespace:        " package "      → "package"
5. Normalize separators:   "lang chain"     → match against aliases
                           "lang-chain"     → match against aliases
6. Keep hyphens/underscores as-is for exact matching:
                           "langchain-openai" stays "langchain-openai"
                           (PyPI normalizes _ to - but we match both)
```

---

## 8. Comparison: PyPI vs GitHub as Primary Source

| Dimension                    | PyPI                                                                            | GitHub                                                                   |
| ---------------------------- | ------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| **Coverage (Python)**        | ~500K packages. Covers all pip-installable libraries                            | Near-universal for open source. Also has non-Python projects             |
| **Structured metadata**      | Yes: name, summary, project_urls, version list, classifiers                     | Limited: description, homepage, topics. No package-level metadata        |
| **Documentation URL**        | Often in `project_urls.Documentation` — but not always set, sometimes stale     | Homepage field — may or may not be docs. Often points to the repo itself |
| **Download/popularity data** | Via BigQuery or top-pypi-packages dataset. Well-established                     | Stars, forks. Less reliable as popularity metric                         |
| **Package grouping**         | Shared Repository URL is the primary grouping signal. Homepage URL as fallback. | Monorepos are visible but sub-packages aren't distinct                   |
| **Multi-language**           | Python only                                                                     | All languages                                                            |
| **Non-public libraries**     | Not on PyPI                                                                     | May be on GitHub Enterprise, or not on GitHub at all                     |
| **Rate limits**              | No auth needed for JSON API. No rate limit documented                           | 60 req/hr unauthenticated, 5,000 with PAT                                |

**Recommendation: PyPI is the primary source for the build script.** It has structured metadata, a reliable popularity ranking (via top-pypi-packages), and the `project_urls` field often points to documentation. GitHub can be used as a secondary source during build-time discovery for libraries that aren't on PyPI.

The build script uses PyPI for discovery and enrichment. The runtime server uses only the pre-built registry for resolution — no network calls, no fallbacks to external APIs.

---

## 9. Open Questions

### Q1: Should the registry include packages below a popularity threshold?

The top-pypi-packages dataset has 15,000 packages. Should we include all of them, or filter?

**Lean**: Start with top 5,000 (>572K monthly downloads). This covers every library a typical developer encounters. Unknown libraries can be added via custom sources config or the next registry update. We can expand the registry size later based on user feedback.

### Q2: How do we handle the agent passing a requirements.txt dump?

An agent might call `resolve-library` with each line from a requirements.txt. Some of those will be transitive dependencies (e.g., `certifi`, `urllib3`) that the developer never directly uses and doesn't need docs for.

**Lean**: Not our problem. The agent decides what to resolve. If it's smart, it resolves direct dependencies only. Pro-Context resolves whatever it's asked to resolve.

### Q3: Should llms.txt take absolute priority over docsUrl?

If a DocSource has both `docsUrl` and `llmsTxtUrl`, should llms.txt always be used first, or should we fall back to GitHub/HTML scraping if llms.txt content seems incomplete?

**Lean**: llms.txt takes absolute priority. Builder guarantees every entry has a valid llmsTxtUrl (either native or generated). MCP server doesn't need fallback logic—all documentation is pre-normalized by builder. If content is incomplete, that's a builder issue to fix in the next weekly build, not a runtime concern.

### Q4: How do we handle llms.txt URL migrations?

A library might move their llms.txt from `library.com/llms.txt` to `docs.library.com/llms.txt`. Should we:

- Keep old URL and periodically re-check for 301 redirects
- Try rediscovery when validation fails
- Require manual registry updates

**Lean**: Combine approaches:

- Follow 301/302 redirects automatically during validation
- If old URL returns 404, trigger rediscovery (try all patterns)
- If rediscovery succeeds, update registry entry
- If rediscovery fails, mark as stale and notify for manual review
