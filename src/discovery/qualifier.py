"""Use Claude to qualify funding announcements and extract structured company info."""
import json
import logging
import anthropic

logger = logging.getLogger(__name__)


def qualify_companies(search_results: list[dict], client: anthropic.Anthropic) -> list[dict]:
    """
    Pass raw search results to Claude for qualification.
    Returns list of dicts: company_name, funding_amount, funding_stage,
    website_url, description, news_url.
    """
    if not search_results:
        return []

    results_text = "\n\n".join([
        f"[{i+1}] From: {r.get('sender','')}\nReceived: {r.get('received','')}\n"
        f"Subject: {r['title']}\nLink: {r['url']}\n---\n{r['snippet']}"
        for i, r in enumerate(search_results[:40])
    ])

    prompt = f"""You are extracting AI/tech startup funding announcements from a batch of newsletter emails and news articles.

INPUT (each entry is one email/article — a single email may mention many funding rounds):
{results_text}

YOUR TASK:
Find every distinct AI/tech startup funding announcement mentioned in the input. For each one, extract a structured record. The same company may be mentioned in multiple emails — return only one record per company.

QUALIFICATION CRITERIA (strict):
- Company type: AI / software / SaaS company building a digital product. The product must be primarily AI- or software-driven. SKIP: biotech, pharma, life sciences, medical devices, hardware-only, robotics-only, real estate, consumer goods, fintech without an AI core, defense, energy, climate-tech without AI. If you're unsure whether it's "AI/tech enough," skip it.
- Funding range: $5M to $300M. Skip if amount unclear or outside this range.
- Funding type: VC/PE/strategic equity round — seed, Series A, Series B, Series C, Series D qualify. Skip debt financing, grants, IPO, secondary tenders, ICOs, fund announcements (a VC firm raising a fund is NOT a portfolio company funding round).
- Recency: must be a NEW round announced in the past 14 days. Skip retrospective mentions of older rounds.
- Real company building an actual product or platform with a real homepage.

For each qualified company, extract:
- company_name: The startup's name (string)
- funding_amount: Amount in millions as a number (e.g. 12.5)
- funding_stage: "seed", "series_a", "series_b", "series_c", or "other"
- website_url: Their homepage. If not stated, infer (e.g. "Acme AI" → "https://acme.ai" or "https://acmeai.com")
- description: 1-2 sentences on what the company does and who their customer is
- news_url: The most relevant article/email link from the input

Return a JSON array only — no other text, no markdown fences.
Return max 12 results, ranked by recency and clarity of funding details.
If no results qualify, return []."""

    response = client.messages.create(
        model="claude-opus-4-5",
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
