import asyncio
from crawl4ai import *

async def scrape_url(url):
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(
            url,
        )
        return result.markdown

