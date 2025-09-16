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
            
            # First try with normal Chromium (HTTP/2 enabled)
            try:
                return await self._crawl_with_browser(url, disable_http2=False)
            except Exception as e:
                # If we get HTTP/2 protocol error or empty response, retry with more aggressive settings
                if any(error in str(e) for error in ["ERR_HTTP2_PROTOCOL_ERROR", "ERR_EMPTY_RESPONSE", "net::ERR_"]):
                    print(f"Network error for {url}, retrying with fallback settings: {str(e)[:100]}")
                    try:
                        return await self._crawl_with_browser(url, disable_http2=True)
                    except Exception as fallback_error:
                        # Final fallback with even more aggressive settings
                        print(f"Fallback also failed for {url}, trying with aggressive settings: {str(fallback_error)[:100]}")
                        try:
                            return await self._crawl_with_aggressive_settings(url)
                        except Exception as final_error:
                            return CrawledPage(
                                url=url,
                                title='Error',
                                content='',
                                status_code=0,
                                error=str(final_error),
                                metadata={'error_type': type(final_error).__name__, 'all_fallbacks_attempted': True}
                            )
                else:
                    return CrawledPage(
                        url=url,
                        title='Error',
                        content='',
                        status_code=0,
                        error=str(e),
                        metadata={'error_type': type(e).__name__}
                    )
    
    async def _crawl_with_browser(self, url: str, disable_http2: bool = False) -> CrawledPage:
        """
        Crawl a single URL with a specific browser configuration.
        
        Args:
            url: URL to crawl
            disable_http2: Whether to disable HTTP/2 protocol
            
        Returns:
            CrawledPage object with the page content and metadata
        """
        async with async_playwright() as p:
            # Configure browser launch args - match playwright_test.py
            launch_args = []
            if disable_http2:
                launch_args.append('--disable-http2')
            
            browser = await p.chromium.launch(headless=False, args=launch_args)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
                timezone_id="America/New_York",
                ignore_https_errors=True,
                extra_http_headers=headers
            )
            page = await context.new_page()
            
            try:
                # Set a timeout for the page load - match playwright_test.py
                response = await page.goto(url, wait_until='domcontentloaded')
                
                # Wait for the page to be fully loaded
                await page.wait_for_selector('body', timeout=30000)
                
                # Get page title and HTML content
                title = await page.title()

                content = await page.content()
                soup = BeautifulSoup(content, "html.parser")

                # Remove unwanted tags
                for tag in soup(["script", "style", "noscript", "img", "svg"]):
                    tag.decompose()

                content = soup.get_text(separator="\n", strip=True)
                return CrawledPage(
                    url=url,
                    title=title,
                    content=content.strip() if content else '',
                    status_code=response.status if response else 200,
                    metadata={
                        'final_url': page.url,
                        'content_type': response.headers.get('content-type') if response else 'text/html',
                        'content_extracted': bool(content),
                        'http2_disabled': disable_http2
                    }
                )
                
            except Exception as e:
                print(f"Error crawling {url} (HTTP/2 disabled: {disable_http2}): {repr(e)}")
                raise e
            
            finally:
                await browser.close()
    
    async def _crawl_with_aggressive_settings(self, url: str) -> CrawledPage:
        """
        Final fallback with aggressive browser settings to handle problematic sites.
        
        Args:
            url: URL to crawl
            
        Returns:
            CrawledPage object with the page content and metadata
        """
        async with async_playwright() as p:
            # Aggressive browser launch args
            launch_args = [
                '--disable-http2',
                '--disable-web-security',
                '--disable-features=VizDisplayCompositor',
                '--disable-extensions',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--disable-background-timer-throttling',
                '--disable-backgrounding-occluded-windows',
                '--disable-renderer-backgrounding'
            ]
            
            browser = await p.chromium.launch(headless=False, args=launch_args)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
                timezone_id="America/New_York",
                ignore_https_errors=True,
                extra_http_headers=headers,
                bypass_csp=True
            )
            page = await context.new_page()
            
            try:
                # More aggressive page loading with longer timeout
                response = await page.goto(url, wait_until='domcontentloaded', timeout=30000)
                
                # Wait for the page to be fully loaded with longer timeout
                try:
                    await page.wait_for_selector('body', timeout=30000)
                except:
                    # If body selector fails, just wait a bit and continue
                    await asyncio.sleep(2)
                
                # Get page title and HTML content
                title = await page.title()

                content = await page.content()
                soup = BeautifulSoup(content, "html.parser")

                # Remove unwanted tags
                for tag in soup(["script", "style", "noscript", "img", "svg"]):
                    tag.decompose()

                content = soup.get_text(separator="\n", strip=True)
                return CrawledPage(
                    url=url,
                    title=title,
                    content=content.strip() if content else '',
                    status_code=response.status if response else 200,
                    metadata={
                        'final_url': page.url,
                        'content_type': response.headers.get('content-type') if response else 'text/html',
                        'content_extracted': bool(content),
                        'aggressive_mode': True
                    }
                )
                
            except Exception as e:
                print(f"Aggressive crawling failed for {url}: {repr(e)}")
                raise e
            
            finally:
                await browser.close()
