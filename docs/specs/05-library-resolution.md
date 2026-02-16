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
  - [4.3 llms.txt Resolution Details](#43-llmstxt-resolution-details)
  - [4.4 Resolution Priority](#44-resolution-priority)
  - [4.5 What `resolve-library` Returns](#45-what-resolve-library-returns)
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
- `versionPattern` (string, optional): How to construct versioned docs URLs
  - Example: `"https://docs.pydantic.dev/{version}/llms.txt"`

**llms.txt Support:**
- `llmsTxt` (object, optional): Present if library has llms.txt file
  - `url` (string, required): Main llms.txt URL (validated)
  - `fullUrl` (string, optional): Full content variant URL (llms-full.txt if exists)
  - `isHub` (boolean, required): Whether this is a hub file (links to multiple variants)
  - `variants` (list, optional): Variant URLs if this is a hub
    - Each variant has: `label` (string), `url` (string), `type` (string: language/version/package/size)
  - `platform` (string, optional): Documentation platform (mintlify, vitepress, custom, etc.)
  - `lastValidated` (string, required): Last validation timestamp (ISO format)

### 3.2 llms.txt Support

**What is llms.txt?** A proposed standard file (`/llms.txt`) that libraries publish at their documentation root to provide AI-optimized content. Research shows 60% adoption among surveyed libraries, with 100% adoption in AI/ML category.

**Why prioritize llms.txt?**
1. **AI-optimized content**: Designed specifically for LLM consumption
2. **Fast resolution**: Direct URL, no HTML parsing needed
3. **Structured format**: Markdown with clear sections and links
4. **Growing adoption**: Mintlify auto-generates for all hosted docs (1000+ sites)

**Discovery strategy**: Pro-Context uses a registry-first approach with fallback URL pattern testing (see `docs/research/llms-txt-resolution-strategy.md`).

**Hub-and-spoke pattern**: Some libraries (Svelte, Supabase, TanStack) provide a main llms.txt file that links to multiple variants (by language, version, package, or size). The registry detects these hubs and stores variant information.

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

**Variants**:
- **Language**: `python.langchain.com/llms.txt` vs `js.langchain.com/llms.txt`
- **Version**: `nextjs.org/docs/15/llms.txt` vs `/docs/14/llms.txt`
- **Package**: `svelte.dev/docs/kit/llms.txt` vs `/docs/svelte/llms.txt`
- **Size**: `svelte.dev/llms-full.txt` vs `/llms-medium.txt` vs `/llms-small.txt`

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
      "pypi": ["langchain", "langchain-openai", "langchain-anthropic", "langchain-community", "langchain-core", "langchain-text-splitters"]
    },
    "aliases": ["lang-chain", "lang chain"],
    "llmsTxt": {
      "url": "https://python.langchain.com/llms.txt",
      "isHub": false,
      "platform": "mintlify",
      "lastValidated": "2026-02-17"
    }
  },
  {
    "id": "langgraph",
    "name": "LangGraph",
    "docsUrl": "https://langchain-ai.github.io/langgraph",
    "repoUrl": "https://github.com/langchain-ai/langgraph",
    "languages": ["python"],
    "packages": {
      "pypi": ["langgraph", "langgraph-sdk", "langgraph-checkpoint", "langgraph-checkpoint-postgres", "langgraph-checkpoint-sqlite"]
    },
    "aliases": ["lang-graph", "lang graph"]
  },
  {
    "id": "pydantic",
    "name": "Pydantic",
    "docsUrl": "https://docs.pydantic.dev/latest",
    "repoUrl": "https://github.com/pydantic/pydantic",
    "languages": ["python"],
    "packages": {
      "pypi": ["pydantic", "pydantic-core", "pydantic-settings", "pydantic-extra-types"]
    },
    "aliases": [],
    "versionPattern": "https://docs.pydantic.dev/{version}/llms.txt",
    "llmsTxt": {
      "url": "https://docs.pydantic.dev/latest/llms.txt",
      "isHub": false,
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
      "pypi": ["fastapi", "fastapi-cli"]
    },
    "aliases": ["fast-api", "fast api"]
  },
  {
    "id": "protobuf",
    "name": "Protocol Buffers",
    "docsUrl": "https://protobuf.dev",
    "repoUrl": "https://github.com/protocolbuffers/protobuf",
    "languages": ["python", "javascript", "go", "java", "cpp"],
    "packages": {
      "pypi": ["protobuf", "grpcio", "grpcio-tools"],
      "npm": ["protobufjs", "@grpc/grpc-js"]
    },
    "aliases": ["protobuf", "protocol buffers", "proto", "grpc"]
  },
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
  },
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
          "label": "Guides",
          "url": "https://supabase.com/llms/guides.txt",
          "type": "package"
        },
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
        },
        {
          "label": "Swift SDK",
          "url": "https://supabase.com/llms/swift.txt",
          "type": "language"
        }
      ],
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

