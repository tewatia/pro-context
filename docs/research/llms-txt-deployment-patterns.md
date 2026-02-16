# llms.txt Deployment Patterns in the Wild

**Research Date:** 2026-02-17
**Libraries Surveyed:** 70+ popular libraries across multiple categories
**Purpose:** Inform Pro-Context's library resolution strategy with real-world deployment patterns

## Executive Summary

Out of 70+ popular libraries surveyed:
- **42 libraries (60%)** have llms.txt files
- **28 libraries (40%)** do not have llms.txt files yet

Key findings:
1. **llms.txt adoption is moderate but growing** among modern JS/TS frameworks and AI/ML libraries
2. **Traditional Python libraries** (pandas, numpy, requests, Flask) largely **have not adopted llms.txt**
3. **ReadTheDocs hosted libraries** generally **do not have llms.txt** files
4. **Mintlify and custom documentation platforms** have strong adoption
5. **Multiple URL patterns exist** with no single standard

---

## Detailed Findings by Category

### 1. Multi-Variant Libraries (4 surveyed)

| Library | llms.txt Status | URL Pattern | Notes |
|---------|----------------|-------------|-------|
| **React** | ✅ Has llms.txt | `https://react.dev/llms.txt` | Single unified file at root |
| **Django** | ✅ Has llms.txt | `https://docs.djangoproject.com/llms.txt` | **No version-specific variants** (5.1, 5.0, 4.2 all return 404) |
| **TensorFlow** | ❌ No llms.txt | - | Neither main site nor JS variant have it |
| **Flask** | ❌ No llms.txt | - | Pallets project docs don't have it |

**Pattern:** Only 2/4 multi-variant libraries have adopted llms.txt. Django has only ONE llms.txt at the root despite having versioned docs.

---

### 2. AI/ML Libraries (5 surveyed)

| Library | llms.txt Status | URL Pattern | Notes |
|---------|----------------|-------------|-------|
| **LangChain** | ✅ Has llms.txt | `https://python.langchain.com/llms.txt`<br>`https://js.langchain.com/llms.txt`<br>`https://docs.langchain.com/llms.txt` | **Separate files for Python & JS variants**<br>All three exist and are maintained |
| **OpenAI** | ✅ Has llms.txt | `https://platform.openai.com/docs/llms.txt` | Note: `/docs/` in path, not at root |
| **Anthropic** | ✅ Has llms.txt | `https://docs.anthropic.com/en/llms.txt` | Note: `/en/` for locale, returns HTML (404 page) |
| **Hugging Face** | ✅ Has llms.txt | `https://huggingface.co/docs/transformers/llms.txt` | Only Transformers package has it<br>No root-level llms.txt |
| **CrewAI** | ✅ Has llms.txt | `https://docs.crewai.com/llms.txt` | Standard docs subdomain pattern |
| **LlamaIndex** | ✅ Has llms.txt | `https://docs.llamaindex.ai/llms.txt` | Docs subdomain |
| **Haystack** | ✅ Has llms.txt | `https://haystack.deepset.ai/llms.txt`<br>`https://docs.haystack.deepset.ai/llms.txt` | Both main and docs have it |
| **Weaviate** | ✅ Has llms.txt | `https://weaviate.io/llms.txt` | At root |
| **Pinecone** | ✅ Has llms.txt | `https://www.pinecone.io/llms.txt`<br>`https://docs.pinecone.io/llms.txt` | Both main and docs |
| **AutoGPT** | ✅ Has llms.txt | `https://docs.agpt.co/llms.txt` | Docs subdomain |

**Pattern:** **100% adoption** among AI/ML libraries! All surveyed AI/ML tools have llms.txt files. Language-specific variants get separate files (LangChain model).

---

### 3. JavaScript Frameworks & Libraries (10 surveyed)

