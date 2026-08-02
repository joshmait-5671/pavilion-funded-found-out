"""Identity verification — the correctness gate before a company is graded.

This tool publicly critiques named companies on LinkedIn, so the single most
dangerous failure is misidentification: the qualifier often *infers* a homepage
URL, and two companies can share a name (e.g. an "Inner Logic" medtech seed vs.
an "Inner Logic" HR product). Grading the wrong homepage — then posting it — is
fatal. This gate confirms the page we scraped is actually the company the news
is about, and drops it (to backfill) when it can't.
"""
from __future__ import annotations

import json
import logging

import anthropic

logger = logging.getLogger(__name__)


def verify_identity(company: dict, content: dict, client: anthropic.Anthropic) -> dict | None:
    """Return {match: bool, confidence: 'high'|'medium'|'low', reason: str}.

    Returns None only on an API/parse failure. Callers should treat a None,
    a False match, OR a 'low' confidence as "do not publish — backfill."
    """
    name = company.get('company_name', '')
    prompt = f"""You are a fact-checker whose only job is to stop a public LinkedIn post from misidentifying a company.

We are about to publicly critique this company's marketing. Confirm the homepage we scraped is ACTUALLY the company the news is about — not a different company that happens to share the name, not a parked/placeholder domain, not a login wall with no product story.

THE COMPANY (from this week's news):
- Name: {name}
- Why it's in the news: {company.get('news_hook', 'N/A')}
- What we believe it does: {company.get('description', 'N/A')}
- Source article: {company.get('news_url', 'N/A')}

THE HOMEPAGE WE SCRAPED ({content.get('url', '')}):
- Page title: {content.get('title', '')}
- Meta description: {content.get('meta_description', '')}
- Hero headings: {content.get('hero_text', '')}
- Page text (excerpt): {content.get('full_text', '')[:3000]}

It is a MATCH only if the product/purpose on the site is clearly consistent with what we believe the company does. It is NOT a match if:
- the site is about a different product, industry, or audience than the news describes;
- it's a parked, "coming soon," or placeholder page with no real product;
- it's a login/app wall with no marketing content to evaluate;
- it's clearly a different company that happens to share the name.

When the evidence is thin or ambiguous, do NOT force a match — use "low" confidence. We would rather skip a company than post the wrong one.

Return ONLY this JSON, no markdown, no extra text:
{{"match": true or false, "confidence": "high" or "medium" or "low", "reason": "one sentence citing the specific evidence"}}"""

    try:
        response = client.messages.create(
            model="claude-opus-4-7",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        if text.startswith('```'):
            text = text.split('```')[1]
            if text.startswith('json'):
                text = text[4:]
        verdict = json.loads(text)
        logger.info(
            f"Identity {name}: match={verdict.get('match')} "
            f"conf={verdict.get('confidence')} — {verdict.get('reason', '')}"
        )
        return verdict
    except Exception as e:
        logger.error(f"Identity check errored for {name}: {e}")
        return None


def passes(verdict: dict | None) -> bool:
    """A company may be published only on a confident, positive match."""
    return bool(verdict) and verdict.get('match') is True and verdict.get('confidence') != 'low'
