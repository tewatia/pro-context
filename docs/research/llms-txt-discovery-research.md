# llms.txt Discovery Research & Approach

**Date:** 2026-02-17
**Status:** Pending Review & Discussion
**Purpose:** Document research findings on discovering libraries with llms.txt files to inform Pro-Context's library resolution strategy

---

## Executive Summary

This document captures research on how to systematically discover and catalog libraries that have published llms.txt files. The goal is to build a registry that will enable Pro-Context to quickly resolve library names to their llms.txt documentation sources.

**Key Finding:** llms.txt files exist on deployed documentation websites (e.g., docs.anthropic.com/llms.txt), NOT in GitHub repositories. Discovery must be web-based, not git-based.

---

## Research Findings

### Finding #1: llms.txt Location

**Critical Discovery:** llms.txt files are typically NOT stored in GitHub repositories. They exist only on deployed documentation sites.

**Validation:**
- ✅ LangChain: Has llms.txt at `https://docs.langchain.com/llms.txt`
  - NOT in GitHub repo: `github.com/langchain-ai/langchain`
- ✅ ElevenLabs: Has llms.txt at `https://elevenlabs.io/docs/llms.txt`
  - Verified accessible, contains structured documentation index
- ✅ Anthropic SDK: NO llms.txt in `github.com/anthropics/anthropic-sdk-python`
  - Only exists at `https://docs.anthropic.com/llms.txt`

**Implication:** Cannot use GitHub Code Search as primary discovery method. Must use web crawling.

---

### Finding #2: Mintlify Auto-Generation

**Discovery:** Mintlify automatically generates llms.txt for ALL hosted documentation sites (rolled out November 2024).

**Details:**
- **Automatic:** Every Mintlify-hosted site gets llms.txt with zero configuration
- **Always current:** Updates automatically when docs change, no maintenance required
- **Two files generated:**
  - `/llms.txt` - Structured index of all pages (like a sitemap for AI)
  - `/llms-full.txt` - Complete documentation content in one file
- **Structure:** Pages listed alphabetically, descriptions pulled from frontmatter
- **Override option:** Sites can provide custom llms.txt to replace auto-generated version
- **Limitation:** Not available for authenticated/private documentation

**Scale:** Thousands of sites gained llms.txt overnight (November 2024) when Mintlify rolled this out.

**Known Mintlify Customers with llms.txt:**
- Anthropic (docs.anthropic.com)
- Cursor (docs.cursor.com)
- Vercel (vercel.com/docs)
- Pinecone (docs.pinecone.io)
- Replit (docs.replit.com)
- LangChain (docs.langchain.com)
- CrewAI (docs.crewai.com)
- Fireworks (docs.fireworks.ai)
- ElevenLabs (elevenlabs.io/docs)
- Cohere (docs.cohere.com)

**Mintlify Detection Signals:**
- Check for meta tag: `<meta name="generator" content="Mintlify">`
- Check for Mintlify-specific scripts in page source
- Test for both `/llms.txt` and `/llms-full.txt` presence

---

### Finding #3: Curated Registries Exist

**Available Resources:**

1. **llms-txt-hub** (github.com/thedaviddias/llms-txt-hub)
   - Largest community-maintained directory
   - 100+ entries as of February 2026
   - Categories: AI/ML, Developer Tools, Data & Analytics, Infrastructure, etc.
   - Regularly updated by community

2. **Awesome-llms-txt** (github.com/SecretiveShell/Awesome-llms-txt)
   - Index of llms.txt files across the web
   - Community-curated
   - Good for seed data

3. **GitHub Topics: llms-txt** (github.com/topics/llms-txt)
   - Repositories tagged with llms-txt topic
   - Mix of tools and documentation sites

**Use Case:** These provide excellent seed data for initial registry (quick win, 100-200 entries).

---

### Finding #4: Adoption Statistics

