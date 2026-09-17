import pytest
from unittest.mock import patch, AsyncMock
from meta_builder_brain.ingestion.hermes import HermesSynthesisAgent, HermesSynthesisError
from meta_builder_brain.ingestion.scraper import PlaywrightSchemaScraper, ScraperError


@pytest.mark.asyncio
async def test_hermes_synthesis_agent_success():
    agent = HermesSynthesisAgent()
    raw_rfc = "Title: User Specification\n\nuser_id: string identifier\nemail: string email_address"

    canonical_schema = await agent.synthesize_rfc_spec(raw_rfc)
    assert canonical_schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert "user_id" in canonical_schema["properties"]
    assert "email" in canonical_schema["properties"]


@pytest.mark.asyncio
async def test_hermes_synthesis_agent_empty_input():
    agent = HermesSynthesisAgent()
    with pytest.raises(HermesSynthesisError):
        await agent.synthesize_rfc_spec("   ")


@pytest.mark.asyncio
async def test_playwright_schema_scraper_success():
    scraper = PlaywrightSchemaScraper()

    mock_page = AsyncMock()
    mock_page.goto.return_value = AsyncMock(status=200)
    mock_page.content.return_value = "<html><body></body></html>"
    mock_page.evaluate.return_value = '{"openapi": "3.0.0", "info": {"title": "Mock API"}}'

    mock_browser = AsyncMock()
    mock_browser.new_page.return_value = mock_page

    mock_pw_cm = AsyncMock()
    mock_pw_cm.__aenter__.return_value.chromium.launch.return_value = mock_browser

    with patch("meta_builder_brain.ingestion.scraper.async_playwright", return_value=mock_pw_cm):
        result = await scraper.scrape_openapi_spec("https://api.example.com/openapi.json")
        assert result["openapi"] == "3.0.0"
        assert result["info"]["title"] == "Mock API"


@pytest.mark.asyncio
async def test_playwright_schema_scraper_http_error():
    scraper = PlaywrightSchemaScraper()

    mock_page = AsyncMock()
    mock_page.goto.return_value = AsyncMock(status=404)

    mock_browser = AsyncMock()
    mock_browser.new_page.return_value = mock_page

    mock_pw_cm = AsyncMock()
    mock_pw_cm.__aenter__.return_value.chromium.launch.return_value = mock_browser

    with patch("meta_builder_brain.ingestion.scraper.async_playwright", return_value=mock_pw_cm):
        with pytest.raises(ScraperError):
            await scraper.scrape_openapi_spec("https://api.example.com/missing.json")