"""Evaluate company websites using the CLEAR framework."""
from __future__ import annotations
import json
import logging
import anthropic

logger = logging.getLogger(__name__)

CLEAR_FRAMEWORK = """
The CLEAR Framework — 5 dimensions of AI startup marketing effectiveness:

1. CENTRICITY (Customer Centricity)
   Do they lead with the customer's problems and outcomes, or with their own product and features?
   A = Customer is the hero everywhere. D = "We built X" language throughout.

2. LEGIBILITY (Use Case Legibility)
   Are the use cases specific, distinct, and actionable? Can a visitor immediately
   understand who this is for and what job it does?
   A = Named personas, concrete scenarios. D = Vague descriptions that fit any AI company.

3. EDGE (Competitive Edge)
   Have they explained what makes them different from ChatGPT, general LLMs, or direct competitors?
   Do they have a clear "why not just use GPT-4" answer?
   A = Crisp, confident differentiation. D = Indistinguishable from 50 other AI companies.

4. ARGUMENT (Point of View)
   Have they articulated a POV or argument for why they exist and why now?
   Do they have an opinion about the market?
   A = Clear thesis, confident stance, memorable argument. D = Feature list with no perspective.

5. RECALL (Brand Recall)
   Is the brand name interesting and memorable? Is the verbal and visual identity distinctive?
   Will someone remember this brand after one visit?
   A = Sticky, original, you'd tell a friend. D = Forgettable, generic, sounds like every other AI startup.
"""


def evaluate_company(company: dict, website_content: dict, client: anthropic.Anthropic) -> dict | None:
    """
    Evaluate a company's website using the CLEAR framework.
    Returns structured evaluation dict or None on failure.
    """
    content_block = f"""
Company: {company['company_name']}
In the news because: {company.get('news_hook', 'N/A')}
Known description: {company.get('description', 'N/A')}

Website: {website_content.get('url', '')}
Page title: {website_content.get('title', '')}
Meta description: {website_content.get('meta_description', '')}
Hero headings: {website_content.get('hero_text', '')}

Full page text:
{website_content.get('full_text', '')[:5000]}
"""

    prompt = f"""You are a senior brand critic in the Michael Bierut / Pentagram tradition, writing for a weekly LinkedIn carousel called "Hyped & Found Out."
Your job: look at an AI company that's in this week's news and grade their marketing on five dimensions.
Voice: observational, plain-spoken, slightly critical but never cruel. Write the way a senior designer at a leading NYC firm talks at lunch — confident, specific, restrained. No jargon. No address to the reader. No "you should." No "this company should." Just observations.

{CLEAR_FRAMEWORK}

COMPANY TO EVALUATE:
{content_block}

YOUR OUTPUT:
Evaluate this company on all 5 CLEAR dimensions. For each:
- Assign a grade: A, B, C, or D.
- Write ONE pithy observation. ~12-22 words. ~110 characters max. No second sentence. No "they should." No "the website does X to do Y." Just call what's on the page.
- Quote their actual copy in single quotes when it sharpens the point. The best lines pair a quote with a verdict: "'Better customer experiences. Built on Sierra.' — brand prose, not a use case."
- Slightly critical eye. Not snarky. Not flattering. The voice is restrained and adult.

Also write:
- headline: A punchy 8-14 word sentence summarizing your overall take. Declarative. Not a question. Not a setup-and-reveal.
- overall_paragraph: 3-4 sentences. Start with what the company does + why they're in the news this week. Then the honest marketing read. Same voice as the grades. No "you." No address to anyone.

BANNED PATTERNS (do not use any of these):
- "Not X. Not Y. The Z." constructions
- "It's not a ___ problem. It's a ___ problem."
- Triple parallel "One X. One Y. One Z." cadence
- Fragment closers like "That's the variable." or "Now you know."
- Em dashes used to sound thoughtful (one per output, max)
- "Empower," "unlock," "elevate," "harness," "leverage"

Return ONLY valid JSON in this exact structure — no markdown, no extra text:
{{
  "headline": "...",
  "overall_paragraph": "...",
  "grades": {{
    "centricity": {{"grade": "A/B/C/D", "explanation": "One pithy observation, ~110 chars max."}},
    "legibility": {{"grade": "A/B/C/D", "explanation": "One pithy observation, ~110 chars max."}},
    "edge": {{"grade": "A/B/C/D", "explanation": "One pithy observation, ~110 chars max."}},
    "argument": {{"grade": "A/B/C/D", "explanation": "One pithy observation, ~110 chars max."}},
    "recall": {{"grade": "A/B/C/D", "explanation": "One pithy observation, ~110 chars max."}}
  }}
}}"""

    response = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=2500,
        messages=[{"role": "user", "content": prompt}]
    )

    try:
        text = response.content[0].text.strip()
        if text.startswith('```'):
            text = text.split('```')[1]
            if text.startswith('json'):
                text = text[4:]
        evaluation = json.loads(text)

        grades = [evaluation['grades'][d]['grade'] for d in ['centricity', 'legibility', 'edge', 'argument', 'recall']]
        logger.info(f"Evaluated {company['company_name']}: {grades}")
        return evaluation

    except Exception as e:
        logger.error(f"Failed to parse evaluation for {company.get('company_name', '?')}: {e}")
        logger.error(f"Raw response: {response.content[0].text[:400]}")
        return None