**Current State (as of February 2026):**
- Only ~951 domains had llms.txt as of mid-2025 (per NerdyData)
- Major boost in November 2024 when Mintlify auto-deployed to all customers
- Now estimated at 2000-3000+ sites (primarily Mintlify-hosted)
- Growing but still niche adoption

**Notable Adopters:**
- AI companies: Anthropic, OpenAI, Cohere, ElevenLabs
- Developer tools: Cursor, Replit, Vercel, Cloudflare
- Documentation platforms: Mintlify (auto), some GitBook sites

**Trend:** Adoption increasing as awareness grows, especially among developer-focused companies.

---

## Discovery Strategies (For Discussion)

### Option 1: Web Crawling from Known Sources

**Approach:**
```
Step 1: Seed with curated lists
├─ Scrape llms-txt-hub (100+ confirmed entries)
├─ Extract from Awesome-llms-txt
└─ Pull from GitHub topics: llms-txt

Step 2: Package manager mapping
├─ Get top N packages from npm, PyPI, RubyGems, crates.io
├─ Extract homepage/docs_url from package metadata
└─ Test common URL patterns:
    - https://docs.{library}.com/llms.txt
    - https://{library}.readthedocs.io/llms.txt
    - https://{library}.github.io/llms.txt
    - https://{library}.com/docs/llms.txt

Step 3: Validate all discovered URLs
├─ HTTP HEAD/GET request to verify 200 OK
├─ Basic content validation (starts with markdown header)
└─ Store validated entries in registry
```

**Pros:**
- Most comprehensive coverage
- Finds sites without GitHub presence
- Discovers non-Mintlify implementations
- Scalable to different package ecosystems

**Cons:**
- Requires many HTTP requests (rate limiting concerns)
- Slower than git-based approaches
- May have false positives from redirects
- Needs periodic re-validation (sites go down)

**Estimated Coverage:** 500-1000 libraries initially, expandable

**Maintenance:** Weekly/monthly re-crawl to discover new llms.txt files

---

### Option 2: Mintlify Site Discovery (Focused)

**Approach:**
```
Step 1: Technology detection
├─ Use Wappalyzer API to find sites using Mintlify
├─ Or: Check known doc sites for Mintlify meta tags
└─ All Mintlify sites automatically have llms.txt

Step 2: Pattern-based discovery
├─ Start with known Mintlify customers (50+)
├─ Check competitor/similar sites in same space
└─ Expand from BuiltWith "similar technologies" data

Step 3: Validate & categorize
├─ Confirm llms.txt exists (should be 100% for Mintlify)
├─ Extract library name from domain/path
└─ Categorize by industry/purpose
```

**Pros:**
- Very high success rate (Mintlify auto-generates)
- Fast validation (know it exists before checking)
- Large scale (1000+ Mintlify sites)
- Always includes llms-full.txt bonus

**Cons:**
- Misses non-Mintlify implementations
- Requires Wappalyzer API (paid service, $50-200/mo)
- Only covers documentation platforms, not custom sites
- Doesn't capture GitHub Pages or self-hosted docs

**Estimated Coverage:** 1000+ sites (Mintlify-only)

**Maintenance:** Monitor new Mintlify customers (quarterly)

---

### Option 3: Hybrid Approach (Balanced)

**Approach:**
```
Phase 1: Quick Win (Week 1)
├─ Scrape llms-txt-hub → ~100 entries
├─ Add known Mintlify customers → ~50 entries
├─ Validate all URLs → Initial registry
└─ Deliverable: 150-200 verified llms.txt sources

Phase 2: Package Ecosystem Coverage (Week 2-3)
├─ npm top 500 → map to docs → test llms.txt
├─ PyPI top 500 → map to docs → test llms.txt
├─ Filter: only include if llms.txt exists
└─ Deliverable: +200-300 additional sources

Phase 3: Ongoing Discovery (Monthly)
├─ Monitor GitHub topics: llms-txt
├─ Check Mintlify new customer announcements
├─ Community submissions via GitHub issues
└─ Re-validate existing entries (detect broken links)
```

