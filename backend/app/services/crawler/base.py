from dataclasses import dataclass
from typing import List, Dict, Optional, Any
from playwright.async_api import async_playwright, Page
import asyncio
import aiohttp
import random
from bs4 import BeautifulSoup

headers = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "accept-encoding": "gzip, deflate, br, zstd",
    "accept-language": "en-US,en;q=0.9",
    "cache-control": "max-age=0",
    "sec-ch-ua": '"Google Chrome";v="120", "Chromium";v="120", "Not=A?Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1"
}

@dataclass
class CrawledPage:
    """Represents a crawled web page with its content and metadata."""
    url: str
    title: str
    content: str
    status_code: int
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class BaseCrawler:
    """Base class for web crawlers."""
    
    def __init__(self, max_concurrent: int = 5, request_delay: float = 0.5):
        """
        Initialize the crawler.
        
        Args:
            max_concurrent: Maximum number of concurrent requests
            request_delay: Delay between requests in seconds
        """
        self.max_concurrent = max_concurrent
        self.request_delay = request_delay
        self.semaphore = asyncio.Semaphore(max_concurrent)
    
    async def crawl(self, urls: List[str]) -> List[CrawledPage]:
        """
        Crawl multiple URLs asynchronously.
        
        Args:
            urls: List of URLs to crawl
            
        Returns:
            List of CrawledPage objects
        """
        tasks = [self._crawl_single(url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out any exceptions and return valid results
        return [result for result in results if isinstance(result, CrawledPage)]
    
    async def crawl_stream(self, urls: List[str]):
        """Yield CrawledPage results as they complete.
        
        Args:
            urls: List of URLs to crawl
        Yields:
            CrawledPage objects as they finish crawling
        """
        tasks = [asyncio.create_task(self._crawl_single(url)) for url in urls]
        for task in asyncio.as_completed(tasks):
            try:
                result = await task
                if isinstance(result, CrawledPage):
                    yield result
            except Exception as e:
                # Yield an error CrawledPage for visibility
                yield CrawledPage(url="", title="Error", content="", status_code=0, error=str(e), metadata={"error_type": type(e).__name__})
    
    async def _crawl_single(self, url: str) -> CrawledPage:
        """
        Crawl a single URL.
        
        Args:
            url: URL to crawl
            
        Returns:
            CrawledPage object with the page content and metadata
        """
        async with self.semaphore:
            # Add random delay to avoid being blocked
            await asyncio.sleep(random.uniform(0.1, self.request_delay))
            
            try:
                async with async_playwright() as p:
                    browser = await p.chromium.launch(headless=False)
                    context = await browser.new_context(
                        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                        viewport={'width': 1920, 'height': 1080},
                        ignore_https_errors=True,
                        extra_http_headers=headers
                    )
                    page = await context.new_page()
                    
                    try:
                        # Set a timeout for the page load
                        response = await page.goto(url,wait_until='domcontentloaded')
                        
                        # Wait for the page to be fully loaded
                        await page.wait_for_selector('body', timeout=30000)
                        
                        # Get page title and HTML content
                        title = await page.title()

                        content=await page.content()
                        soup = BeautifulSoup(content, "html.parser")

                        # Remove unwanted tags
                        for tag in soup(["script", "style", "noscript", "img", "svg"]):tag.decompose()

                        content = soup.get_text(separator="\n", strip=True)
                        return CrawledPage(
                            url=url,
                            title=title,
                            content=content.strip() if content else '',
                            status_code=response.status if response else 200,
                            metadata={
                                'final_url': page.url,
                                'content_type': response.headers.get('content-type') if response else 'text/html',
                                'content_extracted': bool(content)
                            }
                        )
                        
                    except Exception as e:
                        print(repr(e))
                        return CrawledPage(
                            url=url,
                            title='Error',
                            content='',
                            status_code=0,
                            error=str(e),
                            metadata={'error_type': type(e).__name__}
                        )
                    
                    finally:
                        await browser.close()
                        
            except Exception as e:
                return CrawledPage(
                    url=url,
                    title='Error',
                    content='',
                    status_code=0,
                    error=str(e),
                    metadata={'error_type': type(e).__name__}
                )
