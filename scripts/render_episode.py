#!/usr/bin/env python3
"""
Render a single Funded & Found Out episode from a curated company list.

Bypasses the broken DuckDuckGo discovery layer. Reads a JSON file like:

    {
      "run_date": "2026-04-28",
      "companies": [
        {"company_name": "Sierra", "website_url": "https://sierra.ai",
         "funding_amount": 175, "funding_stage": "series_b"},
        ...
      ]
    }

Then: scrape each site → evaluate via Claude → reuse existing screenshots
(or take fresh ones) → validate → render → write PDF + checkpoint.

Usage:
    python scripts/render_episode.py path/to/episode.json
    python scripts/render_episode.py path/to/episode.json --skip-eval

--skip-eval reuses an existing checkpoint's evaluations (for design-only iteration).
"""
import argparse
import json
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import anthropic
from src.analysis.scraper import scrape_website
from src.analysis.screenshotter import take_screenshots
from src.analysis.evaluator import evaluate_company
from src.report.generator import generate_carousel, validate_batch

BASE_DIR = Path(__file__).parent.parent

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)
logger = logging.getLogger(__name__)


def slugify(name: str) -> str:
    return name.lower().replace(' ', '_').replace('/', '')[:28]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('episode_file', help='Path to episode JSON')
    ap.add_argument('--skip-eval', action='store_true',
                    help='Reuse evaluations from checkpoint (design-only iteration)')
    args = ap.parse_args()

    episode_path = Path(args.episode_file)
    with open(episode_path) as f:
        episode = json.load(f)

    run_date = episode['run_date']
    companies = episode['companies']
    print(f"\n=== Funded & Found Out — Episode {run_date} ===")
    print(f"   Companies: {', '.join(c['company_name'] for c in companies)}\n")

    # Dedupe defensively (validate_batch will catch this too)
    seen = set()
    deduped = []
    for c in companies:
        key = c['company_name'].strip().lower()
        if key in seen:
            print(f"   ⚠️  Dropping duplicate: {c['company_name']}")
            continue
        seen.add(key)
        deduped.append(c)
    companies = deduped

    if len(companies) != 5:
        print(f"   ⚠️  Episode has {len(companies)} companies (expected 5). Continuing.")

    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key and not args.skip_eval:
        logger.error("ANTHROPIC_API_KEY not set in .env")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key) if api_key else None

    checkpoint_dir = BASE_DIR / 'data' / 'checkpoints'
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = checkpoint_dir / f"{run_date}.json"

    # Skip-eval mode: load existing checkpoint
    if args.skip_eval and checkpoint_path.exists():
        with open(checkpoint_path) as f:
            cp = json.load(f)
        print(f"   📌 Loaded checkpoint: {checkpoint_path}")
        companies = cp['companies']
        evaluations = cp['evaluations']
        all_screenshots = cp['screenshot_paths']
    else:
        evaluations = []
        all_screenshots = []
        screenshot_dir = BASE_DIR / 'screenshots' / run_date
        screenshot_dir.mkdir(parents=True, exist_ok=True)

        for i, company in enumerate(companies):
            name = company['company_name']
            url = company['website_url']
            slug = slugify(name)
            print(f"   [{i+1}/{len(companies)}] {name} — {url}")

            # Reuse existing screenshot if present, else take fresh
            existing = screenshot_dir / f"{slug}.png"
            if existing.exists():
                shots = [str(existing)]
                print(f"     ✓ Reusing screenshot: {existing.name}")
            else:
                shots = take_screenshots(url, screenshot_dir, slug)
                print(f"     ✓ Took {len(shots)} screenshot(s)")
            all_screenshots.append(shots)

            content = scrape_website(url)
            if not content.get('success'):
                logger.warning(f"  Scrape failed for {url}")

            evaluation = evaluate_company(company, content, client)
            evaluations.append(evaluation)
            if evaluation:
                grades = [evaluation['grades'][d]['grade']
                          for d in ['centricity', 'legibility', 'edge', 'argument', 'recall']]
                print(f"     ✓ Grades: C={grades[0]} L={grades[1]} E={grades[2]} A={grades[3]} R={grades[4]}")
            else:
                print(f"     ✗ Evaluation failed")

        with open(checkpoint_path, 'w') as f:
            json.dump({
                'run_date': run_date,
                'companies': companies,
                'evaluations': evaluations,
                'screenshot_paths': all_screenshots,
            }, f, indent=2)
        print(f"\n   📌 Checkpoint saved: {checkpoint_path}")

    # Validate
    ok, errors = validate_batch(companies, evaluations, all_screenshots)
    if not ok:
        print("\n❌ Batch validation failed:")
        for e in errors:
            print(f"   · {e}")
        sys.exit(1)
    print(f"   ✓ Batch validated")

    # Render
    print(f"\n📄 Rendering carousel...")
    pdf_path = generate_carousel(
        companies=companies,
        evaluations=evaluations,
        screenshot_paths=all_screenshots,
        output_dir=BASE_DIR / 'output',
        slides_dir=BASE_DIR / 'slides' / run_date,
    )

    if not pdf_path:
        print("PDF generation failed")
        sys.exit(1)

    print(f"\n✅ Done!")
    print(f"   PDF: {pdf_path}")


if __name__ == '__main__':
    main()