**Pros:**
- Balanced between speed and coverage
- Phased approach (immediate value in Phase 1)
- Covers multiple discovery methods
- Adapts to llms.txt adoption growth
- Community-extensible

**Cons:**
- Multi-phase complexity
- Still requires HTTP validation overhead
- Package manager mapping may have low hit rate
- Needs ongoing maintenance commitment

**Estimated Coverage:**
- Phase 1: 150-200 libraries (immediate)
- Phase 2: 350-500 libraries (3 weeks)
- Phase 3: 500+ libraries (6 months)

**Maintenance:** Automated weekly GitHub checks + monthly validation runs

---

## Recommended Approach

**Recommendation: Option 3 (Hybrid Approach)**

**Rationale:**

1. **Immediate Value:** Phase 1 delivers 150-200 verified sources within days using existing curated lists. This provides quick validation of the approach and immediate utility for Pro-Context.

2. **Comprehensive Coverage:** Phase 2 extends beyond Mintlify to capture popular libraries across package ecosystems (npm, PyPI), ensuring Pro-Context can resolve major libraries regardless of documentation platform.

3. **Sustainable Growth:** Phase 3 establishes monitoring and community contribution paths, allowing the registry to grow organically as llms.txt adoption increases.

4. **Risk Mitigation:** Phased approach allows course correction based on Phase 1 findings. If hit rates are low in Phase 2, can pivot strategy before investing heavily.

5. **Cost-Effective:** Doesn't require paid APIs (unlike Option 2's Wappalyzer dependency). Uses free GitHub API and public package registry data.

**Alignment with Pro-Context:**
- Supports library resolution strategy (see `05-library-resolution.md`)
- Enables high-priority `LLMsTxtAdapter` in adapter chain
- Provides fast-path resolution before falling back to HTML scraping
- Grows over time as llms.txt standard gains adoption

---

## Integration with Pro-Context

### Library Resolution Impact

The llms.txt registry should be integrated as **Step 0** in the library resolution algorithm:

**Current Flow (from 05-library-resolution.md):**
```
1. Check cache
2. Normalize library name
3. Query package managers
4. Try heuristics (GitHub, docs patterns)
5. Fall back to search
```

**Proposed Flow with llms.txt:**
```
0. Check llms.txt registry [NEW - HIGHEST PRIORITY]
   ↓ (if not found)
1. Check cache
2. Normalize library name
3. Query package managers
4. Try heuristics
5. Fall back to search
```

**Benefits:**
- **Fast:** Direct URL lookup, no heuristics needed
- **Accurate:** Curated by library maintainers
- **AI-Optimized:** Content designed for LLM consumption
- **Structured:** Follows standardized llms.txt format
- **Bonus:** llms-full.txt provides complete docs in one file

---

### Data Model

**Registry Entry Schema:**
```json
{
  "library_name": "anthropic",
  "normalized_name": "anthropic",
  "aliases": ["anthropic-sdk", "claude-sdk"],
  "docs_url": "https://docs.anthropic.com",
  "llms_txt_url": "https://docs.anthropic.com/llms.txt",
  "llms_full_txt_url": "https://docs.anthropic.com/llms-full.txt",
  "github_repo": "anthropics/anthropic-sdk-python",
  "doc_platform": "mintlify",
  "language": "python",
  "package_managers": ["pypi"],
  "stars": 4500,
  "topics": ["ai", "llm", "api"],
  "last_validated": "2026-02-17",
  "validation_status": "active",
  "source": "llms-txt-hub",
  "discovered_at": "2026-02-15"
}
```