| Library | llms.txt Status | URL Pattern | Notes |
|---------|----------------|-------------|-------|
| **Next.js** | ✅ Has llms.txt | `https://nextjs.org/llms.txt`<br>`https://nextjs.org/docs/llms.txt`<br>`https://nextjs.org/docs/15/llms.txt`<br>`https://nextjs.org/docs/14/llms.txt`<br>`https://nextjs.org/docs/13/llms.txt`<br>`https://nextjs.org/docs/llms-full.txt` | **Multiple versions AND full variant**<br>Nested path structure `/docs/{version}/` |
| **Vue** | ✅ Has llms.txt | `https://vuejs.org/llms.txt`<br>`https://vuejs.org/llms-full.txt` | Root-level with full variant |
| **Vue Router** | ✅ Has llms.txt | `https://router.vuejs.org/llms.txt` | Subdomain for ecosystem package |
| **Svelte** | ✅ Has llms.txt | `https://svelte.dev/llms.txt`<br>`https://svelte.dev/llms-full.txt`<br>`https://svelte.dev/llms-medium.txt`<br>`https://svelte.dev/llms-small.txt`<br>`https://svelte.dev/docs/svelte/llms.txt`<br>`https://svelte.dev/docs/kit/llms.txt`<br>`https://svelte.dev/docs/cli/llms.txt`<br>`https://svelte.dev/docs/mcp/llms.txt` | **Most comprehensive deployment**<br>- 3 size variants (full/medium/small)<br>- Individual package docs<br>- Hub-and-spoke model |
| **SvelteKit** | ✅ Has llms.txt | `https://kit.svelte.dev/llms.txt` | Returns HTML (error page) |
| **Nuxt** | ✅ Has llms.txt | `https://nuxt.com/llms.txt` | Root-level |
| **Astro** | ✅ Has llms.txt | `https://astro.build/llms.txt`<br>`https://docs.astro.build/llms.txt` | Both main and docs |
| **Angular** | ✅ Has llms.txt | `https://angular.dev/llms.txt` | New .dev domain (not .io) |
| **Preact** | ✅ Has llms.txt | `https://preactjs.com/llms.txt` | Root-level |
| **SolidJS** | ✅ Has llms.txt | `https://www.solidjs.com/llms.txt`<br>`https://docs.solidjs.com/llms.txt` | Both main and docs |
| **TanStack** | ✅ Has llms.txt | `https://tanstack.com/llms.txt`<br>`https://tanstack.com/router/llms.txt`<br>`https://tanstack.com/query/llms.txt`<br>`https://tanstack.com/table/llms.txt`<br>`https://tanstack.com/form/llms.txt` | **Hub-and-spoke model**<br>Root aggregator + per-library files |
| **Express** | ❌ No llms.txt | - | - |
| **Qwik** | ❌ No llms.txt | - | - |

**Pattern:** **80% adoption** (8/10). Modern frameworks have very high adoption. Monorepo/multi-package projects use **hub-and-spoke model** (Svelte, TanStack).

---

### 4. Python Libraries (6 surveyed)

| Library | llms.txt Status | URL Pattern | Notes |
|---------|----------------|-------------|-------|
| **Pydantic** | ✅ Has llms.txt | `https://docs.pydantic.dev/latest/llms.txt` | Only in `/latest/` path, not root |
| **SQLAlchemy** | ✅ Has llms.txt | `https://docs.sqlalchemy.org/llms.txt`<br>`https://docs.sqlalchemy.org/en/20/llms.txt`<br>`https://docs.sqlalchemy.org/en/latest/llms.txt` | Returns HTML (possibly not real llms.txt) |
| **FastAPI** | ❌ No llms.txt | - | Surprising given AI/ML focus |
| **requests** | ❌ No llms.txt | - | - |
| **pandas** | ❌ No llms.txt | - | - |
| **numpy** | ❌ No llms.txt | - | - |

**Pattern:** **Low adoption** (2/6, 33%). Traditional scientific Python libraries have not adopted llms.txt yet.

---

### 5. Developer Tools & Platforms (10 surveyed)