### 4.2 Resolution Steps

```
resolve-library(query: "langchain-openai", language?: "python")
  │
  ├─ Step 0: Parse query context
  │    Extract: name, language, version, variant from query
  │    Example: "nextjs@14" → {name: "nextjs", version: "14"}
  │    Example: "langchain python" → {name: "langchain", language: "python"}
  │    Normalize: strip pip extras, version specs, lowercase
  │    "langchain[openai]>=0.3" → "langchain"
  │
  ├─ Step 1: Registry lookup with llms.txt preference
  │
  │    1a. Exact package match in registry
  │        Search packages.pypi across all DocSource entries
  │        "langchain-openai" found in DocSource "langchain"
  │        → MATCH: DocSource "langchain"
  │
  │    1b. Check if DocSource has llms.txt
  │        If llmsTxt.url exists and validated:
  │          → Select appropriate variant based on context
  │          → Return llms.txt URL as primary source
  │        If no llms.txt:
  │          → Use docsUrl as fallback
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
  │    → Might match "langchain" (distance 7 — too far)
  │    → No useful fuzzy match
  │
  ├─ Step 5: llms.txt URL pattern discovery (if step 4 fails)
  │    Try common llms.txt URL patterns:
  │    - https://docs.{name}.com/llms.txt
  │    - https://{name}.dev/llms.txt
  │    - https://{name}.com/llms.txt
  │    - https://{name}.io/llms.txt
  │    - (+ 6 more patterns, see section 4.3)
  │
  │    For each pattern:
  │      a. Validate URL (HTTP 200 + content validation)
  │      b. If valid: detect hub, create DocSource, cache
  │      c. Return DocSource with llms.txt info
  │
  ├─ Step 6: PyPI discovery (if step 5 fails)
  │    GET https://pypi.org/pypi/{name}/json
  │    → Extract project_urls.Documentation → docsUrl
  │    → Extract project_urls.Source → repoUrl
  │    → Try llms.txt patterns on discovered docsUrl
  │    → Create ephemeral DocSource, cache it
  │
  └─ Step 7: GitHub discovery (if step 6 fails)
       If query looks like "owner/repo", try GitHub API
       GET https://api.github.com/repos/{owner}/{repo}
       → Extract homepage → docsUrl
       → Try llms.txt patterns on discovered homepage
       → Create ephemeral DocSource, cache it
```

### 4.3 llms.txt Resolution Details

**URL Pattern Priority** (based on research of 70+ libraries):

When Step 5 tries llms.txt URL patterns, it tests in this order:

**If language context provided, prepend:**
- `https://{language}.{name}.com/llms.txt` (python.langchain.com)
- `https://{name}.com/llms/{language}.txt` (supabase.com/llms/python.txt)

**If version context provided, prepend:**
- `https://{name}.org/docs/{version}/llms.txt` (nextjs.org/docs/15/llms.txt)
- `https://docs.{name}.com/{version}/llms.txt`