**Database Integration (SQLite):**
```sql
-- Add to Pro-Context database (see 03-technical-spec.md)
CREATE TABLE llms_txt_registry (
  id INTEGER PRIMARY KEY,
  library_name TEXT NOT NULL UNIQUE,
  normalized_name TEXT NOT NULL,
  docs_url TEXT NOT NULL,
  llms_txt_url TEXT NOT NULL,
  llms_full_txt_url TEXT,
  github_repo TEXT,
  doc_platform TEXT,
  language TEXT,
  package_managers TEXT, -- JSON array
  stars INTEGER,
  last_validated TEXT,
  validation_status TEXT,
  source TEXT,
  discovered_at TEXT,
  metadata TEXT -- JSON for extensibility
);

CREATE INDEX idx_normalized_name ON llms_txt_registry(normalized_name);
CREATE INDEX idx_validation_status ON llms_txt_registry(validation_status);
```

---

### Adapter Chain Integration

**New Adapter: LLMsTxtAdapter**
```javascript
class LLMsTxtAdapter extends DocumentationAdapter {
  priority = 0; // Highest priority

  async resolve(libraryName) {
    // Check registry
    const entry = await db.get(
      'SELECT * FROM llms_txt_registry WHERE normalized_name = ?',
      normalizeLibraryName(libraryName)
    );

    if (!entry) return null;

    // Validate last check was recent (< 30 days)
    if (isStale(entry.last_validated)) {
      await this.revalidate(entry);
    }

    return {
      type: 'llms-txt',
      url: entry.llms_txt_url,
      fullTextUrl: entry.llms_full_txt_url,
      metadata: {
        docPlatform: entry.doc_platform,
        lastValidated: entry.last_validated
      }
    };
  }

  async revalidate(entry) {
    // Check if llms.txt still exists
    const response = await fetch(entry.llms_txt_url, { method: 'HEAD' });
    const status = response.ok ? 'active' : 'dead';

    await db.run(
      'UPDATE llms_txt_registry SET validation_status = ?, last_validated = ? WHERE id = ?',
      status, new Date().toISOString(), entry.id
    );
  }
}
```

**Benefits:**
- Fast resolution (database lookup)
- Automatic staleness detection
- Graceful degradation (falls back to next adapter if llms.txt is gone)
- Bonus content via llms-full.txt

---

## Open Questions for Discussion

### 1. Approach Selection
- **Question:** Which option do you prefer? (Option 1, 2, or 3)
- **Context:** Option 3 (Hybrid) recommended, but may have tradeoffs
- **Decision needed:** Before any implementation begins

### 2. Coverage Goals
- **Question:** What's the target coverage?
  - Conservative: Top 200 most popular libraries
  - Moderate: Top 500 across major ecosystems
  - Aggressive: 1000+ including niche libraries
- **Context:** Affects Phase 2 scope and HTTP request volume
- **Decision needed:** Informs implementation effort

### 3. Maintenance Strategy
- **Question:** How should the registry be maintained?
  - One-time manual build (static, no updates)
  - Periodic automated updates (weekly/monthly cron)
  - Community-driven (GitHub issues/PRs for additions)
  - Hybrid (automated + community)
- **Context:** Affects long-term project overhead
- **Decision needed:** Before Phase 3 design

### 4. Implementation Timeline
- **Question:** When should this be built?
  - Now (during design phase) - provides concrete data for specs
  - Phase 2 (Core Documentation Pipeline) - alongside adapter implementation
  - Phase 3 (Search & Navigation) - when search needs it
- **Context:** Registry could inform technical spec database design
- **Decision needed:** Affects current phase scope

### 5. Validation Frequency
- **Question:** How often should we re-validate existing entries?
  - Real-time (on each use) - ensures accuracy but slow
  - On-access if stale (> 30 days) - balanced approach
  - Batch weekly/monthly - efficient but may serve stale data
- **Context:** Affects user experience vs. HTTP overhead tradeoff
- **Decision needed:** Informs adapter caching strategy

### 6. Package Manager Priority
- **Question:** Which package ecosystems to prioritize in Phase 2?
  - JavaScript/TypeScript (npm) - largest ecosystem, 2M+ packages
  - Python (PyPI) - popular for AI/ML libraries
  - Rust (crates.io) - growing, modern docs
  - Ruby (RubyGems) - mature ecosystem
  - All of the above