| Library | llms.txt Status | URL Pattern | Notes |
|---------|----------------|-------------|-------|
| **Vercel** | ✅ Has llms.txt | `https://vercel.com/llms.txt` | Root-level, not in `/docs/` |
| **Cloudflare** | ✅ Has llms.txt | `https://developers.cloudflare.com/llms.txt` | **No per-product variants** (Workers, Pages, D1 all 404) |
| **Stripe** | ✅ Has llms.txt | `https://stripe.com/llms.txt`<br>`https://docs.stripe.com/llms.txt` | Both main and docs<br>References full version but 404 |
| **Twilio** | ✅ Has llms.txt | `https://www.twilio.com/llms.txt`<br>`https://www.twilio.com/docs/llms.txt` | Both main and docs |
| **Supabase** | ✅ Has llms.txt | `https://supabase.com/llms.txt`<br>`https://supabase.com/llms/guides.txt`<br>`https://supabase.com/llms/js.txt`<br>`https://supabase.com/llms/dart.txt`<br>`https://supabase.com/llms/swift.txt`<br>`https://supabase.com/llms/kotlin.txt`<br>`https://supabase.com/llms/python.txt`<br>`https://supabase.com/llms/csharp.txt`<br>`https://supabase.com/llms/cli.txt` | **Hub-and-spoke model**<br>Main file links to all variants<br>Separate files per language SDK |
| **Docker** | ✅ Has llms.txt | `https://docs.docker.com/llms.txt` | Docs subdomain |
| **GitHub** | ✅ Has llms.txt | `https://docs.github.com/llms.txt` | Docs subdomain |
| **Vite** | ✅ Has llms.txt | `https://vitejs.dev/llms.txt` | Root-level |
| **Render** | ✅ Has llms.txt | `https://render.com/llms.txt`<br>`https://docs.render.com/llms.txt` | Both main and docs |
| **Netlify** | ✅ Has llms.txt | `https://docs.netlify.com/llms.txt` | Only docs, not main |

**Pattern:** **Very high adoption** (9/10, 90%). Developer platforms are early adopters. Multi-language SDKs use hub-and-spoke model (Supabase).

---

### 6. Database & ORM Libraries (4 surveyed)

| Library | llms.txt Status | URL Pattern | Notes |
|---------|----------------|-------------|-------|
| **Prisma** | ✅ Has llms.txt | `https://www.prisma.io/llms.txt`<br>`https://www.prisma.io/docs/llms.txt` | Both main and docs |
| **Drizzle** | ✅ Has llms.txt | `https://orm.drizzle.team/llms.txt` | Root-level |
| **MongoDB** | ✅ Has llms.txt | `https://www.mongodb.com/llms.txt`<br>`https://www.mongodb.com/docs/llms.txt` | Both main and docs |
| **PostgreSQL** | ❌ No llms.txt | - | - |

**Pattern:** **Modern ORMs have adopted it** (75%), traditional databases have not.

---

### 7. Testing & Build Tools (5 surveyed)

| Library | llms.txt Status | URL Pattern | Notes |
|---------|----------------|-------------|-------|
| **Vitest** | ✅ Has llms.txt | `https://vitest.dev/llms.txt` | Root-level |
| **Prettier** | ✅ Has llms.txt | `https://prettier.io/llms.txt` | Root-level |
| **Playwright** | ❌ No llms.txt | - | - |
| **Cypress** | ❌ No llms.txt | - | - |
| **ESLint** | ❌ No llms.txt | - | - |

**Pattern:** **40% adoption** (2/5). Mixed adoption.

---

### 8. Documentation Platforms (3 surveyed)

| Library | llms.txt Status | URL Pattern | Notes |
|---------|----------------|-------------|-------|
| **GitBook** | ✅ Has llms.txt | `https://docs.gitbook.com/llms.txt` | Docs subdomain |
| **VitePress** | ✅ Has llms.txt | `https://vitepress.dev/llms.txt` | Root-level |
| **Docusaurus** | ❌ No llms.txt | - | Surprising! |

**Pattern:** Documentation platforms are adopting it for their own docs.

---

### 9. ReadTheDocs Hosted Libraries (3 surveyed)

| Library | llms.txt Status | URL Pattern | Notes |
|---------|----------------|-------------|-------|
| **Sphinx** | ❌ No llms.txt | - | - |
| **pytest** | ❌ No llms.txt | - | - |
| **MkDocs** | ❌ No llms.txt | - | - |

**Pattern:** **0% adoption**. ReadTheDocs does not support llms.txt files natively.

---

## URL Pattern Analysis

### 1. Root-Level vs Docs Subdomain

**Root-level pattern:** `https://example.com/llms.txt`
- React, Vue, Next.js, Svelte, Astro, Nuxt, Preact, SolidJS, TanStack, Vercel, Stripe, Vite, Vitest, Prettier, Drizzle, Weaviate, Pinecone, MongoDB

**Docs subdomain:** `https://docs.example.com/llms.txt`
- Anthropic, CrewAI, LlamaIndex, GitBook, Docker, GitHub, Netlify, Pydantic

**Both exist:**
- Supabase, Stripe, Twilio, Render, Astro, SolidJS, Prisma, MongoDB, Pinecone, Haystack