**Standard patterns (ordered by frequency from research):**
- `https://docs.{name}.com/llms.txt` (30% of cases)
- `https://{name}.dev/llms.txt` (Modern frameworks)
- `https://{name}.com/llms.txt` (25% of cases)
- `https://{name}.io/llms.txt` (15% of cases)
- `https://www.{name}.com/llms.txt` (10% of cases)
- `https://docs.{name}.dev/llms.txt` (Pydantic pattern)
- `https://{name}.com/docs/llms.txt` (OpenAI pattern)
- `https://docs.{name}.com/en/llms.txt` (Anthropic pattern)
- `https://docs.{name}.io/llms.txt` (Pinecone pattern)
- `https://{name}.readthedocs.io/llms.txt` (ReadTheDocs - low success rate)

**Content Validation** (critical to avoid HTML error pages):

For each candidate URL, perform validation checks:

1. **HTTP Status Check**
   - Make HEAD request to URL
   - Must return HTTP 200 status
   - If not 200, URL is invalid

2. **Content-Type Header Check**
   - Examine Content-Type response header
   - Should be `text/plain` or `text/markdown`
   - If contains "html", URL is invalid

3. **Content Validation** (first 1KB only)
   - Fetch first 1024 bytes of content
   - Check for HTML indicators:
     - `<!DOCTYPE`
     - `<html>` or `<HTML>`
     - `<head>`
     - `<body>`
   - If any HTML tags found, URL is invalid

4. **Markdown Format Check**
   - Extract first line of content
   - Must start with `#` (markdown header)
   - If not markdown, URL is invalid

Result: URL is valid only if all checks pass

**Hub Detection** (for multi-variant libraries):

When a valid llms.txt is found, check if it's a hub file:

**Hub Detection Algorithm:**

1. **Extract Markdown Links**
   - Parse llms.txt content for markdown link pattern: `[label](url)`
   - Find all links ending with `.txt` extension

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

- **Language variant**: Contains language keywords (python, javascript, typescript, rust, go, etc.)
- **Size variant**: Contains size keywords (full, medium, small, lite)
- **Version variant**: Contains version number pattern (v14, v15, etc.)
- **Package variant**: Default for all others (kit, router, query, cli, etc.)

**Variant Selection** (when hub detected):

When hub file has multiple variants, select best match based on context:

1. **Language Filter** (if language specified in context)
   - Find variant where type is "language"
   - Check if variant label includes requested language
   - If found, return that variant's URL

2. **Version Filter** (if version specified in context)
   - Find variant where type is "version"
   - Check if variant URL includes requested version
   - If found, return that variant's URL

3. **Multiple Variants Remain**
   - If >1 variant after filtering
   - Return hub URL with metadata about available variants
   - Agent can prompt user to select specific variant

4. **Default**
   - Return first variant URL
   - Or return hub URL if no variants selected

### 4.4 Resolution Priority

| Step | Source | Speed | Coverage | When Used |
|------|--------|-------|----------|-----------|
| 0 | Query parsing | <1ms | All queries | Extract context (language, version) |
| 1 | Registry lookup (with llms.txt) | <10ms | 80% (curated) | Always (first check) |
| 2 | DocSource ID exact match | <1ms | Curated libraries only | Agent uses known IDs |
| 3 | Alias match | <1ms | Curated libraries only | Typos, alternative names |
| 4 | Fuzzy match (Levenshtein) | <10ms | Curated libraries only | Misspellings |
| 5 | llms.txt URL pattern testing | 5-10s | 60% of popular libs | Unknown libs with llms.txt |
| 6 | PyPI metadata discovery | ~500ms | Any PyPI package | Unknown Python libraries |
| 7 | GitHub discovery | ~500ms | Any GitHub repo | Non-PyPI libraries |

**Key insights:**
- Steps 0-4 are in-memory, fast (<10ms), depend on registry quality
- Step 5 is network calls but **highly effective** (60% of libs have llms.txt)
- Steps 6-7 are fallbacks for libraries without llms.txt
- **llms.txt prioritization** means 95%+ of popular libraries resolve fast

**Performance optimization:**
- Step 5 can test patterns in parallel (10 patterns in ~5s instead of 50s)
- Discovered llms.txt URLs are cached in registry
- Registry hits (Step 1) serve llms.txt URL immediately (<10ms)

