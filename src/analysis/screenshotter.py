"""Take a single tall screenshot of a company's homepage using Playwright."""
import asyncio
import logging
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

logger = logging.getLogger(__name__)

# Early-stage company sites fail in boringly predictable ways: a marketing domain
# that only answers on www (or only on the apex), a half-configured cert, a hero
# that never stops fetching so `networkidle` never fires. Each of those used to
# drop a company from the week's lineup and backfill junk in its place, so every
# navigation now walks host variants x load-strategies before giving up.
NAV_STRATEGIES = [
    ('networkidle', 25000),
    ('load', 25000),
    ('domcontentloaded', 20000),
]


def url_candidates(url: str) -> list:
    """The URL as given, plus its www<->apex twin. Order is preserved and dupes dropped."""
    out = [url]
    try:
        parts = urlsplit(url)
        host = parts.netloc
        if host.startswith('www.'):
            twin = host[4:]
        else:
            twin = 'www.' + host
        out.append(urlunsplit((parts.scheme, twin, parts.path, parts.query, parts.fragment)))
    except Exception:
        pass
    seen = set()
    return [u for u in out if not (u in seen or seen.add(u))]


async def _goto_resilient(page, url: str) -> str:
    """Try every host variant against every load strategy. Returns the URL that
    loaded, or '' if the site is genuinely unreachable."""
    last_err = None
    for candidate in url_candidates(url):
        for wait_until, timeout in NAV_STRATEGIES:
            try:
                await page.goto(candidate, wait_until=wait_until, timeout=timeout)
                if candidate != url:
                    logger.info(f"Reached {candidate} (fallback from {url})")
                return candidate
            except Exception as e:
                last_err = e
                # A dead host fails identically on every strategy — don't burn
                # three timeouts proving it. Move to the next candidate host.
                if 'ERR_NAME_NOT_RESOLVED' in str(e):
                    break
    logger.warning(f"Navigation failed for {url}: {last_err}")
    return ''


async def _new_context(browser):
    return await browser.new_context(
        viewport={'width': 1440, 'height': 1800},
        # Half-configured certs on early-stage marketing domains are a deploy
        # smell, not a reason to skip the company.
        ignore_https_errors=True,
        user_agent=(
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
            'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ),
    )


async def _take_screenshots_async(url: str, output_dir: Path, company_slug: str) -> list:
    """
    Take one tall screenshot of the homepage (top 1800px).
    Returns a list with a single file path.
    """
    from playwright.async_api import async_playwright

    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await _new_context(browser)
            page = await context.new_page()

            if not await _goto_resilient(page, url):
                return paths

            await asyncio.sleep(2)  # Let animations and fonts settle

            shot_path = output_dir / f"{company_slug}.png"
            await page.screenshot(
                path=str(shot_path),
                clip={'x': 0, 'y': 0, 'width': 1440, 'height': 1800},
            )
            paths.append(str(shot_path))
            logger.info(f"Screenshot saved: {shot_path.name}")

        except Exception as e:
            logger.warning(f"Screenshot failed for {url}: {e}")
        finally:
            await browser.close()

    return paths


def take_screenshots(url: str, output_dir: Path, company_slug: str) -> list:
    """Sync wrapper around async screenshot function."""
    return asyncio.run(_take_screenshots_async(url, output_dir, company_slug))


async def _capture_async(url: str, output_dir: Path, company_slug: str):
    """Screenshot AND read the page text from the same Chromium render.

    Returns (paths, content) where content matches scraper.scrape_website's
    shape. One fetch means the grades, the identity check, and the image on
    the slide are always the same page — and Chromium handles the JS-heavy and
    TLS-picky sites the requests scraper silently fails on.
    """
    from playwright.async_api import async_playwright

    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    content = {'url': url, 'title': '', 'meta_description': '',
               'hero_text': '', 'full_text': '', 'success': False}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await _new_context(browser)
            page = await context.new_page()

            landed = await _goto_resilient(page, url)
            if not landed:
                return paths, content
            content['url'] = landed

            # Nudge lazy-loaded heroes into painting, then return to the top.
            # Many JS-heavy sites render the hero blank if you shoot too early.
            await asyncio.sleep(3)
            try:
                await page.evaluate("window.scrollTo(0, 1200)")
                await asyncio.sleep(1.5)
                await page.evaluate("window.scrollTo(0, 0)")
                await asyncio.sleep(1.5)
            except Exception:
                pass

            # Full-page (tall) capture so the deck can slice different sections
            # of the homepage onto different cards. full_page is required — a tall
            # `clip` on a short viewport is silently truncated to the viewport.
            shot_path = output_dir / f"{company_slug}.png"
            await page.screenshot(path=str(shot_path), full_page=True)
            paths.append(str(shot_path))
            logger.info(f"Screenshot saved: {shot_path.name}")

            # Pull text from the same rendered DOM.
            try:
                content['title'] = await page.title() or ''
                content['meta_description'] = await page.evaluate(
                    """() => {
                        const m = document.querySelector('meta[name="description"]')
                              || document.querySelector('meta[property="og:description"]');
                        return m ? (m.getAttribute('content') || '') : '';
                    }"""
                )
                heros = await page.evaluate(
                    """() => Array.from(document.querySelectorAll('h1,h2'))
                        .map(e => (e.innerText || '').trim())
                        .filter(t => t.length > 3).slice(0, 12)"""
                )
                content['hero_text'] = ' | '.join(heros)
                body = await page.evaluate("() => document.body ? document.body.innerText : ''")
                content['full_text'] = ' '.join((body or '').split())[:6000]
                content['success'] = bool(content['full_text'])
            except Exception as e:
                logger.warning(f"Text extraction failed for {url}: {e}")

        except Exception as e:
            logger.warning(f"Capture failed for {url}: {e}")
        finally:
            await browser.close()

    return paths, content


def capture_page(url: str, output_dir: Path, company_slug: str):
    """Sync wrapper: returns (screenshot_paths, content_dict) from one render."""
    return asyncio.run(_capture_async(url, output_dir, company_slug))
