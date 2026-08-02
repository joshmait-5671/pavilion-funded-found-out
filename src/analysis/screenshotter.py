"""Take a single tall screenshot of a company's homepage using Playwright."""
import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


async def _take_screenshots_async(url: str, output_dir: Path, company_slug: str) -> list[str]:
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
            context = await browser.new_context(
                viewport={'width': 1440, 'height': 1800},
                user_agent=(
                    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                ),
            )
            page = await context.new_page()

            # Navigate — fallback from networkidle to domcontentloaded
            try:
                await page.goto(url, wait_until='networkidle', timeout=20000)
            except Exception:
                try:
                    await page.goto(url, wait_until='domcontentloaded', timeout=15000)
                except Exception as e:
                    logger.warning(f"Navigation failed for {url}: {e}")
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


def take_screenshots(url: str, output_dir: Path, company_slug: str) -> list[str]:
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
            context = await browser.new_context(
                viewport={'width': 1440, 'height': 1800},
                user_agent=(
                    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                ),
            )
            page = await context.new_page()

            try:
                await page.goto(url, wait_until='networkidle', timeout=20000)
            except Exception:
                try:
                    await page.goto(url, wait_until='domcontentloaded', timeout=15000)
                except Exception as e:
                    logger.warning(f"Navigation failed for {url}: {e}")
                    return paths, content

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
