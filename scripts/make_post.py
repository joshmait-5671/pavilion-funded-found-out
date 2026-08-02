#!/usr/bin/env python3
"""
make_post.py — turn ONE verified company from the pipeline checkpoint into a
ready-to-post LinkedIn carousel: editable HTML + square PDF + caption.

Workflow (auto-draft, ~5-minute human finish):
    1. run_pipeline.py            → discovers, verifies, grades → checkpoint
    2. make_post.py "ChatCut"     → writes this company's deck + caption
    3. eyeball the numbers, post the PDF as a LinkedIn document, paste the caption.

Usage:
    python scripts/make_post.py "ChatCut"
    python scripts/make_post.py "ChatCut" --date 2026-08-01 --screenshot path/to/tall.png
    python scripts/make_post.py "ChatCut" --render-only   # re-render HTML after hand-edits
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import anthropic

BASE_DIR = Path(__file__).parent.parent
CHECKPOINT_DIR = BASE_DIR / 'data' / 'checkpoints'
POSTS_DIR = BASE_DIR / 'output' / 'posts'
# 100 Yards brand (from 100yardstogo.com)
ACCENT = '#e85d26'        # burnt orange
ACCENT_LT = '#f4926a'     # lighter orange for dark grounds
INK = '#1a1a1a'

DIMS = ['centricity', 'legibility', 'edge', 'argument', 'recall']
DEFINITIONS = {
    'centricity': 'Is the page about the customer, or the company?',
    'legibility': 'Can a stranger tell what you do, and who for?',
    'edge':       'Do you say why you, not the alternative?',
    'argument':   'A point of view, or just a feature list?',
    'recall':     'Will anyone remember you tomorrow?',
}
# Each card shows a different vertical slice of the (tall) homepage screenshot.
CHUNK = {'centricity': '0%', 'legibility': '26%', 'edge': '50%', 'argument': '74%', 'recall': '100%'}


def latest_checkpoint() -> Path:
    cps = sorted(CHECKPOINT_DIR.glob('*.json'), reverse=True)
    if not cps:
        sys.exit("No checkpoints found. Run scripts/run_pipeline.py first.")
    return cps[0]


def compose(company: dict, evaluation: dict, client) -> dict:
    """One LLM call → cover copy, through-line, caption, and per-dimension fix."""
    reads = "\n".join(
        f"- {d.capitalize()} [{evaluation['grades'][d]['grade']}]: {evaluation['grades'][d]['explanation']}"
        for d in DIMS
    )
    prompt = f"""You are Josh Mait, founder of the boutique marketing agency 100 Yards, writing a LinkedIn carousel that critiques an early-stage company's homepage marketing. It is sharp but constructive — a demonstration of what you'd fix, not a dunk. The company is a potential client.

VOICE: Plain-spoken, confident, a little unexpected. Short sentences of varied length. No jargon. NEVER use these AI-tells: "Not X. Not Y.", triple parallel phrases, dramatic one-line fragments as closers, "unlock/elevate/harness/leverage", em-dash overuse (one max), or rhythmic short-sentence stacking.

COMPANY: {company.get('company_name')}
In the news: {company.get('news_hook','')}
What it does: {company.get('description','')}

THE CLEAR READ (grade + your critique per dimension — grades are for your judgment only, they will NOT appear on the cards):
{reads}

Write, and return ONLY this JSON:
{{
  "doc_title": "short label shown on the LinkedIn carousel, e.g. 'ChatCut: a five-part read'",
  "cover_hook": "the diagnosis in <=14 words — the one thing wrong, stated plainly",
  "cover_sub": "one line under the hook, <=18 words",
  "through_line": "the closing synthesis, 1-2 sentences — what the company is vs. what the page says",
  "caption": "the LinkedIn post body: 3-5 short lines, may hint at an overall verdict, ends by pointing to swiping. No hashtags. No 'DM me'.",
  "dims": {{
    "centricity": {{"fix": "one constructive line — what you'd change"}},
    "legibility": {{"fix": "..."}},
    "edge": {{"fix": "..."}},
    "argument": {{"fix": "..."}},
    "recall": {{"fix": "..."}}
  }}
}}"""
    resp = client.messages.create(model="claude-opus-4-7", max_tokens=1500,
                                  messages=[{"role": "user", "content": prompt}])
    text = resp.content[0].text.strip()
    if text.startswith('```'):
        text = text.split('```')[1]
        if text.startswith('json'):
            text = text[4:]
    return json.loads(text)


def card_html(i: int, dim: str, read: str, fix: str, shot_uri: str) -> str:
    ypos = CHUNK[dim]
    return f"""
