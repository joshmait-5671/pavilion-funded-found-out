"""
Generate the Funded & Found Out LinkedIn carousel PDF.

Each slide is rendered as a 1080x1080 PNG via Playwright,
then all slides are combined into a single PDF via Pillow.

Design v2 (April 2026):
  - White ground, black ink, single accent color extracted per company
  - Per-company slide is screenshot-led, Bierut-style grid
  - Headline + 5 pithy graded observations, hairline rules, generous space
"""
from __future__ import annotations
import asyncio
import base64
import html as html_lib
import io
import logging
from collections import Counter
from datetime import datetime
from pathlib import Path
from PIL import Image

logger = logging.getLogger(__name__)

SLIDE_W = 1080
SLIDE_H = 1080

INK = '#0a0a0a'
PAPER = '#ffffff'
RULE = '#e3e3e3'
MUTE = '#7a7a7a'
SOFT = '#444444'

GRADE_COLORS = {
    'A': '#1f8a4c',
    'B': '#1d4ed8',
    'C': '#b8860b',
    'D': '#b91c1c',
}

DIMENSION_LABELS = {
    'centricity': 'Centricity',
    'legibility': 'Legibility',
    'edge': 'Edge',
    'argument': 'Argument',
    'recall': 'Recall',
}

BASE_CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  width: 1080px; height: 1080px; overflow: hidden;
  background: #ffffff;
  color: #0a0a0a;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  -webkit-font-smoothing: antialiased;
  text-rendering: geometricPrecision;
}
.mono { font-family: ui-monospace, 'SF Mono', Menlo, monospace; }
.rule { height: 1px; background: #e3e3e3; }
"""


# ─── COLOR EXTRACTION ─────────────────────────────────────────────────────────

def extract_accent_color(path: str, fallback: str = '#0a0a0a') -> str:
    """
    Pull a saturated dominant color from the top of a screenshot.
    Skips near-white, near-black, and low-saturation grays.
    """
    if not path or not Path(path).exists():
        return fallback
    try:
        img = Image.open(path).convert('RGB')
        w, h = img.size
        # Look at the top portion only — that's where the brand lives (nav + hero)
        img = img.crop((0, 0, w, min(h, 1000)))
        img.thumbnail((180, 180), Image.LANCZOS)
        pixels = list(img.getdata())

        buckets: Counter = Counter()
        for r, g, b in pixels:
            mx, mn = max(r, g, b), min(r, g, b)
            sat = (mx - mn) / mx if mx > 0 else 0
            lum = (r + g + b) / 3
            if lum < 35 or lum > 232:
                continue
            if sat < 0.30:
                continue
            buckets[(r // 24 * 24, g // 24 * 24, b // 24 * 24)] += 1

        if not buckets:
            return fallback

        (r, g, b), _ = buckets.most_common(1)[0]
        # Darken slightly for ink-on-white legibility
        r = int(r * 0.88)
        g = int(g * 0.88)
        b = int(b * 0.88)
        return f'#{r:02x}{g:02x}{b:02x}'
    except Exception as e:
        logger.warning(f"Color extraction failed for {path}: {e}")
        return fallback


# ─── SCREENSHOT EMBED ─────────────────────────────────────────────────────────

def _embed_hero_crop(path: str) -> str:
    """
    Crop the screenshot to a consistent hero + nav frame and embed as base64.
    Source is 1440x1800. We keep the top 1100px (nav + full hero) and downscale.
    """
    placeholder = '<div style="width:100%;aspect-ratio:8/5;background:#f3f3f3;"></div>'
    if not path or not Path(path).exists():
        return placeholder
    try:
        img = Image.open(path).convert('RGB')
        w, h = img.size
        crop_h = min(h, 1100)
        img = img.crop((0, 0, w, crop_h))
        img.thumbnail((1100, 1100), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=88)
        b64 = base64.b64encode(buf.getvalue()).decode()
        return (
            f'<img src="data:image/jpeg;base64,{b64}" '
            f'style="width:100%;display:block;" />'
        )
    except Exception as e:
        logger.warning(f"Screenshot embed failed for {path}: {e}")
        return placeholder


# ─── SLIDE BUILDERS ───────────────────────────────────────────────────────────

def build_intro_slide(week_label: str, company_count: int) -> str:
    company_word = 'company' if company_count == 1 else 'companies'
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>
{BASE_CSS}
body {{
  background: #0a0a0a; color: #ffffff;
  display: flex; flex-direction: column;
  justify-content: space-between;
  padding: 80px 80px 64px;
}}
.top {{
  display: flex; justify-content: space-between; align-items: center;
  font-size: 11px; letter-spacing: 2px; text-transform: uppercase;
  color: #999; font-weight: 600;
}}
.center {{ display: flex; flex-direction: column; gap: 32px; max-width: 880px; }}
.kicker {{
  font-size: 12px; letter-spacing: 3px; text-transform: uppercase;
  color: #fff; font-weight: 700;
}}
.title {{
  font-size: 96px; font-weight: 800; color: #fff;
  line-height: 0.95; letter-spacing: -3.5px;
}}
.subtitle {{
  font-size: 22px; color: #bdbdbd; font-weight: 400; line-height: 1.45;
  max-width: 620px;
}}
.framework {{
  display: flex; gap: 0; border-top: 1px solid #2a2a2a; padding-top: 20px;
}}
.dim {{ flex: 1; padding-right: 16px; }}
.dim .letter {{
  font-size: 28px; font-weight: 800; color: #fff; line-height: 1;
}}
.dim .name {{
  font-size: 10px; letter-spacing: 2px; text-transform: uppercase;
  color: #888; font-weight: 600; margin-top: 8px;
}}
.byline {{
  display: flex; justify-content: space-between; align-items: center;
  font-size: 11px; letter-spacing: 1.5px; text-transform: uppercase;
  color: #777; font-weight: 600;
}}
</style>
</head><body>
  <div class="top">
    <div>Funded &amp; Found Out</div>
    <div>{week_label}</div>
  </div>
  <div class="center">
    <div class="kicker">Weekly AI Marketing Report</div>
    <div class="title">Funded.<br>And found out.</div>
    <div class="subtitle">{company_count} newly funded AI {company_word}, graded on their marketing.</div>
    <div class="framework">
      <div class="dim"><div class="letter">C</div><div class="name">Centricity</div></div>
      <div class="dim"><div class="letter">L</div><div class="name">Legibility</div></div>
      <div class="dim"><div class="letter">E</div><div class="name">Edge</div></div>
      <div class="dim"><div class="letter">A</div><div class="name">Argument</div></div>
      <div class="dim"><div class="letter">R</div><div class="name">Recall</div></div>
    </div>
  </div>
  <div class="byline">
    <div>By Josh Mait · Pavilion</div>
    <div>Issue · {week_label}</div>
  </div>
</body></html>"""


def build_company_slide(
    company: dict,
    evaluation: dict,
    screenshot_paths: list,
    slide_num: int,
    total: int,
    week_label: str,
) -> str:
    company_name = html_lib.escape(company.get('company_name', ''))
    website_url = html_lib.escape((company.get('website_url') or '').replace('https://', '').replace('http://', '').rstrip('/'))
    stage = (company.get('funding_stage') or '').replace('_', ' ').upper()
    funding_label = f"${company.get('funding_amount', '?')}M · {stage}".strip(' ·')
    headline = html_lib.escape(evaluation.get('headline', '') or '')
    paragraph = html_lib.escape(evaluation.get('overall_paragraph', '') or '')
    if len(paragraph) > 360:
        paragraph = paragraph[:360].rstrip() + '…'
    grades = evaluation.get('grades', {})

    shot_path = screenshot_paths[0] if screenshot_paths else ''
    accent = extract_accent_color(shot_path, fallback=INK)
    screenshot_html = _embed_hero_crop(shot_path)

    rows = ''
    for key in ['centricity', 'legibility', 'edge', 'argument', 'recall']:
        data = grades.get(key, {})
        grade = data.get('grade', '?')
        explanation = html_lib.escape(data.get('explanation', '') or '')
        if len(explanation) > 140:
            explanation = explanation[:140].rstrip() + '…'
        label = DIMENSION_LABELS.get(key, key.title())
        grade_color = GRADE_COLORS.get(grade, MUTE)
        rows += f"""
<div class="row">
  <div class="row-head">
    <div class="dim-label">{label}</div>
    <div class="grade" style="color:{grade_color};">{grade}</div>
  </div>
  <div class="obs">{explanation}</div>
</div>"""

    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>
{BASE_CSS}
body {{ display: flex; flex-direction: column; padding: 44px 56px 36px; }}

.metabar {{
  display: flex; justify-content: space-between; align-items: center;
  font-size: 11px; letter-spacing: 2px; text-transform: uppercase;
  color: {MUTE}; font-weight: 600;
  padding-bottom: 14px; border-bottom: 1px solid {RULE};
}}
.metabar .meta-mid {{ color: {INK}; }}

.headline-zone {{
  padding: 26px 0 22px;
}}
.headline {{
  font-size: 42px; font-weight: 800; color: {INK};
  line-height: 1.05; letter-spacing: -1.4px;
  max-width: 980px;
}}
.byline {{
  margin-top: 14px;
  font-size: 12px; letter-spacing: 1.8px; text-transform: uppercase;
  color: {MUTE}; font-weight: 600;
}}
.byline strong {{ color: {INK}; font-weight: 700; }}

.grid {{
  display: flex; gap: 36px; flex: 1; min-height: 0;
  padding-top: 22px; border-top: 1px solid {RULE};
}}

.shot-col {{
  width: 56%; display: flex; flex-direction: column; justify-content: flex-start;
}}
.shot-frame-outer {{
  border: 1px solid {accent};
  padding: 6px;
  background: #fff;
}}
.shot-frame-inner {{
  border: 7px solid {accent};
  line-height: 0;
  background: #f5f5f5;
}}
.shot-caption {{
  margin-top: 12px;
  display: flex; justify-content: space-between; align-items: center;
  font-size: 10px; letter-spacing: 1.5px; text-transform: uppercase;
  color: {MUTE}; font-weight: 600;
}}
.shot-caption .dot {{
  display: inline-block; width: 8px; height: 8px;
  background: {accent}; margin-right: 8px; vertical-align: middle;
}}
.body-copy {{
  margin-top: 22px; padding-top: 18px;
  border-top: 1px solid {RULE};
  font-size: 14px; color: {SOFT}; line-height: 1.55; font-weight: 400;
  letter-spacing: -0.05px;
}}
.body-copy::first-letter {{ font-weight: 700; color: {INK}; }}

.grades-col {{
  width: 44%; display: flex; flex-direction: column; justify-content: space-between;
}}
.row {{
  padding: 12px 0 14px;
  border-bottom: 1px solid {RULE};
}}
.row:last-child {{ border-bottom: none; }}
.row-head {{
  display: flex; justify-content: space-between; align-items: baseline;
  margin-bottom: 6px;
}}
.dim-label {{
  font-size: 10px; letter-spacing: 2.2px; text-transform: uppercase;
  color: {MUTE}; font-weight: 700;
}}
.grade {{
  font-size: 28px; font-weight: 800; line-height: 1;
}}
.obs {{
  font-size: 14px; color: {INK}; line-height: 1.45; font-weight: 400;
  letter-spacing: -0.1px;
}}

.footer {{
  margin-top: 18px;
  display: flex; justify-content: space-between; align-items: center;
  font-size: 10px; letter-spacing: 2px; text-transform: uppercase;
  color: {MUTE}; font-weight: 600;
}}
</style>
</head><body>
  <div class="metabar">
    <div class="mono">{slide_num:02d} / {total:02d}</div>
    <div class="meta-mid">Funded &amp; Found Out</div>
    <div class="mono">{html_lib.escape(week_label)}</div>
  </div>

  <div class="headline-zone">
    <div class="headline">{headline}</div>
    <div class="byline">
      <strong>{company_name}</strong> &nbsp;·&nbsp; {website_url} &nbsp;·&nbsp; {html_lib.escape(funding_label)}
    </div>
  </div>

  <div class="grid">
    <div class="shot-col">
      <div class="shot-frame-outer">
        <div class="shot-frame-inner">{screenshot_html}</div>
      </div>
      <div class="shot-caption">
        <div><span class="dot"></span>Homepage · {website_url}</div>
        <div>Captured {html_lib.escape(week_label)}</div>
      </div>
      <div class="body-copy">{paragraph}</div>
    </div>
    <div class="grades-col">{rows}</div>
  </div>

  <div class="footer">
    <div>C · L · E · A · R</div>
    <div>By Josh Mait · Pavilion</div>
  </div>
</body></html>"""


def build_outro_slide(company_count: int = 5) -> str:
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>
{BASE_CSS}
body {{
  background: #0a0a0a; color: #ffffff;
  display: flex; flex-direction: column;
  justify-content: space-between;
  padding: 80px 80px 64px;
}}
.top {{
  display: flex; justify-content: space-between; align-items: center;
  font-size: 11px; letter-spacing: 2px; text-transform: uppercase;
  color: #999; font-weight: 600;
}}
.center {{ max-width: 800px; }}
.kicker {{
  font-size: 12px; letter-spacing: 3px; text-transform: uppercase;
  color: #fff; font-weight: 700; margin-bottom: 28px;
}}
.title {{
  font-size: 84px; font-weight: 800; color: #fff;
  line-height: 0.95; letter-spacing: -3px; margin-bottom: 28px;
}}
.body {{
  font-size: 19px; color: #bdbdbd; line-height: 1.55; font-weight: 400;
  max-width: 620px;
}}
.cta {{
  margin-top: 36px;
  border-top: 1px solid #2a2a2a; padding-top: 24px;
  font-size: 15px; color: #fff; line-height: 1.6; font-weight: 500;
}}
.cta strong {{ font-weight: 700; }}
.byline {{
  display: flex; justify-content: space-between; align-items: center;
  font-size: 11px; letter-spacing: 1.5px; text-transform: uppercase;
  color: #777; font-weight: 600;
}}
</style>
</head><body>
  <div class="top">
    <div>Funded &amp; Found Out</div>
    <div>End of Issue</div>
  </div>
  <div class="center">
    <div class="kicker">Closing Note</div>
    <div class="title">{company_count} {('company' if company_count == 1 else 'companies')}.<br>{company_count} {('report card' if company_count == 1 else 'report cards')}.</div>
    <div class="body">Every funded AI company is making a bet. The ones who get marketing right will compound that investment. The ones who don't will struggle to explain why they matter.</div>
    <div class="cta">
      <strong>New issue every week.</strong> Real funding. Real grades. No filter.<br>
      Follow Josh Mait · Head of Marketing, Pavilion.
    </div>
  </div>
  <div class="byline">
    <div>joinpavilion.com</div>
    <div>Funded &amp; Found Out</div>
  </div>
</body></html>"""


# ─── RENDERING ─────────────────────────────────────────────────────────────────

async def _render_slide_async(html: str, output_path: Path) -> bool:
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page(viewport={'width': SLIDE_W, 'height': SLIDE_H})
            await page.set_content(html, wait_until='networkidle')
            await asyncio.sleep(0.3)
            await page.screenshot(path=str(output_path), full_page=False)
            return True
        except Exception as e:
            logger.error(f"Slide render failed: {e}")
            return False
        finally:
            await browser.close()


def render_slide(html: str, output_path: Path) -> bool:
    return asyncio.run(_render_slide_async(html, output_path))


def combine_to_pdf(slide_paths: list[Path], pdf_path: Path) -> bool:
    """Combine PNG slides into a single PDF using Pillow."""
    try:
        images = []
        for p in slide_paths:
            if p.exists():
                images.append(Image.open(p).convert('RGB'))

        if not images:
            logger.error("No slides to combine")
            return False

        images[0].save(
            str(pdf_path),
            format='PDF',
            save_all=True,
            append_images=images[1:],
            resolution=150,
        )
        logger.info(f"PDF saved: {pdf_path.name} ({len(images)} slides)")
        return True
    except Exception as e:
        logger.error(f"PDF creation failed: {e}")
        return False


# ─── PRE-PUBLISH VALIDATION ───────────────────────────────────────────────────

def validate_batch(
    companies: list[dict],
    evaluations: list[dict | None],
    screenshot_paths: list[list[str]],
) -> tuple[bool, list[str]]:
    """
    Verify the batch is publishable. Returns (ok, errors).
    Checks: no duplicate names, every company has eval + non-empty screenshot,
    and counts align.
    """
    errors: list[str] = []

    if not (len(companies) == len(evaluations) == len(screenshot_paths)):
        errors.append(
            f"Count mismatch: {len(companies)} companies, "
            f"{len(evaluations)} evaluations, {len(screenshot_paths)} screenshot lists"
        )

    seen_names: dict[str, int] = {}
    for i, c in enumerate(companies):
        key = (c.get('company_name') or '').strip().lower()
        if not key:
            errors.append(f"[{i}] empty company_name")
            continue
        if key in seen_names:
            errors.append(
                f"[{i}] duplicate company '{c.get('company_name')}' "
                f"(also at index {seen_names[key]})"
            )
        else:
            seen_names[key] = i

    for i, (c, ev, shots) in enumerate(zip(companies, evaluations, screenshot_paths)):
        name = c.get('company_name', f'idx{i}')
        if ev is None:
            errors.append(f"[{i}] {name}: missing evaluation")
        if not shots:
            errors.append(f"[{i}] {name}: no screenshot path recorded")
            continue
        path = shots[0]
        if not path or not Path(path).exists():
            errors.append(f"[{i}] {name}: screenshot file missing ({path})")
        elif Path(path).stat().st_size < 1024:
            errors.append(f"[{i}] {name}: screenshot file is empty / tiny ({path})")

    return (len(errors) == 0), errors


# ─── MAIN ENTRY ────────────────────────────────────────────────────────────────

def generate_carousel(
    companies: list[dict],
    evaluations: list[dict],
    screenshot_paths: list[list[str]],
    output_dir: Path,
    slides_dir: Path,
) -> Path | None:
    """
    Build the full LinkedIn carousel PDF.
    Returns the PDF path or None on failure.
    Caller is responsible for running validate_batch() first.
    """
    slides_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    week_label = datetime.now().strftime("Week of %b %d, %Y")
    date_str = datetime.now().strftime("%Y-%m-%d")
    pdf_path = output_dir / f"funded-and-found-out-{date_str}.pdf"

    all_slide_paths: list[Path] = []

    intro_path = slides_dir / "00_intro.png"
    if render_slide(build_intro_slide(week_label, len(companies)), intro_path):
        all_slide_paths.append(intro_path)
        logger.info("Rendered intro slide")

    for i, (company, evaluation, shots) in enumerate(zip(companies, evaluations, screenshot_paths)):
        if not evaluation:
            logger.warning(f"Skipping {company.get('company_name')} — no evaluation")
            continue

        company_path = slides_dir / f"{i+1:02d}_company.png"
        if render_slide(
            build_company_slide(company, evaluation, shots, i + 1, len(companies), week_label),
            company_path,
        ):
            all_slide_paths.append(company_path)

        logger.info(f"Rendered slide for {company.get('company_name')}")

    outro_path = slides_dir / "99_outro.png"
    if render_slide(build_outro_slide(len(companies)), outro_path):
        all_slide_paths.append(outro_path)
        logger.info("Rendered outro slide")

    logger.info(f"Total slides: {len(all_slide_paths)}")

    if combine_to_pdf(all_slide_paths, pdf_path):
        return pdf_path
    return None
