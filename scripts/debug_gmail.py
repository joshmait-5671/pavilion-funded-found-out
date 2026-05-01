#!/usr/bin/env python3
"""Probe Gmail to figure out which queries actually return funding-related mail."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.discovery.email_searcher import _service, NEWSLETTER_SENDERS

BASE_DIR = Path(__file__).parent.parent

QUERIES = [
    'newer_than:7d',  # everything in past 7d (sanity check inbox volume)
    'newer_than:7d in:anywhere',  # include spam/trash/categories
    'newer_than:7d category:promotions',
    'newer_than:7d category:promotions ("raised" OR "Series" OR "funding")',
    'newer_than:30d category:promotions ("raised $" OR "Series A" OR "Series B")',
    'newer_than:14d in:anywhere "raised $"',
    'newer_than:30d in:anywhere "raised $"',
    'newer_than:30d in:anywhere from:substack.com',
    'newer_than:30d in:anywhere from:techcrunch.com',
    'newer_than:30d in:anywhere from:axios.com',
    'newer_than:30d in:anywhere from:crunchbase.com',
]


def main():
    svc = _service(BASE_DIR / 'auth')
    print(f"\n=== Gmail probe (past 7-30 days) ===\n")

    for q in QUERIES:
        try:
            r = svc.users().messages().list(userId='me', q=q, maxResults=5).execute()
            count = r.get('resultSizeEstimate', 0)
            msgs = r.get('messages', []) or []
            print(f"  [{len(msgs):>3}] {q[:140]}")
            for m in msgs[:2]:
                full = svc.users().messages().get(userId='me', id=m['id'], format='metadata').execute()
                hdrs = {h['name']: h['value'] for h in full['payload'].get('headers', [])}
                print(f"        · {hdrs.get('From','')[:60]}")
                print(f"          {hdrs.get('Subject','')[:90]}")
        except Exception as e:
            print(f"  [ERR] {q[:80]} — {e}")

    print()


if __name__ == '__main__':
    main()
