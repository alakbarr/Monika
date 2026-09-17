# ==============================================================================
# File: data_sources/academic_search.py
# ==============================================================================

"""
Academic Paper Search Client.

Searches quantitative finance, statistical modeling, algorithmic trading,
and economic research publications on arXiv.org via public Atom/XML API.
"""

import asyncio
import logging
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Optional
import aiohttp

logger = logging.getLogger("TradingAgent.AcademicSearch")

ARXIV_API_URL = "https://export.arxiv.org/api/query"
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


class AcademicSearchClient:
    """Client for querying academic research papers via arXiv public API."""

    def __init__(self, timeout_seconds: float = 15.0):
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)

    async def search_papers(self, query: str, max_results: int = 5) -> Dict[str, Any]:
        """
        Searches arXiv for academic literature matching the query.
        Returns list of structured paper metadata (title, summary, authors, links).
        """
        clean_query = (query or "").strip()
        if not clean_query:
            return {"success": False, "query": "", "error": "Query cannot be empty", "papers": []}

        # Build arXiv query url
        params = {
            "search_query": f"all:{clean_query}",
            "start": "0",
            "max_results": str(max(1, min(20, max_results))),
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
        encoded_query = urllib.parse.urlencode(params)
        url = f"{ARXIV_API_URL}?{encoded_query}"

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        return {
                            "success": False,
                            "query": clean_query,
                            "status": response.status,
                            "error": f"arXiv API returned HTTP {response.status}",
                            "papers": [],
                        }

                    xml_data = await response.text()
                    papers = self._parse_atom_feed(xml_data)
                    return {
                        "success": True,
                        "query": clean_query,
                        "total_results": len(papers),
                        "papers": papers,
                    }

        except asyncio.TimeoutError:
            logger.warning(f"AcademicSearch timeout for query: '{clean_query}'")
            return {"success": False, "query": clean_query, "error": "Search timed out", "papers": []}
        except Exception as e:
            logger.warning(f"AcademicSearch error: {e}")
            return {"success": False, "query": clean_query, "error": str(e), "papers": []}

    def _parse_atom_feed(self, xml_text: str) -> List[Dict[str, Any]]:
        """Parses arXiv Atom XML response into structured dictionary items."""
        papers = []
        try:
            root = ET.fromstring(xml_text)
            for entry in root.findall("atom:entry", ATOM_NS):
                title_elem = entry.find("atom:title", ATOM_NS)
                summary_elem = entry.find("atom:summary", ATOM_NS)
                published_elem = entry.find("atom:published", ATOM_NS)
                id_elem = entry.find("atom:id", ATOM_NS)

                # Extract authors
                authors = []
                for author_elem in entry.findall("atom:author", ATOM_NS):
                    name_elem = author_elem.find("atom:name", ATOM_NS)
                    if name_elem is not None and name_elem.text:
                        authors.append(name_elem.text.strip())

                # Extract link (pdf or abstract)
                paper_url = ""
                for link_elem in entry.findall("atom:link", ATOM_NS):
                    if link_elem.get("title") == "pdf":
                        paper_url = link_elem.get("href", "")
                        break
                    elif not paper_url:
                        paper_url = link_elem.get("href", "")

                title = " ".join((title_elem.text or "").split()) if title_elem is not None else "Untitled"
                summary = " ".join((summary_elem.text or "").split()) if summary_elem is not None else ""
                published = (published_elem.text or "")[:10] if published_elem is not None else ""
                arxiv_id = (id_elem.text or "") if id_elem is not None else ""

                final_url = paper_url or arxiv_id
                if final_url.startswith("http://"):
                    final_url = "https://" + final_url[7:]
                if arxiv_id.startswith("http://"):
                    arxiv_id = "https://" + arxiv_id[7:]

                papers.append({
                    "title": title,
                    "authors": authors,
                    "summary": summary,
                    "published": published,
                    "url": final_url,
                    "arxiv_id": arxiv_id,
                })
        except Exception as e:
            logger.error(f"Failed to parse arXiv Atom XML: {e}")

        return papers
