"""Search for recent AI/tech funding announcements using DuckDuckGo."""
import time
import logging
from duckduckgo_search import DDGS

logger = logging.getLogger(__name__)

NEWS_QUERIES = [
    "AI startup funding raised million series",
    "artificial intelligence company raises million venture capital",
    "AI SaaS startup funding announcement series",
    "machine learning startup raises seed series million",
    "AI company funding round million 2026",
]


def search_funding_news(max_results_per_query: int = 10) -> list[dict]:
    """
    Search DuckDuckGo News for recent AI/tech funding announcements.
    Returns a deduplicated list of raw search results.
    """
    results = []
    seen_urls = set()

    with DDGS() as ddgs:
        for query in NEWS_QUERIES:
            try:
                logger.info(f"Searching news: {query[:70]}...")
                time.sleep(4)

                hits = ddgs.news(
                    query,
                    max_results=max_results_per_query,
                )

                for r in (hits or []):
                    url = r.get('url', '')
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        results.append({
                            'title': r.get('title', ''),
                            'url': url,
                            'snippet': r.get('body', '') or r.get('excerpt', ''),
                        })

            except Exception as e:
                logger.warning(f"Search failed for query '{query}': {e}")
                continue

    logger.info(f"Discovery: {len(results)} raw results across {len(NEWS_QUERIES)} queries")
    return results