### 4.5 What `resolve-library` Returns

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
- The agent (or user) provides a GitHub URL directly
- `resolve-library("github.com/some-org/some-lib")` → triggers GitHub discovery (Step 6)
- The server creates an ephemeral DocSource from the repo metadata
- Subsequent calls can use the generated `libraryId`

### 5.6 Version Variants

Some libraries publish separate PyPI packages for different release channels or build configurations:

| Stable package | Variant packages | Relationship |
|---|---|---|
| `tensorflow` | `tf-nightly`, `tensorflow-gpu`, `tensorflow-cpu` | Nightly / build variants |
| `torch` | `torch-nightly` | Nightly build |

These are **not** separate libraries — they're distribution variants of the same project and share the same documentation. The registry handles this by listing all variants under a single DocSource's `packages.pypi` array:

```json
{
  "id": "tensorflow",
  "packages": {
    "pypi": ["tensorflow", "tensorflow-gpu", "tensorflow-cpu", "tf-nightly", "keras"]
  }
}
```

When an agent calls `resolve-library("tf-nightly")`, step 1 (exact package match) finds `"tf-nightly"` in the TensorFlow DocSource and returns it immediately. The agent never needs to know these are separate PyPI packages.

**The nightly version problem.** The tricky part is what happens *after* resolution, when the server needs to fetch version-specific docs. A nightly package like `tf-nightly==2.18.0.dev20260215` implies version 2.18 — but that version is unreleased, and its docs likely don't exist yet. For example, TensorFlow publishes versioned docs at `tensorflow.org/api/r2.17`, but there's no `/api/r2.18` until 2.18 is released.

**Fallback behavior:** When a version variant maps to an unreleased docs version, the server should:

1. Attempt to fetch docs for the resolved version (e.g., `r2.18`).
2. If that fails (404), fall back to the **latest stable** version (e.g., `r2.17`).
3. Include a note in the response: `"Note: tf-nightly targets unreleased version 2.18. Serving docs for latest stable release (2.17). Some APIs may differ."`

This is the right trade-off — slightly stale docs are far more useful than no docs at all, and the explicit warning lets the agent (and developer) know to watch for discrepancies.

---

## 6. Building the Registry

### 6.1 Data Sources

The registry is built from multiple sources, combined and deduplicated:

```
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

### 6.2 Build Script

A build script (not part of the runtime server) generates the registry:

```
build-registry.ts

1. Fetch top-pypi-packages (top 5,000 by downloads)

2. For each package:
   a. GET https://pypi.org/pypi/{name}/json
   b. Extract: name, summary, project_urls
   c. Determine docsUrl from project_urls.Documentation or project_urls.Homepage
   d. Determine repoUrl from project_urls.Source or project_urls.Repository

3. Group packages by documentation URL:
   - If two packages share the same docsUrl → same DocSource
   - Example: langchain, langchain-openai, langchain-core all have
     Documentation → docs.langchain.com → grouped into one DocSource