<div class="slide light">
  <div class="pad">
    <div class="top"><span>0{i} / 05 &nbsp;·&nbsp; {dim.capitalize()}</span><span>{{company}}</span></div>
    <div class="band"><img src="{shot_uri}" style="object-position:50% {ypos};"></div>
    <div class="namerow">
      <div class="dimname">{dim.capitalize()}</div>
      <div class="dimdef">{DEFINITIONS[dim]}</div>
    </div>
    <div class="rule"></div>
    <div class="label">The read</div>
    <div class="read">{read}</div>
    <div class="fixbox">
      <div class="label" style="color:{ACCENT}">The fix</div>
      <div class="fix">{fix}</div>
    </div>
    <div class="foot"><span class="mark">100&nbsp;<b>Yards</b></span><span>The Read</span></div>
  </div>
</div>"""


def build_html(company: dict, evaluation: dict, post: dict, shot_uri: str) -> str:
    name = company.get('company_name', '')
    cards = "".join(
        card_html(i + 1, d, evaluation['grades'][d]['explanation'],
                  post['dims'][d]['fix'], shot_uri)
        for i, d in enumerate(DIMS)
    ).replace('{company}', name)
    return TEMPLATE.format(
        name=name, accent=ACCENT, accent_lt=ACCENT_LT, ink=INK,
        hook=post['cover_hook'], sub=post['cover_sub'],
        kicker=company.get('news_hook', ''), shot=shot_uri, cards=cards,
        through=post['through_line'],
    )


TEMPLATE = """<meta charset="utf-8">
<title>The Read — {name}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600;9..144,700&family=Inter:wght@400;500;600;700;800&display=swap');
  @page {{ size: 720px 720px; margin: 0; }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  :root {{ --ink:{ink}; --mute:#6b7280; --line:#e7e2dd; --accent:{accent}; --accentlt:{accent_lt}; --paper:#fbf9f6; }}
  html,body {{ background:#333; }}
  body {{ font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif; -webkit-font-smoothing:antialiased; }}
  .serif {{ font-family:'Fraunces',Georgia,serif; }}
  .slide {{ width:720px; height:720px; position:relative; overflow:hidden; page-break-after:always; }}
  @media screen {{ body{{padding:24px; display:flex; flex-direction:column; gap:20px; align-items:center;}} .slide{{box-shadow:0 8px 40px rgba(0,0,0,.4);}} }}
  .light {{ background:var(--paper); color:var(--ink); }}
  .dark  {{ background:{ink}; color:#fff; }}
  .pad {{ padding:44px 50px; height:100%; display:flex; flex-direction:column; }}
  .top {{ display:flex; justify-content:space-between; font-size:11px; letter-spacing:.16em; text-transform:uppercase; color:var(--mute); font-weight:600; }}
  .dark .top {{ color:#9a9a9a; }}
  .foot {{ display:flex; justify-content:space-between; align-items:center; font-size:11px; letter-spacing:.14em; text-transform:uppercase; color:var(--mute); font-weight:600; margin-top:auto; }}
  .mark {{ letter-spacing:.02em; }}
  .mark b {{ color:var(--accent); }}
  .grow {{ flex:1; }}
  /* cover / close */
  .kicker {{ font-size:12px; letter-spacing:.16em; text-transform:uppercase; color:var(--accentlt); font-weight:700; margin-bottom:18px; }}
  .hook {{ font-family:'Fraunces',Georgia,serif; font-size:44px; line-height:1.04; font-weight:700; letter-spacing:-.01em; }}
  .sub {{ font-size:16px; line-height:1.5; color:#d7d2cc; margin-top:16px; font-weight:500; max-width:88%; }}
  .cshot {{ margin-top:22px; border:1px solid #333; border-radius:8px; overflow:hidden; height:232px; }}
  .cshot img {{ width:100%; height:100%; object-fit:cover; object-position:top; }}
  .clearrow {{ display:flex; gap:24px; margin-top:20px; }}
  .clearrow div {{ font-size:20px; font-weight:800; color:var(--accent); }}
  .clearrow span {{ display:block; font-size:8.5px; letter-spacing:.11em; color:#8a8a8a; font-weight:600; margin-top:4px; }}
  .synth {{ font-family:'Fraunces',Georgia,serif; font-size:30px; line-height:1.24; font-weight:600; letter-spacing:-.01em; }}
  .cta {{ margin-top:auto; }}
  .ctaline {{ font-size:15px; color:#d7d2cc; font-weight:500; line-height:1.5; }}
  .ctaurl {{ font-size:22px; font-weight:800; color:var(--accentlt); margin-top:10px; letter-spacing:-.01em; }}
  /* dimension card */
  .band {{ width:100%; height:392px; border-radius:8px; overflow:hidden; border:1px solid var(--line); margin-top:12px; background:#fff; }}
  .band img {{ width:100%; height:100%; object-fit:cover; }}
  .namerow {{ margin-top:15px; }}
  .dimname {{ font-size:12.5px; letter-spacing:.2em; text-transform:uppercase; color:var(--mute); font-weight:700; }}
  .dimdef {{ font-family:'Fraunces',Georgia,serif; font-size:20px; color:var(--accent); font-weight:600; margin-top:5px; line-height:1.22; letter-spacing:-.01em; }}
  .rule {{ height:1px; background:var(--line); margin:13px 0 11px; }}
  .label {{ font-size:10px; letter-spacing:.18em; text-transform:uppercase; font-weight:700; color:var(--mute); margin-bottom:6px; }}
  .read {{ font-size:16px; line-height:1.3; font-weight:600; letter-spacing:-.01em; }}
  .fixbox {{ margin-top:12px; border-left:3px solid var(--accent); padding-left:14px; }}
  .fix {{ font-size:15px; line-height:1.34; font-weight:600; color:var(--ink); }}
</style>

<div class="slide dark">
  <div class="pad">
    <div class="top"><span class="mark">100&nbsp;<b>Yards</b> &nbsp;·&nbsp; The Read</span><span>Seed–Series A</span></div>
    <div class="grow" style="display:flex;flex-direction:column;justify-content:center;">
      <div class="kicker">{kicker}</div>
      <div class="hook">{hook}</div>
      <div class="sub">{sub}</div>
      <div class="cshot"><img src="{shot}"></div>
    </div>
    <div class="clearrow">
      <div>C<span>CENTRICITY</span></div><div>L<span>LEGIBILITY</span></div><div>E<span>EDGE</span></div><div>A<span>ARGUMENT</span></div><div>R<span>RECALL</span></div>
    </div>
  </div>
</div>
{cards}
<div class="slide dark">
  <div class="pad">
    <div class="top"><span class="mark">100&nbsp;<b>Yards</b> &nbsp;·&nbsp; The Read</span><span>{name}</span></div>
    <div class="grow" style="display:flex;flex-direction:column;justify-content:center;">
      <div class="kicker">The through-line</div>
      <div class="synth">{through}</div>
    </div>
    <div class="cta">
      <div class="ctaline">A 60-second read from the 100 Yards brand engine. Want one on your site?</div>
      <div class="ctaurl">100yardstogo.com</div>
    </div>
  </div>
</div>
"""


def render_pdf(html_path: Path, pdf_path: Path):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.goto(html_path.resolve().as_uri())
        pg.wait_for_timeout(1200)  # let Fraunces load
        pg.emulate_media(media="print")
        pg.pdf(path=str(pdf_path), width="720px", height="720px", print_background=True)
        b.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('company')
    ap.add_argument('--date', help='checkpoint date (default: latest)')
    ap.add_argument('--screenshot', help='override screenshot path (tall homepage capture)')
    ap.add_argument('--render-only', action='store_true', help='re-render existing HTML to PDF')
    args = ap.parse_args()

    slug = args.company.lower().replace(' ', '-').replace('/', '')
    cp_path = (CHECKPOINT_DIR / f"{args.date}.json") if args.date else latest_checkpoint()
    cp = json.load(open(cp_path))
    run_date = cp['run_date']
    out_dir = POSTS_DIR / f"{run_date}-{slug}"
    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / 'index.html'
    pdf_path = out_dir / 'post.pdf'

    if args.render_only:
        if not html_path.exists():
            sys.exit(f"No HTML at {html_path}. Run without --render-only first.")
        render_pdf(html_path, pdf_path)
        print(f"✓ Re-rendered {pdf_path}")
        return

    match = next((i for i, c in enumerate(cp['companies'])
                  if c['company_name'].lower() == args.company.lower()), None)
    if match is None:
        names = ", ".join(c['company_name'] for c in cp['companies'])
        sys.exit(f"'{args.company}' not in checkpoint {run_date}. Available: {names}")
    company = cp['companies'][match]
    evaluation = cp['evaluations'][match]
    shot = args.screenshot or (cp['screenshot_paths'][match] or [None])[0]
    if not shot or not Path(shot).exists():
        sys.exit(f"Screenshot missing for {args.company}. Pass --screenshot.")

    # Copy the screenshot in next to the HTML and reference it relatively, so the
    # deck renders identically over file:// and a local http server.
    import shutil
    shutil.copy(shot, out_dir / 'shot.png')
    shot_uri = 'shot.png'

    client = anthropic.Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY'))
    print(f"Composing post for {company['company_name']}...")
    post = compose(company, evaluation, client)

    html_path.write_text(build_html(company, evaluation, post, shot_uri))
    (out_dir / 'caption.txt').write_text(
        f"── DOCUMENT TITLE ──\n{post['doc_title']}\n\n── POST CAPTION ──\n{post['caption']}\n"
    )
    render_pdf(html_path, pdf_path)

    print(f"\n✅ Post drafted for {company['company_name']}")
    print(f"   Deck (editable):  {html_path}")
    print(f"   Deck (PDF):       {pdf_path}")
    print(f"   Caption + title:  {out_dir / 'caption.txt'}")
    print(f"\n   Finish: eyeball the numbers, then upload post.pdf as a LinkedIn document + paste the caption.")


if __name__ == '__main__':
    main()
