"""
Email-based discovery for Funded & Found Out.

Replaces the broken DuckDuckGo searcher. Scans Josh's Gmail for AI/tech
funding announcements from a curated set of newsletter senders + a broad
keyword sweep, in the past N days. Returns search-result-shaped dicts so
the existing qualifier.py works unchanged.

Borrows the sender list and query approach from the AI Digest skill at
~/Documents/Claude/Scheduled/daily-ai-digest/SKILL.md.
"""
from __future__ import annotations
import base64
import logging
import re
from pathlib import Path
from typing import Iterable

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)


# Senders confirmed in the AI Digest skill — Josh's actual subscriptions.
# These newsletters consistently mention AI/tech startup funding rounds.
NEWSLETTER_SENDERS: list[str] = [
    # AI / VC newsletters from AI Digest
    'a16z@substack.com',
    'speedrun@substack.com',
    'a16zcrypto@substack.com',
    'consumerstartups@mail.beehiiv.com',
    'profgmedia+markets-newsletter@substack.com',
    'profgmedia+prof-g-markets@substack.com',
    'robotic@substack.com',
    'thegtmnewsletter@substack.com',
    'bensbites@substack.com',
    'superhuman@mail.joinsuperhuman.ai',
    'uppitai@mail.beehiiv.com',
    'claudiaplusai@substack.com',
    'adlrocha@substack.com',
    # Common VC / funding-news senders (will only match if Josh is subscribed)
    'newsletter@axios.com',
    'pro-rata@axios.com',
    'newsletters@strictlyvc.com',
    'newsletter@strictlyvc.com',
    'no-reply@crunchbase.com',
    'digest@crunchbase.com',
    'newsletter@techcrunch.com',
    'press@techcrunch.com',
    'newsletter@theinformation.com',
    'fortune@email.fortune.com',
    'termsheet@fortune.com',
]

FUNDING_KEYWORDS = [
    'funding', 'raised', 'series', 'seed round', 'closes round',
    'venture round', 'led the round',
]


# ─── GMAIL CLIENT ─────────────────────────────────────────────────────────────

def _service_for_token(token_path: Path):
    """Return an authenticated Gmail service for a specific token file."""
    creds = Credentials.from_authorized_user_file(
        str(token_path),
        ['https://www.googleapis.com/auth/gmail.send',
         'https://www.googleapis.com/auth/gmail.readonly'],
    )
    return build('gmail', 'v1', credentials=creds, cache_discovery=False)


def _all_token_paths(auth_dir: Path) -> list[Path]:
    """Discover every per-account token in auth/ (token-<label>.json)."""
    return sorted(auth_dir.glob('token-*.json'))


def _service(auth_dir: Path):
    """Backwards compat — single-account service for the first available token."""
    tokens = _all_token_paths(auth_dir)
    if not tokens:
        raise RuntimeError(
            f"No Gmail tokens in {auth_dir}. Run scripts/auth_gmail.py <label>."
        )
    return _service_for_token(tokens[0])


# ─── BODY EXTRACTION ──────────────────────────────────────────────────────────

def _decode(data: str) -> str:
    try:
        return base64.urlsafe_b64decode(data + '==').decode('utf-8', errors='ignore')
    except Exception:
        return ''