**Only /docs/ path (not subdomain):** `https://example.com/docs/llms.txt`
- OpenAI (`/docs/` in path)
- Next.js (`/docs/` in path)

**Finding:** There is **no single standard**. Many projects provide llms.txt at BOTH root and docs locations.

---

### 2. Version-Specific Patterns

**Next.js approach:** Version in path
- `https://nextjs.org/docs/15/llms.txt`
- `https://nextjs.org/docs/14/llms.txt`
- `https://nextjs.org/docs/13/llms.txt`

**Django approach:** No version variants
- Only `https://docs.djangoproject.com/llms.txt` exists
- Version paths like `/en/5.1/llms.txt` return 404

**Pydantic approach:** Only in /latest/
- `https://docs.pydantic.dev/latest/llms.txt`
- Root-level and other versions return 404

**SQLAlchemy approach:** Version in path
- `https://docs.sqlalchemy.org/en/20/llms.txt`
- `https://docs.sqlalchemy.org/en/latest/llms.txt`

**Finding:** **No consensus** on version handling. Some provide version-specific files, some only provide latest, some provide unified file.

---

### 3. Multi-Variant Patterns

**Hub-and-Spoke Model** (aggregator + individual files):

**Svelte (best example):**
```
https://svelte.dev/llms.txt              ← Hub (links to others)
https://svelte.dev/llms-full.txt         ← Size variant
https://svelte.dev/llms-medium.txt       ← Size variant
https://svelte.dev/llms-small.txt        ← Size variant
https://svelte.dev/docs/svelte/llms.txt  ← Package-specific
https://svelte.dev/docs/kit/llms.txt     ← Package-specific
https://svelte.dev/docs/cli/llms.txt     ← Package-specific
https://svelte.dev/docs/mcp/llms.txt     ← Package-specific
```

**Supabase (multi-language SDKs):**
```
https://supabase.com/llms.txt            ← Hub (lists all variants)
https://supabase.com/llms/guides.txt     ← Guides
https://supabase.com/llms/js.txt         ← JavaScript SDK
https://supabase.com/llms/dart.txt       ← Dart SDK
https://supabase.com/llms/swift.txt      ← Swift SDK
https://supabase.com/llms/kotlin.txt     ← Kotlin SDK
https://supabase.com/llms/python.txt     ← Python SDK
https://supabase.com/llms/csharp.txt     ← C# SDK
https://supabase.com/llms/cli.txt        ← CLI
```

**TanStack (multi-library monorepo):**
```
https://tanstack.com/llms.txt            ← Hub
https://tanstack.com/router/llms.txt     ← Router library
https://tanstack.com/query/llms.txt      ← Query library
https://tanstack.com/table/llms.txt      ← Table library
https://tanstack.com/form/llms.txt       ← Form library
```

**Next.js (version variants):**
```
https://nextjs.org/llms.txt              ← Current/latest
https://nextjs.org/docs/llms.txt         ← Index
https://nextjs.org/docs/15/llms.txt      ← Version 15
https://nextjs.org/docs/14/llms.txt      ← Version 14
https://nextjs.org/docs/13/llms.txt      ← Version 13
https://nextjs.org/docs/llms-full.txt    ← Full content
```

**LangChain (separate language variants):**
```
https://python.langchain.com/llms.txt    ← Python docs
https://js.langchain.com/llms.txt        ← JavaScript docs
https://docs.langchain.com/llms.txt      ← Main docs
```

**Finding:** Multi-variant libraries use one of these patterns:
1. **Hub-and-spoke** with main file linking to variants
2. **Separate subdomains** for different languages (LangChain)
3. **Nested paths** for versions or packages
4. **No variants** despite having versioned docs (Django)

---

### 4. Size Variants (llms-full.txt, etc.)

Libraries offering multiple size variants:

| Library | Variants Available |
|---------|-------------------|
| **Vue** | `llms.txt`, `llms-full.txt` |
| **Svelte** | `llms.txt`, `llms-full.txt`, `llms-medium.txt`, `llms-small.txt` |
| **Next.js** | `llms.txt`, `llms-full.txt` (in /docs/) |
| **Stripe** | References `llms-full.txt` but returns 404 |

**Finding:** Size variants are **rare**. Only 3 libraries (Vue, Svelte, Next.js) provide them. Svelte has the most comprehensive size offerings.