- **Context:** Affects hit rate and implementation effort
- **Decision needed:** Before Phase 2 implementation

---

## Success Metrics (Proposed)

### Coverage Metrics
- **Breadth:** Number of unique libraries with llms.txt mapped
- **Depth:** Percentage of top N libraries (by downloads) covered
- **Target:** 80% of top 100 libraries across npm + PyPI

### Quality Metrics
- **Accuracy:** Percentage of URLs returning valid llms.txt (target: >95%)
- **Freshness:** Average days since last validation (target: <30 days)
- **Availability:** Uptime of llms.txt URLs (target: >98%)

### Growth Metrics
- **Discovery Rate:** New llms.txt sources found per week
- **Adoption Trend:** Month-over-month growth in total registry size
- **Target:** 10+ new sources per month (as llms.txt adoption grows)

---

## Next Steps (After Approval)

**If Option 3 (Hybrid) is approved:**

1. **Design Phase (This Phase):**
   - Update `05-library-resolution.md` to include llms.txt as Step 0
   - Design database schema for llms_txt_registry table
   - Add to `03-technical-spec.md` database section

2. **Phase 1 Implementation (Week 1 of development):**
   - Create scripts to scrape llms-txt-hub
   - Fetch known Mintlify customer list
   - Validate all URLs (HTTP 200 check)
   - Populate initial database (150-200 entries)

3. **Phase 2 Implementation (Week 2-3 of development):**
   - Implement package manager mapping (npm, PyPI)
   - Test llms.txt URL patterns
   - Validate and add to database (+200-300 entries)

4. **Phase 3 Implementation (Ongoing):**
   - Set up monitoring (GitHub Actions cron)
   - Create community contribution docs
   - Implement re-validation cron job

**If different option selected:**
- Adjust timeline and scope accordingly
- Update technical specs to reflect chosen approach

---

## References & Sources

### Primary Research
- [Mintlify llms.txt Documentation](https://www.mintlify.com/docs/ai/llmstxt) - Official Mintlify implementation details
- [How to Generate llms.txt](https://www.mintlify.com/blog/how-to-generate-llmstxt-file-automatically) - Mintlify auto-generation announcement
- [Mintlify Auto-Generation Article](https://codenote.net/en/posts/mintlify-llms-txt-auto-generation/) - Third-party analysis
- [What is llms.txt](https://www.mintlify.com/blog/what-is-llms-txt) - Overview and benefits

### Curated Registries
- [llms-txt-hub](https://github.com/thedaviddias/llms-txt-hub) - Largest community directory
- [Awesome-llms-txt](https://github.com/SecretiveShell/Awesome-llms-txt) - Curated index
- [GitHub Topics: llms-txt](https://github.com/topics/llms-txt) - Tagged repositories

### Standards & Specifications
- [llms.txt Official Site](https://llmstxt.org/) - Original proposal by Jeremy Howard
- [llms.txt Specification](https://github.com/AnswerDotAI/llms-txt) - Format definition

### Industry Analysis
- [Semrush: What Is LLMs.txt](https://www.semrush.com/blog/llms-txt/) - SEO perspective
- [GitBook: What is llms.txt](https://www.gitbook.com/blog/what-is-llms-txt) - Documentation platform view
- [Search Engine Land: llms.txt Standard](https://searchengineland.com/llms-txt-proposed-standard-453676) - Industry adoption analysis

---

## Document Status

- **Created:** 2026-02-17
- **Author:** Research conducted during Pro-Context design phase
- **Review Status:** ⏳ Pending Ankur's review
- **Next Action:** Discussion and approach approval
- **Related Specs:**
  - `05-library-resolution.md` - Will be updated with llms.txt strategy
  - `03-technical-spec.md` - Will include registry database schema
  - `02-functional-spec.md` - May affect adapter chain design

---

**Note:** No implementation has occurred. This is a research document to inform decision-making. All code generation is blocked pending approach approval per CLAUDE.md guidelines.
