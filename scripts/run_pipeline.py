#!/usr/bin/env python3
"""
Funded & Found Out — Full Pipeline
Runs discovery → qualification → analysis → PDF generation.

Run this on Monday. Delivery (email) is handled separately by run_delivery.py.

Usage:
    python scripts/run_pipeline.py
"""
import json
import sys
import logging
import os
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import anthropic
from src.discovery.searcher import search_funding_news
from src.discovery.qualifier import qualify_companies
from src.analysis.scraper import scrape_website
from src.analysis.screenshotter import take_screenshots
from src.analysis.evaluator import evaluate_company
from src.report.generator import generate_carousel, validate_batch
from src.tracking.database import Database

BASE_DIR = Path(__file__).parent.parent

# Ensure output directories exist
for d in ['output', 'screenshots', 'slides', 'data', 'logs']:
    (BASE_DIR / d).mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(BASE_DIR / 'logs' / 'pipeline.log'),
    ],
)
logger = logging.getLogger(__name__)


def main():
    run_date = datetime.now().strftime('%Y-%m-%d')
    logger.info(f"=== Funded & Found Out Pipeline — {run_date} ===")

    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not set in .env")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    db = Database(BASE_DIR / 'data' / 'tracker.db')

    # ── STEP 1: DISCOVERY ────────────────────────────────────────────
    print("\n🔍 Step 1: Searching for funding announcements...")
    raw_results = search_funding_news(max_results_per_query=8)

    if not raw_results:
        logger.error("No search results returned. Check network / DuckDuckGo availability.")
        sys.exit(1)

    print(f"   Found {len(raw_results)} raw articles")

    # ── STEP 2: QUALIFY ──────────────────────────────────────────────
    print("\n🤖 Step 2: Qualifying companies with Claude...")
    qualified = qualify_companies(raw_results, client)

    if not qualified:
        logger.error("Claude returned 0 qualified companies. Try running again or adjusting search queries.")
        sys.exit(1)

    print(f"   Qualified: {len(qualified)} companies")

    # Remove recently covered companies
    fresh = [c for c in qualified if not db.is_recently_covered(c['company_name'])]
    print(f"   After dedup (last 6 weeks): {len(fresh)} fresh companies")

    companies = fresh[:5]
    if len(companies) < 2:
        logger.warning(f"Only {len(companies)} fresh companies. Proceeding anyway.")

    print(f"\n   Selected: {', '.join(c['company_name'] for c in companies)}\n")

    # ── STEP 3: ANALYZE ──────────────────────────────────────────────
    print("🔬 Step 3: Analyzing websites...")
    evaluations = []
    all_screenshots = []

    for i, company in enumerate(companies):
        name = company.get('company_name', '?')
        url = company.get('website_url', '')
        print(f"   [{i+1}/{len(companies)}] {name} — {url}")

        if not url:
            logger.warning(f"  No URL for {name}, skipping")
            evaluations.append(None)
            all_screenshots.append([])
            continue

        # Scrape
        content = scrape_website(url)
        if not content['success']:
            logger.warning(f"  Scrape failed for {url}")

        # Screenshots
        slug = name.lower().replace(' ', '_').replace('/', '')[:28]
        shots = take_screenshots(url, BASE_DIR / 'screenshots' / run_date, slug)
        all_screenshots.append(shots)
        print(f"     ✓ {len(shots)} screenshots")

        # CLEAR evaluation
        evaluation = evaluate_company(company, content, client)
        evaluations.append(evaluation)
        if evaluation:
            grades = [evaluation['grades'][d]['grade'] for d in ['centricity', 'legibility', 'edge', 'argument', 'recall']]
            print(f"     ✓ Grades: C={grades[0]} L={grades[1]} E={grades[2]} A={grades[3]} R={grades[4]}")
        else:
            print(f"     ✗ Evaluation failed")

    # Drop any companies where evaluation failed
    valid = [
        (c, e, s)
        for c, e, s in zip(companies, evaluations, all_screenshots)
        if e is not None
    ]

    if not valid:
        logger.error("All evaluations failed. Nothing to report.")
        sys.exit(1)

    companies, evaluations, all_screenshots = map(list, zip(*valid))

    # ── STEP 3.5: CHECKPOINT (so we can re-render without re-running the LLM) ─
    checkpoint_dir = BASE_DIR / 'data' / 'checkpoints'
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = checkpoint_dir / f"{run_date}.json"
    with open(checkpoint_path, 'w') as f:
        json.dump({
            'run_date': run_date,
            'companies': companies,
            'evaluations': evaluations,
            'screenshot_paths': all_screenshots,
        }, f, indent=2)
    print(f"   📌 Checkpoint saved: {checkpoint_path}")

    # ── STEP 3.6: VALIDATE BATCH ─────────────────────────────────────
    ok, errors = validate_batch(companies, evaluations, all_screenshots)
    if not ok:
        print("\n❌ Batch validation failed — refusing to publish:")
        for e in errors:
            print(f"   · {e}")
        logger.error(f"Validation failed with {len(errors)} error(s); see above")
        sys.exit(1)
    print(f"   ✓ Batch validated ({len(companies)} companies, no dupes, all screenshots present)")

    # ── STEP 4: GENERATE PDF ─────────────────────────────────────────
    print(f"\n📄 Step 4: Generating PDF carousel ({len(companies)} companies)...")
    pdf_path = generate_carousel(
        companies=companies,
        evaluations=evaluations,
        screenshot_paths=all_screenshots,
        output_dir=BASE_DIR / 'output',
        slides_dir=BASE_DIR / 'slides' / run_date,
    )

    if not pdf_path:
        logger.error("PDF generation failed")
        sys.exit(1)

    # ── STEP 5: SAVE TO DB ────────────────────────────────────────────
    db.add_covered_companies(companies, run_date)
    db.log_run(
        run_date=run_date,
        companies_found=len(qualified),
        companies_analyzed=len(companies),
        pdf_path=str(pdf_path),
    )

    print(f"\n✅ Done!")
    print(f"   PDF: {pdf_path}")
    print(f"   Companies: {', '.join(c['company_name'] for c in companies)}")
    print(f"\n   Send it Wednesday: python scripts/run_delivery.py")


if __name__ == '__main__':
    main()
