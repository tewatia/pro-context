# ProContext: Security Specification

> **Document**: 05-security-spec.md
> **Status**: Draft v1
> **Last Updated**: 2026-02-24
> **Depends on**: 01-functional-spec.md, 02-technical-spec.md

---

## Table of Contents

- [1. Scope and Threat Actors](#1-scope-and-threat-actors)
- [2. Trust Boundaries](#2-trust-boundaries)
- [3. Threat Model](#3-threat-model)
  - [3.1 SSRF via Documentation Fetching](#31-ssrf-via-documentation-fetching)
  - [3.2 Malicious Documentation Content](#32-malicious-documentation-content)
  - [3.3 Registry Poisoning](#33-registry-poisoning)
  - [3.4 DNS Rebinding (HTTP Transport)](#34-dns-rebinding-http-transport)
  - [3.5 Cache Tampering](#35-cache-tampering)
  - [3.6 Dependency Supply Chain](#36-dependency-supply-chain)
- [4. Security Controls Summary](#4-security-controls-summary)
- [5. Known Limitations and Accepted Risks](#5-known-limitations-and-accepted-risks)
- [6. Data Handling](#6-data-handling)
- [7. Dependency Vulnerability Management](#7-dependency-vulnerability-management)
- [8. Security Testing by Phase](#8-security-testing-by-phase)

---

## 1. Scope and Threat Actors

This document covers the security model for the open-source ProContext MCP server (v0.1) in its two deployment modes:

- **stdio** — local process, spawned by the MCP client. No network listener.
- **HTTP** — single `/mcp` endpoint on a trusted network. Optional shared-key authentication is controlled by `server.auth_enabled` and `server.auth_key`, and is disabled by default (see 01-functional-spec, Section 10, D3).

### In-scope threat actors

| Actor                                | Description                                                                                                                                    | Relevant mode             |
| ------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------- |
| **Compromised documentation source** | A legitimate library's docs site is compromised or a malicious `llms.txt` is published. Content served to the AI agent is attacker-controlled. | Both                      |
| **Man-in-the-middle**                | Attacker on the network path between ProContext and upstream documentation hosts. Can modify responses in transit.                             | Both (mitigated by HTTPS) |
| **Local network attacker**           | Attacker on the same network as the HTTP-mode server. Can send requests directly if auth is disabled, or if the shared key is known.           | HTTP only                 |
| **Compromised registry publisher**   | Attacker gains write access to the registry hosted on GitHub Pages. Can inject entries pointing to malicious domains.                          | Both                      |

### Out-of-scope threat actors

- **Unauthenticated internet attackers** — HTTP mode is designed for trusted-network or localhost use, not public internet exposure (01-functional-spec, Section 10, D3). Exposing ProContext to the public internet without a reverse proxy is unsupported. For non-local deployments, set `server.auth_enabled=true`.
- **Malicious MCP client** — The MCP client spawns the server process. A malicious client already has full control of the server's execution environment.

---

## 2. Trust Boundaries

ProContext operates at the intersection of five trust boundaries. Understanding what is trusted, validated, and unvalidated at each boundary is critical for security review.

```
┌─────────────────────────────────────────────────────────────┐
│  MCP Client (AI Agent)                                      │
│  Trust level: FULL — spawns the server, consumes all output │
└────────────────────────────┬────────────────────────────────┘
                             │ stdio / HTTP
┌────────────────────────────▼────────────────────────────────┐
│  ProContext MCP Server                                     │
│                                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────┐  │
│  │ Registry │  │ Fetcher  │  │  Cache   │  │  Resolver  │  │
│  └────┬─────┘  └────┬─────┘  └──────────┘  └────────────┘  │
└───────┼──────────────┼──────────────────────────────────────┘
        │              │
        ▼              ▼
┌──────────────┐  ┌──────────────────────┐
│  GitHub      │  │  Documentation       │
│  Pages       │  │  Sources             │
│  (registry)  │  │  (llms.txt, pages)   │
└──────────────┘  └──────────────────────┘
```

| Boundary                             | What is trusted                                  | What is validated                                                            | What is unvalidated                                                              |
| ------------------------------------ | ------------------------------------------------ | ---------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| **MCP Client → Server**              | Client identity (it spawns us)                   | Tool inputs via Pydantic (02-technical-spec, Section 3.3)                    | —                                                                                |
| **Server → Registry (GitHub Pages)** | HTTPS transport integrity                        | SHA-256 checksum of downloaded registry (02-technical-spec, Section 9)       | Content semantics — a valid-checksum registry with malicious entries is accepted |
| **Server → llms.txt sources**        | Domain membership (SSRF allowlist from registry) | URL against allowlist + private IP blocking (02-technical-spec, Section 5.2) | Content — returned as-is to the agent                                            |
| **Server → documentation pages**     | Same as llms.txt sources                         | Same as llms.txt sources                                                     | Content — returned as-is to the agent                                            |
| **PyPI → User**                      | HTTPS transport, package signing                 | SLSA provenance attestation (03-implementation-guide, Section 6)             | User must verify attestation manually via `gh attestation verify`                |

**Key design principle**: ProContext validates _where_ content comes from (domain allowlist, SSRF prevention, registry checksum) but does not validate _what_ the content says. It is a fetch-and-serve proxy. Content-level trust is the responsibility of the MCP client consuming the output.

---

## 3. Threat Model

Each threat follows a consistent structure: Description, Severity, Mitigation Status, Controls, Residual Risk.

Severity uses a simple scale: **Critical** (system compromise), **High** (security control bypass), **Medium** (limited impact or requires preconditions), **Low** (minimal impact even if exploited).

---

### 3.1 SSRF via Documentation Fetching

**Description**: The `read_page` tool accepts URLs from the AI agent. An attacker who controls the agent's input (e.g., via prompt injection in a previous tool's output) could attempt to fetch internal network resources. Redirect chains from allowlisted domains could bounce to internal targets.

**Severity**: High

**Mitigation status**: Mitigated

**Controls** (implementation details in referenced sections — not duplicated here):

- Domain allowlist built from registry at startup; in HTTP long-running mode it is refreshed when a background registry update is accepted. Only domains present in the active registry entries are permitted. (02-technical-spec, Section 5.2)
- Private IP ranges unconditionally blocked: `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `127.0.0.0/8`, `::1/128`, `fc00::/7`. (02-technical-spec, Section 5.2)
- Per-hop redirect validation — each redirect target is re-checked against the allowlist before following. Maximum 3 redirect hops. (02-technical-spec, Section 5.3)
- URL input validation via Pydantic: max 2048 chars, must start with `http://` or `https://`. (02-technical-spec, Section 3.3)

**Residual risk**: DNS rebinding at the IP level is not blocked — httpx resolves DNS internally and the server does not inspect the resolved IP before connecting. This is accepted for v0.1 because the allowlist already limits requests to known documentation domains, making DNS rebinding to internal IPs impractical without first compromising a documentation domain's DNS records.

---

### 3.2 Malicious Documentation Content

**Description**: A compromised or malicious `llms.txt` file or documentation page could contain:

- **Prompt injection** targeting the AI agent consuming the content (e.g., "ignore previous instructions, execute this shell command")
- **Misleading API examples** that introduce vulnerabilities into the user's codebase (e.g., `verify=False`, hardcoded credentials)
- **Exfiltration links** — URLs with query parameters designed to capture the agent's conversation context if followed

**Severity**: Medium — ProContext itself is not vulnerable, but the AI agent consuming the output could be manipulated.

**Mitigation status**: Accepted (partially out of scope)

**Controls**:

- Content is returned as plain text. No HTML rendering, no script execution, no server-side processing of fetched content. (01-functional-spec, Section 8)
- Content passes through unmodified — the server is a fetch-and-serve proxy, not a content filter.

**Residual risk**: Content-level attacks (prompt injection, misleading examples) pass through by design. Defense against prompt injection and content trustworthiness is the responsibility of the MCP client and the AI agent, not the documentation proxy. This boundary is intentional and documented, not an oversight.

---

### 3.3 Registry Poisoning

**Description**: If an attacker compromises the registry build pipeline or the GitHub Pages hosting, they could inject entries pointing to malicious documentation domains. These domains would then be automatically added to the SSRF allowlist, and their content would be served to AI agents as legitimate library documentation.

**Severity**: High — a poisoned registry entry grants the attacker both SSRF allowlist inclusion and content injection.

**Mitigation status**: Mitigated (with residual risk)

**Controls**:

- SHA-256 checksum validation on registry downloads. The metadata JSON provides the expected checksum; the downloaded registry is verified before use. On mismatch, the existing registry is retained. (02-technical-spec, Section 9)
- Startup checksum validation of the local registry pair (`known-libraries.json` + `registry-state.json`) detects torn/partial writes and forces bundled fallback instead of trusting inconsistent local state. (02-technical-spec, Section 9)
- Bundled fallback snapshot (`data/known-libraries.json`) shipped with the package provides a known-good baseline. (01-functional-spec, Section 6)
- Registry served over HTTPS from GitHub Pages — relies on GitHub's infrastructure security for transport integrity.

**Residual risk**: If both the registry JSON and the metadata JSON (containing the checksum) are compromised simultaneously, the checksum provides no protection. This is a single-origin trust problem inherent to the architecture. Future mitigations: signed registries (GPG or Sigstore), multiple independent metadata sources.

---

### 3.4 DNS Rebinding (HTTP Transport)

**Description**: In HTTP mode, a malicious webpage could use DNS rebinding to make requests to the ProContext server running on localhost, using the server as an SSRF proxy to access the user's internal network.

**Severity**: Medium (HTTP mode only; stdio is unaffected)

**Mitigation status**: Mitigated

**Controls**:

- Optional bearer key authentication — when `server.auth_enabled=true`, all HTTP requests must include `Authorization: Bearer <key>`. If `server.auth_key` is empty, a key is auto-generated at startup. Requests with a missing or incorrect key are rejected with HTTP 401. A browser-based DNS rebinding attack cannot inject the `Authorization` header into cross-origin requests. (02-technical-spec, Section 8.2)
- Origin validation in `MCPSecurityMiddleware`. Only `http://localhost` and `https://localhost` (with optional port) are permitted. Non-localhost origins are rejected with HTTP 403. (02-technical-spec, Section 8.2)
- Protocol version validation — requests with unknown `MCP-Protocol-Version` headers are rejected with HTTP 400. (02-technical-spec, Section 8.2)
- Startup warning when `server.auth_enabled=false` to make unauthenticated deployment explicit in logs. (02-technical-spec, Section 8.2)

**Residual risk**: If auth is disabled (default), any client on the reachable network can call the endpoint. If auth is enabled, non-browser clients that obtain the bearer key can make requests. The key is a shared secret — if leaked (e.g., via config file exposure), any client with the key has full access. This is accepted for the trusted-network deployment model (01-functional-spec, Section 10, D3).

---

### 3.5 Cache Tampering

**Description**: The SQLite cache stores documentation content in plaintext on the local filesystem. An attacker with local filesystem access could modify cached content, which would then be served to the AI agent as legitimate documentation.

**Severity**: Low

**Mitigation status**: Accepted

**Controls**: None beyond operating system filesystem permissions. Cache is plaintext SQLite with WAL mode. No encryption, no integrity checking of cached content.

**Rationale**: An attacker who can write to the ProContext data directory (platform-specific, resolved by `platformdirs`) already has write access to the user's source code, shell configuration, and SSH keys. Encrypting the cache provides no meaningful additional protection in this threat model. This is the correct trade-off for a local-first tool.

---

### 3.6 Dependency Supply Chain

**Description**: ProContext has 9 runtime dependencies. A compromised dependency update could introduce malicious code that runs with the server's permissions (which are the user's permissions).

**Severity**: Medium

**Mitigation status**: Partially mitigated

**Controls**:

- Minor-version upper bounds on all runtime dependencies (e.g., `>=0.27.0,<1.0.0`). Prevents automatic adoption of new major versions. (03-implementation-guide, Section 2)
- SLSA provenance attestation on ProContext's own releases — cryptographic proof of which source commit produced which artifact. (03-implementation-guide, Section 6)
- License compatibility verified for all dependencies. (03-implementation-guide, Section 2)
- `uv.lock` committed for reproducible builds — ensures the same dependency versions across all installs.

**Residual risk**: Upper bounds prevent major version surprises but do not protect against a compromised minor/patch release within bounds. Dependency vulnerability scanning (Section 7) addresses this gap.

---

## 4. Security Controls Summary

| Control                         | Protects against                                            | Spec reference         | Source file                     | Phase |
| ------------------------------- | ----------------------------------------------------------- | ---------------------- | ------------------------------- | ----- |
| Optional bearer key auth (HTTP) | Unauthorized access in HTTP mode (when `auth_enabled=true`) | 02-technical-spec §8.2 | `transport.py`                  | 4     |
| Domain allowlist (SSRF)         | Internal network access via fetcher                         | 02-technical-spec §5.2 | `fetcher.py`                    | 2     |
| Private IP blocking             | Fetching localhost/private resources                        | 02-technical-spec §5.2 | `fetcher.py`                    | 2     |
| Per-hop redirect validation     | Redirect-based SSRF bypass                                  | 02-technical-spec §5.3 | `fetcher.py`                    | 2     |
| Pydantic input validation       | Malformed/oversized inputs                                  | 02-technical-spec §3.3 | `models/tools.py`               | 1–3   |
| Registry checksum (SHA-256)     | Registry tampering                                          | 02-technical-spec §9   | `registry.py`                   | 5     |
| Origin validation (HTTP)        | DNS rebinding attacks                                       | 02-technical-spec §8.2 | `transport.py`                  | 4     |
| Protocol version check (HTTP)   | Unknown protocol exploitation                               | 02-technical-spec §8.2 | `transport.py`                  | 4     |
| Dependency version bounds       | Major-version supply chain risk                             | 03-impl-guide §2       | `pyproject.toml`                | 0     |
| SLSA provenance attestation     | Build pipeline tampering                                    | 03-impl-guide §6       | `.github/workflows/release.yml` | 5     |

---

## 5. Known Limitations and Accepted Risks

These are intentional trade-offs documented for transparency, not oversights.

### 5.1 Base domain simplification

The SSRF allowlist extracts the last two DNS labels as the base domain (e.g., `api.docs.langchain.com` → `langchain.com`). This is a simplification — shared hosting platforms like `github.io` and `readthedocs.io` allow any project to serve content. If any project on `github.io` is in the registry, all `github.io` subdomains are permitted.

**Mitigation path**: Adopt `tldextract` for eTLD+1 matching in a future version. See 02-technical-spec, Section 5.2 (known limitation).

### 5.2 Bearer key is a shared secret (when enabled)

HTTP mode supports an optional bearer key controlled by `auth_enabled`. When enabled, the key is a static shared secret — there is no key rotation, hashing, rate-limited brute-force protection, or revocation mechanism. If the key is leaked (e.g., via config file exposure or process listing), any client with the key has full access until the key is changed and the server is restarted.

**Rationale**: This is lightweight access control for a trusted-network tool, not a full auth system. See 01-functional-spec, Section 10, D3.

### 5.3 No content validation

Documentation content fetched from upstream sources passes through to the AI agent unmodified. Prompt injection, misleading examples, or exfiltration links in documentation are not detected or filtered.

**Rationale**: ProContext is a fetch-and-serve proxy. Content filtering is the MCP client's responsibility. See Section 3.2.

### 5.4 No rate limiting

A client could exhaust upstream documentation sources by triggering rapid cache misses. The 24-hour cache TTL provides partial mitigation — repeated requests for the same content are served from cache.

**Rationale**: Rate limiting adds complexity disproportionate to the risk for a single-user local tool.

### 5.5 Plaintext cache

The SQLite cache stores documentation content without encryption. Local filesystem access grants full read/write to cached content.

**Rationale**: Local filesystem access already grants access to the user's source code and credentials. Cache encryption provides no additional protection. See Section 3.5.

---

## 6. Data Handling

> **`<data_dir>`** = `platformdirs.user_data_dir("procontext")`: `~/.local/share/procontext` on Linux, `~/Library/Application Support/procontext` on macOS, `C:\Users\<user>\AppData\Local\procontext` on Windows.

### What is stored

| Location                                                  | Content                                 | Purpose                                    |
| --------------------------------------------------------- | --------------------------------------- | ------------------------------------------ |
| `<data_dir>/cache.db`                      | `toc_cache` table: raw llms.txt content | Avoid re-fetching table of contents        |
| `<data_dir>/cache.db`                      | `page_cache` table: full page markdown  | Avoid re-fetching documentation pages      |
| `<data_dir>/registry/known-libraries.json` | Library registry                        | Local copy of the registry for offline use |
| `<data_dir>/registry/registry-state.json`  | Registry metadata (`version`, `checksum`, `updated_at`) | Local version/checksum source for update checks |

### What is NOT stored

- No user data or query history
- No session logs (logs go to stderr, not persisted by default)
- No credentials, API keys, or tokens
- No telemetry or analytics

### Retention

- Cache entries expire after 24 hours (configurable via `cache.ttl_hours` in `procontext.yaml`).
- Cleanup job runs every 6 hours, deleting entries older than 7 days past expiry.
- See 02-technical-spec, Section 6.1 for the full cache schema.

### Deletion

Delete the ProContext data directory to remove all persistent data (cache + registry). The data directory is platform-specific (`<data_dir>` = `platformdirs.user_data_dir("procontext")`): `~/.local/share/procontext` on Linux, `~/Library/Application Support/procontext` on macOS, `C:\Users\<user>\AppData\Local\procontext` on Windows. No other filesystem locations are written to.

### PII

ProContext stores no personally identifiable information. The cache contains only publicly available library documentation content.

---

## 7. Dependency Vulnerability Management

### Audit mechanism

Run `pip-audit` (or equivalent) as a CI step to detect known vulnerabilities in the dependency tree. Add to the CI pipeline (03-implementation-guide, Section 6) once Phase 5 CI is implemented.

### Automated alerts

Configure Dependabot (or Renovate) on the GitHub repository for automated pull request creation when dependency CVEs are published.

### Response SLA targets

| Severity | CVSS   | Response                        |
| -------- | ------ | ------------------------------- |
| Critical | >= 9.0 | Patch or pin within 72 hours    |
| High     | >= 7.0 | Patch within 2 weeks            |
| Medium   | >= 4.0 | Address in next regular release |
| Low      | < 4.0  | Address in next regular release |

### Version pinning policy

- `uv.lock` committed for reproducible builds.
- `pyproject.toml` uses minor-version upper bounds (e.g., `>=0.27.0,<1.0.0`).
- Re-verify dependency license compatibility whenever a dependency is added or its major version is bumped. See 03-implementation-guide, Section 2.

---

## 8. Security Testing by Phase

Each implementation phase introduces new attack surface. The following table maps specific security tests to the phase that introduces the relevant code.

### Phase 1: Registry & Resolution

| Test                                           | What it verifies                                 |
| ---------------------------------------------- | ------------------------------------------------ |
| Oversized query input (>500 chars)             | Pydantic validation rejects with `INVALID_INPUT` |
| Query with shell metacharacters (`; rm -rf /`) | Normalisation handles safely, no injection       |
| Malformed library ID pattern                   | Pydantic rejects non-`[a-z0-9_-]+` patterns      |
| Registry entry with missing required fields    | `RegistryEntry` Pydantic model rejects on load   |

### Phase 2: Fetcher & Cache

| Test                                                                        | What it verifies                                                               |
| --------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| Fetch URL targeting private IPv4 (`10.x`, `172.16.x`, `192.168.x`, `127.x`) | Blocked by private IP check                                                    |
| Fetch URL targeting private IPv6 (`::1`, `fc00::`)                          | Blocked by private IP check                                                    |
| Redirect chain to non-allowlisted domain                                    | Blocked at redirect hop                                                        |
| Redirect chain to private IP                                                | Blocked at redirect hop                                                        |
| Redirect chain exceeding 3 hops                                             | Raises `PAGE_FETCH_FAILED`                                                     |
| URL with allowlisted domain but non-HTTPS scheme                            | Rejected by URL validation                                                     |
| `github.io` subdomain not in registry                                       | Verify shared-hosting limitation is understood (documents behaviour, may pass) |
| SQL injection via library ID in cache key                                   | Parameterised queries prevent injection (verify no string formatting in SQL)   |
| SQL injection via URL in cache key                                          | Same as above                                                                  |
| Cache read failure (simulated `aiosqlite.Error`)                            | Returns `None`, does not leak error details                                    |
| Cache write failure (simulated `aiosqlite.Error`)                           | Fetched content still returned, error logged                                   |

### Phase 3: Page Reading & Parser

| Test                                    | What it verifies                                  |
| --------------------------------------- | ------------------------------------------------- |
| Extremely large document (>1MB)         | Server handles without memory exhaustion or crash |
| Deeply nested code fences (100+ levels) | Parser terminates correctly                       |
| URL input >2048 chars                   | Pydantic validation rejects with `INVALID_INPUT`  |

### Phase 4: HTTP Transport

| Test                                                                                             | What it verifies                                                                          |
| ------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------- |
| `auth_enabled=true` + explicit `auth_key` + valid `Authorization: Bearer <key>`                  | Request proceeds (HTTP 200)                                                               |
| `auth_enabled=true` + explicit `auth_key` + missing `Authorization` header                       | Rejected with HTTP 401                                                                    |
| `auth_enabled=true` + explicit `auth_key` + incorrect bearer key                                 | Rejected with HTTP 401                                                                    |
| `auth_enabled=true` + explicit `auth_key` + malformed `Authorization` header (e.g., `Basic ...`) | Rejected with HTTP 401                                                                    |
| `auth_enabled=true` + empty `auth_key`                                                           | Key auto-generated at startup and logged                                                  |
| `auth_enabled=false`                                                                             | Auth disabled; requests without `Authorization` are allowed and startup warning is logged |
| Non-localhost `Origin` header                                                                    | Rejected with HTTP 403                                                                    |
| Missing `Origin` header (with auth requirements satisfied)                                       | Allowed (standard for non-browser clients)                                                |
| Various localhost formats (`127.0.0.1`, `localhost`, `[::1]`)                                    | Accepted or rejected per middleware regex                                                 |
| Unknown `MCP-Protocol-Version` header                                                            | Rejected with HTTP 400                                                                    |
| Error response body                                                                              | No stack traces, internal file paths, or debug info leaked                                |

### Phase 5: Registry Updates & Polish

| Test                                          | What it verifies                                              |
| --------------------------------------------- | ------------------------------------------------------------- |
| Registry download with valid checksum         | Accepted, indexes rebuilt                                     |
| Registry download with mismatched checksum    | Rejected, existing registry retained, warning logged          |
| Registry download with missing checksum field | Rejected, existing registry retained                          |
| No `verify=False` in codebase                 | Grep for `verify=False` — must not appear in any `httpx` call |
| `pip-audit` (or equivalent) in CI             | No known CVEs in dependency tree                              |