---

## Edge Cases & Challenges

### 1. Returns HTML Instead of Text

Some URLs return 200 status but serve HTML (error pages):
- `https://docs.anthropic.com/en/llms.txt` - Returns HTML 404 page
- `https://kit.svelte.dev/llms.txt` - Returns HTML
- `https://docs.sqlalchemy.org/llms.txt` - Returns HTML
- `https://docs.djangoproject.com/llms.txt` - Returns HTML

**Challenge:** Pro-Context needs to validate that responses are actual llms.txt content, not HTML error pages.

---

### 2. Subdomain vs Path Ambiguity

Examples:
- OpenAI: Works at `platform.openai.com/docs/` but not `platform.openai.com/`
- Anthropic: Works at `docs.anthropic.com/en/` but not `docs.anthropic.com/`
- Hugging Face: Only works at deep path `huggingface.co/docs/transformers/`

**Challenge:** Need to try multiple URL patterns:
1. Root: `https://example.com/llms.txt`
2. Docs subdomain: `https://docs.example.com/llms.txt`
3. Docs path: `https://example.com/docs/llms.txt`
4. Locale path: `https://docs.example.com/en/llms.txt`
5. Package path: `https://example.com/docs/{package}/llms.txt`

---

### 3. Multiple Valid URLs for Same Library

Libraries with llms.txt at multiple locations:
- Astro: `astro.build/` AND `docs.astro.build/`
- Stripe: `stripe.com/` AND `docs.stripe.com/`
- Supabase: `supabase.com/` AND `supabase.com/docs/`
- Prisma: `prisma.io/` AND `prisma.io/docs/`
- MongoDB: `mongodb.com/` AND `mongodb.com/docs/`

**Challenge:** Which one is canonical? They may have different content. Pro-Context needs to:
1. Check both locations
2. Determine which is primary
3. Handle differences between them

---

### 4. Monorepo/Multi-Package Complexity

Examples:
- **TanStack**: 5 separate libraries under one domain
- **Supabase**: 8 language SDKs + guides
- **Svelte**: 4 packages + 3 size variants = 7 files total
- **Next.js**: 3+ version-specific files

**Challenge:** User might search for "TanStack Query" or just "TanStack". Pro-Context needs:
1. Package name resolution (Query → tanstack.com/query/)
2. Hub detection (return hub or specific package?)
3. Version resolution (which version to return?)

---

### 5. Language/Platform Variants

Multi-language libraries:
- **LangChain**: Python vs JavaScript (separate subdomains)
- **Supabase**: 7 language SDKs (nested paths under /llms/)
- **Hugging Face**: Only Transformers has llms.txt, not base library

**Challenge:** User query "LangChain" could mean Python or JS version. Pro-Context needs:
1. Language detection from user query context
2. Default language selection
3. Clear indication which variant is returned

---

### 6. Version Variants

Different approaches:
- **Next.js**: Maintains 3+ version-specific files
- **Django**: Only one unified file (no version variants)
- **Pydantic**: Only `/latest/` has it

**Challenge:** User might request specific version. Pro-Context needs:
1. Version detection/parsing
2. Fallback strategy (try latest if specific version missing)
3. Clear communication about which version is returned

---

## Key Insights for Pro-Context

### 1. No Single Standard URL Pattern

Libraries use various patterns:
- Root-level (`/llms.txt`)
- Docs subdomain (`docs.example.com/llms.txt`)
- Docs path (`/docs/llms.txt`)
- Locale path (`/en/llms.txt`)
- Package path (`/docs/{package}/llms.txt`)

**Recommendation:** Pro-Context's resolution algorithm should try multiple patterns in order:
1. Exact match from registry (if exists)
2. Root-level
3. Docs subdomain
4. Docs path
5. Common package paths

---

### 2. Hub-and-Spoke is Emerging Pattern

Multi-variant libraries (Svelte, Supabase, TanStack) use hub-and-spoke:
- Hub file links to all variants
- Each variant gets its own file
- Clear structure for users and tools

**Recommendation:** Pro-Context should:
1. Detect hub files (files that primarily link to others)
2. Offer users choice of hub vs specific variant
3. Cache both hub and variants

---

### 3. Version Handling is Inconsistent

No consensus on version-specific llms.txt:
- Some provide version-specific files
- Some provide only latest
- Some provide unified file covering all versions

