from dataclasses import dataclass
from typing import List, Dict, Optional, Any
from playwright.async_api import async_playwright, Page
import asyncio
import aiohttp
import random

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
                    browser = await p.chromium.launch(headless=True)
                    context = await browser.new_context(
                        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                        viewport={'width': 1920, 'height': 1080},
                        ignore_https_errors=True
                    )
                    page = await context.new_page()
                    
                    try:
                        # Set a timeout for the page load
                        response = await page.goto(url, timeout=10000, wait_until='domcontentloaded')
                        
                        # Wait for the page to be fully loaded
                        await page.wait_for_selector('body', timeout=30000)
                        
                        # Get page title and HTML content
                        title = await page.title()
                        html_content = await page.content()
                        
                        # Extract main content using DOM cleaning (no scripts, nav, footer, imgs)
                        content = await page.evaluate('''() => {
                            const removeSelectors = ['script','style','nav','footer','header','aside','noscript','svg','img','form','iframe','button','input','video','audio','canvas','figure','figcaption'];
                            const clone = document.body ? document.body.cloneNode(true) : null;
                            if (!clone) return '';
                            removeSelectors.forEach(sel => clone.querySelectorAll(sel).forEach(n => n.remove()));
                            clone.querySelectorAll('[role="navigation"], [role="banner"], [aria-hidden="true"]').forEach(n => n.remove());
                            const selectors = [
                                'article', 'main', 'div[role="main"]', '.content', '.main', '.article', '.post', '.entry', '.entry-content',
                                '.article-content', '.post-content', '.article-body', '.post-body', '.entry-body', '.article-text', '.post-text',
                                '#content', '#main', '#article', '#post', '#entry', '#article-content', '#post-content', '#main-content', '#content-main'
                            ];
                            let text = '';
                            for (const sel of selectors) {
                                const el = clone.querySelector(sel);
                                if (el) {
                                    text = el.innerText || '';
                                    if (text && text.trim().length > 200) break;
                                }
                            }
                            if (!text) text = clone.innerText || '';
                            return text.replace(/\s+/g, ' ').trim();
                        }''')
                        
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
