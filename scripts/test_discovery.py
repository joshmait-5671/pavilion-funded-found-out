#!/usr/bin/env python3
"""
Test the email-based discovery layer.
Pulls funding-related newsletters from the past 7 days and runs the qualifier
on them. Prints the qualified company list. No PDF generated, no email sent.
"""
import json
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import anthropic
from src.discovery.email_searcher import search_funding_news
from src.discovery.qualifier import qualify_companies

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)

BASE_DIR = Path(__file__).parent.parent


def main():
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        print("ANTHROPIC_API_KEY not set in .env")
        sys.exit(1)

    print("\n=== Email Discovery Test ===\n")

    print("Step 1: Pulling newsletters (past 7 days)...")
    raw = search_funding_news(max_results_per_query=50, days=7)
    print(f"  → {len(raw)} newsletter messages captured\n")

    if not raw:
        print("⚠️  No newsletters matched. Check that token.json has gmail.readonly scope.")
        print("    Run: python scripts/auth_gmail.py")
        sys.exit(1)

    for r in raw[:10]:
        print(f"  · {r['title'][:90]}")
        print(f"    {r.get('sender','')[:80]}")

    if len(raw) > 10:
        print(f"  ... +{len(raw) - 10} more")

    print("\nStep 2: Qualifying with Claude...")
    client = anthropic.Anthropic(api_key=api_key)
    qualified = qualify_companies(raw, client)
    print(f"  → {len(qualified)} qualified companies\n")

    for c in qualified:
        print(f"  · {c.get('company_name')} — ${c.get('funding_amount','?')}M "
              f"{c.get('funding_stage','')} — {c.get('website_url')}")
        if c.get('description'):
            print(f"    {c['description'][:110]}")

    # Save raw output for inspection
    out_path = BASE_DIR / 'data' / 'last_discovery_test.json'
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump({'raw': raw, 'qualified': qualified}, f, indent=2)
    print(f"\n  Full result saved: {out_path}")


if __name__ == '__main__':
    main()