def _strip_html(html: str) -> str:
    text = re.sub(r'<style[^>]*>.*?</style>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<script[^>]*>.*?</script>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&lt;', '<', text)
    text = re.sub(r'&gt;', '>', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _extract_body(payload: dict) -> str:
    """Recursively pull the best-effort plaintext body from a Gmail payload."""
    body_data = payload.get('body', {}).get('data')
    mime = payload.get('mimeType', '')
    if body_data:
        raw = _decode(body_data)
        return _strip_html(raw) if 'html' in mime else raw

    parts = payload.get('parts') or []
    # Prefer text/plain
    for p in parts:
        if p.get('mimeType') == 'text/plain':
            got = _extract_body(p)
            if got:
                return got
    # Fall back to text/html
    for p in parts:
        if p.get('mimeType') == 'text/html':
            got = _extract_body(p)
            if got:
                return got
    # Recurse into nested multiparts
    for p in parts:
        if p.get('parts'):
            got = _extract_body(p)
            if got:
                return got
    return ''


# ─── SEARCH ────────────────────────────────────────────────────────────────────

DIGEST_SUBJECT = 'Daily AI Digest'  # Josh's self-generated weekly AI-company roundup


def _build_query(days: int) -> str:
    """
    Three trusted sources — and CRUCIALLY, private 1:1 mail is never read:
      A) Curated newsletter senders — trusted, any folder.
      B) The Daily AI Digest — matched by subject (so we catch it without
         whitelisting a personal address, which would pull in private mail).
      C) A funding-keyword sweep, RESTRICTED to bulk-mail categories
         (Promotions/Updates/Forums). Primary is never keyword-swept, so client
         threads and personal correspondence in the inbox stay unreadable.

    The old query keyword-swept `in:anywhere` across every sender, which vacuumed
    up private client email that merely mentioned money (a Neuroflow deal thread,
    Aktivate intake notes). Scoping arm C to bulk categories closes that leak.
    """
    senders_or = ' OR '.join(f'from:{s}' for s in NEWSLETTER_SENDERS)
    keyword_or = ' OR '.join(f'"{kw}"' for kw in FUNDING_KEYWORDS)
    bulk = 'category:promotions OR category:updates OR category:forums'
    return (
        f'newer_than:{days}d '
        f'(({senders_or}) '
        f'OR subject:"{DIGEST_SUBJECT}" '
        f'OR (({keyword_or}) ({bulk})))'
    )


def _search_one_account(
    token_path: Path,
    query: str,
    max_results: int,
) -> list[dict]:
    label = token_path.stem.replace('token-', '')
    try:
        service = _service_for_token(token_path)
    except Exception as e:
        logger.error(f"[{label}] Gmail auth failed: {e}")
        return []

    try:
        listing = service.users().messages().list(
            userId='me', q=query, maxResults=max_results
        ).execute()
    except Exception as e:
        logger.error(f"[{label}] Gmail list failed: {e}")
        return []

    messages = listing.get('messages', []) or []
    logger.info(f"[{label}] {len(messages)} candidate messages")

    results: list[dict] = []
    for m in messages:
        try:
            msg = service.users().messages().get(
                userId='me', id=m['id'], format='full'
            ).execute()
        except Exception as e:
            logger.warning(f"[{label}] skip {m['id']}: {e}")
            continue

        headers = {h['name']: h['value'] for h in msg['payload'].get('headers', [])}
        subject = headers.get('Subject', '')
        sender = headers.get('From', '')
        date_hdr = headers.get('Date', '')

        body = _extract_body(msg['payload'])
        if not body:
            continue

        snippet = body[:3500]
        results.append({
            'title': subject or '(no subject)',
            'url': f"https://mail.google.com/mail/u/0/#inbox/{m['id']}",
            'snippet': snippet,
            'sender': sender,
            'received': date_hdr,
            'account': label,
        })

    return results


def search_funding_news(
    max_results_per_query: int = 50,
    days: int = 7,
    auth_dir: Path | None = None,
) -> list[dict]:
    """
    Scan every authenticated Gmail account in auth/token-*.json for funding-
    related newsletters in the past N days. Returns search-result-shaped
    dicts so the existing qualifier.py works unchanged.
    """
    if auth_dir is None:
        auth_dir = Path(__file__).resolve().parents[2] / 'auth'

    tokens = _all_token_paths(auth_dir)
    if not tokens:
        logger.error(f"No tokens in {auth_dir}. Run scripts/auth_gmail.py <label>.")
        return []

    query = _build_query(days)
    logger.info(f"Query: {query[:200]}…")
    logger.info(f"Scanning {len(tokens)} account(s): {[t.stem for t in tokens]}")

    all_results: list[dict] = []
    for tok in tokens:
        all_results.extend(_search_one_account(tok, query, max_results_per_query))

    logger.info(f"Email searcher: {len(all_results)} newsletters total across accounts")
    return all_results