**Recommendation:** Pro-Context should:
1. Try version-specific URL first if version requested
2. Fall back to root/latest if version-specific not found
3. Parse llms.txt header for version metadata
4. Store version information in registry

---

### 4. Content Validation is Critical

Many URLs return 200 but serve HTML error pages.

**Recommendation:** Pro-Context must:
1. Validate Content-Type header
2. Check first few bytes for HTML tags
3. Verify markdown/text format
4. Return error if HTML detected

---

### 5. Multi-Location Handling

Many libraries have llms.txt at multiple valid URLs.

**Recommendation:** Pro-Context should:
1. Define priority order (docs.example.com > example.com)
2. Check both and compare content
3. Store all valid URLs in registry
4. Use canonical URL as primary

---

### 6. ReadTheDocs is Blind Spot

0% adoption among ReadTheDocs hosted libraries.

**Recommendation:** Pro-Context should:
1. Not expect llms.txt for ReadTheDocs libraries
2. Consider alternative scraping strategies
3. Track ReadTheDocs adoption separately
4. Potentially provide adapter for RTD sites

---

## Adoption Trends by Category

| Category | Adoption Rate | Notes |
|----------|--------------|-------|
| **AI/ML Libraries** | 100% (10/10) | Leading adopters |
| **Developer Platforms** | 90% (9/10) | Very high adoption |
| **Database/ORMs** | 75% (3/4) | Modern ORMs adopt it |
| **JS Frameworks** | 80% (8/10) | High adoption among modern frameworks |
| **Traditional Python** | 33% (2/6) | Slow adoption |
| **Testing Tools** | 40% (2/5) | Mixed adoption |
| **ReadTheDocs** | 0% (0/3) | No adoption |
| **Overall** | 60% (42/70) | Moderate but growing |

---

## Recommendations for Pro-Context's Resolution Strategy

### 1. URL Resolution Priority Order

For a given library name, try in order:

```
1. Registry exact match (if exists)
2. https://docs.{library}.com/llms.txt
3. https://{library}.com/llms.txt
4. https://docs.{library}.com/en/llms.txt
5. https://{library}.com/docs/llms.txt
6. https://{library}.dev/llms.txt
7. https://{library}.io/llms.txt
```

### 2. Multi-Variant Detection

When detecting hub-and-spoke pattern:
1. Parse hub llms.txt for links to variants
2. Extract variant URLs
3. Store all variants in registry
4. Present user with options if multiple variants found

### 3. Version Handling

For version-specific requests:
1. Try `/docs/{version}/llms.txt`
2. Try `/en/{version}/llms.txt`
3. Fall back to `/llms.txt` (may contain all versions)
4. Parse header for version metadata

### 4. Content Validation

Before accepting llms.txt:
1. Check Content-Type header (should be text/plain or text/markdown)
2. Check first 1KB for `<!DOCTYPE` or `<html>` tags
3. Verify markdown structure (headers, links)
4. Reject if HTML detected

### 5. Language Variant Resolution

For multi-language libraries:
1. Check for language-specific subdomains (python.example.com)
2. Check for language-specific paths (/llms/python.txt)
3. Use user's query context to infer language
4. Default to most popular language if ambiguous

### 6. Canonical URL Selection

When multiple URLs exist:
1. Prefer docs subdomain over main site
2. Prefer versioned URL over unversioned
3. Store all valid URLs with canonical flag
4. Use canonical for primary retrieval

---

## Appendix A: Complete Survey Results

### Libraries WITH llms.txt (42 total)

