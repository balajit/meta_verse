import json
from typing import Dict, Any
from playwright.async_api import async_playwright, Playwright
from meta_telemetry import trace_span, get_tracer

tracer = get_tracer("meta_builder_brain.ingestion.scraper")


class ScraperError(Exception):
    """Raised when Playwright headless retrieval fails."""
    pass


class PlaywrightSchemaScraper:
    """Headless browser scraping pipeline for OpenAPI endpoint and documentation retrieval."""

    @trace_span(name="scraper.scrape_openapi_spec")
    async def scrape_openapi_spec(self, url: str) -> Dict[str, Any]:
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                response = await page.goto(url, wait_until="networkidle")
                if not response or response.status >= 400:
                    raise ScraperError(
                        f"Failed to fetch content from '{url}', HTTP status: {response.status if response else 'No Response'}"
                    )

                content = await page.content()
                try:
                    text_content = await page.evaluate("() => document.body.innerText")
                    parsed_json: Dict[str, Any] = json.loads(text_content)
                    await browser.close()
                    return parsed_json
                except json.JSONDecodeError:
                    await browser.close()
                    return {
                        "$schema": "https://json-schema.org/draft/2020-12/schema",
                        "type": "object",
                        "title": f"Scraped OpenAPI Spec from {url}",
                        "raw_html_length": len(content),
                        "properties": {},
                    }
        except Exception as exc:
            raise ScraperError(f"Playwright browser execution failed for URL '{url}': {exc}") from exc