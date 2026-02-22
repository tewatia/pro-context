# Pro-Context: Competitive Analysis

> **Document**: 01-competitive-analysis.md
> **Status**: Final (rev 1)
> **Last Updated**: 2026-02-16

---

## Table of Contents

- [1. Executive Summary](#1-executive-summary)
- [2. Defining Accuracy](#2-defining-accuracy)
  - [2.1 What Does Accuracy Measure?](#21-what-does-accuracy-measure)
  - [2.2 Benchmark Reliability](#22-benchmark-reliability)
  - [2.3 Failure Mode Taxonomy](#23-failure-mode-taxonomy)
- [3. Documentation Retrieval Solutions](#3-documentation-retrieval-solutions)
  - [3.1 Context7 (Upstash)](#31-context7-upstash)
  - [3.2 Docfork](#32-docfork)
  - [3.3 Deepcon](#33-deepcon)
- [4. Code Analysis Platforms](#4-code-analysis-platforms)
  - [4.1 DeepWiki (Cognition AI)](#41-deepwiki-cognition-ai)
- [5. The llms.txt Ecosystem](#5-the-llmstxt-ecosystem)
  - [5.1 The Standard](#51-the-standard)
  - [5.2 Adoption Landscape](#52-adoption-landscape)
  - [5.3 How AI Agents Actually Use llms.txt](#53-how-ai-agents-actually-use-llmstxt)
  - [5.4 What llms.txt Gets Right for Our Use Case](#54-what-llmstxt-gets-right-for-our-use-case)
  - [5.5 What llms.txt Gets Wrong (or Doesn't Address)](#55-what-llmstxt-gets-wrong-or-doesnt-address)
- [6. The Agent Reading Paradigm](#6-the-agent-reading-paradigm)
  - [6.1 How Modern Coding Agents Already Work](#61-how-modern-coding-agents-already-work)
  - [6.2 LangChain's mcpdoc: The Agent-Driven Pattern](#62-langchains-mcpdoc-the-agent-driven-pattern)
  - [6.3 The Hybrid Opportunity](#63-the-hybrid-opportunity)
- [7. Documentation Platforms as Infrastructure](#7-documentation-platforms-as-infrastructure)
  - [7.1 Mintlify](#71-mintlify)
  - [7.2 Fern](#72-fern)
  - [7.3 Implications](#73-implications)
- [8. Community Solutions](#8-community-solutions)
  - [8.1 Rtfmbro](#81-rtfmbro)
  - [8.2 King-Context](#82-king-context)
  - [8.3 docs-mcp-server (arabold)](#83-docs-mcp-server-arabold)
- [9. Accuracy Analysis](#9-accuracy-analysis)
  - [9.1 What Drives Accuracy?](#91-what-drives-accuracy)
  - [9.2 The Two Paths to Accuracy](#92-the-two-paths-to-accuracy)
  - [9.3 Accuracy vs Token Efficiency Tradeoff](#93-accuracy-vs-token-efficiency-tradeoff)
- [10. Feature Comparison](#10-feature-comparison)
  - [10.1 Documentation Retrieval Solutions](#101-documentation-retrieval-solutions)
  - [10.2 Code Analysis Platforms](#102-code-analysis-platforms)
  - [10.3 Documentation Access Patterns](#103-documentation-access-patterns)
- [11. Key Observations](#11-key-observations)
- [12. Open Questions](#12-open-questions)
- [13. References](#13-references)

---

## 1. Executive Summary

This analysis examines the landscape of MCP documentation servers through the lens of **accuracy** — the degree to which a server returns correct, relevant documentation that enables an agent to complete its task. Token efficiency matters, but only as a secondary concern after accuracy clears a useful threshold.

The analysis is structured in four tiers:

1. **Documentation retrieval solutions** (Context7, Docfork, Deepcon) — battle-tested products that serve library documentation to coding agents, with real user bases and measurable performance data.
2. **Code analysis platforms** (DeepWiki) — AI-powered systems that generate documentation from source code analysis rather than serving official docs. These represent an alternative approach to the same underlying problem.
3. **The llms.txt ecosystem** — a growing standard that changes how documentation is published and consumed, with major platform support from Mintlify, Fern, and others. LangChain's mcpdoc server demonstrates a fundamentally different retrieval paradigm that leverages the reading capabilities of modern AI agents.
4. **Community solutions** (Rtfmbro, King-Context, docs-mcp-server) — open-source projects with interesting ideas but limited validation.

**Key finding**: The highest-accuracy approach (Deepcon, 90%) uses a query-understanding model + semantic search + reranking pipeline. But a fundamentally different paradigm is emerging: instead of the server deciding what's relevant, give the agent a structured index and let it navigate documentation itself — the way a human developer would browse docs. LangChain's mcpdoc implements this pattern. Modern coding agents (Claude Code, Cursor, Windsurf) already have the capability to read progressively, follow links, and scroll through content. This capability is underutilized by current MCP doc servers.

Separately, Cognition's DeepWiki represents a different approach entirely: AI-generated documentation from source code analysis. It's well-funded (50K+ repos indexed, ~$300K compute for initial indexing) and has an MCP server, but its source of truth is AI-inferred rather than author-written — a fundamental distinction for accuracy.

---

## 2. Defining Accuracy

Before comparing solutions, we need to define what "accuracy" means. The term is used loosely across competitor marketing and benchmarks.

### 2.1 What Does Accuracy Measure?

| Dimension | Description | Example |
|-----------|------------|---------|
| **Correctness** | Is the returned content factually accurate for the requested version? | Returning v0.2 API when v0.3 was requested = incorrect |
| **Relevance** | Does the content address the user's actual question? | Returning installation docs when the user asked about streaming = irrelevant |
| **Completeness** | Does the content contain enough information to act on? | Returning a function signature without parameter descriptions = incomplete |
| **Specificity** | Is the content focused on the question, or diluted with tangential information? | Returning an entire "Getting Started" page for a question about one method = unspecific |

A truly accurate response is correct, relevant, complete, and specific.

### 2.2 Benchmark Reliability

The only published benchmark across multiple MCP doc servers comes from Deepcon's own evaluation:

- **20 scenarios** implementing Autogen, LangGraph, OpenAI Agents, Agno, and OpenRouter SDK
- **Evaluated by 3 LLMs** (GPT-5, Grok-4, Deepseek-v3.2) for completeness and relevance
- Results: Deepcon 90% (18/20), Context7 65% (13/20), Nia 55% (11/20)

An independent benchmark from the ZK Framework team tested Context7 specifically:

- **59% accuracy** on ZK-specific questions
- Performed well on basic API lookups (method signatures, class structures)
- Failed on conceptual questions (architecture, component lifecycles, best practices)

**Caveat**: Deepcon's benchmark is self-reported. No independent third-party benchmark exists that tests all major MCP doc servers under identical conditions. All accuracy figures in this document should be read with this in mind.

### 2.3 Failure Mode Taxonomy

Based on available benchmark data and user reports, MCP doc servers fail in predictable ways:

| Failure Mode | Description | Which Servers Struggle |
|-------------|-------------|----------------------|
| **Wrong version** | Returns docs for a different version than requested | Context7 (pre-scan staleness), Docfork |
| **Wrong section** | Returns content from the right library but wrong topic | Context7, any chunk-based retrieval |
| **Conceptual miss** | Fails on "how does X work" questions that require understanding, not keyword matching | Context7 (59% on ZK conceptual questions), any BM25-only system |
| **Over-broad return** | Returns too much content, burying the relevant part | Context7 (5,626 avg tokens), Rtfmbro (raw dumps) |
| **Library confusion** | Returns docs for the wrong library entirely | Any system with fuzzy matching |
| **Stale content** | Returns outdated documentation | Any pre-indexed system without freshness checking |

The most important insight: **conceptual misses are the hardest failure mode**. Keyword search handles "what is the signature of ChatOpenAI.invoke()" well but fails on "how do I implement retry logic with LangChain" — which is what developers actually ask.

---

## 3. Documentation Retrieval Solutions

### 3.1 Context7 (Upstash)

**Website**: [github.com/upstash/context7](https://github.com/upstash/context7)
**Architecture**: Centralized pre-scanned database, 2 tools
**License**: Apache-2.0
**Status**: Most popular MCP doc server. Listed on Thoughtworks Technology Radar (Tools/Trial, November 2025).

#### Architecture

```
┌──────────────┐     ┌──────────────────┐     ┌─────────────┐
│  MCP Client  │────▶│  Context7 Server │────▶│  Upstash DB │
│              │◀────│  (2 tools)       │◀────│  (pre-scan) │
└──────────────┘     └──────────────────┘     └─────────────┘
```

Context7 uses a centralized architecture where documentation is pre-scanned and stored in Upstash's managed database. The server exposes exactly 2 tools:

1. **`resolve-library-id`**: Takes a library name, returns a canonical ID from their registry
2. **`get-library-docs`**: Takes a library ID + topic, returns pre-indexed documentation chunks

#### Accuracy Profile

| Benchmark | Score | Source |
|-----------|-------|--------|
| Deepcon benchmark (20 AI framework scenarios) | 65% (13/20) | Self-reported by Deepcon |
| ZK Framework specific questions | 59% | Independent (ZK team) |

**Where it succeeds**: Basic API lookups — method signatures, class structures, parameter lists. These are keyword-heavy queries where pre-indexed chunks match well.

**Where it fails**: Conceptual and architectural questions — "how does the component lifecycle work", "what's the best practice for error handling", "how do these two features interact". The ZK team's 59% score specifically highlighted this gap: Context7 couldn't answer questions about framework architecture, design patterns, or how server-centric models interact with client rendering.

#### Why It Fails

1. **Pre-scan chunking has no query awareness**: Documentation is chunked at index time, not query time. The chunks that happen to exist may not align with what the user is asking.
2. **No reranking**: Chunks are returned based on keyword overlap without any semantic understanding of the query intent.
3. **Staleness**: Pre-scanned content can be days or weeks behind the actual documentation.
4. **One-shot retrieval**: The server returns chunks in a single response. The agent has no ability to navigate, browse, or request more context if the initial result is insufficient.

#### Strengths

- **Minimal tool count**: 2 tools means ~200-400 tokens of tool definition overhead.
- **Wide adoption**: Largest user base of any MCP doc server. Good signal that the problem is real and developers want solutions.
- **Fast retrieval**: Pre-indexed content means no JIT processing latency.
- **5,000+ libraries**: Broad coverage across ecosystems.

#### What We Learn

Context7 proves the **demand** for MCP documentation servers is real. Its popularity despite 59-65% accuracy shows that even imperfect documentation retrieval is valuable to developers. But it also shows the ceiling of the "pre-chunk everything and do keyword matching" approach. The 59% score on conceptual questions is the key data point — it tells us that returning pre-existing chunks is not enough when the question requires understanding.

---

### 3.2 Docfork

**Website**: [docfork.com](https://docfork.com)
**Repository**: [github.com/docfork/docfork-mcp](https://github.com/docfork/docfork)
**Architecture**: Pre-chunked content with AI reranking, edge-cached
**License**: Proprietary (free tier: 1,000 req/month)
**Status**: Active development (v1.3.0, January 2026). 10,000+ libraries indexed.

#### Architecture

```
┌──────────────┐     ┌───────────────────────────────┐
│  MCP Client  │────▶│  Docfork Edge                  │
│              │◀────│  (CDN-cached, AI reranking)    │
└──────────────┘     │                                │
                     │  ┌────────────────────────┐    │
                     │  │  Pre-chunked Content   │    │
                     │  │  + AI Reranking        │    │
                     │  └────────────────────────┘    │
                     │                                │
                     │  ┌────────────────────────┐    │
                     │  │  "Cabinets"            │    │
                     │  │  (project-scoped sets) │    │
                     │  └────────────────────────┘    │
                     └───────────────────────────────┘
```

#### Key Differentiators

**AI Reranking**: Unlike Context7's pure keyword matching, Docfork applies "advanced AI reranking algorithms" to ensure the most relevant chunks surface first. This is likely the reason it claims better accuracy than Context7, though no published benchmark compares them directly.

**Single API call**: Docfork combines resolution and retrieval into a single API call, vs Context7's two-call pattern. This reduces latency and simplifies the agent's decision-making.

**Cabinets**: Project-scoped documentation collections. A team can lock their agent to a verified library stack (e.g., "Next.js + Better Auth"), preventing context pollution from unrelated libraries. This is a sophisticated feature aimed at enterprise use.

#### Accuracy Profile

No independent benchmark data exists for Docfork. Claims include:

- "Cleaner, more relevant output" than Context7 (from their marketing)
- AI reranking as a differentiator
- ~200ms retrieval for cached content

Without benchmark data, we cannot make accuracy claims. The presence of AI reranking suggests awareness that raw chunk retrieval (Context7's approach) is insufficient.

#### Strengths

- **10,000+ libraries**: Broadest coverage of any solution.
- **~200ms retrieval**: Edge caching produces very low latency.
- **Cabinets**: Project-scoped context isolation is a genuinely useful organizational feature.
- **AI reranking**: Moves beyond raw keyword matching.
- **Team features**: Shared cabinets, usage analytics, API key management.

#### Weaknesses

- **Centralized SaaS**: Cannot self-host. Requires internet connectivity.
- **No transparency**: Cannot inspect chunking, reranking, or indexing logic. Black box.
- **1,000 req/month free tier**: Quickly exhausted in active development (a developer asking 30 questions/day hits the limit in ~5 weeks).
- **No published accuracy benchmarks**: Claims of quality without measurable evidence.

#### What We Learn

Docfork's key contribution is the **Cabinets** concept — project-scoped documentation sets that reduce noise. Its AI reranking is a step beyond Context7's keyword matching, but the black-box nature means we can't learn how it works. The biggest takeaway is that Docfork, despite having 10,000+ libraries and AI reranking, still operates in the "server decides what's relevant" paradigm. The agent receives chunks; it cannot navigate or explore.

---

### 3.3 Deepcon

**Website**: [deepcon.ai](https://deepcon.ai/)
**Documentation**: [opactor.mintlify.app/introduction](https://opactor.mintlify.app/introduction)
**Architecture**: Query Composer model + semantic search + reranking
**License**: Closed-source
**Status**: Active. Hosted on Mintlify. Featured on Hacker News (Show HN).

#### Architecture (Inferred)

```
┌──────────────┐     ┌──────────────────────────────────────┐
│  MCP Client  │────▶│  Deepcon                              │
│              │◀────│                                        │
└──────────────┘     │  Query                                │
                     │    │                                   │
                     │    ▼                                   │
                     │  ┌────────────────────────────┐       │
                     │  │  Query Composer Model       │       │
                     │  │  (analyzes request intent)  │       │
                     │  └──────────┬─────────────────┘       │
                     │             │                          │
                     │             ▼                          │
                     │  ┌────────────────────────────┐       │
                     │  │  Indexed Documentation     │       │
                     │  │  (10,000+ official docs)   │       │
                     │  └──────────┬─────────────────┘       │
                     │             │                          │
                     │             ▼                          │
                     │  ┌────────────────────────────┐       │
                     │  │  Relevance Extraction       │       │
                     │  │  (extract relevant sections)│       │
                     │  └────────────────────────────┘       │
                     └──────────────────────────────────────┘
```

Deepcon is the accuracy benchmark in this space. Its architecture, while proprietary, reveals several important principles through its observable behavior and documentation:

1. **Query Composer model**: An AI model that analyzes the user's request before searching. This means the system understands *intent*, not just keywords. This is fundamentally different from BM25 or keyword matching.
2. **Semantic search over indexed documentation**: The indexed docs are searched using semantic understanding, not just keyword overlap.
3. **Relevance extraction**: Only the most relevant sections are extracted and returned — "exactly what's needed, nothing more."

#### Accuracy Profile

| Benchmark | Score | Method | Source |
|-----------|-------|--------|--------|
| 20 AI framework scenarios | **90% (18/20)** | Evaluated by 3 LLMs (GPT-5, Grok-4, Deepseek-v3.2) | Self-reported |
| Avg tokens per response | **~1,000-2,365** | Measured across benchmark | Self-reported |

**Important caveat**: This benchmark is self-reported. However, the methodology (20 real-world scenarios, 3-LLM evaluation panel) is more rigorous than most competitor claims. The benchmark tested complex implementation tasks across Autogen, LangGraph, OpenAI Agents, Agno, and OpenRouter SDK — not trivial lookups.

Without any MCP context, Claude Sonnet 4.5 scored 0% on the same benchmark. This validates that the problem space is real: agents genuinely cannot implement modern AI framework code from training data alone.

#### Why It Achieves 90%

The 25+ percentage point accuracy gap between Deepcon (90%) and Context7 (65%) likely comes from the **Query Composer model**. By understanding query intent before searching, Deepcon can:

- Distinguish "how do I stream with ChatOpenAI" (conceptual) from "ChatOpenAI constructor parameters" (reference)
- Identify which documentation sections are semantically relevant, not just keyword-adjacent
- Extract focused answers rather than returning pre-existing chunks that may not align with the question

This is the core architectural insight: **a retrieval system that understands the question will always outperform one that only matches keywords**.

#### Strengths

- **90% accuracy**: Highest published accuracy of any MCP doc server.
- **Low token usage**: ~1,000-2,365 avg tokens — highly efficient.
- **Multi-language**: Python, JavaScript, TypeScript, Go, Rust.
- **10,000+ official docs**: Broad coverage with official sources.
- **Sub-5s response time**: Fast enough for interactive development.

#### Weaknesses

- **Closed-source**: Cannot inspect, self-host, or modify.
- **Self-reported benchmark**: No independent validation of the 90% figure.
- **AI dependency at query time**: The Query Composer model adds latency and cost. Not viable for a self-hosted, zero-dependency solution.
- **No transparency**: How docs are indexed, chunked, or ranked is unknown.

#### What We Learn

Deepcon demonstrates that **query understanding is the key differentiator for accuracy**. The leap from 65% to 90% isn't about better chunks or faster caching — it's about understanding what the developer is actually asking and then finding the right content.

For an open-source project that can't embed a proprietary query model, this insight still applies: we need approaches that go beyond keyword matching. This could mean leveraging the agent's own reasoning capability (which is already an LLM) rather than trying to replicate a query-understanding model on the server side. This connects directly to the agent reading paradigm discussed in Section 6.

---

## 4. Code Analysis Platforms

### 4.1 DeepWiki (Cognition AI)

**Website**: [deepwiki.com](https://deepwiki.com/)
**Blog**: [cognition.ai/blog/deepwiki](https://cognition.ai/blog/deepwiki)
**Architecture**: AI code analysis + RAG + wiki generation
**License**: Proprietary (free for public repos, paid for private via Devin account)
**Status**: Active. Built by Cognition AI (the team behind Devin). 50K+ repos indexed. MCP server available.

#### How It Works

DeepWiki auto-generates structured, wiki-style documentation for any GitHub repository by analyzing its source code, configuration files, and existing documentation. You can access the wiki for any repo by replacing `github.com` with `deepwiki.com` in the URL.

```
┌──────────────┐     ┌──────────────────────────────────────────┐
│  MCP Client  │────▶│  DeepWiki                                 │
│              │◀────│                                            │
└──────────────┘     │  MCP Tools:                               │
                     │  1. read_wiki_structure (TOC)              │
                     │  2. read_wiki_contents  (page content)     │
                     │  3. ask_question         (RAG Q&A)         │
                     │                                            │
                     │  ┌────────────────────────────────┐       │
                     │  │  Pre-indexed Repo Analysis      │       │
                     │  │  50K+ repos, 4B lines of code  │       │
                     │  │  ~$300K compute for indexing     │       │
                     │  └────────────────────────────────┘       │
                     │                                            │
                     │  ┌────────────────────────────────┐       │
                     │  │  AI Analysis Pipeline           │       │
                     │  │  - Code understanding models    │       │
                     │  │  - Relationship mapping         │       │
                     │  │  - Knowledge summarization      │       │
                     │  │  - Mermaid diagram generation   │       │
                     │  └────────────────────────────────┘       │
                     └──────────────────────────────────────────┘
```

#### Key Features

- **Pre-indexed at scale**: 50K+ top public GitHub repos indexed, 4 billion lines of code analyzed
- **MCP server**: 3 tools — `read_wiki_structure` (TOC), `read_wiki_contents` (page content), `ask_question` (RAG-powered Q&A)
- **Deep Research Mode**: Extended analysis mimicking a senior code reviewer — identifies bugs, optimization opportunities, architectural critiques
- **Auto-generated diagrams**: Mermaid.js flowcharts and dependency graphs
- **Customizable via `.devin/wiki.json`**: Repository owners can steer wiki generation, specify pages, and add notes

#### The Fundamental Distinction: AI-Inferred vs Author-Written

DeepWiki and the documentation retrieval servers (Context7, Docfork, Deepcon, Pro-Context) solve overlapping but distinct problems:

| Dimension | DeepWiki | Documentation Retrieval Servers |
|-----------|----------|-------------------------------|
| **Source of truth** | AI analysis of source code | Official documentation written by library maintainers |
| **Content** | Architecture diagrams, code relationships, AI-inferred explanations | API references, guides, examples, changelogs, migration notes |
| **Accuracy model** | Only as good as the AI's code understanding | As accurate as the official docs |
| **Coverage** | Any public GitHub repo (50K+ pre-indexed, any repo on-demand) | Libraries in the pre-built registry (builder-generated llms.txt for all entries) |
| **Strengths** | "How does this codebase work?" — architecture, code flow, internal relationships | "How do I use this API?" — correct parameters, patterns, version-specific behavior |
| **Failure modes** | AI misinterprets code intent, infers incorrect behavior, misses undocumented conventions | Official docs are incomplete, outdated, or poorly structured |

For a coding agent trying to use `ChatOpenAI(streaming=True)`, the official LangChain docs are the authoritative source. DeepWiki's AI-generated analysis of the LangChain source code might get the parameters right, but it might also miss nuances that the official docs capture — deprecated patterns, recommended alternatives, version-specific caveats.

Conversely, for understanding how a codebase is architectured or how modules interact — questions that official docs may not address — DeepWiki's code analysis is genuinely useful.

#### Strengths

- **Massive scale**: 50K+ repos, backed by Cognition's resources (~$300K compute for initial indexing alone)
- **Universal coverage**: Works on any public GitHub repo, not just those with llms.txt or good documentation
- **MCP server**: Well-structured 3-tool interface (TOC, content, Q&A)
- **Complementary to official docs**: Provides insights (architecture, code flow) that official docs often don't cover
- **Zero effort for library authors**: Documentation is generated automatically

#### Weaknesses

- **Not authoritative**: Content is AI-generated, not author-written. For API usage questions, this is a liability
- **Proprietary and centralized**: Cannot self-host. Free for public repos, paid for private (requires Devin account)
- **Freshness depends on re-indexing**: When a library updates, the wiki must be regenerated
- **Community MCP server blocked**: Cognition has blocked scraping of deepwiki.com, limiting community-built alternatives
- **No version awareness**: Wiki is generated for the default branch; no mechanism for version-specific documentation

#### What We Learn

DeepWiki is important to acknowledge because it's a well-funded alternative that coding agents could use instead of documentation retrieval servers. A developer with DeepWiki's MCP server configured may get "good enough" results for many queries without needing Pro-Context.

However, the key insight is about **source of truth**. DeepWiki tells you what the code *does* (as inferred by AI). Pro-Context tells you what the code *should do* (as documented by the authors). For correctness-critical tasks — using the right API, migrating between versions, understanding deprecated patterns — official documentation is the authoritative source. DeepWiki is complementary, not a substitute.

The operational insight is also instructive: Cognition spent ~$300K pre-indexing 50K repos. This provides a real data point for the cost of the pre-indexed approach at scale.

---

## 5. The llms.txt Ecosystem

### 5.1 The Standard

The `/llms.txt` standard, proposed by Jeremy Howard (co-founder of Answer.AI) in September 2024, provides a way for websites to publish LLM-friendly documentation. The format is intentionally simple: a markdown file with a title, summary, and links to detailed pages.

Two file variants exist:

| File | Purpose | Typical Size |
|------|---------|-------------|
| `/llms.txt` | Navigation index. Title, summary, and categorized links with one-sentence descriptions per page. | Small (Anthropic: ~8,400 tokens) |
| `/llms-full.txt` | Complete documentation in a single file. All page content inlined. | Large (Anthropic: ~481,000 tokens; Cloudflare: ~3.7M tokens; Vercel: ~400K words) |
| `/{page}.md` | Individual page as markdown (Mintlify feature). Appending `.md` to any docs page URL returns a markdown version. | Per-page (~500-5,000 tokens) |

The size ratio between `llms.txt` and `llms-full.txt` can be enormous — Anthropic's is 57x. This is the core design tension: `llms.txt` is a navigable index that fits in any context window, while `llms-full.txt` contains everything but exceeds most context windows.

### 5.2 Adoption Landscape

As of early 2026, llms.txt adoption has crossed a critical threshold thanks to documentation platform support:

**Documentation platforms with automatic llms.txt generation:**

| Platform | llms.txt | llms-full.txt | .md pages | MCP Server | Scale |
|----------|----------|---------------|-----------|------------|-------|
| **Mintlify** | Auto-generated for all hosted sites | Auto-generated | Yes (.md suffix) | Supported | 10,000+ companies; 8-figure ARR |
| **Fern** | Auto-generated | Auto-generated | Yes | Auto-generated per site | Growing; API-first docs |
| **ReadMe** | Generated | Generated | — | Supported | Established API docs platform |
| **Redocly** | Generated | Generated | — | Supported | API documentation |

**Mintlify's impact was transformative**: When Mintlify rolled out llms.txt across all hosted docs sites in November 2025, thousands of documentation sites gained llms.txt support overnight — including Anthropic's docs and Cursor's docs. Mintlify now hosts 10,000+ companies and handles 1M+ monthly AI queries.

**Notable developer libraries/tools with llms.txt:**

| Library/Tool | llms.txt URL | llms-full.txt | Notes |
|-------------|-------------|---------------|-------|
| **Pydantic** | docs.pydantic.dev/latest/llms.txt | Yes | Both formats available |
| **Pydantic AI** | ai.pydantic.dev/llms.txt | Yes | Both formats |
| **LangChain** | docs.langchain.com/llms.txt | — | Redirected from python.langchain.com |
| **LangGraph** | langchain-ai.github.io/langgraph/llms.txt | Yes (very large) | Hundreds of thousands of tokens |
| **Docker** | docs.docker.com/llms.txt | Yes | Official docs |
| **Svelte** | svelte.dev/llms.txt | — | Framework docs |
| **Anthropic** | docs.anthropic.com/llms.txt | Yes | ~8,400 / ~481,000 tokens |
| **Vercel** | vercel.com/llms.txt | Yes | AI SDK docs |
| **Cloudflare** | developers.cloudflare.com/llms.txt | Yes (~3.7M tokens) | Massive documentation set |
| **Stripe** | docs.stripe.com/llms.txt | — | Payment API docs |
| **Mastercard** | developer.mastercard.com/llms.txt | — | Agent toolkit docs |

**Notable gaps**: FastAPI does **not** have llms.txt — a PR was submitted and closed by the maintainer (tiangolo) in August 2025, who indicated it should be auto-generated rather than manually maintained. Many popular Python libraries (requests, SQLAlchemy, Django, Flask, NumPy, pandas) do not have llms.txt as of early 2026, though Mintlify-hosted docs have it automatically.

**Quantitative adoption**: The llms-txt-hub directory lists 500+ implementations. NerdyData found 951 domains with llms.txt as of July 2025. The actual number is likely higher post-Mintlify rollout.

### 5.3 How AI Agents Actually Use llms.txt

Real-world usage data provides a critical insight: **AI agents visit llms-full.txt more than twice as often as llms.txt**. This suggests agents prefer the complete content when it's available, even at the cost of more tokens.

However, this behavior is suboptimal. A 3.7M token file (Cloudflare) or 481K token file (Anthropic) cannot fit in any current context window. The agent is wasting tokens on irrelevant content or the file is being truncated.

The optimal pattern — which LangChain's mcpdoc implements — is:

1. Read `llms.txt` (the index) — small, fits easily
2. Identify which pages are relevant to the query
3. Fetch only those specific pages
4. Read them progressively if they're large

This is exactly how a human developer uses documentation: scan the table of contents, navigate to the relevant section, read it.

### 5.4 What llms.txt Gets Right for Our Use Case

1. **Authoritative source**: llms.txt files come from the library authors themselves, hosted on official documentation sites. This is the highest-quality source for documentation.
2. **Structured for navigation**: The index + individual pages pattern maps naturally to how agents can browse content.
3. **Markdown by default**: No HTML parsing, no scraping, no cleaning. Content is already in the format agents consume best.
4. **Version-aligned**: Documentation sites publish docs per-version, so the llms.txt content matches the version at that URL.
5. **Growing coverage**: With Mintlify (10,000+ companies) and Fern auto-generating llms.txt, coverage will continue to expand without any action from library maintainers.
6. **Token-efficient delivery**: Up to 10x token reduction vs serving HTML, per real-world reports.

### 5.5 What llms.txt Gets Wrong (or Doesn't Address)

1. **No search semantics**: llms.txt is a flat index. It has no concept of relevance, ranking, or semantic similarity. Finding the right page for a given question depends entirely on the agent's ability to match its question to the one-sentence descriptions in the index.
2. **Coverage gaps**: Many popular Python libraries (FastAPI, Django, Flask, requests, SQLAlchemy, NumPy, pandas) do not have llms.txt. For these, we need fallback sources.
3. **Size variance is extreme**: From 8,400 tokens (Anthropic llms.txt) to 3.7M tokens (Cloudflare llms-full.txt). No consistent sizing guarantees.
4. **Quality varies**: Some llms.txt files are comprehensive with good descriptions; others are auto-generated stubs with minimal context. The descriptions in the index determine whether the agent can navigate effectively.
5. **No standard for versioned URLs**: The llms.txt spec doesn't mandate a pattern for version-specific documentation URLs. Different sites handle versioning differently.
6. **No query parameters for filtering**: Only Mintlify/Fern support query parameters like `?lang=python` on llms-full.txt. The standard itself doesn't define filtering.

---

## 6. The Agent Reading Paradigm

### 6.1 How Modern Coding Agents Already Work

Modern AI coding agents (Claude Code, Cursor, Windsurf) are not simple prompt-response systems. They have sophisticated capabilities:

- **Progressive file reading**: Agents can read files in chunks, scroll through content, and focus on specific sections.
- **Sub-agent delegation**: Claude Code uses specialized sub-agents for research tasks — reading web content, searching documentation, exploring codebases.
- **Multi-step reasoning**: Agents can decide "I need more context", fetch additional pages, and synthesize across multiple sources.
- **Tool chaining**: Agents call multiple tools sequentially, using the output of one call to inform the next.

These capabilities are directly relevant to documentation retrieval. An agent doesn't need a server to pre-chew documentation into perfect chunks — it can navigate, read, and extract what it needs, just like a human developer browsing docs.

### 6.2 LangChain's mcpdoc: The Agent-Driven Pattern

LangChain's [mcpdoc](https://github.com/langchain-ai/mcpdoc) server demonstrates this paradigm. It's an open-source MCP server with a fundamentally different approach from Context7, Docfork, and Deepcon.

#### Architecture

```
┌──────────────┐     ┌──────────────────────────────┐
│  MCP Client  │────▶│  mcpdoc Server               │
│  (Claude,    │◀────│                               │
│   Cursor,    │     │  Tools:                       │
│   Windsurf)  │     │  1. list_doc_sources          │
│              │     │  2. fetch_docs(url)            │
└──────────────┘     └──────────────────────────────┘
```

**2 tools. No search. No indexing. No chunking. No ranking.**

#### How It Works

1. Server is configured with one or more llms.txt URLs (e.g., LangChain, LangGraph)
2. Agent calls `list_doc_sources` → gets available documentation sources
3. Agent calls `fetch_docs` on an llms.txt URL → gets the index (table of contents with links and descriptions)
4. **Agent reads the index and reasons about which pages are relevant to the user's question**
5. Agent calls `fetch_docs` on specific page URLs → gets the actual documentation content
6. Agent reads the content and synthesizes an answer

The critical step is **step 4**: the agent — which is an LLM — performs the relevance judgment. It reads the index and decides where to look. This is fundamentally different from having a server-side BM25 or vector search decide what's relevant.

#### Why This Matters

| Aspect | Server-Decides (Context7/Docfork/Deepcon) | Agent-Decides (mcpdoc) |
|--------|-------------------------------------------|----------------------|
| **Who judges relevance** | Server-side algorithm (BM25, vector search, AI reranking) | The agent itself (LLM reasoning) |
| **Query understanding** | Limited to server's search capability | Full LLM reasoning over the query |
| **Context awareness** | None — server doesn't know what the agent is working on | Full — agent knows the entire conversation, code context, and goal |
| **Navigation** | One-shot: server returns chunks, agent takes what it gets | Multi-step: agent can browse, go deeper, try different sections |
| **Failure recovery** | If chunks are wrong, agent is stuck | Agent can try different pages, refine its search, ask for more |
| **Accuracy ceiling** | Limited by server's search quality | Limited by agent's reasoning quality (which improves with model quality) |

The agent-driven approach has a higher **accuracy ceiling** because the relevance judgment is made by an LLM with full context awareness, not by a keyword-matching algorithm with no context.

#### Limitations of mcpdoc

mcpdoc is minimal by design. It has real limitations:

- **No caching**: Every `fetch_docs` call fetches the URL live. No local cache, no freshness checking.
- **No search fallback**: If the agent misjudges which page to read, it wastes a tool call and must try again.
- **Depends on llms.txt quality**: If the llms.txt index has poor descriptions, the agent can't navigate effectively.
- **No version resolution**: No integration with PyPI/npm for version-specific documentation URLs.
- **Domain-locked security**: Can only fetch from pre-configured domains. This is a good security feature but limits flexibility.
- **Token cost of browsing**: Each navigation step costs a tool call and tokens for the returned content. An agent might make 3-5 calls to find what it needs, vs a server-decides approach that ideally returns the right answer in 1 call.

### 6.3 The Hybrid Opportunity

Neither approach alone is optimal:

- **Server-decides** is efficient (1 call) but accuracy-limited (65% for Context7, 90% for Deepcon with an expensive query model)
- **Agent-decides** has a higher accuracy ceiling but costs more tool calls and tokens per query

The hybrid approach: **use server-side search to narrow the field, then let the agent navigate the results**. The server finds the most likely relevant sections; the agent reads them with full context awareness and decides what's actually useful.

This is analogous to how a developer uses Google: search narrows the results to a few candidate pages, but the developer reads and evaluates each page with their full understanding of what they're trying to do.

---

## 7. Documentation Platforms as Infrastructure

A development that changes the landscape significantly: documentation platforms themselves are becoming the infrastructure layer for AI documentation access.

### 7.1 Mintlify

**Scale**: 10,000+ companies, 8-figure ARR, 1M+ monthly AI queries.

Mintlify auto-generates for every hosted docs site:
- `/llms.txt` — structured index with page descriptions
- `/llms-full.txt` — complete documentation in one file
- `/{page}.md` — individual page as markdown (append `.md` to any page URL)
- MCP server support

**Significance**: When Mintlify shipped llms.txt support, thousands of documentation sites gained AI-friendly documentation overnight. This includes docs for Anthropic, Cursor, and thousands of SaaS companies. Mintlify's stated mission for 2026 is to be "the infrastructure layer for how AI understands technical knowledge."

Vercel reported going from <1% to 10% of signups coming from ChatGPT in six months, attributed partly to AI-optimized documentation.

### 7.2 Fern

**Features**: Auto-generates llms.txt, llms-full.txt, per-page markdown, and a dedicated MCP server for each hosted docs site.

Fern's approach is notable because it generates **both** the documentation files and the MCP server automatically. A library that hosts its docs on Fern gets an MCP server for free.

### 7.3 Implications

The doc platform approach means:

1. **Coverage will continue to grow automatically**: As more projects use Mintlify or Fern, they get llms.txt without any effort. No need to manually curate a library registry.
2. **Per-page markdown access is a game-changer**: The ability to fetch `docs.example.com/some/page.md` and get clean markdown — without scraping HTML — makes the agent-driven browsing pattern practical.
3. **Documentation platforms are building their own MCP servers**: This could mean our server's primary value shifts to being a unifying layer across multiple documentation sources (llms.txt, GitHub, custom), rather than competing with platform-native MCP servers.

---

## 8. Community Solutions

These projects are smaller in scale and user base but contribute interesting ideas to the design space.

### 8.1 Rtfmbro

**Repository**: [github.com/marckrenn/rtfmbro-mcp](https://github.com/marckrenn/rtfmbro-mcp)
**License**: MIT

**Key contribution: SHA-based freshness checking.** Rtfmbro fetches docs JIT from GitHub using exact git tags, then caches with SHA comparison. On subsequent requests, a cheap GitHub API HEAD request checks if the content SHA has changed. This is an elegant cache invalidation strategy that avoids refetching unchanged content.

**Weakness**: Returns raw documentation dumps without any chunking or relevance filtering. Entire files are sent to the agent, wasting tokens.

### 8.2 King-Context

**Repository**: [github.com/deandevz/king-context](https://github.com/deandevz/king-context)
**License**: MIT

**Key contribution: Cascade search concept.** King-Context claims that ~90% of queries resolve at cache or metadata levels (levels 1-2), with only ~10% needing full-text or hybrid search (levels 3-4). Claims 59-69% token reduction vs Context7.

**Caveats**: These numbers are self-reported from a small project without independent verification. The cascade concept is sound in principle — check cheap sources before expensive ones — but the specific resolution rates should not be treated as reliable data.

### 8.3 docs-mcp-server (arabold)

**Repository**: [github.com/arabold/docs-mcp-server](https://github.com/arabold/docs-mcp-server)
**License**: MIT

**Key contribution: Hybrid search with RRF.** Uses SQLite FTS5 (keyword) + sqlite-vec (vector) with Reciprocal Rank Fusion to merge results. This is a well-established pattern from the information retrieval literature.

**Weakness**: Requires an embedding model (OpenAI API key or local Ollama), adding a dependency. Must pre-index documentation before querying — no JIT support.

---

## 9. Accuracy Analysis

### 9.1 What Drives Accuracy?

Based on the analysis of all solutions above, accuracy in documentation retrieval is driven by:

| Factor | Impact | Evidence |
|--------|--------|----------|
| **Query understanding** | Very High | Deepcon's Query Composer model is the primary differentiator for its 90% accuracy. Context7's lack of query understanding contributes to its 59-65% score. |
| **Source quality** | High | llms.txt content (authored by library maintainers, structured for LLMs) is inherently higher quality than scraped HTML or raw GitHub markdown. |
| **Relevance ranking** | High | Docfork's AI reranking and Deepcon's semantic extraction outperform Context7's keyword matching. |
| **Agent navigation capability** | High (potential) | mcpdoc's approach leverages the agent's LLM reasoning for relevance judgment, which has a theoretically higher ceiling. Unproven at scale. |
| **Version precision** | Medium | Returning docs for the wrong version is a binary failure. Version resolution via PyPI/npm is straightforward to implement. |
| **Freshness** | Medium | Stale docs create subtle failures — the API exists but the signature changed. SHA-based freshness checking (Rtfmbro) addresses this. |
| **Chunk granularity** | Medium | Too-large chunks waste tokens and dilute relevance. Too-small chunks lose context. docs-mcp-server and Deepcon get this right; Context7 does not. |

### 9.2 The Two Paths to Accuracy

The analysis reveals two fundamentally different strategies for achieving high accuracy:

**Path 1: Smarter Server (Deepcon's approach)**

Build increasingly sophisticated server-side retrieval: query understanding models, semantic search, reranking pipelines. The server does the hard work; the agent receives the answer.

- Pro: Efficient for the agent (1 call, low tokens)
- Pro: Works with any agent, regardless of agent quality
- Con: Requires AI infrastructure on the server (models, embeddings, GPU/API costs)
- Con: Server has no context about what the agent is working on
- Con: Accuracy is capped by the server's retrieval quality

**Path 2: Smarter Navigation (mcpdoc's approach)**

Provide the agent with structured documentation access (indexes, per-page retrieval) and let the agent's own LLM reasoning determine what's relevant. The server is a thin access layer; the agent does the hard work.

- Pro: Leverages the agent's full context awareness and reasoning ability
- Pro: Accuracy improves as agent models improve (no server changes needed)
- Pro: No AI infrastructure needed on the server
- Con: Costs more tool calls per query (3-5 vs 1)
- Con: Depends on documentation being well-structured (good llms.txt)
- Con: Agent quality directly affects retrieval quality

**Path 3: Hybrid**

Use server-side search to narrow candidates, then provide the agent with navigable documentation to make the final relevance judgment. The server does coarse filtering; the agent does fine-grained selection.

### 9.3 Accuracy vs Token Efficiency Tradeoff

| Solution | Accuracy | Avg Tokens | Strategy |
|----------|----------|-----------|----------|
| Context7 | 59-65% | 5,626 | Server-decides, keyword matching |
| Docfork | Unknown (likely >65%) | Unknown | Server-decides, AI reranking |
| Deepcon | 90% | ~1,000-2,365 | Server-decides, query model + semantic search |
| mcpdoc | Unknown (depends on agent) | Variable (multi-call) | Agent-decides, index navigation |

Note: Deepcon achieves both the highest accuracy AND the lowest token usage. This reinforces that **accuracy and token efficiency are correlated, not competing goals**. A system that returns the right content naturally uses fewer tokens because it doesn't return irrelevant content.

---

## 10. Feature Comparison

### 10.1 Documentation Retrieval Solutions

| Feature | Context7 | Docfork | Deepcon |
|---------|----------|---------|--------|
| Published accuracy | 59-65% | No data | 90% (self-reported) |
| Avg tokens/response | 5,626 | Unknown (~fast) | ~1,000-2,365 |
| Library coverage | 5,000+ | 10,000+ | 10,000+ |
| Self-hostable | No | No | No |
| Open source | Yes (Apache-2.0) | No | No |
| Version-aware | Yes | Yes | Yes |
| Multi-language | Yes | Yes | Yes (Py, JS, TS, Go, Rust) |
| Query understanding | No | Partial (AI reranking) | Yes (Query Composer) |
| Project scoping | No | Yes (Cabinets) | No |
| Team features | No | Yes | No |
| llms.txt native | No | No | No |
| Agent navigation | No | No | No |

### 10.2 Code Analysis Platforms

| Feature | DeepWiki |
|---------|----------|
| Source of truth | AI-generated from source code |
| Published accuracy | No data (AI-inferred, not benchmarked against official docs) |
| Coverage | 50K+ repos (any public GitHub repo) |
| Self-hostable | No |
| Open source | No (open-source alternatives exist: DeepWiki-Open, OpenDeepWiki) |
| Version-aware | No (default branch only) |
| Multi-language | Any language in the repo |
| MCP server | Yes (3 tools) |
| Agent navigation | Yes (TOC + page content) |
| llms.txt native | No |

### 10.3 Documentation Access Patterns

| Pattern | Who Uses It | Accuracy Model | Token Model |
|---------|------------|----------------|-------------|
| Pre-chunked retrieval | Context7, Docfork | Server determines relevance | Fixed per response |
| Query model + semantic search | Deepcon | AI model determines relevance | Optimized per response |
| Index + agent navigation | mcpdoc | Agent LLM determines relevance | Variable (multi-call) |
| AI-generated code analysis | DeepWiki | AI infers from source code | Variable (wiki-style) |
| Raw file dump | Rtfmbro | No relevance filtering | Very high |

---

## 11. Key Observations

These are analytical observations, not design decisions. Design decisions will be made in subsequent documents.

### Observation 1: Query Understanding Is the Accuracy Bottleneck

The 25+ percentage point gap between Deepcon (90%) and Context7 (65%) is attributable to query understanding. Context7 treats every query as a keyword matching problem. Deepcon understands the intent behind the query. Any solution targeting >85% accuracy must address query understanding — either on the server side (expensive) or by leveraging the agent's existing LLM capabilities (the mcpdoc approach).

### Observation 2: llms.txt Coverage Is Approaching a Useful Threshold

With Mintlify (10,000+ companies) and Fern auto-generating llms.txt, and major projects like LangChain, Pydantic, Docker, Anthropic, and Vercel publishing their own, the coverage is substantial and growing. However, significant gaps remain in the Python ecosystem (FastAPI, Django, Flask, requests, NumPy, pandas). A fallback source strategy is necessary.

### Observation 3: The Per-Page Markdown Pattern Is Underutilized

Mintlify's `.md` suffix feature — appending `.md` to any page URL to get clean markdown — is extremely powerful for the agent navigation paradigm. It means the agent can fetch individual documentation pages as clean markdown without scraping HTML. Combined with llms.txt as an index, this enables precise, page-level documentation retrieval.

### Observation 4: Documentation Platforms Are Building the Infrastructure

Mintlify and Fern are building exactly the infrastructure that MCP doc servers need: structured indexes (llms.txt), per-page markdown access (.md), and even auto-generated MCP servers. Rather than competing with this infrastructure, a new MCP doc server should complement it — adding caching, version resolution, fallback sources, and the agent navigation experience on top.

### Observation 5: The "Server Decides" Paradigm Has a Ceiling

Every "server decides what's relevant" solution shares a fundamental limitation: the server doesn't know what the agent is working on. It receives a query string and must guess what's relevant without the conversation history, the code being written, or the developer's goal. This is why Context7 achieves only 59% on conceptual questions — it lacks the context to judge relevance. Deepcon compensates with an expensive query model, but even that model lacks the full conversation context.

### Observation 6: Caching and Freshness Are Solved Problems

Rtfmbro's SHA-based freshness checking and the general two-tier cache pattern (memory LRU + persistent store) are well-understood and proven. These are implementation details, not differentiators.

### Observation 7: Code Analysis Is Complementary, Not Competing

DeepWiki (Cognition) demonstrates that AI-generated documentation from source code is viable at scale (50K+ repos, ~$300K compute). However, AI-inferred documentation and author-written documentation serve different purposes. For correctness-critical tasks — using the right API parameters, migrating between versions, understanding deprecations — official documentation is the authoritative source. Code analysis platforms are complementary for understanding architecture and code flow, but they are not a substitute for official docs. A coding agent ideally has access to both.

### Observation 8: No Existing Solution Combines llms.txt + Agent Navigation + Caching

mcpdoc has the right paradigm (agent-driven navigation via llms.txt) but lacks caching, version resolution, search fallback, and multi-source support. Context7/Docfork/Deepcon have caching and coverage but don't leverage llms.txt or agent navigation. The gap is a solution that combines both.

---

## 12. Open Questions

These questions should be addressed in subsequent design and specification documents:

1. **How should the server balance server-side search with agent-driven navigation?** Pure search (Context7) is efficient but less accurate. Pure navigation (mcpdoc) is more accurate but costs more tool calls. What's the optimal split?

2. **What's the realistic accuracy of BM25-only search for documentation queries?** BM25 excels at keyword queries ("ChatOpenAI parameters") but struggles with conceptual queries ("how do I implement retry logic"). If BM25-only gets us to ~70% accuracy, is that acceptable as a baseline while agent navigation handles the rest?

3. **What percentage of the target Python library set has usable llms.txt?** _(Resolved: Builder system normalizes all sources to llms.txt format at build time, achieving 100% coverage)_

4. **How many tool calls does agent navigation typically require?** mcpdoc's approach might need 3-5 calls to answer a question. Is this acceptable to users, or does it feel too slow?

5. **Should we provide the agent with a table-of-contents resource?** Instead of making the agent call `fetch_docs` on the llms.txt URL (which costs a tool call), should the TOC be available as an MCP resource that's automatically attached to the conversation?

6. **How should we handle libraries without llms.txt?** _(Resolved: Builder system generates llms.txt from GitHub README/docs at build time. See `docs/builder/` for normalization strategy)_

---

## 13. References

### Documentation Retrieval Solutions
- [Context7 MCP Server](https://github.com/upstash/context7) — Apache-2.0
- [Docfork MCP](https://github.com/docfork/docfork) — Proprietary
- [Deepcon](https://deepcon.ai/) — Proprietary
- [Deepcon Show HN Discussion](https://news.ycombinator.com/item?id=45839378)
- [Deepcon Documentation](https://opactor.mintlify.app/introduction)

### Code Analysis Platforms
- [DeepWiki](https://deepwiki.com/) — Cognition AI
- [Cognition Blog: DeepWiki](https://cognition.ai/blog/deepwiki)
- [Cognition Blog: DeepWiki MCP Server](https://cognition.ai/blog/deepwiki-mcp-server)
- [DeepWiki on Devin Docs](https://docs.devin.ai/work-with-devin/deepwiki)
- [DeepWiki MCP on Devin Docs](https://docs.devin.ai/work-with-devin/deepwiki-mcp)
- [DeepWiki-Open (community)](https://github.com/AsyncFuncAI/deepwiki-open) — MIT
- [OpenDeepWiki (community)](https://github.com/AIDotNet/OpenDeepWiki) — MIT

### llms.txt Ecosystem
- [llms.txt Standard (llmstxt.org)](https://llmstxt.org/)
- [llms.txt Hub — Directory of 500+ Implementations](https://llmstxthub.com/)
- [llms-txt-hub GitHub](https://github.com/thedaviddias/llms-txt-hub)
- [Mintlify: Simplifying Docs for AI with llms.txt](https://www.mintlify.com/blog/simplifying-docs-with-llms-txt)
- [Mintlify: What is llms.txt? Breaking Down the Skepticism](https://www.mintlify.com/blog/what-is-llms-txt)
- [Mintlify llms.txt Documentation](https://www.mintlify.com/docs/ai/llmstxt)
- [Mintlify LLM Ingestion Settings](https://mintlify.com/docs/settings/llms)
- [Fern: llms.txt and llms-full.txt](https://buildwithfern.com/learn/docs/ai-features/llms-txt)
- [LangChain llms.txt Files and MCPDOC Launch](https://changelog.langchain.com/announcements/llms-txt-files-and-mcpdoc-server-launch-for-langchain-and-langgraph)
- [LangGraph llms.txt Overview](https://langchain-ai.github.io/langgraph/llms-txt-overview/)

### Agent Navigation Pattern
- [LangChain mcpdoc MCP Server](https://github.com/langchain-ai/mcpdoc)
- [mcpdoc Deep Dive](https://skywork.ai/skypage/en/langchain-mcpdoc-bridge-llm-docs/1978710111180595200)

### Community Solutions
- [Rtfmbro MCP](https://github.com/marckrenn/rtfmbro-mcp) — MIT
- [King-Context](https://github.com/deandevz/king-context) — MIT
- [docs-mcp-server](https://github.com/arabold/docs-mcp-server) — MIT

### Benchmarks and Analysis
- [ZK Doc MCP Server — Context7 Accuracy Analysis](https://docs.zkoss.org/small-talk/2026/01/01/zk-doc-mcp-server)
- [FastMCP: Top Context7 Alternatives](https://fastmcp.me/blog/top-context7-mcp-alternatives)
- [llms.txt vs llms-full.txt Guide](https://hitlseo.ai/blog/llms.txt-vs-llms-full.txt-the-complete-2025-guide-to-ai-friendly-documentation/)
- [Thoughtworks Technology Radar — MCP Impact](https://www.thoughtworks.com/en-us/insights/blog/generative-ai/model-context-protocol-mcp-impact-2025)

### Standards and Best Practices
- [MCP Specification (2025-11-25)](https://modelcontextprotocol.io/specification/2025-11-25)
- [MCP Best Practices (Philipp Schmid)](https://www.philschmid.de/mcp-best-practices)
- [15 Best Practices for MCP Servers (The New Stack)](https://thenewstack.io/15-best-practices-for-building-mcp-servers-in-production/)

### FastAPI llms.txt Status
- [FastAPI llms.txt PR #13977 — Closed](https://github.com/fastapi/fastapi/pull/13977)
