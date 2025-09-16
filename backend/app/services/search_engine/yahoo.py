import logging
import time
import random
import asyncio
from typing import List
from playwright.async_api import async_playwright
from .base import BaseSearchEngine, SearchResult

logger = logging.getLogger(__name__)

class YahooSearchEngine(BaseSearchEngine):
    """Yahoo search engine implementation using Playwright."""
    
    def __init__(self, max_retries: int = 3, request_delay: float = 2.0):
        """
        Initialize the Yahoo search engine.
        
        Args:
            max_retries: Maximum number of retry attempts for failed requests
            request_delay: Base delay between requests in seconds
        """
        super().__init__("yahoo")
        self.max_retries = max_retries
        self.request_delay = request_delay
        self.last_request_time = 0
    
    async def _enforce_rate_limit(self):
        """Enforce rate limiting by waiting if needed."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.request_delay:
            wait_time = self.request_delay - time_since_last + random.uniform(0.5, 1.5)
            await asyncio.sleep(wait_time)
        self.last_request_time = time.time()
    
    async def _yahoo_search_playwright(self, query: str, page_num: int = 1, results_per_page: int = 10) -> List[dict]:
        """
        Search Yahoo with Playwright, return a list of {title, link} dicts.
        Uses XPath based on observed structure.
        page_num starts from 1.
        """
        # Calculate which result to start from
        # Yahoo uses `b=` parameter: start index, 1-based
        start = (page_num - 1) * results_per_page + 1
        
        search_url = f"https://search.yahoo.com/search?p={query}&b={start}"
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 800}
            )
            
            try:
                page = await context.new_page()
                await page.goto(search_url, timeout=60000)

                # Wait for something that signals results have loaded
                try:
                    await page.wait_for_selector('xpath=//*[@id="web"]/ol/li[1]/div/div[1]/a', timeout=10000)
                except:
                    logger.warning("Timeout waiting for first result link. Page may not be loaded properly.")
                    return []

                results = []
                # Loop over the first results_per_page results, using XPath pattern
                for i in range(1, results_per_page + 1):
                    # Build the XPath for the i-th result
                    xpath = f'//*[@id="web"]/ol/li[{i}]/div/div[1]/a'
                    # Try to get the element
                    try:
                        element_handle = await page.query_selector(f'xpath={xpath}')
                        if element_handle:
                            link = await element_handle.get_attribute('href')
                            title = (await element_handle.inner_text()).strip()
                            if link and title:
                                results.append({"title": title, "link": link})
                    except Exception as e:
                        logger.debug(f"Error extracting result {i}: {e}")
                        continue

                # Sleep a little to mimic human browsing
                await asyncio.sleep(random.uniform(2, 5))
                
                return results
                
            finally:
                await context.close()
                await browser.close()
    
    async def search(self, query: str, max_results: int = 10) -> List[SearchResult]:
        """
        Search Yahoo for the given query with pagination support.
        
        Args:
            query: The search query
            max_results: Maximum number of results to return
            
        Returns:
            List of SearchResult objects
        """
        logger.info(f"Searching Yahoo via Playwright for: {query} (max {max_results} results)")
        results: List[SearchResult] = []
        seen = set()
        
        try:
            page = 1
            results_per_page = 7
            max_page = max_results//results_per_page
            
            while len(results) < max_results and page<=max_page:
                remaining = max_results - len(results)
                current_page_limit = min(results_per_page, remaining)
                
                logger.debug(f"Making Yahoo Playwright request: page={page}, limit={current_page_limit}")
                
                # Enforce rate limiting
                await self._enforce_rate_limit()
                
                page_results = await self._yahoo_search_playwright(query, page, current_page_limit)
                
                if not page_results:
                    logger.info(f"No more results found on page {page}")
                    break
                
                # Process results
                for item in page_results:
                    link = item.get('link')
                    if link and isinstance(link, str):
                        if link not in seen:
                            seen.add(link)
                            results.append(SearchResult(url=link, source='yahoo'))
                            # print(len(results),"  --  ",max_results,page)
                            if len(results) >= max_results:
                                break
                
                logger.debug(f"Found {len(page_results)} results on page {page}")
                
                # If we got fewer results than expected, we've reached the end
                # if len(page_results) < results_per_page:
                #     logger.info(f"Received fewer results ({len(page_results)}) than expected, stopping pagination")
                #     break
                
                page += 1
                
        except Exception as e:
            logger.error(f"Error in Yahoo Playwright search: {type(e).__name__}: {str(e)}", exc_info=True)
            
        logger.info(f"Found {len(results)} results from Yahoo (Playwright) for: {query}")
        return results
