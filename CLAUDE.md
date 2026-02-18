# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## About the Project

Pro-Context is an open-source MCP (Model Context Protocol) documentation server that provides AI coding agents with accurate, up-to-date library documentation to prevent hallucination of API details. Licensed under GPL-3.0.

## About the Author

This project is authored by Ankur Tewatia, a Senior Lead Consultant with more than a decade of experience in the software industry.

## Project Motivation

Ankur has recently been working with Generative AI-based applications. Since this is a relatively new technology, all the libraries are relatively new as well and are updated frequently, which makes it difficult for coding agents to produce accurate code leveraging these libraries. Ankur's aim with this repo is to make coding agents more reliable by providing them with correct and up-to-date information.

## Implementation Phases

0. **Specification/Design Phase** - Define the problem, design the system architecture, and create detailed specifications for each component. This phase will culminate in a comprehensive documentation that will guide the implementation.
1. **Foundation** — MCP server skeleton, config, logging, errors, stdio transport, health check
2. **Core Documentation Pipeline** — Adapter chain, cache, `resolve-library` + `get-library-info` + `read-page` tools
3. **Search & Navigation** — BM25 chunker/indexer, `get-docs` + `search-docs` tools, prompt templates
4. **HTTP Mode & Authentication** — HTTP transport, API key auth, rate limiting, admin CLI
5. **Polish & Production Readiness** — CI/CD, Docker, E2E tests, performance tuning

**Current state**: The project is in the specification/design phase. There is no source code yet — only design documents in `docs/specs/`. **You are not allowed to write any code until the design phase is complete.** The design phase will be considered complete when all the documents are finalized and approved by Ankur.

All implementation decisions are captured in these six spec documents, which are the authoritative design source.

- `docs/specs/01-competitive-analysis.md` — Market analysis and key insight: query understanding is the accuracy bottleneck
- `docs/specs/02-functional-spec.md` — Problem statement, 5 MCP tools, 2 resources, 3 prompt templates, adapter chain, security model
- `docs/specs/03-technical-spec.md` — System architecture, data models, two-tier cache, BM25 search, database schema (7 SQLite tables)
- `docs/specs/04-implementation-guide.md` — Project structure, dependencies, coding conventions, 6 implementation phases (0-5), testing strategy
- `docs/specs/05-library-resolution.md` — Library name → documentation source mapping, runtime resolution algorithm (6 steps), curated registries as seed data (llms-txt-hub, Awesome-llms-txt), PyPI enrichment, repo-based grouping
- `docs/specs/06-registry-build-system.md` — Build-time discovery pipeline, PyPI metadata extraction, llms.txt probing (10+ URL patterns), content validation, hub resolution, quality assurance

### Research Documents

Additional research documents that inform the specifications:

- `docs/research/llms-txt-deployment-patterns.md` — Comprehensive survey of 70+ libraries showing real-world llms.txt deployment patterns, URL structures, version handling, and multi-variant strategies
- `docs/research/llms-txt-resolution-strategy.md` — Approved strategy for resolving library names to llms.txt URLs: registry-first approach with smart fallback, hub detection, content validation, and maintenance plan
- `docs/research/llms-txt-discovery-research.md` — Research on discovering libraries with llms.txt support, including curated registries (llms-txt-hub, Awesome-llms-txt) and Mintlify auto-generation findings

You are allowed to create new documents if you think that the discussion warrants it. Make sure you edit this section to link to any new documents you create.

## Overview of tech stack, architecture, coding conventions, configurations, commands and testing strategy

This section will be updated in later phases. Make sure these sections are appropriately filled out as soon as these details are finalized.
We must only add information that Claude cannot infer on its own. Use the following as a guide:

| Include in this section                              | Do NOT include                                     |
| ---------------------------------------------------- | -------------------------------------------------- |
| Bash commands Claude can't guess                     | Anything Claude can figure out by reading code     |
| Code style rules that differ from defaults           | Standard language conventions Claude already knows |
| Testing instructions and preferred test runners      | Detailed API documentation (link to docs instead)  |
| Repository etiquette (branch naming, PR conventions) | Information that changes frequently                |
| Architectural decisions specific to this project     | Long explanations or tutorials                     |
| Developer environment quirks (required env vars)     | File-by-file descriptions of the codebase          |
| Common gotchas or non-obvious behaviors              | Self-evident practices like "write clean code"     |

## Instructions for working with this repo

1. Your job is to act as a coding partner, not as an assistant.
2. Your key responsibility is making this repo better and useful for everyone, including Ankur and yourself.
3. Ankur appreciates honest feedback. Do not blindly agree to whatever he asks.
4. When brainstorming, actively participate and add value to the conversation rather than just answering questions.
5. You are a contributor to the project. Take ownership and actively look for ways to improve this repo.
6. Avoid making assumptions. Refer to online sources and cross-verify information. If the requirement is unclear, ask Ankur for clarification.
