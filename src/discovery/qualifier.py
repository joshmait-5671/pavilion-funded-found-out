"""Use Claude to qualify funding announcements and extract structured company info."""
import json
import logging
import anthropic

logger = logging.getLogger(__name__)


def qualify_companies(search_results: list[dict], client: anthropic.Anthropic) -> list[dict]:
    """
    Pass raw search results to Claude for qualification.
    Returns list of dicts: company_name, news_hook, website_url, description, news_url.
    """
    if not search_results:
        return []

    results_text = "\n\n".join([
        f"[{i+1}] From: {r.get('sender','')}\nReceived: {r.get('received','')}\n"
        f"Subject: {r['title']}\nLink: {r['url']}\n---\n{r['snippet']}"
        for i, r in enumerate(search_results[:40])
    ])

    prompt = f"""You are extracting AI/software companies that are getting attention in this week's news cycle, from a batch of newsletter emails and articles.

INPUT (each entry is one email/article — a single email may mention many companies):
{results_text}

YOUR TASK:
Find every distinct AI/software company mentioned in a substantive way in the input. For each one, extract a structured record. The same company may be mentioned in multiple emails — return only one record per company, picking the most newsworthy hook.

QUALIFICATION CRITERIA:
- Company type: AI / software / SaaS company building a digital product. The product must be primarily AI- or software-driven. SKIP: pure hardware (no software story), biotech with no AI angle, life sciences, real estate, energy without AI, defense, consumer-goods physical products, financial services without AI, generic media properties.
- Substantive mention: the company is the subject of the news, not a passing reference. Skip "X uses Y's API" type asides unless Y is itself the story. Skip articles that just list 30 companies in a paragraph.
- Real company with a real homepage. SKIP: fictional examples, anonymous "a startup", VC firms talking about themselves (a VC firm is not the news subject — its portfolio company is).
- Newsworthy this week: it's in the news because something happened — a launch, a controversy, a layoff, a deal, a rebrand, a stat, a debate, a fundraise, a quote, a product update. The thing that happened is the "news_hook".
- No size filter. Anthropic at $900B and a 5-person seed startup both qualify if they're in the news.

For each qualified company, extract:
- company_name: The company's name (string)
- news_hook: 4-10 words describing why they're in the news this week (e.g. "$900B fundraising round", "AI-driven RIF announcement", "MS 365 integration launch", "Claude API hits new model SOTA")
- website_url: Their homepage. If not stated, infer (e.g. "Acme AI" → "https://acme.ai" or "https://acmeai.com")
- description: 1-2 sentences on what the company does and who their customer is
- news_url: The most relevant article/email link from the input

Return a JSON array only — no other text, no markdown fences.
Return max 12 results, ranked by newsworthiness + clarity of the hook.
If no results qualify, return []."""

    response = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}]
    )

    try:
        text = response.content[0].text.strip()
        # Strip markdown code fences if present
        if text.startswith('```'):
            text = text.split('```')[1]
            if text.startswith('json'):
                text = text[4:]
        companies = json.loads(text)
        deduped = _dedupe_companies(companies)
        if len(deduped) < len(companies):
            logger.info(f"Qualifier: collapsed {len(companies) - len(deduped)} duplicate(s) within batch")
        logger.info(f"Qualifier: {len(deduped)} companies qualified from {len(search_results)} results")
        return deduped
    except Exception as e:
        logger.error(f"Failed to parse qualifier response: {e}\nRaw: {response.content[0].text[:300]}")
        return []


def _normalize_name(name: str) -> str:
    """Normalize company name for dedupe — lowercase, strip suffixes/punctuation."""
    n = (name or "").lower().strip()
    for suffix in [' inc.', ' inc', ' llc', ' ltd', ' ltd.', ' co.', ' co', ' ai', '.ai', '.com']:
        if n.endswith(suffix):
            n = n[:-len(suffix)].strip()
    return ''.join(c for c in n if c.isalnum())


def _dedupe_companies(companies: list[dict]) -> list[dict]:
    """Collapse duplicate companies within a single batch — first occurrence wins."""
    seen = set()
    out = []
    for c in companies:
        key = _normalize_name(c.get('company_name', ''))
        url_key = (c.get('website_url') or '').lower().rstrip('/')
        if not key:
            continue
        if key in seen or (url_key and url_key in seen):
            continue
        seen.add(key)
        if url_key:
            seen.add(url_key)
        out.append(c)
    return out