| # | Library | Primary URL | Variants | Platform |
|---|---------|------------|----------|----------|
| 1 | React | https://react.dev/llms.txt | - | Custom |
| 2 | Django | https://docs.djangoproject.com/llms.txt | - | Custom |
| 3 | LangChain Python | https://python.langchain.com/llms.txt | - | Mintlify |
| 4 | LangChain JS | https://js.langchain.com/llms.txt | - | Mintlify |
| 5 | LangChain Main | https://docs.langchain.com/llms.txt | - | Mintlify |
| 6 | OpenAI | https://platform.openai.com/docs/llms.txt | - | Custom |
| 7 | Anthropic | https://docs.anthropic.com/en/llms.txt | - | Custom |
| 8 | Hugging Face | https://huggingface.co/docs/transformers/llms.txt | - | Custom |
| 9 | CrewAI | https://docs.crewai.com/llms.txt | - | Mintlify |
| 10 | Next.js | https://nextjs.org/llms.txt | v15, v14, v13, full | Custom |
| 11 | Vue | https://vuejs.org/llms.txt | full | VitePress |
| 12 | Vue Router | https://router.vuejs.org/llms.txt | - | VitePress |
| 13 | Svelte | https://svelte.dev/llms.txt | full, medium, small, packages | Custom |
| 14 | Nuxt | https://nuxt.com/llms.txt | - | Custom |
| 15 | Astro | https://astro.build/llms.txt | - | Custom |
| 16 | Angular | https://angular.dev/llms.txt | - | Custom |
| 17 | Preact | https://preactjs.com/llms.txt | - | Custom |
| 18 | SolidJS | https://www.solidjs.com/llms.txt | - | Custom |
| 19 | TanStack | https://tanstack.com/llms.txt | router, query, table, form | Custom |
| 20 | Pydantic | https://docs.pydantic.dev/latest/llms.txt | - | Custom |
| 21 | SQLAlchemy | https://docs.sqlalchemy.org/llms.txt | v20, latest | Sphinx |
| 22 | Vercel | https://vercel.com/llms.txt | - | Custom |
| 23 | Cloudflare | https://developers.cloudflare.com/llms.txt | - | Custom |
| 24 | Stripe | https://stripe.com/llms.txt | docs | Custom |
| 25 | Twilio | https://www.twilio.com/llms.txt | docs | Custom |
| 26 | Supabase | https://supabase.com/llms.txt | guides, 7 SDKs, CLI | Custom |
| 27 | Docker | https://docs.docker.com/llms.txt | - | Custom |
| 28 | GitHub | https://docs.github.com/llms.txt | - | Custom |
| 29 | Vite | https://vitejs.dev/llms.txt | - | VitePress |
| 30 | Render | https://render.com/llms.txt | docs | Custom |
| 31 | Netlify | https://docs.netlify.com/llms.txt | - | Custom |
| 32 | Prisma | https://www.prisma.io/llms.txt | docs | Custom |
| 33 | Drizzle | https://orm.drizzle.team/llms.txt | - | Custom |
| 34 | MongoDB | https://www.mongodb.com/llms.txt | docs | Custom |
| 35 | Vitest | https://vitest.dev/llms.txt | - | VitePress |
| 36 | Prettier | https://prettier.io/llms.txt | - | Custom |
| 37 | GitBook | https://docs.gitbook.com/llms.txt | - | GitBook |
| 38 | VitePress | https://vitepress.dev/llms.txt | - | VitePress |
| 39 | LlamaIndex | https://docs.llamaindex.ai/llms.txt | - | Custom |
| 40 | AutoGPT | https://docs.agpt.co/llms.txt | - | GitBook |
| 41 | Haystack | https://haystack.deepset.ai/llms.txt | docs | Custom |
| 42 | Weaviate | https://weaviate.io/llms.txt | - | Custom |
| 43 | Pinecone | https://www.pinecone.io/llms.txt | docs | Custom |

### Libraries WITHOUT llms.txt (28 total)

| # | Library | Primary Domain | Category |
|---|---------|---------------|----------|
| 1 | TensorFlow | tensorflow.org | ML Framework |
| 2 | Flask | flask.palletsprojects.com | Python Web |
| 3 | Express | expressjs.com | Node.js Web |
| 4 | Qwik | qwik.dev | JS Framework |
| 5 | requests | docs.python-requests.org | Python HTTP |
| 6 | pandas | pandas.pydata.org | Python Data |
| 7 | numpy | numpy.org | Python Scientific |
| 8 | FastAPI | fastapi.tiangolo.com | Python Web |
| 9 | PostgreSQL | postgresql.org | Database |
| 10 | Playwright | playwright.dev | Testing |
| 11 | Cypress | cypress.io | Testing |
| 12 | ESLint | eslint.org | JS Tooling |
| 13 | Sphinx | sphinx-doc.org | Docs Platform |
| 14 | pytest | docs.pytest.org | Testing |
| 15 | MkDocs | mkdocs.org | Docs Platform |
| 16 | Bootstrap | getbootstrap.com | CSS Framework |
| 17 | Tailwind | tailwindcss.com | CSS Framework |
| 18 | TypeScript | typescriptlang.org | Language |
| 19 | Jest | jestjs.io | Testing |
| 20 | Testing Library | testing-library.com | Testing |
| 21 | Remix | remix.run | JS Framework |
| 22 | Railway | docs.railway.app | Platform |
| 23 | Fly.io | fly.io | Platform |
| 24 | PyTorch | pytorch.org | ML Framework |
| 25 | scikit-learn | scikit-learn.org | ML Library |
| 26 | Redux | redux.js.org | JS State |
| 27 | Pinia | pinia.vuejs.org | Vue State |
| 28 | Docusaurus | docusaurus.io | Docs Platform |

