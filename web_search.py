"""
web_search.py — بحث ويب حقيقي عبر Tavily API — النسخة المطورة.
"""
import os
import requests
from logger import log

TAVILY_KEY = os.getenv("TAVILY_API_KEY", "")
TAVILY_URL = "https://api.tavily.com/search"

EXCLUDE_DOMAINS = [
    "haraj.com.sa", "souq.com", "noon.com", "extra.com",
    "jarir.com", "alarabiya.net", "okaz.com.sa", "sabq.org",
]


def is_search_available() -> bool:
    return bool(TAVILY_KEY)


def search_real_links(query: str, max_results: int = 5) -> list:
    """يبحث ويرجع [{title, url, snippet}] أو [] عند الفشل."""
    if not TAVILY_KEY:
        return []
    try:
        resp = requests.post(
            TAVILY_URL,
            json={
                "api_key":        TAVILY_KEY,
                "query":          query,
                "max_results":    max_results,
                "search_depth":   "basic",
                "topic":          "general",
                "exclude_domains": EXCLUDE_DOMAINS,
            },
            timeout=15,
        )
        if resp.status_code != 200:
            log(f"[SEARCH_ERR] status={resp.status_code}")
            return []
        results = []
        for item in resp.json().get("results", [])[:max_results]:
            results.append({
                "title":   item.get("title", "")[:150],
                "url":     item.get("url", ""),
                "snippet": item.get("content", "")[:200],
            })
        log(f"[SEARCH_OK] query={query[:50]} found={len(results)}")
        return results
    except Exception as e:
        log(f"[SEARCH_FAIL] {e}")
        return []


def format_links_for_prompt(results: list) -> str:
    if not results:
        return ""
    lines = ["\n\n[روابط حقيقية — استخدمها حرفياً لا تخترع أخرى]:"]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']} — {r['url']}")
    return "\n".join(lines)
