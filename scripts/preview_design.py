#!/usr/bin/env python3
"""
Render a single sample company slide for design review.
Uses the Sierra screenshot from 2026-04-28 + a mocked evaluation written
in the new pithy voice. No API calls. Output: slides/preview/sierra_preview.png
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.report.generator import build_company_slide, render_slide

BASE_DIR = Path(__file__).parent.parent

SAMPLE_COMPANY = {
    'company_name': 'Sierra',
    'website_url': 'https://sierra.ai',
    'funding_amount': 175,
    'funding_stage': 'series_b',
    'description': 'AI agents for customer service across chat, SMS, WhatsApp, email, voice.',
}

SAMPLE_EVAL = {
    'headline': 'Enterprise logos, founder logos, $175M — and still no use case on the page.',
    'overall_paragraph': (
        'Sierra raised $175M Series B for AI customer service agents. The site is polished, the logo wall is loud, '
        'and the homepage barely commits to a job to be done. Read three sections in and the question still stands: '
        'what does buying Sierra get me on Monday?'
    ),
    'grades': {
        'centricity': {
            'grade': 'B',
            'explanation': "'Better customer experiences. Built on Sierra.' — brand prose where a use case should be.",
        },
        'legibility': {
            'grade': 'B',
            'explanation': "Channels are clear (chat, SMS, voice). The actual job done is buried two scrolls deep.",
        },
        'edge': {
            'grade': 'C',
            'explanation': "'Outcome-based pricing' is a footnote, not a wedge. Nothing here that a generalist can't claim.",
        },
        'argument': {
            'grade': 'C',
            'explanation': "No thesis on where customer service is headed. 'Transform your CX' is a wish, not an argument.",
        },
        'recall': {
            'grade': 'B',
            'explanation': "Strong name. Polished identity. The verbal world ('Agent OS') is generic and forgettable.",
        },
    },
}


def main():
    screenshot = BASE_DIR / 'screenshots' / '2026-04-28' / 'sierra.png'
    if not screenshot.exists():
        print(f"Missing screenshot: {screenshot}")
        sys.exit(1)

    out_dir = BASE_DIR / 'slides' / 'preview'
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / 'sierra_preview.png'

    html = build_company_slide(
        company=SAMPLE_COMPANY,
        evaluation=SAMPLE_EVAL,
        screenshot_paths=[str(screenshot)],
        slide_num=1,
        total=5,
        week_label='Week of Apr 28, 2026',
    )

    if render_slide(html, out_path):
        print(f"✓ Rendered: {out_path}")
    else:
        print("Render failed")
        sys.exit(1)


if __name__ == '__main__':
    main()