4. For each unique docsUrl, discover llms.txt:
   a. Try common URL patterns (see section 4.3 for full list):
      - {docsUrl}/llms.txt
      - docs.{domain}/llms.txt
      - {domain}/docs/llms.txt
      - (+ 7 more patterns)

   b. For each pattern:
      - HEAD request to check HTTP 200
      - GET first 1KB to validate content (reject HTML error pages)
      - Check starts with markdown header (#)

   c. If valid llms.txt found:
      - Parse content to detect hub-and-spoke structure
      - Extract variant URLs if hub detected
      - Determine doc platform (mintlify, vitepress, custom)
      - Store llmsTxt object in DocSource

   d. If no llms.txt found and no docsUrl:
      - Check if repoUrl has /docs/ directory
      - Try llms.txt patterns on repoUrl

5. Apply manual overrides:
   - Package groupings that PyPI metadata can't detect
   - Aliases for common misspellings
   - Version URL patterns
   - docsUrl corrections (some PyPI metadata is wrong/stale)

6. Output known-libraries.json
```

### 6.3 Package Grouping Heuristic

How do we know that `langchain-openai` belongs with `langchain`?

**Heuristic 1: Shared documentation URL.** If two PyPI packages list the same `project_urls.Documentation`, they belong to the same DocSource. This catches most monorepo sub-packages.

**Heuristic 2: Prefix matching with shared org.** If `langchain-openai` and `langchain` have the same GitHub org (`langchain-ai`), and `langchain-openai` doesn't have its own documentation URL (or it points to the parent docs), group them.

**Heuristic 3: Manual override.** For cases the heuristics miss, a manual override file specifies explicit groupings.

### 6.4 Registry Size Estimates

| Filter | Packages | Unique DocSources | With llms.txt | Registry File Size |
|--------|----------|-------------------|---------------|-------------------|
| Top 1,000 by downloads | 1,000 | ~600-700 | ~400-500 (80%) | ~200KB (with llms.txt data) |
| Top 5,000 by downloads | 5,000 | ~3,000-3,500 | ~2,000-2,500 (70%) | ~900KB (with llms.txt data) |
| llms.txt-only subset | ~500 | ~500 | ~500 (100%) | ~150KB |

**Notes:**
- The package-to-source deduplication is significant — top 1,000 packages collapse to ~600-700 unique documentation sources because of ecosystem grouping
- llms.txt data adds ~30-40% to registry size (URLs, variant info, platform metadata)
- Expected llms.txt adoption: 80% of top 1,000, 70% of top 5,000 (based on research showing 60% overall, 100% for AI/ML, 90% for dev platforms)

### 6.5 Registry Refresh Cadence

- **Monthly**: Re-run build script against latest top-pypi-packages
  - Discover new packages that crossed popularity threshold
  - Re-probe all docsUrls for llms.txt (detect new adoptions)
  - Update hub structures (libraries may add new variants)
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
  - Hub variant URLs are reachable

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

**Resolution Steps:**

**Step 1: Exact package match**
- Look up normalized query in package-to-ID index
- If found, retrieve DocSource by ID
- Return DocSource
- If not found, continue to Step 2

**Step 2: Exact ID match**
- Look up normalized query in DocSource-by-ID index
- If found, return DocSource
- If not found, continue to Step 3

**Step 3: Fuzzy match**
- Search normalized query against fuzzy corpus
- Use Levenshtein distance or similar algorithm
- If matches found with acceptable distance, return matching DocSources
- If not found, continue to Step 4

**Step 4: PyPI discovery** (if Python or language unspecified)
- Query PyPI API for package metadata
- If found, create ephemeral DocSource and cache
- Return DocSource
- If not found, continue to Step 5

**Step 5: GitHub discovery** (if query looks like repo path)
- If query contains "/" character
- Query GitHub API for repository metadata
- If found, create ephemeral DocSource and cache
- Return DocSource
- If not found, continue to Step 6

**Step 6: No match**
- Return empty result

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

| Dimension | PyPI | GitHub |
|-----------|------|--------|
| **Coverage (Python)** | ~500K packages. Covers all pip-installable libraries | Near-universal for open source. Also has non-Python projects |
| **Structured metadata** | Yes: name, summary, project_urls, version list, classifiers | Limited: description, homepage, topics. No package-level metadata |
| **Documentation URL** | Often in `project_urls.Documentation` — but not always set, sometimes stale | Homepage field — may or may not be docs. Often points to the repo itself |
| **Download/popularity data** | Via BigQuery or top-pypi-packages dataset. Well-established | Stars, forks. Less reliable as popularity metric |
| **Package grouping** | Possible via shared docs URL. Explicit package names | Monorepos are visible but sub-packages aren't distinct |
| **Multi-language** | Python only | All languages |
| **Non-public libraries** | Not on PyPI | May be on GitHub Enterprise, or not on GitHub at all |
| **Rate limits** | No auth needed for JSON API. No rate limit documented | 60 req/hr unauthenticated, 5,000 with PAT |

**Recommendation: PyPI is the primary source for the build script.** It has structured metadata, a reliable popularity ranking (via top-pypi-packages), and the `project_urls` field often points to documentation. GitHub is the fallback at runtime — when a library isn't in the registry and isn't on PyPI, the GitHub adapter can fetch docs from the repo.

The build script uses PyPI for discovery and enrichment. The runtime server uses the pre-built registry for fast resolution and falls back to PyPI/GitHub for unknown libraries.

---

## 9. Open Questions

### Q1: Should ephemeral discoveries be persisted?

When the server discovers a library via PyPI at runtime (Step 5), should it persist the DocSource to SQLite so it's available across sessions? Or is session-scoped caching sufficient?

**Lean**: Persist to SQLite with a TTL (e.g., 7 days). If a library is queried once, it's likely to be queried again. Persisting avoids repeated PyPI lookups.

### Q2: How do we handle packages that share a docs URL but shouldn't be grouped?

For example, if two unrelated packages happen to link to the same documentation hosting platform (e.g., both link to readthedocs.io root). The grouping heuristic would incorrectly merge them.

**Lean**: Only group when the full docs URL matches (not just the domain). `readthedocs.io` wouldn't match, but `langchain.readthedocs.io` would correctly group LangChain packages.

### Q3: Should the registry include packages below a popularity threshold?

The top-pypi-packages dataset has 15,000 packages. Should we include all of them, or filter?

**Lean**: Start with top 5,000 (>572K monthly downloads). This covers every library a typical developer encounters. The PyPI discovery fallback handles the long tail. We can expand later based on user feedback.

### Q4: Runtime discovery can create duplicate DocSources for version variants

When a new variant package (e.g., `tensorflow-lite`) is published to PyPI and isn't in the curated registry, Step 5 (PyPI discovery) creates an ephemeral DocSource for it. If that package's `project_urls.Documentation` points to `tensorflow.org` — the same docs URL as the existing `"tensorflow"` DocSource — the server now has two DocSources for the same documentation site. The shared-docs-URL grouping heuristic (section 6.3) only runs at registry build time, not at runtime, so this duplication goes undetected.

This could lead to the agent getting separate results for `tensorflow` and `tensorflow-lite` when they should be unified, or to redundant cache entries for the same pages.

**Possible mitigations:**
- At runtime, before creating an ephemeral DocSource, check if the discovered `docsUrl` already belongs to an existing DocSource. If it does, add the new package name to the existing entry instead of creating a new one.
- Periodically re-run the registry build script to absorb popular ephemeral discoveries into the curated registry.

**Lean**: No lean yet — needs further thought on the runtime check approach and whether it introduces false positives (e.g., packages that legitimately share a docs *domain* but not a docs *site*).

### Q5: How do we handle the agent passing a requirements.txt dump?

An agent might call `resolve-library` with each line from a requirements.txt. Some of those will be transitive dependencies (e.g., `certifi`, `urllib3`) that the developer never directly uses and doesn't need docs for.

**Lean**: Not our problem. The agent decides what to resolve. If it's smart, it resolves direct dependencies only. Pro-Context resolves whatever it's asked to resolve.

### Q6: When hub-and-spoke detected, should we cache all variants proactively?

When a library has a hub llms.txt with 5-9 variants (like Supabase), should we:
- Cache only the hub + selected variant, OR
- Proactively fetch and cache all variants

**Lean**: Cache only what's requested. Proactive caching wastes bandwidth/storage for variants the user never needs. The hub detection provides metadata so the agent can request specific variants as needed.

### Q7: Should llms.txt take absolute priority over docsUrl?

If a DocSource has both `docsUrl` and `llmsTxt.url`, should llms.txt always be used first, or should we fall back to HTML scraping if llms.txt content seems incomplete?

**Lean**: llms.txt takes absolute priority. If a library publishes llms.txt, they're explicitly supporting AI agents. Trust their curation. If content is incomplete, that's the library maintainer's problem to fix, not ours to work around.

### Q8: How do we handle llms.txt URL migrations?

A library might move their llms.txt from `library.com/llms.txt` to `docs.library.com/llms.txt`. Should we:
- Keep old URL and periodically re-check for 301 redirects
- Try rediscovery when validation fails
- Require manual registry updates

**Lean**: Combine approaches:
- Follow 301/302 redirects automatically during validation
- If old URL returns 404, trigger rediscovery (try all patterns)
- If rediscovery succeeds, update registry entry
- If rediscovery fails, mark as stale and notify for manual review