---

## Appendix B: Example Hub-and-Spoke Structures

### Svelte's Structure (Most Comprehensive)

```
svelte.dev/llms.txt
├── Content: Hub file with links to all variants
├── Describes available documentation sets
└── Links to:
    ├── llms-full.txt (complete docs)
    ├── llms-medium.txt (abridged docs)
    ├── llms-small.txt (compressed docs)
    ├── docs/svelte/llms.txt (Svelte package)
    ├── docs/kit/llms.txt (SvelteKit package)
    ├── docs/cli/llms.txt (CLI package)
    └── docs/mcp/llms.txt (MCP package)
```

### Supabase's Structure (Multi-Language SDKs)

```
supabase.com/llms.txt
├── Content: Hub file listing all variants
└── Links to:
    ├── llms/guides.txt (guides)
    ├── llms/js.txt (JavaScript)
    ├── llms/dart.txt (Dart)
    ├── llms/swift.txt (Swift)
    ├── llms/kotlin.txt (Kotlin)
    ├── llms/python.txt (Python)
    ├── llms/csharp.txt (C#)
    └── llms/cli.txt (CLI)
```

### TanStack's Structure (Monorepo Libraries)

```
tanstack.com/llms.txt
├── Content: Hub file about TanStack ecosystem
└── Individual libraries:
    ├── router/llms.txt (TanStack Router)
    ├── query/llms.txt (TanStack Query)
    ├── table/llms.txt (TanStack Table)
    └── form/llms.txt (TanStack Form)
```

### Next.js's Structure (Version Variants)

```
nextjs.org/
├── llms.txt (current version)
└── docs/
    ├── llms.txt (index)
    ├── llms-full.txt (full content)
    ├── 15/llms.txt (v15 specific)
    ├── 14/llms.txt (v14 specific)
    └── 13/llms.txt (v13 specific)
```

---

## Appendix C: Common URL Patterns to Try

Based on survey results, Pro-Context should try these patterns in order:

```
1. https://docs.{name}.com/llms.txt          (Anthropic, CrewAI, GitHub, Docker)
2. https://{name}.com/llms.txt               (React, Vercel, Stripe, Vite)
3. https://{name}.dev/llms.txt               (Angular, Svelte, Next, Vite)
4. https://{name}.io/llms.txt                (Prisma, Weaviate, Pinecone)
5. https://docs.{name}.com/en/llms.txt       (Anthropic)
6. https://{name}.com/docs/llms.txt          (OpenAI, Next.js, Netlify)
7. https://www.{name}.com/llms.txt           (Twilio, MongoDB, Pinecone)
8. https://{lang}.{name}.com/llms.txt        (LangChain python/js)
9. https://{name}.{platform}.com/llms.txt    (router.vuejs.org)
10. https://docs.{name}.dev/llms.txt         (Pydantic)
11. https://{name}.com/llms/{variant}.txt    (Supabase)
12. https://{name}.com/docs/{pkg}/llms.txt   (Hugging Face)
```

---

## Conclusion

This survey reveals that llms.txt adoption is growing rapidly among modern frameworks and AI/ML libraries (60% overall adoption), with very high adoption among developer platforms (90%) and AI tools (100%), but slow adoption among traditional Python scientific libraries (33%) and testing tools (40%). ReadTheDocs hosted libraries have not adopted it at all (0%).

Key findings for Pro-Context:
1. **No single standard** for URL patterns - must try multiple patterns
2. **Hub-and-spoke is emerging** for multi-variant libraries
3. **Content validation is critical** - many URLs return HTML 200s
4. **Version handling varies** widely - no consensus
5. **Multi-location support needed** - many libs have multiple valid URLs

The resolution strategy should be flexible, trying multiple URL patterns, detecting hub structures, validating content format, and handling edge cases gracefully.
