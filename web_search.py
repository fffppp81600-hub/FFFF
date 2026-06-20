"""
web_search.py — بحث ويب حقيقي عبر Tavily (مجاني حتى 1000 بحث/شهر، بدون بطاقة).

يُستخدم عندما يطلب المستخدم محتوى يحتاج روابط حقيقية فعلاً (فيديوهات يوتيوب، مواقع منافسين،
صفحات مرجعية)، بدل ما يخترع AI روابط وهمية لا تعمل.

الإعداد: ضع TAVILY_API_KEY في متغيرات البيئة (مفتاح مجاني من https://tavily.com).
"""
import os
import requests
from logger import log

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
TAVILY_URL = "https://api.tavily.com/search"

# نطاقات سعودية/خليجية شائعة تُستثنى صريحاً من نتائج البحث (استثناء فعلي حقيقي،
# أقوى من country boosting وحده لأن الأخير يفضّل فقط ولا يضمن الاستثناء الكامل).
# Tavily exclude_domains يتوقع أسماء نطاقات فعلية، لا أكواد دول — هذي قائمة مبدئية، أضف عليها حسب الحاجة.
EXCLUDE_GULF_DOMAINS = [
    "haraj.com.sa", "souq.com", "noon.com", "extra.com", "jarir.com",
    "alarabiya.net", "okaz.com.sa", "sabq.org", "spa.gov.sa",
    "hungerstation.com", "tamimimarkets.com", "panda.com.sa",
]


def is_search_available() -> bool:
    return bool(TAVILY_API_KEY)


def search_real_links(query: str, max_results: int = 5, country: str = "austria") -> list:
    """
    يبحث عن روابط حقيقية متعلقة بالاستعلام ويرجعها كقائمة:
    [{"title": ..., "url": ..., "snippet": ...}, ...]
    country: يفضّل نتائج من هذا البلد (Tavily "country boosting"، يعمل فقط مع topic="general").
    EXCLUDE_GULF_DOMAINS: استثناء فعلي (لا تفضيل فقط) لأشهر النطاقات السعودية/الخليجية،
    لأن country boosting وحده لا يمنع ظهورها بشكل مضمون.
    يرجع [] (قائمة فاضية) عند أي فشل أو غياب المفتاح، بدون رفع استثناء يكسر تدفق البوت.
    """
    if not TAVILY_API_KEY:
        log("[WEB_SEARCH_SKIP] TAVILY_API_KEY غير مضبوط — تخطي البحث الحقيقي")
        return []

    try:
        resp = requests.post(
            TAVILY_URL,
            json={
                "api_key": TAVILY_API_KEY,
                "query": query,
                "max_results": max_results,
                "search_depth": "basic",
                "topic": "general",
                "country": country,
                "exclude_domains": EXCLUDE_GULF_DOMAINS,
            },
            timeout=15,
        )
        if resp.status_code != 200:
            log(f"[WEB_SEARCH_ERR] status={resp.status_code} body={resp.text[:200]}")
            return []

        data = resp.json()
        results = []
        for item in data.get("results", [])[:max_results]:
            results.append({
                "title": item.get("title", "")[:150],
                "url": item.get("url", ""),
                "snippet": item.get("content", "")[:200],
            })
        log(f"[WEB_SEARCH_OK] query={query[:60]} found={len(results)}")
        return results

    except requests.exceptions.RequestException as e:
        log(f"[WEB_SEARCH_NETWORK_ERR] query={query[:60]} err={e}")
        return []
    except Exception as e:
        log(f"[WEB_SEARCH_UNEXPECTED_ERR] query={query[:60]} err={e}")
        return []


def format_links_for_prompt(results: list) -> str:
    """يحوّل نتائج البحث لنص جاهز يُحقن داخل prompt البناء — روابط حقيقية ثابتة لا يخترعها AI."""
    if not results:
        return ""

    lines = ["\n\n[روابط حقيقية تم العثور عليها فعلياً عبر بحث ويب — استخدم هذه الروابط بالضبط حرفياً، لا تخترع روابط أخرى]:"]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']} — {r['url']}")
    return "\n".join(lines)
