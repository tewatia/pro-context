# Pro-Context: Registry Build System

> **Document**: 06-registry-build-system.md
> **Status**: Draft v1
> **Last Updated**: 2026-02-18
> **Depends on**: 05-library-resolution.md

---

## Table of Contents

- [1. Overview](#1-overview)
- [2. System Architecture](#2-system-architecture)
- [3. Discovery Pipeline](#3-discovery-pipeline)
  - [3.0 Curated Registry Seed Data](#30-curated-registry-seed-data)
  - [3.1 Package Source Discovery](#31-package-source-discovery)
  - [3.2 PyPI Metadata Extraction](#32-pypi-metadata-extraction)
  - [3.3 Documentation URL Discovery](#33-documentation-url-discovery)
  - [3.4 llms.txt Discovery](#34-llmstxt-discovery)
  - [3.5 Content Validation](#35-content-validation)
  - [3.6 Hub Detection and Resolution](#36-hub-detection-and-resolution)
  - [3.7 Package Grouping](#37-package-grouping)
  - [3.8 Manual Overrides](#38-manual-overrides)
- [4. llms.txt URL Patterns](#4-llmstxt-url-patterns)
- [5. Content Validation Rules](#5-content-validation-rules)
- [6. Hub Structures](#6-hub-structures)
- [7. Error Handling and Recovery](#7-error-handling-and-recovery)
- [8. Quality Assurance](#8-quality-assurance)
- [9. Output Format](#9-output-format)
- [10. CI/CD Automation](#10-cicd-automation)
- [11. Monitoring and Maintenance](#11-monitoring-and-maintenance)

---

## 1. Overview

The Registry Build System is a **build-time** process that discovers, validates, and curates library documentation into a production-ready registry file (`known-libraries.json`). This registry is **independent from pro-context package version** and is published separately on GitHub Releases.

**Core responsibility**: Transform the chaotic landscape of Python packages into a comprehensive registry of popular libraries, marking which have llms.txt documentation available.

**Registry scope**:
- **Broad coverage**: Top 1000 PyPI packages + curated llms.txt sources + MCP servers + popular GitHub projects
- **All libraries included**: Even libraries without llms.txt are tracked (marked `llmsTxtAvailable: false`)
- **Clear availability marking**: Users know what's tracked vs what's available

**Key principles**:
1. **Include everything popular** — Top 1000 PyPI packages are all tracked
2. **Validate llms.txt availability** — Mark which libraries have working llms.txt
3. **Group intelligently** — Detect monorepo sub-packages using Repository URL
4. **Robust error handling** — Network failures, rate limits, HTML error pages — handle gracefully
5. **Audit trail** — Every decision (include, exclude, group, separate) is logged
6. **Reproducible** — Same input = same output, deterministic grouping rules

**Execution cadence**:
- **Community edition**: Weekly via GitHub Actions
- **Enterprise edition**: Daily (scheduled job)
- **Manual**: On-demand via `python scripts/build_registry.py`

---

## 2. System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Registry Build System                        │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                   Discovery Pipeline                      │  │
│  │                                                           │  │
│  │  0. Curated Registry Seed Data                            │  │
│  │     └─ llms-txt-hub, Awesome-llms-txt (100-200 entries) │  │
│  │                                                           │  │
│  │  1. Package Source Discovery                              │  │
│  │     └─ hugovk/top-pypi-packages (monthly snapshot)       │  │
│  │                                                           │  │
│  │  2. PyPI Metadata Extraction                              │  │
│  │     └─ GET https://pypi.org/pypi/{name}/json             │  │
│  │                                                           │  │
│  │  3. Documentation URL Discovery                           │  │
│  │     └─ Extract from project_urls                          │  │
│  │                                                           │  │
│  │  4. llms.txt Discovery                                    │  │
│  │     └─ Probe 10+ URL patterns                             │  │
│  │                                                           │  │
│  │  5. Content Validation                                    │  │
│  │     └─ HTTP status, Content-Type, HTML detection         │  │
│  │                                                           │  │
│  │  6. Hub Detection and Resolution                          │  │
│  │     └─ Follow hub links, create per-variant DocSources   │  │
│  │                                                           │  │
│  │  7. Package Grouping                                      │  │
│  │     └─ Group by Repository URL                            │  │
│  │                                                           │  │
│  │  8. Manual Overrides                                      │  │
│  │     └─ Apply corrections, merge with curated seed data   │  │
│  │                                                           │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                   Quality Assurance                       │  │
│  │                                                           │  │
│  │  • Deduplication (no duplicate IDs)                       │  │
│  │  • URL validation (all URLs return 200)                   │  │
│  │  • Completeness (all packages have docs or marked N/A)    │  │
│  │  • Consistency (grouping rules applied uniformly)         │  │
│  │  • Audit log (decisions recorded)                         │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                   Output Generation                       │  │
│  │                                                           │  │
│  │  • data/known-libraries.json (production registry)        │  │
│  │  • data/build_log.txt (detailed audit trail)             │  │
│  │  • data/build_stats.json (metrics)                        │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

**Key components**:

| Component | Responsibility | Key Files |
|-----------|---------------|-----------|
| **Pipeline orchestrator** | Coordinates all discovery steps, manages state | `scripts/build_registry.py` |
| **PyPI client** | Fetches package metadata, handles rate limits | `scripts/utils/pypi_client.py` |
| **llms.txt validator** | Validates content, detects hubs | `scripts/utils/llms_txt_validator.py` |
| **Hub resolver** | Follows hub links, creates variants | `scripts/utils/hub_resolver.py` |
| **Grouping engine** | Groups packages by Repository URL | `scripts/utils/grouping_engine.py` |
| **Override loader** | Applies manual corrections | `scripts/utils/override_loader.py` |
| **Quality checker** | Validates output integrity | `scripts/utils/quality_checker.py` |

---

## 3. Discovery Pipeline

### 3.0 Curated Registry Seed Data

**Objective**: Bootstrap the registry with validated llms.txt entries from community-maintained sources.

**Data sources**:
1. **llms-txt-hub** (`github.com/thedaviddias/llms-txt-hub`)
   - Largest community-maintained directory (100+ entries)
   - Organized by category: AI/ML, Developer Tools, Data & Analytics, Infrastructure
   - JSON/YAML format with library name, docs URL, llms.txt URL, description
   - Regularly updated by community contributors

2. **Awesome-llms-txt** (`github.com/SecretiveShell/Awesome-llms-txt`)
   - Community-curated index of llms.txt files
   - Markdown format with links to llms.txt URLs
   - Supplementary source for additional entries

**Process**:
```python
async def fetch_curated_registries() -> list[DocSource]:
    """Fetch and parse curated registries as seed data"""
    sources = []

    # Clone/fetch llms-txt-hub
    hub_url = "https://api.github.com/repos/thedaviddias/llms-txt-hub/contents/data"
    # Parse registry files, extract entries

    # Clone/fetch Awesome-llms-txt
    awesome_url = "https://raw.githubusercontent.com/SecretiveShell/Awesome-llms-txt/main/README.md"
    # Parse markdown, extract llms.txt URLs

    # For each entry:
    #   1. Validate llms.txt URL (HEAD request + content check)
    #   2. Extract library metadata
    #   3. Create DocSource entry

    logger.info(f"Fetched {len(sources)} entries from curated registries")
    return sources
```

**Benefits**:
- **Quick win**: 100-200 validated entries immediately
- **High quality**: Community-vetted, known-working llms.txt files
- **AI/ML focus**: Covers major libraries (LangChain, Anthropic, Pydantic AI, OpenAI)
- **Reduced API calls**: Less PyPI probing needed for popular libraries

**Validation**:
- Each llms.txt URL must return 200 OK
- Content must be valid markdown (not HTML)
- First line must start with `#` (markdown header)
- File size > 100 bytes (not empty stub)

**Deduplication**:
- Entries from curated registries take precedence
- PyPI-discovered entries (section 3.1-3.4) are merged, with curated data winning on conflicts

---

### 3.1 Package Source Discovery

**Objective**: Identify the top N Python packages to process.

**Data source**: `hugovk/top-pypi-packages` repository
- Publishes monthly snapshots of PyPI package download statistics
- Includes ~15,000 packages ranked by download count
- JSON format: `[{"project": "requests", "download_count": 1234567}, ...]`

**Process**:
```python
async def fetch_top_packages(limit: int) -> list[str]:
    """Fetch top N packages by download count from hugovk/top-pypi-packages"""
    url = "https://hugovk.github.io/top-pypi-packages/top-pypi-packages-30-days.min.json"

    async with httpx.AsyncClient() as client:
        response = await client.get(url, timeout=30.0)
        response.raise_for_status()

        data = response.json()
        packages = [row["project"] for row in data["rows"][:limit]]

    logger.info(f"Fetched {len(packages)} packages from top-pypi-packages")
    return packages
```

**Configuration**:
- Community edition: `limit = 1000`
- Enterprise edition: `limit = 5000`

**Edge cases**:
- Snapshot not available → Fallback to cached previous month
- Download count ties → Use alphabetical order for determinism

---

### 3.2 PyPI Metadata Extraction

**Objective**: Extract documentation URLs and repository URLs from PyPI metadata.

**API endpoint**: `https://pypi.org/pypi/{package_name}/json`

**Key fields to extract**:

```python
{
    "info": {
        "name": str,                  # Canonical package name
        "summary": str,               # One-line description
        "project_urls": {             # Key-value pairs of URLs
            "Documentation": str,     # PRIMARY: docs URL
            "Homepage": str,          # FALLBACK: often docs URL
            "Source": str,            # Repository URL
            "Repository": str,        # Repository URL (alternative key)
            "Bug Tracker": str,       # Ignore (not useful)
            "Changelog": str          # Ignore
        }
    }
}
```

**Extraction logic**:

```python
async def extract_metadata(package_name: str) -> PackageMetadata:
    """Extract metadata from PyPI JSON API"""
    url = f"https://pypi.org/pypi/{package_name}/json"

    async with httpx.AsyncClient() as client:
        response = await client.get(url, timeout=10.0, follow_redirects=True)
        response.raise_for_status()

        data = response.json()
        info = data["info"]
        project_urls = info.get("project_urls") or {}

        # Extract documentation URL
        docs_url = (
            project_urls.get("Documentation")
            or project_urls.get("Docs")
            or project_urls.get("documentation")
            or (project_urls.get("Homepage") if is_docs_site(project_urls.get("Homepage")) else None)
            or None
        )

        # Extract repository URL (prefer "Source" over "Repository")
        repo_url = (
            project_urls.get("Source")
            or project_urls.get("Repository")
            or project_urls.get("Code")
            or (project_urls.get("Homepage") if is_github_url(project_urls.get("Homepage")) else None)
            or None
        )

        return PackageMetadata(
            name=info["name"],
            summary=info.get("summary", ""),
            docs_url=normalize_url(docs_url),
            repo_url=normalize_github_url(repo_url),
        )


def is_docs_site(url: str | None) -> bool:
    """Check if URL looks like a documentation site"""
    if not url:
        return False

    docs_indicators = [
        "docs.", ".readthedocs.io", "documentation", "/docs",
        "api-docs", "devdocs", "developer"
    ]
    return any(indicator in url.lower() for indicator in docs_indicators)


def is_github_url(url: str | None) -> bool:
    """Check if URL is a GitHub repository"""
    if not url:
        return False
    return "github.com" in url.lower()


def normalize_url(url: str | None) -> str | None:
    """Normalize URL: strip trailing slash, ensure https"""
    if not url:
        return None
    url = url.rstrip("/")
    if url.startswith("http://"):
        url = url.replace("http://", "https://", 1)
    return url


def normalize_github_url(url: str | None) -> str | None:
    """Normalize GitHub URL to canonical form"""
    if not url:
        return None

    # github.com/owner/repo (canonical)
    # github.com/owner/repo.git → remove .git
    # github.com/owner/repo/tree/main → strip path after repo
    # github.com/owner/repo/issues → strip path after repo

    url = normalize_url(url)
    if "github.com" not in url:
        return url

    # Parse: https://github.com/owner/repo[/optional/path]
    parts = url.split("github.com/", 1)[1].split("/")
    if len(parts) >= 2:
        owner, repo = parts[0], parts[1]
        repo = repo.removesuffix(".git")
        return f"https://github.com/{owner}/{repo}"

    return url
```

**Rate limiting**:
- PyPI allows ~10 req/sec without API key
- Implement exponential backoff on 429 responses
- Use `asyncio.Semaphore(10)` to limit concurrent requests

**Edge cases**:

| Issue | Handling |
|-------|----------|
| Package not found (404) | Skip, log as "package_not_found" |
| PyPI timeout | Retry up to 3 times with exponential backoff |
| Missing `project_urls` | Use None for docs_url and repo_url |
| Homepage is GitHub repo | Use as repo_url if no Source/Repository key |
| Homepage is docs site | Use as docs_url if no Documentation key |
| Multiple Documentation URLs | Use first one (PyPI JSON API doesn't have multiples, but if it does, take first) |

---

### 3.3 Documentation URL Discovery

**Objective**: Determine the canonical documentation URL for each package.

**Priority order**:
1. `project_urls.Documentation` (most reliable)
2. `project_urls.Homepage` (if it's a docs site — check for "docs.", ".readthedocs.io", "/docs")
3. Derived from `repo_url` if GitHub Pages pattern detected (e.g., `github.com/owner/repo` → `owner.github.io/repo`)
4. None (no docs URL found)

**Docs site detection heuristics**:

```python
def classify_homepage(url: str) -> Literal["docs_site", "repo", "marketing", "unknown"]:
    """Classify what type of site the homepage URL points to"""
    url_lower = url.lower()

    # Docs site indicators
    if any(pattern in url_lower for pattern in [
        "docs.", ".readthedocs.io", "documentation.", "/docs",
        "api-docs", "devdocs", "developer.", "guide."
    ]):
        return "docs_site"

    # Repository indicators
    if any(pattern in url_lower for pattern in [
        "github.com", "gitlab.com", "bitbucket.org"
    ]):
        return "repo"

    # Marketing site indicators (not useful for docs)
    if any(pattern in url_lower for pattern in [
        "www.", "home.", "landing.", "marketing."
    ]):
        return "marketing"

    return "unknown"
```

**GitHub Pages detection**:

Some projects host docs on GitHub Pages but don't list it in `project_urls`:
- Pattern: `github.com/owner/repo` → `https://owner.github.io/repo/`
- Only probe if `project_urls.Documentation` is missing
- Validate by checking if `https://owner.github.io/repo/` returns 200

---

### 3.4 llms.txt Discovery

**Objective**: Discover llms.txt files for each documentation URL.

**Research foundation**: Based on analysis of 70+ libraries in `docs/research/llms-txt-deployment-patterns.md`.

**URL patterns to probe** (in priority order):

```python
def generate_llms_txt_candidates(docs_url: str) -> list[str]:
    """Generate all possible llms.txt URL candidates for a docs site"""

    from urllib.parse import urlparse

    parsed = urlparse(docs_url)
    domain = parsed.netloc
    path = parsed.path.rstrip("/")

    candidates = []

    # Pattern 1: Direct root
    # Example: docs.langchain.com → docs.langchain.com/llms.txt
    # Frequency: 30% of cases
    candidates.append(f"https://{domain}/llms.txt")

    # Pattern 2: Locale prefix (common for international sites)
    # Example: docs.anthropic.com → docs.anthropic.com/en/llms.txt
    # Frequency: 15% of cases (Anthropic, ReadTheDocs sites)
    candidates.append(f"https://{domain}/en/llms.txt")

    # Pattern 3: Version prefix (common for versioned docs)
    # Example: docs.pydantic.dev → docs.pydantic.dev/latest/llms.txt
    # Frequency: 20% of cases (Pydantic, Django)
    candidates.append(f"https://{domain}/latest/llms.txt")

    # Pattern 4: Path-based (if docs_url has a path)
    # Example: python.langchain.com/v0.2 → python.langchain.com/v0.2/llms.txt
    # Frequency: 10% of cases
    if path:
        candidates.append(f"https://{domain}{path}/llms.txt")

    # Pattern 5: Domain root (if docs_url has a deep path)
    # Example: supabase.com/docs/guides → supabase.com/llms.txt
    # Frequency: 5% of cases
    if path and path != "/":
        candidates.append(f"https://{domain}/llms.txt")  # Already added, dedupe

    # Pattern 6: Docs subdirectory
    # Example: openai.com → openai.com/docs/llms.txt
    # Frequency: 5% of cases (OpenAI pattern)
    if not path or path == "/":
        candidates.append(f"https://{domain}/docs/llms.txt")

    # Pattern 7: API subdirectory
    # Example: stripe.com → stripe.com/api/llms.txt
    # Frequency: <5%
    if not path or path == "/":
        candidates.append(f"https://{domain}/api/llms.txt")

    # Pattern 8: Versioned locale
    # Example: docs.example.com → docs.example.com/en/latest/llms.txt
    # Frequency: <5% (rare, but ReadTheDocs uses this)
    candidates.append(f"https://{domain}/en/latest/llms.txt")

    # Pattern 9: Alternative locale prefix
    # Example: docs.example.com → docs.example.com/en-us/llms.txt
    # Frequency: <5%
    candidates.append(f"https://{domain}/en-us/llms.txt")

    # Pattern 10: Multi-product path with llms.txt
    # Example: svelte.dev → svelte.dev/docs/svelte/llms.txt
    # Frequency: Rare but important (Svelte, Supabase patterns)
    # This is handled by hub detection (if svelte.dev/llms.txt is a hub)

    # Deduplicate while preserving order
    seen = set()
    unique_candidates = []
    for url in candidates:
        if url not in seen:
            seen.add(url)
            unique_candidates.append(url)

    return unique_candidates
```

**Probing strategy**:

```python
async def discover_llms_txt(docs_url: str) -> LlmsTxtInfo | None:
    """
    Probe all candidate URLs to find a valid llms.txt file.
    Returns the first valid one found.
    """
    candidates = generate_llms_txt_candidates(docs_url)

    for candidate_url in candidates:
        try:
            is_valid, content = await validate_llms_txt_content(candidate_url)
            if is_valid:
                # Check if it's a hub (contains links to other llms.txt files)
                is_hub = detect_hub_structure(content)

                logger.info(f"Found valid llms.txt: {candidate_url} (hub={is_hub})")

                return LlmsTxtInfo(
                    url=candidate_url,
                    is_hub=is_hub,
                    content=content if is_hub else None,  # Store content for hubs
                    platform=detect_platform(candidate_url),
                    last_validated=datetime.now().isoformat(),
                )
        except Exception as e:
            logger.debug(f"Probe failed for {candidate_url}: {e}")
            continue

    logger.warning(f"No valid llms.txt found for {docs_url}")
    return None
```

**Platform detection**:

```python
def detect_platform(llms_txt_url: str) -> str:
    """Detect documentation platform from URL structure"""
    url_lower = llms_txt_url.lower()

    if ".mintlify.app" in url_lower or "mint" in url_lower:
        return "mintlify"
    elif ".readthedocs.io" in url_lower:
        return "readthedocs"
    elif "vitepress" in url_lower or ".dev" in url_lower:
        return "vitepress"
    elif "docusaurus" in url_lower:
        return "docusaurus"
    elif "github.io" in url_lower:
        return "github-pages"
    else:
        return "custom"
```

---

### 3.5 Content Validation

**Objective**: Validate that a URL serves a real llms.txt file, not an HTML error page.

**Problem**: Many URLs return HTTP 200 but serve HTML error pages:
- Generic "Page not found" pages
- Authentication walls
- Redirects to homepage
- CDN error pages

**Validation steps**:

```python
async def validate_llms_txt_content(url: str) -> tuple[bool, str | None]:
    """
    Validate that URL serves a valid llms.txt file.
    Returns (is_valid, content).
    """

    # Step 1: HTTP Status Check
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
            # HEAD request first (faster, no content download)
            head_response = await client.head(url)

            if head_response.status_code != 200:
                logger.debug(f"HEAD {url} returned {head_response.status_code}")
                return (False, None)

            # Step 2: Content-Type Check
            content_type = head_response.headers.get("Content-Type", "").lower()

            # Reject if Content-Type contains "html"
            if "html" in content_type:
                logger.debug(f"{url} has Content-Type: {content_type} (rejected)")
                return (False, None)

            # Accept text/plain, text/markdown, or unspecified
            # (Some servers don't set Content-Type for .txt files)

            # Step 3: Content Download (first 1KB for validation)
            # Use Range header to avoid downloading huge files
            get_response = await client.get(
                url,
                headers={"Range": "bytes=0-1023"}  # First 1KB
            )

            # Handle partial content or full content
            if get_response.status_code not in (200, 206):
                logger.debug(f"GET {url} returned {get_response.status_code}")
                return (False, None)

            content_sample = get_response.text

            # Step 4: HTML Detection
            html_indicators = [
                "<!DOCTYPE html",
                "<!doctype html",
                "<html",
                "<HTML",
                "<head>",
                "<body>",
                "<div",
            ]

            if any(indicator in content_sample for indicator in html_indicators):
                logger.debug(f"{url} contains HTML tags (rejected)")
                return (False, None)

            # Step 5: Markdown Header Check
            # llms.txt files should start with a markdown header
            trimmed = content_sample.strip()
            if not trimmed.startswith("#"):
                logger.debug(f"{url} does not start with '#' (rejected)")
                return (False, None)

            # All checks passed — download full content
            full_response = await client.get(url)
            full_content = full_response.text

            logger.info(f"Validated llms.txt: {url} ({len(full_content)} bytes)")
            return (True, full_content)

    except httpx.TimeoutException:
        logger.debug(f"Timeout validating {url}")
        return (False, None)
    except httpx.HTTPStatusError as e:
        logger.debug(f"HTTP error validating {url}: {e}")
        return (False, None)
    except Exception as e:
        logger.warning(f"Unexpected error validating {url}: {e}")
        return (False, None)
```

**Why these checks matter**:

| Check | Catches |
|-------|---------|
| HTTP 200 | 404s, 403s, 500s |
| Content-Type | HTML error pages with correct status |
| HTML detection | CDN error pages, authentication walls |
| Markdown header | Plain text files that aren't llms.txt, JSON responses |

---

### 3.6 Hub Detection and Resolution

**Objective**: Detect hub llms.txt files that link to multiple per-product/per-language llms.txt files, and create separate DocSources for each variant.

**Hub definition**: An llms.txt file is a hub if it contains multiple links to other llms.txt files but minimal documentation content itself.

**Examples from research**:

| Site | Hub URL | Variant URLs |
|------|---------|--------------|
| **Supabase** | `supabase.com/llms.txt` | `supabase.com/llms/python.txt`, `supabase.com/llms/js.txt`, `supabase.com/llms/swift.txt` |
| **Svelte** | `svelte.dev/llms.txt` | `svelte.dev/docs/svelte/llms.txt`, `svelte.dev/docs/kit/llms.txt` |

**Hub detection algorithm**:

```python
def detect_hub_structure(content: str) -> bool:
    """
    Detect if an llms.txt file is a hub (links to other llms.txt files).

    Heuristics:
    1. Contains 2+ links to other llms.txt files
    2. Has minimal content (< 2000 chars after stripping links)
    3. Links are to different paths or subdomains
    """

    # Extract all llms.txt links
    llms_txt_links = extract_llms_txt_links(content)

    if len(llms_txt_links) < 2:
        return False  # Not a hub if < 2 variant links

    # Check content size (excluding links)
    content_without_links = content
    for link in llms_txt_links:
        content_without_links = content_without_links.replace(link, "")

    # If content is mostly just links to other llms.txt files, it's a hub
    if len(content_without_links.strip()) < 2000:
        return True

    return False


def extract_llms_txt_links(content: str) -> list[str]:
    """Extract all llms.txt URLs from markdown content"""
    import re

    # Match markdown links: [text](url) or just URLs
    # Focus on URLs containing "llms.txt"
    pattern = r'\[([^\]]+)\]\(([^)]+llms\.txt[^)]*)\)|https?://[^\s]+llms\.txt'

    matches = re.findall(pattern, content)

    urls = []
    for match in matches:
        if isinstance(match, tuple):
            url = match[1] if match[1] else match[0]
        else:
            url = match
        urls.append(url)

    return urls
```

**Hub resolution process**:

```python
async def resolve_hub(hub_info: LlmsTxtInfo, docs_url: str) -> list[DocSourceVariant]:
    """
    Follow hub links and create separate DocSource for each valid variant.
    """
    variants: list[DocSourceVariant] = []

    # Extract all variant links from hub content
    variant_urls = extract_llms_txt_links(hub_info.content)

    logger.info(f"Hub detected at {hub_info.url} with {len(variant_urls)} variants")

    for variant_url in variant_urls:
        # Resolve relative URLs
        variant_url = urljoin(hub_info.url, variant_url)

        # Validate variant
        is_valid, variant_content = await validate_llms_txt_content(variant_url)

        if not is_valid:
            logger.warning(f"Invalid variant: {variant_url}")
            continue

        # Check if variant is itself a hub (recursive hubs are possible but rare)
        is_nested_hub = detect_hub_structure(variant_content)

        if is_nested_hub:
            logger.warning(f"Nested hub detected at {variant_url} — skipping")
            continue

        # Determine variant name from URL structure
        variant_name = extract_variant_name(variant_url, hub_info.url)

        variants.append(DocSourceVariant(
            name=variant_name,
            llms_txt_url=variant_url,
            docs_url=infer_docs_url_from_variant(variant_url, docs_url),
        ))

        logger.info(f"Discovered variant: {variant_name} → {variant_url}")

    return variants


def extract_variant_name(variant_url: str, hub_url: str) -> str:
    """
    Extract variant name from URL.

    Examples:
    - supabase.com/llms/python.txt → "python"
    - svelte.dev/docs/kit/llms.txt → "kit"
    - svelte.dev/docs/svelte/llms.txt → "svelte"
    """
    from urllib.parse import urlparse

    variant_path = urlparse(variant_url).path
    hub_path = urlparse(hub_url).path

    # Remove .txt extension
    variant_path = variant_path.removesuffix("/llms.txt")

    # Extract last path component
    parts = [p for p in variant_path.split("/") if p]
    if parts:
        return parts[-1]

    return "unknown"


def infer_docs_url_from_variant(variant_url: str, base_docs_url: str) -> str:
    """
    Infer the documentation URL for a variant.

    For Supabase: supabase.com/llms/python.txt → supabase.com/docs/reference/python
    For Svelte: svelte.dev/docs/svelte/llms.txt → svelte.dev/docs/svelte
    """
    from urllib.parse import urlparse

    parsed = urlparse(variant_url)
    path = parsed.path.removesuffix("/llms.txt")

    if path:
        return f"https://{parsed.netloc}{path}"

    return base_docs_url
```

**Hub processing rules**:

1. **Hub itself is NOT stored** in the registry
2. Each valid variant becomes a separate DocSource
3. Variant naming convention: `{base-name}-{variant}`
   - Example: `supabase-python`, `supabase-js`, `svelte`, `sveltekit`
4. If a variant is invalid, log warning but continue with other variants
5. Nested hubs (hub pointing to hub) are rejected

---

### 3.7 Package Grouping

**Objective**: Group PyPI packages that belong to the same documentation source.

**Grouping rule**: Same Repository URL = same DocSource (primary signal)

**Why Repository URL?**
- Monorepo sub-packages share the same Repository URL
- Verified against LangChain, Pydantic, HuggingFace, TensorFlow ecosystems
- Most reliable signal for "these packages belong together"

**Fallback rule**: If Repository URL is missing, use Homepage URL (only if both packages have same Homepage and no Repository URL)

**Algorithm**:

```python
def group_packages_by_repository(
    packages: list[PackageMetadata]
) -> dict[str, list[PackageMetadata]]:
    """
    Group packages by Repository URL.
    Returns dict: repo_url → list of packages
    """
    groups: dict[str, list[PackageMetadata]] = {}

    for pkg in packages:
        # Primary grouping key: Repository URL
        if pkg.repo_url:
            key = pkg.repo_url
        # Fallback grouping key: Homepage URL (only if no Repository URL)
        elif pkg.docs_url:
            key = f"homepage:{pkg.docs_url}"
        # No grouping key: treat as standalone
        else:
            key = f"standalone:{pkg.name}"

        if key not in groups:
            groups[key] = []
        groups[key].append(pkg)

    return groups


def create_doc_sources_from_groups(
    groups: dict[str, list[PackageMetadata]]
) -> list[DocSource]:
    """
    Create DocSource entries from grouped packages.
    """
    doc_sources: list[DocSource] = []

    for key, packages in groups.items():
        # Sort packages by name for determinism
        packages.sort(key=lambda p: p.name)

        # Primary package (use first one alphabetically, or most downloaded)
        primary = packages[0]

        # Determine DocSource ID
        # If grouped by repo: use github.com/owner/repo → "owner/repo"
        # If standalone: use package name
        if key.startswith("standalone:"):
            doc_source_id = primary.name
        elif key.startswith("homepage:"):
            doc_source_id = primary.name  # Fallback: use package name
        else:
            # Extract owner/repo from GitHub URL
            doc_source_id = extract_repo_id(key)

        doc_sources.append(DocSource(
            id=doc_source_id,
            name=primary.name.title(),  # Human-readable name
            docs_url=primary.docs_url,
            repo_url=primary.repo_url,
            languages=["python"],  # Will be extended in future for JS/TS
            packages={"pypi": [pkg.name for pkg in packages]},
            aliases=generate_aliases(primary.name),
            llms_txt=None,  # Will be populated by llms.txt discovery
        ))

    return doc_sources


def extract_repo_id(repo_url: str) -> str:
    """
    Extract owner/repo from GitHub URL.

    https://github.com/langchain-ai/langchain → langchain-ai/langchain
    """
    if "github.com" not in repo_url:
        return repo_url  # Return as-is if not GitHub

    parts = repo_url.split("github.com/", 1)[1].split("/")
    if len(parts) >= 2:
        return f"{parts[0]}/{parts[1]}"
    return repo_url
```

**Examples**:

| Packages | Repository URL | Grouping Result |
|----------|---------------|-----------------|
| `langchain`, `langchain-openai`, `langchain-core` | `github.com/langchain-ai/langchain` | Single DocSource: `langchain-ai/langchain` |
| `pydantic`, `pydantic-core` | `github.com/pydantic/pydantic` | Single DocSource: `pydantic/pydantic` |
| `pydantic-ai`, `pydantic-ai-slim` | `github.com/pydantic/pydantic-ai` | Separate DocSource: `pydantic/pydantic-ai` |
| `transformers` | `github.com/huggingface/transformers` | Single DocSource: `huggingface/transformers` |
| `diffusers` | `github.com/huggingface/diffusers` | Separate DocSource: `huggingface/diffusers` |
| `tensorflow`, `tensorflow-gpu`, `tf-nightly` | All have Homepage: `tensorflow.org` (no Repository URL) | Single DocSource: `tensorflow` (fallback grouping) |

---

### 3.8 Manual Overrides

**Objective**: Allow human curation to correct automated grouping errors, add missing libraries, and fix stale metadata.

**Override file**: `data/manual_overrides.yaml`

**Structure**:

```yaml
# Force-group packages that automated rule missed
force_group:
  - repo_url: "https://github.com/langchain-ai/langchain"
    packages:
      - "langchain"
      - "langchain-openai"
      - "langchain-anthropic"
      - "langchain-community"
      - "langchain-core"
      - "langchain-text-splitters"

# Force-separate packages that were incorrectly grouped
force_separate:
  - package: "pydantic-ai"
    reason: "Separate project from pydantic, different docs site"

# Add aliases for common misspellings
aliases:
  langchain:
    - "lang-chain"
    - "lang chain"
  fastapi:
    - "fast-api"
    - "fast api"
  pydantic:
    - "pydanctic"
    - "pydantic2"

# Correct stale/wrong docs URLs from PyPI metadata
docs_url_overrides:
  anthropic: "https://docs.anthropic.com/en/api"
  openai: "https://platform.openai.com/docs"

# Add non-PyPI libraries (GitHub-only, private)
manual_additions:
  - id: "anthropics/anthropic-sdk-python"
    name: "Anthropic Python SDK"
    docs_url: "https://docs.anthropic.com/en/api"
    repo_url: "https://github.com/anthropics/anthropic-sdk-python"
    languages: ["python"]
    packages:
      pypi: ["anthropic"]
    aliases: ["claude-api"]

# Exclude packages from registry (spam, broken, deprecated)
exclude:
  - package: "some-broken-package"
    reason: "No documentation available"
```

**Application order**:
1. Run automated discovery
2. Apply `force_group` rules
3. Apply `force_separate` rules
4. Apply `docs_url_overrides`
5. Add `manual_additions`
6. Apply `exclude` rules
7. Merge `aliases`

---

## 4. llms.txt URL Patterns

**Comprehensive list** (from research of 70+ libraries):

```python
LLMS_TXT_PATTERNS = [
    # Direct root (30% of cases)
    "{docs_url}/llms.txt",

    # Locale prefix (15% - Anthropic, many ReadTheDocs sites)
    "{docs_url}/en/llms.txt",
    "{docs_url}/en-us/llms.txt",

    # Version prefix (20% - Pydantic, Django, versioned docs)
    "{docs_url}/latest/llms.txt",
    "{docs_url}/stable/llms.txt",
    "{docs_url}/v1/llms.txt",
    "{docs_url}/v2/llms.txt",

    # Versioned + locale (5% - ReadTheDocs pattern)
    "{docs_url}/en/latest/llms.txt",
    "{docs_url}/en/stable/llms.txt",

    # Docs subdirectory (5% - OpenAI pattern)
    "{domain_root}/docs/llms.txt",
    "{domain_root}/documentation/llms.txt",

    # API subdirectory (< 5%)
    "{domain_root}/api/llms.txt",

    # Multi-product paths (rare but important - Svelte, Supabase)
    # These are discovered via hub resolution, not direct probing
]
```

---

## 5. Content Validation Rules

**5-step validation process**:

1. **HTTP Status**: Must return 200 (follow redirects)
2. **Content-Type**: Must be `text/plain`, `text/markdown`, or unspecified. Reject if contains `html`.
3. **HTML Detection**: First 1KB must NOT contain HTML tags (`<!DOCTYPE`, `<html>`, `<head>`, `<body>`, `<div>`)
4. **Markdown Header**: First line (after trimming) must start with `#`
5. **Size Check**: Must be > 100 bytes (too small = probably error page) and < 10MB (too large = probably not llms.txt)

**Why each rule matters**:

| Rule | Catches |
|------|---------|
| HTTP 200 | Dead links, authentication walls |
| Content-Type | HTML error pages with correct HTTP status |
| HTML detection | CDN errors, auth walls, generic "not found" pages |
| Markdown header | JSON responses, plain text that isn't markdown, empty files |
| Size check | Placeholder files, huge binary files misnamed as .txt |

---

## 6. Hub Structures

**Real-world hub patterns** (from research):

### 6.1 Language-Based Hubs (Supabase Pattern)

```
Hub: supabase.com/llms.txt
Content:
  # Supabase Documentation

  - [Python SDK](https://supabase.com/llms/python.txt)
  - [JavaScript SDK](https://supabase.com/llms/js.txt)
  - [Swift SDK](https://supabase.com/llms/swift.txt)
  - [Flutter SDK](https://supabase.com/llms/flutter.txt)

Variants created:
  - supabase-python (id: supabase-python, llms.txt: supabase.com/llms/python.txt)
  - supabase-js (id: supabase-js, llms.txt: supabase.com/llms/js.txt)
  - supabase-swift (id: supabase-swift, llms.txt: supabase.com/llms/swift.txt)
  - supabase-flutter (id: supabase-flutter, llms.txt: supabase.com/llms/flutter.txt)
```

### 6.2 Product-Based Hubs (Svelte Pattern)

```
Hub: svelte.dev/llms.txt
Content:
  # Svelte Ecosystem

  - [Svelte](https://svelte.dev/docs/svelte/llms.txt)
  - [SvelteKit](https://svelte.dev/docs/kit/llms.txt)

Variants created:
  - svelte (id: svelte, llms.txt: svelte.dev/docs/svelte/llms.txt)
  - sveltekit (id: sveltekit, llms.txt: svelte.dev/docs/kit/llms.txt)
```

### 6.3 NOT a Hub (TanStack Pattern)

```
File: tanstack.com/llms.txt
Content:
  # TanStack Documentation

  ## TanStack Query
  [Installation](https://tanstack.com/query/latest/docs/installation)
  ...

  ## TanStack Router
  [Getting Started](https://tanstack.com/router/latest/docs/getting-started)
  ...

  ## TanStack Table
  [Quick Start](https://tanstack.com/table/latest/docs/quick-start)
  ...

Analysis: This is NOT a hub — it's a single llms.txt file that covers multiple products.
The TOC contains sections for each product. The agent navigates to the relevant section.
Result: Single DocSource: "tanstack" with llms.txt URL: tanstack.com/llms.txt
```

**Hub detection heuristic refined**:

A file is a hub if:
1. Contains 2+ markdown links pointing to other llms.txt files (URLs ending in `/llms.txt` or containing `/llms/`)
2. Has minimal content (<2000 chars) after stripping those links
3. Links are to different subpaths or domains

---

## 7. Error Handling and Recovery

### 7.1 Network Errors

| Error | Handling |
|-------|----------|
| `httpx.TimeoutException` | Retry up to 3 times with exponential backoff (1s, 2s, 4s) |
| `httpx.HTTPStatusError` (429) | Respect Retry-After header, or exponential backoff |
| `httpx.HTTPStatusError` (5xx) | Retry up to 3 times |
| `httpx.HTTPStatusError` (4xx except 429) | No retry, mark as failed |
| `httpx.NetworkError` | Retry up to 3 times (DNS, connection errors) |

### 7.2 PyPI Rate Limiting

- PyPI allows ~10 req/sec without authentication
- Use `asyncio.Semaphore(10)` to limit concurrent requests
- On 429: Exponential backoff (30s, 60s, 120s)
- Consider using PyPI mirrors for large builds

### 7.3 Incomplete Data

| Issue | Handling |
|-------|----------|
| Package metadata missing `project_urls` | Use None for docs_url/repo_url, mark as "no_docs" |
| docs_url returns 404 | Mark as "docs_unavailable", exclude from registry |
| llms.txt not found | Include in registry with `llms_txt: null`, mark for manual review |
| Invalid llms.txt content | Log validation failure, exclude from registry |

### 7.4 Audit Trail

Every decision is logged to `data/build_log.txt`:

```
[2026-02-18 10:15:23] Package: langchain
  ├─ PyPI metadata extracted: docs_url=docs.langchain.com, repo_url=github.com/langchain-ai/langchain
  ├─ llms.txt discovery: Probing 10 candidate URLs
  ├─ llms.txt found: https://python.langchain.com/llms.txt (probe #4)
  ├─ Content validation: PASSED (text/plain, 15KB, markdown header detected)
  ├─ Hub detection: NOT a hub
  └─ Grouped with: langchain-openai, langchain-core, langchain-community (same repo_url)

[2026-02-18 10:15:45] Package: pydantic-ai
  ├─ PyPI metadata extracted: docs_url=ai.pydantic.dev, repo_url=github.com/pydantic/pydantic-ai
  ├─ llms.txt discovery: Probing 10 candidate URLs
  ├─ llms.txt found: https://ai.pydantic.dev/llms.txt (probe #1)
  ├─ Content validation: PASSED (text/plain, 8KB, markdown header detected)
  ├─ Hub detection: NOT a hub
  └─ Separate DocSource: Different repo_url from pydantic (github.com/pydantic/pydantic-ai vs github.com/pydantic/pydantic)

[2026-02-18 10:16:02] Package: some-broken-package
  ├─ PyPI metadata extracted: docs_url=None, repo_url=None
  ├─ llms.txt discovery: SKIPPED (no docs_url)
  └─ Excluded: No documentation URL available
```

---

## 8. Quality Assurance

### 8.1 Pre-Flight Checks

Before starting the build:
- Verify `hugovk/top-pypi-packages` is accessible
- Verify PyPI API is reachable
- Verify manual override file is valid YAML
- Verify output directory is writable

### 8.2 Validation Checks

After building the registry:

```python
async def validate_registry(registry: list[DocSource]) -> ValidationReport:
    """Run quality checks on generated registry"""

    issues: list[str] = []

    # Check 1: No duplicate IDs
    ids = [doc.id for doc in registry]
    if len(ids) != len(set(ids)):
        duplicates = {id for id in ids if ids.count(id) > 1}
        issues.append(f"Duplicate IDs found: {duplicates}")

    # Check 2: All URLs are valid (return 200)
    for doc in registry:
        if doc.docs_url:
            status = await check_url_status(doc.docs_url)
            if status != 200:
                issues.append(f"{doc.id}: docs_url returns {status}")

        if doc.llms_txt and doc.llms_txt.url:
            status = await check_url_status(doc.llms_txt.url)
            if status != 200:
                issues.append(f"{doc.id}: llms_txt.url returns {status}")

    # Check 3: All packages have docs or marked N/A
    for doc in registry:
        if not doc.docs_url and not doc.repo_url:
            issues.append(f"{doc.id}: No docs_url or repo_url")

    # Check 4: Grouping consistency
    # Packages with same repo_url should be in same DocSource
    repo_to_packages = {}
    for doc in registry:
        if doc.repo_url:
            if doc.repo_url not in repo_to_packages:
                repo_to_packages[doc.repo_url] = []
            repo_to_packages[doc.repo_url].extend(doc.packages.get("pypi", []))

    for repo_url, packages in repo_to_packages.items():
        # Find all DocSources with this repo_url
        doc_sources = [d for d in registry if d.repo_url == repo_url]
        if len(doc_sources) > 1:
            issues.append(f"Grouping inconsistency: repo {repo_url} split across {len(doc_sources)} DocSources")

    # Check 5: Alias uniqueness (no alias maps to multiple libraries)
    alias_to_lib = {}
    for doc in registry:
        for alias in doc.aliases:
            if alias in alias_to_lib:
                issues.append(f"Alias '{alias}' maps to both {alias_to_lib[alias]} and {doc.id}")
            alias_to_lib[alias] = doc.id

    return ValidationReport(
        total_doc_sources=len(registry),
        total_packages=sum(len(doc.packages.get("pypi", [])) for doc in registry),
        with_llms_txt=sum(1 for doc in registry if doc.llms_txt),
        issues=issues,
    )
```

### 8.3 Statistics

Generate build statistics:

```json
{
  "build_timestamp": "2026-02-18T10:30:00Z",
  "input": {
    "total_packages_processed": 1000,
    "pypi_api_calls": 1000,
    "llms_txt_probes": 8523,
    "manual_overrides_applied": 15
  },
  "output": {
    "total_doc_sources": 687,
    "with_llms_txt": 412,
    "without_llms_txt": 275,
    "hubs_resolved": 3,
    "packages_grouped": 313,
    "packages_standalone": 687
  },
  "quality": {
    "validation_errors": 0,
    "warnings": 5,
    "excluded_packages": 45
  },
  "performance": {
    "total_duration_seconds": 342,
    "avg_package_processing_time_ms": 342
  }
}
```

---

## 9. Output Format

### 9.1 known-libraries.json

**Key change**: All entries include `llmsTxtAvailable` field to explicitly mark availability.

```json
[
  {
    "id": "langchain-ai/langchain",
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
    "llmsTxtAvailable": true,
    "llmsTxt": {
      "url": "https://python.langchain.com/llms.txt",
      "platform": "mintlify",
      "lastValidated": "2026-02-20T10:15:23Z"
    }
  },
  {
    "id": "requests/requests",
    "name": "Requests",
    "docsUrl": "https://requests.readthedocs.io",
    "repoUrl": "https://github.com/psf/requests",
    "languages": ["python"],
    "packages": {
      "pypi": ["requests"]
    },
    "aliases": [],
    "llmsTxtAvailable": false
  },
  {
    "id": "pydantic/pydantic",
    "name": "Pydantic",
    "docsUrl": "https://docs.pydantic.dev/latest",
    "repoUrl": "https://github.com/pydantic/pydantic",
    "languages": ["python"],
    "packages": {
      "pypi": ["pydantic", "pydantic-core", "pydantic-settings"]
    },
    "aliases": ["pydanctic"],
    "llmsTxtAvailable": true,
    "llmsTxt": {
      "url": "https://docs.pydantic.dev/latest/llms.txt",
      "platform": "custom",
      "lastValidated": "2026-02-20T10:16:15Z"
    }
  }
]
```

### 9.2 File Size Estimates

**Scope**:
- **Community edition**: Top 1000 PyPI + ~350 curated (llms-txt-hub, MCP, GitHub) = **~1,350 total entries**
- **Enterprise edition**: Top 5000 PyPI + ~350 curated = **~5,350 total entries**

**Expected llms.txt coverage**: ~60-70% of PyPI packages, ~95%+ of curated sources

| Registry Size | Entries | With llms.txt | File Size | Load Time |
|---------------|---------|---------------|-----------|-----------|
| Community | 1,350 | ~850 (63%) | ~300KB | ~10ms |
| Enterprise | 5,350 | ~3,400 (64%) | ~1.2MB | ~35ms |

---

## 10. CI/CD Automation

### 10.1 GitHub Actions Workflow

```yaml
# .github/workflows/update-registry.yml
name: Update Registry

on:
  schedule:
    # Weekly: Every Monday at 3 AM UTC
    - cron: '0 3 * * 1'
  workflow_dispatch:  # Allow manual trigger

jobs:
  build-registry:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install -r scripts/requirements.txt

      - name: Run build script
        run: python scripts/build_registry.py --limit 1000
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}

      - name: Validate registry
        run: python scripts/validate_registry.py data/known-libraries.json

      - name: Generate stats
        run: python scripts/generate_stats.py data/known-libraries.json > data/build_stats.json

      - name: Commit and push
        run: |
          git config user.name "Pro-Context Bot"
          git config user.email "bot@pro-context.dev"
          git add data/known-libraries.json data/build_stats.json data/build_log.txt
          git commit -m "chore: update registry ($(date +%Y-%m-%d))"
          git push
```

### 10.2 Manual Execution

```bash
# Community edition (1000 packages)
python scripts/build_registry.py --limit 1000

# Enterprise edition (5000 packages)
python scripts/build_registry.py --limit 5000

# With validation
python scripts/build_registry.py --limit 1000 --validate

# Dry run (no output)
python scripts/build_registry.py --limit 100 --dry-run
```

---

## 11. Monitoring and Maintenance

### 11.1 Key Metrics

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| Build success rate | 100% | < 95% |
| Registry size (DocSources) | 700 (1K packages) | < 600 or > 800 |
| llms.txt coverage | 60-70% | < 50% |
| Build duration | < 10 minutes | > 15 minutes |
| Validation errors | 0 | > 5 |

### 11.2 Maintenance Tasks

**Weekly**:
- Review build logs for new failures
- Check for new popular packages (hugovk updates monthly)
- Validate stale llms.txt URLs (> 30 days old)

**Monthly**:
- Full rebuild with latest top-pypi-packages snapshot
- Review manual overrides for outdated entries
- Check for new llms.txt adoption (probe previously failed URLs)

**Quarterly**:
- Review grouping rules for edge cases
- Update URL patterns based on new deployment trends
- Performance optimization (reduce probe count, improve caching)

### 11.3 Community Contributions

Users can contribute via PR:
1. Add missing libraries to `data/manual_overrides.yaml`
2. Correct package groupings
3. Report broken llms.txt URLs
4. Add aliases for common misspellings

PR template:
```markdown
## Type of Change
- [ ] Add new library
- [ ] Fix incorrect grouping
- [ ] Report broken URL
- [ ] Add aliases

## Details
Library: [name]
Issue: [description]
Proposed fix: [what you're changing]

## Validation
- [ ] I've verified the docs URL is correct
- [ ] I've verified the llms.txt URL returns valid content
- [ ] I've checked this doesn't duplicate an existing entry
```

---

## Appendix A: Research References

All design decisions in this document are based on empirical research:

1. **llms.txt deployment patterns** — Analysis of 70+ libraries
   See: `docs/research/llms-txt-deployment-patterns.md`

2. **llms.txt resolution strategy** — Validation approach, URL patterns
   See: `docs/research/llms-txt-resolution-strategy.md`

3. **Package grouping** — Repository URL analysis across ecosystems
   See: `docs/specs/05-library-resolution.md` Section 6.3

4. **Hub structures** — Supabase, Svelte, TanStack case studies
   See: `docs/specs/05-library-resolution.md` Section 3.2

---

## Appendix B: Decision Log

| Decision | Rationale | Date |
|----------|-----------|------|
| Use Repository URL for grouping | Most reliable signal for monorepo sub-packages | 2026-02-16 |
| Validate llms.txt content (not just HTTP 200) | Many sites return HTML error pages with 200 status | 2026-02-17 |
| Build-time discovery only (no runtime JIT) | Ensures quality, eliminates false positives | 2026-02-18 |
| Hub resolution creates separate DocSources | Each variant llms.txt is a distinct documentation source | 2026-02-17 |
| Weekly registry updates (community) | Balance freshness vs build cost | 2026-02-18 |

---

**End of Document**
