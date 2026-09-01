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
from src.discovery.email_searcher import search_funding_news
from src.discovery.qualifier import qualify_companies, _screen_out_too_big, _dedupe_companies
from src.analysis.scraper import scrape_website
from src.analysis.screenshotter import take_screenshots, capture_page
from src.analysis.evaluator import evaluate_company
from src.analysis.verifier import verify_identity, passes as identity_passes
from src.report.generator import validate_batch
from src.tracking.database import Database
from src.delivery.emailer import send_curation_prompt

MIN_COMPANIES = 5

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


def main(seed_path=None):
    run_date = datetime.now().strftime('%Y-%m-%d')
    logger.info(f"=== Funded & Found Out Pipeline — {run_date} ===")

    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not set in .env")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    db = Database(BASE_DIR / 'data' / 'tracker.db')

    # ── STEPS 1+2: DISCOVERY & QUALIFY ───────────────────────────────
    # Normal path reads the newsletters. --seed skips straight to a hand-supplied
    # candidate list, so an expired Gmail token can delay the week's post but
    # never block it. Seeded companies still get the deterministic too-big screen
    # and the same identity check, screenshot and grade as discovered ones.
    if seed_path:
        print(f"\n🌱 Steps 1+2 skipped — seeding candidates from {seed_path}")
        try:
            seeded = json.loads(Path(seed_path).read_text())
        except Exception as e:
            logger.error(f"Could not read seed file {seed_path}: {e}")
            sys.exit(1)
        if isinstance(seeded, dict):
            seeded = seeded.get('companies', [])
        missing = [c.get('company_name', '?') for c in seeded if not c.get('website_url')]
        if missing:
            logger.error(f"Seed entries missing website_url: {missing}")
            sys.exit(1)
        qualified = _dedupe_companies(_screen_out_too_big(seeded))
        print(f"   Seeded: {len(seeded)} → {len(qualified)} after too-big screen + dedupe")
    else:
        print("\n🔍 Step 1: Scanning Gmail accounts for funding announcements...")
        raw_results = search_funding_news(max_results_per_query=50, days=7)

        if not raw_results:
            logger.error(
                "No newsletters captured. Check that auth/token-*.json files exist "
                "and were authorized with gmail.readonly scope. Run: "
                "python scripts/auth_gmail.py <label>   "
                "(or bypass discovery: run_pipeline.py --seed candidates.json)"
            )
            sys.exit(1)

        print(f"   Found {len(raw_results)} newsletter messages across all accounts")

        print("\n🤖 Step 2: Qualifying companies with Claude...")
        qualified = qualify_companies(raw_results, client)

        print(f"   Qualified: {len(qualified)} companies")

    # Remove recently covered companies
    fresh = [c for c in qualified if not db.is_recently_covered(c['company_name'])]
    print(f"   After dedup (last 6 weeks): {len(fresh)} fresh companies")

    # Floor: under MIN_COMPANIES, send curation prompt instead of generating PDF
    if len(fresh) < MIN_COMPANIES:
        print(f"\n⚠️  Only {len(fresh)} qualified — below the {MIN_COMPANIES}-company floor.")
        print("   Sending curation-prompt email and exiting without generating a PDF.")
        to_email = os.environ.get('TO_EMAIL', 'josh.mait@gmail.com')
        from_email = os.environ.get('FROM_EMAIL', 'josh.mait@gmail.com')
        send_curation_prompt(
            auth_dir=BASE_DIR / 'auth',
            to_email=to_email,
            from_email=from_email,
            candidates=fresh,
            minimum=MIN_COMPANIES,
        )
        # Save what we found so manual curation has a starting point
        episode_dir = BASE_DIR / 'data' / 'episodes'
        episode_dir.mkdir(parents=True, exist_ok=True)
        starter_path = episode_dir / f"{run_date}.json"
        import json as _json
        with open(starter_path, 'w') as _f:
            _json.dump({
                'run_date': run_date,
                '_note': 'Auto-generated starter — only N candidates were found. Edit and add more, then re-run scripts/render_episode.py against this file.',
                'companies': fresh,
            }, _f, indent=2)
        print(f"   📝 Starter episode JSON: {starter_path}")
        sys.exit(0)

    print(f"\n   Qualified pool ({len(fresh)}): {', '.join(c['company_name'] for c in fresh)}")
    print(f"   Filling {MIN_COMPANIES} slots, backfilling past any site that won't screenshot or grade.\n")

    # ── STEP 3: ANALYZE (with backfill) ──────────────────────────────
    # Walk the full qualified pool. A company is kept only if it produces
    # BOTH a usable screenshot AND a valid evaluation. Anything that fails
    # either is dropped and the next candidate is pulled — so one bad site
    # never sinks the whole issue. Stop once MIN_COMPANIES slots are filled.
    print("🔬 Step 3: Analyzing websites...")
    companies = []
    evaluations = []
    all_screenshots = []

    for company in fresh:
        if len(companies) >= MIN_COMPANIES:
            break
        name = company.get('company_name', '?')
        url = company.get('website_url', '')
        print(f"   [{len(companies) + 1}/{MIN_COMPANIES}] {name} — {url}")

        if not url:
            logger.warning(f"  No URL for {name} — skipping, backfilling from pool")
            print(f"     ✗ No URL — pulling next candidate")
            continue

        # One Chromium render → screenshot + page text, so the image, the
        # grades, and the identity check all read the exact same page.
        # No usable shot → drop & backfill.
        slug = name.lower().replace(' ', '_').replace('/', '')[:28]
        shots, content = capture_page(url, BASE_DIR / 'screenshots' / run_date, slug)
        if not shots:
            logger.warning(f"  Screenshot failed for {name} ({url}) — skipping, backfilling from pool")
            print(f"     ✗ Screenshot failed — pulling next candidate")
            continue

        # Fall back to the requests scraper only if the rendered DOM had no text.
        if not content.get('success'):
            fb = scrape_website(url)
            if fb.get('success'):
                content = fb
            else:
                logger.warning(f"  No readable page text for {url} — identity gate will decide")

        # CORRECTNESS GATE: confirm this homepage is actually the company the
        # news is about (guards against inferred/wrong URLs and name collisions).
        # This is named + published, so an unverified company is dropped, not shipped.
        verdict = verify_identity(company, content, client)
        if not identity_passes(verdict):
            reason = (verdict or {}).get('reason', 'could not confirm the homepage matches the company')
            logger.warning(f"  Identity check failed for {name} ({url}): {reason} — skipping, backfilling")
            print(f"     ✗ Identity check failed — {reason}")
            print(f"       pulling next candidate")
            continue
        company['_identity'] = verdict
        print(f"     ✓ Identity verified ({verdict.get('confidence')})")

        # CLEAR evaluation. Failure → drop & backfill.
        evaluation = evaluate_company(company, content, client)
        if evaluation is None:
            logger.warning(f"  Evaluation failed for {name} — skipping, backfilling from pool")
            print(f"     ✗ Evaluation failed — pulling next candidate")
            continue

        companies.append(company)
        evaluations.append(evaluation)
        all_screenshots.append(shots)
        grades = [evaluation['grades'][d]['grade'] for d in ['centricity', 'legibility', 'edge', 'argument', 'recall']]
        print(f"     ✓ Grades: C={grades[0]} L={grades[1]} E={grades[2]} A={grades[3]} R={grades[4]}")

    if not companies:
        logger.error("No companies survived analysis. Nothing to report.")
        sys.exit(1)

    if len(companies) < MIN_COMPANIES:
        logger.warning(f"Only {len(companies)} of {MIN_COMPANIES} slots filled (pool exhausted). Publishing a shorter issue.")
        print(f"   ⚠️  {len(companies)}/{MIN_COMPANIES} slots filled — publishing a shorter issue.")

    print(f"\n   Final lineup: {', '.join(c['company_name'] for c in companies)}\n")

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

    # ── STEP 4: SAVE TO DB ────────────────────────────────────────────
    # The old 5-company report PDF used to render here. The product is now a
    # single-company carousel from make_post.py, so this pipeline's job ends at
    # a verified, graded lineup — no PDF.
    db.add_covered_companies(companies, run_date)
    db.log_run(
        run_date=run_date,
        companies_found=len(qualified),
        companies_analyzed=len(companies),
        pdf_path=str(checkpoint_path),
    )

    print(f"\n✅ Done!")
    print(f"   Pick one and build the post:")
    for c in companies:
        print(f"     .venv/bin/python scripts/make_post.py \"{c['company_name']}\"")


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description="The Read — weekly discovery pipeline")
    ap.add_argument('--seed', metavar='FILE',
                    help='JSON list of candidate companies (company_name, website_url, '
                         'news_hook, description, news_url). Skips the Gmail scan.')
    main(seed_path=ap.parse_args().seed)
