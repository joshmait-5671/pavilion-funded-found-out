#!/usr/bin/env python3
"""
Funded & Found Out — Email Delivery
Finds the most recent PDF in output/ and sends it to josh.mait@gmail.com.

Run on Wednesday at 5pm via cron.

Usage:
    python scripts/run_delivery.py
"""
import sys
import os
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from src.delivery.emailer import send_report
from src.tracking.database import Database

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(Path(__file__).parent.parent / 'logs' / 'delivery.log'),
    ],
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent


def main():
    to_email = os.environ.get('TO_EMAIL', 'josh.mait@gmail.com')
    from_email = os.environ.get('FROM_EMAIL', 'josh.mait@gmail.com')
    auth_dir = BASE_DIR / 'auth'

    if not (auth_dir / 'client_secrets.json').exists():
        print("❌ auth/client_secrets.json not found.")
        print("   Follow the README to set up Gmail API credentials.")
        sys.exit(1)

    # Find most recent PDF
    pdfs = sorted((BASE_DIR / 'output').glob('funded-and-found-out-*.pdf'), reverse=True)
    if not pdfs:
        print("❌ No PDFs found in output/. Run pipeline first: python scripts/run_pipeline.py")
        sys.exit(1)

    latest_pdf = pdfs[0]
    print(f"📎 Sending: {latest_pdf.name}")

    # Get company names from DB for email body
    db = Database(BASE_DIR / 'data' / 'tracker.db')
    company_names = db.get_latest_company_names()
    if not company_names:
        company_names = ["(see attached PDF)"]

    success = send_report(
        pdf_path=latest_pdf,
        auth_dir=auth_dir,
        to_email=to_email,
        from_email=from_email,
        company_names=company_names,
    )

    if success:
        print(f"✅ Sent to {to_email}")
        # Mark as sent in DB
        db.log_run(
            run_date=latest_pdf.stem.replace('funded-and-found-out-', ''),
            companies_found=0,
            companies_analyzed=len(company_names),
            pdf_path=str(latest_pdf),
            email_sent=True,
        )
    else:
        print("❌ Send failed — check logs/delivery.log")
        sys.exit(1)


if __name__ == '__main__':
    main()
