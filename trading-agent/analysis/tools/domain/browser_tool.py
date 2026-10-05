# ==============================================================================
# File: analysis/tools/domain/browser_tool.py
# ==============================================================================

"""
Interactive Browser Automation Tool via DrissionPage.
Provides real browser automation when web_search, scrapers, or HTTP read_url fail
due to JavaScript rendering, Cloudflare Turnstile, complex SPAs, or interactive pages.

Supported actions:
- open: navigate to URL and wait for DOM load
- extract: extract clean text or element text by CSS/XPath selector
- click: click an element matching selector
- type: type text into an input field matching selector
- screenshot: capture full page screenshot to PNG and return path
- close: terminate browser instance
"""

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Dict, Any, Optional

from scrapers.base_scraper import BaseScraper
from analysis.tools.unified_registry import unified_tool_registry
from pydantic import BaseModel, Field

logger = logging.getLogger("TradingAgent.Tools.Browser")

_ACTIVE_BROWSER_SCRAPER: Optional[BaseScraper] = None


def _get_or_create_browser(headless: bool = True) -> BaseScraper:
    global _ACTIVE_BROWSER_SCRAPER
    if _ACTIVE_BROWSER_SCRAPER is not None:
        try:
            if _ACTIVE_BROWSER_SCRAPER.page:
                return _ACTIVE_BROWSER_SCRAPER
        except Exception:
            _ACTIVE_BROWSER_SCRAPER = None

    _ACTIVE_BROWSER_SCRAPER = BaseScraper(headless=headless, profile_name="monika_browser_tool")
    return _ACTIVE_BROWSER_SCRAPER


def _close_browser() -> None:
    global _ACTIVE_BROWSER_SCRAPER
    if _ACTIVE_BROWSER_SCRAPER is not None:
        try:
            _ACTIVE_BROWSER_SCRAPER.close()
        except Exception:
            pass
        _ACTIVE_BROWSER_SCRAPER = None


class BrowserActionInput(BaseModel):
    action: str = Field(..., description="Action to perform: 'open', 'extract', 'click', 'type', 'screenshot', 'close'.")
    url: Optional[str] = Field(None, description="Target URL (required for 'open').")
    selector: Optional[str] = Field(None, description="CSS or XPath selector for click/type/extract.")
    text: Optional[str] = Field(None, description="Text to type into input field (for 'type').")
    headless: bool = Field(True, description="Run browser in headless mode (default True).")


def _run_browser_action_sync(params: BrowserActionInput) -> Dict[str, Any]:
    action = params.action.lower().strip()

    if action == "close":
        _close_browser()
        return {"status": "success", "message": "Browser session closed."}

    scraper = _get_or_create_browser(headless=params.headless)
    page = scraper.page
    if not page:
        return {"status": "error", "error": "Failed to initialize Chromium browser page."}

    try:
        if action == "open":
            if not params.url:
                return {"status": "error", "error": "Parameter 'url' is required for action 'open'."}
            success = scraper.navigate_with_fallback(params.url, timeout=20)
            if hasattr(page, "wait"):
                page.wait(2)
            title = getattr(page, "title", "")
            return {
                "status": "success" if success else "warning",
                "action": "open",
                "url": params.url,
                "title": title,
                "current_url": getattr(page, "url", params.url),
            }

        elif action == "extract":
            if params.selector:
                ele = page.ele(params.selector)
                if not ele:
                    return {"status": "error", "error": f"Element not found for selector: '{params.selector}'"}
                extracted = ele.text
            else:
                extracted = getattr(page, "text", "") or ""

            # Truncate to safe token size
            return {
                "status": "success",
                "action": "extract",
                "selector": params.selector,
                "content": extracted[:10000],
                "length": len(extracted),
            }

        elif action == "click":
            if not params.selector:
                return {"status": "error", "error": "Parameter 'selector' is required for action 'click'."}
            ele = page.ele(params.selector)
            if not ele:
                return {"status": "error", "error": f"Element not found for selector: '{params.selector}'"}
            ele.click()
            if hasattr(page, "wait"):
                page.wait(1.5)
            return {
                "status": "success",
                "action": "click",
                "selector": params.selector,
                "current_url": getattr(page, "url", ""),
            }

        elif action == "type":
            if not params.selector or params.text is None:
                return {"status": "error", "error": "Parameters 'selector' and 'text' are required for action 'type'."}
            ele = page.ele(params.selector)
            if not ele:
                return {"status": "error", "error": f"Element not found for selector: '{params.selector}'"}
            ele.input(params.text)
            return {
                "status": "success",
                "action": "type",
                "selector": params.selector,
                "typed_text": params.text,
            }

        elif action == "screenshot":
            out_dir = Path("data/screenshots")
            out_dir.mkdir(parents=True, exist_ok=True)
            ts = int(time.time())
            filename = f"browser_{ts}.png"
            filepath = out_dir / filename
            page.get_screenshot(path=str(filepath))
            return {
                "status": "success",
                "action": "screenshot",
                "file_path": str(filepath.resolve()),
                "filename": filename,
            }

        else:
            return {"status": "error", "error": f"Unknown action: '{action}'. Must be open, extract, click, type, screenshot, or close."}

    except Exception as e:
        logger.error(f"Browser action '{action}' failed: {e}", exc_info=True)
        return {"status": "error", "action": action, "error": str(e)}


@unified_tool_registry.register(
    name="browser",
    category="RESEARCH",
    input_model=BrowserActionInput,
)
async def handle_browser_tool(params: BrowserActionInput, context: Optional[Any] = None) -> Dict[str, Any]:
    """Execute browser automation action asynchronously in a worker thread."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _run_browser_action_sync, params)
