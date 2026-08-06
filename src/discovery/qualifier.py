"""Use Claude to qualify funding announcements and extract structured company info."""
import json
import logging
import re
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
- Newsworthy this week: something happened — a fundraise, a launch, a rebrand, a notable stat, a debate. A just-closed Series A is a great hook (fresh budget, real GTM need), but the hook matters far less than the company being a real prospect (next criterion). Do not keep a company just because it raised — keep it because it's the right kind of company.
- THE SWEET SPOT — THIS IS A NEW-BUSINESS PROSPECT LIST FOR A BOUTIQUE POSITIONING AGENCY (100 Yards). Every company that survives is someone the agency could pitch. The company must be far enough along to (a) be a real business worth hiring an agency for, and (b) have a substantial homepage worth critiquing — yet not so big it runs its own brand org. Use judgment; you will not have exact numbers.
  - KEEP — companies with clear PRODUCT-MARKET FIT: a shipping product, real customers, visible traction or revenue, a team well past the founding handful. Best fit is roughly SERIES A THROUGH GROWTH STAGE (think ~$5M–$100M revenue, a Series A or B behind them) where the product works but the positioning isn't landing yet. A well-funded seed company with real customers and clear momentum can count — PMF is the gate, not the round label.
  - SKIP — TOO EARLY (this is the common mistake, weigh it hard): pre-product or barely launched, pre-revenue, no customers yet, a two- or three-person team, "just raised pre-seed/seed" or "backed by [an accelerator]" with nothing shipped. If it reads like an idea with a landing page rather than a business, SKIP — there is no company to reposition and nothing real to tear down.
  - SKIP — TOO BIG (weigh this as hard as too-early): a company is past the sweet spot and MUST be dropped if ANY of these are true — Series C or later; post-money valuation over ~$500M; revenue over ~$100M; a household name or market mover; public; a decacorn/unicorn; big-tech, or a product owned by/part of a big-tech company. These companies run their own brand orgs and will never hire a boutique agency. A big, impressive raise is a REASON TO SKIP, not a reason to rank highly. Explicit skip tiers (and anyone like them):
    · Frontier/big-tech: OpenAI, Anthropic, Google / DeepMind / Gemini, Microsoft / Copilot, Meta / Llama, Amazon (incl. its products like Kiro/Q), Apple, Nvidia, xAI / Grok, DeepSeek, Mistral, Perplexity, Databricks, Scale AI, Cohere, Stability, Hugging Face, Kalshi.
    · Large scale-ups with mature marketing teams: Deel, Rippling, Ramp, Brex, Vanta, Notion, Figma, Canva, GlossGenius / Genius AI, and any similarly large, well-known, or heavily-funded name.
  - THE TEST: "Does this company have a real business — product in market, customers, a marketing budget — that a boutique agency could realistically win AND meaningfully help, with a homepage worth tearing down?" Yes on all → keep. Too early to be a business, or too big to need help → skip.

For each qualified company, extract:
- company_name: The company's name (string)
- news_hook: 4-10 words describing why they're breaking through this week (e.g. "Series A for AI contract review", "launches coding agent for COBOL", "scrutiny over training-data scraping", "$40M to automate claims")
- website_url: Their homepage. If not stated, infer (e.g. "Acme AI" → "https://acme.ai" or "https://acmeai.com")
- description: 1-2 sentences on what the company does and who their customer is
- news_url: The most relevant article/email link from the input

Return a JSON array only — no other text, no markdown fences.
Return up to 12 results, ranked BEST-PROSPECT-FIRST — clearest product-market fit and strongest agency fit at the top (a Series-A-ish company with real customers and shaky positioning beats a just-launched seed). Do NOT rank by fame or raise size; a big raise never earns a high rank. Returning fewer, cleaner prospects is better than padding to 12. Before returning, re-check every entry against both gates and DROP it if it's too early to be a real business OR too big to need a boutique agency (Series C+, >~$100M revenue, >~$500M valuation, unicorn, big-tech, or big-tech-owned). When unsure whether a company is too big, drop it.
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
        screened = _screen_out_too_big(deduped)
        logger.info(f"Qualifier: {len(screened)} companies qualified from {len(search_results)} results")
        return screened
    except Exception as e:
        logger.error(f"Failed to parse qualifier response: {e}\nRaw: {response.content[0].text[:300]}")
        return []


# Deterministic backstop for the "too big" gate. The LLM instruction reduces
# big companies but doesn't guarantee it (a $1B Base Power slipped through once),
# so this drops them in code after the model runs — no talking it out of the rule.
_TOO_BIG_NAMES = {
    'openai', 'anthropic', 'google', 'deepmind', 'gemini', 'microsoft', 'copilot',
    'meta', 'llama', 'amazon', 'apple', 'nvidia', 'xai', 'grok', 'deepseek',
    'mistral', 'perplexity', 'databricks', 'scale ai', 'cohere', 'stability',
    'hugging face', 'kalshi', 'deel', 'rippling', 'ramp', 'brex', 'vanta',
    'notion', 'figma', 'canva', 'glossgenius', 'genius ai', 'base power',
}
# Late-stage / billion-dollar signals in the hook or description.
_TOO_BIG_PATTERNS = [
    re.compile(r'series\s+[c-z]\b', re.I),                 # Series C or later
    re.compile(r'\$\s?\d+(?:\.\d+)?\s*b\b', re.I),          # $1B, $1.5B, $44B
    re.compile(r'\b\d+(?:\.\d+)?\s*billion\b', re.I),       # "1.5 billion"
    re.compile(r'\b(?:decacorn|ipo|public\s+company)\b', re.I),
]


def _screen_out_too_big(companies: list[dict]) -> list[dict]:
    """Drop companies that are clearly past the sweet spot, in code."""
    kept = []
    for c in companies:
        name = _normalize_name(c.get('company_name', ''))
        blob = f"{c.get('company_name','')} {c.get('news_hook','')} {c.get('description','')}"
        if name in {_normalize_name(n) for n in _TOO_BIG_NAMES} \
                or any(p.search(blob) for p in _TOO_BIG_PATTERNS):
            logger.info(f"Qualifier: dropped too-big company '{c.get('company_name')}' "
                        f"(hook: {c.get('news_hook','')[:40]})")
            continue
        kept.append(c)
    return kept


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
