---
name: web-research-fallback
description: "Web research cascade: API, RSS, WebSearch, DrissionPage browser, and PDF parsing."
category: GENERAL
version: 1.0.0
platforms: [windows, linux, macos]
tags: [fallback, browser, pdf, paywall, cloudflare, scrape, read_url, web_search, dokumen, jurnal]
---

# Web Research Cascade & Anti-Block Fallback Playbook

## 1. Operating Principle
When performing online research, reading articles, or gathering external intelligence, network and scraper failures are inevitable due to JavaScript rendering, Cloudflare protections, paywalls, or PDF formats. 
Monika implements a deterministic 4-tier fallback cascade to ensure zero information drop.

## 2. The 4-Tier Fallback Cascade

```
[Tier 1: Direct HTTP / RSS / API]
       |
       v (If 403, 429, JS-render required, or timeout)
[Tier 2: Web Search & Aggregators (DuckDuckGo / Bing / Google API)]
       |
       v (If page blocked, obfuscated, or requires interaction)
[Tier 3: Headless DrissionPage Browser (`browser` tool)]
       |
       v (If PDF document or Wayback Machine archive required)
[Tier 4: PDF Extraction (`pypdf`) or Wayback Machine (`archive.org`)]
```

## 3. Tool Usage Directives

### Direct URL Inspection (`read_url`)
- Attempt initial HTTP fetch.
- If response contains status 403, Cloudflare challenge, or empty body:
  - Immediately escalate to `browser(action="open", url=...)`.

### Headless Browser Automation (`browser`)
- Use DrissionPage-powered browser tool for dynamic Single Page Applications (SPAs), financial dashboards, or anti-bot protected sites:
  ```python
  # 1. Open target URL
  browser(action="open", url="https://example.com/research")
  # 2. Extract DOM content or text
  browser(action="extract", selector="article.content")
  # 3. If needed, click interactive tab or scroll
  browser(action="click", selector="button#view-full")
  # 4. Clean up resources
  browser(action="close")
  ```

### Document & PDF Processing
- For central bank PDFs, academic papers, and broker reports:
  - If URL ends in `.pdf` or returns `application/pdf`, extract text via `pypdf`.
  - For archived historical pages, prepend `https://web.archive.org/web/` to the requested target URL.

## 4. Quality Standard
Never inform the user "I cannot access this website" without exhausting all 4 fallback tiers.
