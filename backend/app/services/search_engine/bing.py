import logging
import random
import asyncio
from typing import List, Optional, Dict, Any
import httpx
import os
import time
from playwright.async_api import async_playwright

from .base import BaseSearchEngine, SearchResult

# Set up logging
logger = logging.getLogger(__name__)

class BingSearchEngine(BaseSearchEngine):
    """Bing search engine implementation supporting both SerpApi and Playwright methods."""
    
    def __init__(self, max_retries: int = 3, request_delay: float = 2.0):
        """
        Initialize the Bing search engine.
        
        Args:
            max_retries: Maximum number of retry attempts for failed requests
            request_delay: Base delay between requests in seconds
        """
        super().__init__("bing")
        self.base_url = "https://serpapi.com/search.json"
        self.max_retries = max_retries
        self.request_delay = request_delay
        self.last_request_time = 0
        self.results_per_page = 10
        self.max_pages = 5  # kept for compatibility, SerpApi supports num param
        
        # Check which method to use based on environment variable
        self.use_serp_api = os.getenv("USE_SERP_API_FOR_BING", "false").lower() == "true"
        logger.info(f"Bing search engine initialized with {'SerpAPI' if self.use_serp_api else 'Playwright'} method")
    
    async def _enforce_rate_limit(self):
        """Enforce rate limiting by waiting if needed."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.request_delay:
            wait_time = self.request_delay - time_since_last + random.uniform(0.5, 1.5)
            await asyncio.sleep(wait_time)
        self.last_request_time = time.time()

    async def _serpapi_search(self, client: httpx.AsyncClient, query: str, num: int, start: int = 1) -> Optional[Dict[str, Any]]:
        api_key = os.getenv("SERP_API_KEY")
        if not api_key:
            logger.error("SERP_API_KEY is not set in environment")
            return None
        params = {
            'engine': 'bing',
            'q': query,
            'num': max(1, min(num, 50)),  # SerpApi Bing max 50 per request
            'first': start,
            'api_key': api_key,
            "location": "India"
        }
        for attempt in range(self.max_retries + 1):
            try:
                await self._enforce_rate_limit()
                logger.info(f"SerpApi Bing search (attempt {attempt+1}) for: {query} num={params['num']} start={start}")
                resp = await client.get(self.base_url, params=params, timeout=30.0)
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code == 429:
                    # Respect Retry-After if present; otherwise backoff 20-30s window
                    retry_after = int(resp.headers.get('Retry-After', 0)) or int(20 + random.uniform(0, 10))
                    logger.warning(f"SerpApi rate limited. Retrying in {retry_after}s")
                    await asyncio.sleep(retry_after)
                    continue
                logger.warning(f"SerpApi returned status {resp.status_code}: {resp.text[:200]}")
                await asyncio.sleep(2 ** attempt + random.random())
            except (httpx.ConnectError, httpx.ReadTimeout) as e:
                logger.warning(f"SerpApi request error: {e}")
                await asyncio.sleep(2 ** attempt + random.uniform(0, 1))
        return None

    async def search(self, query: str, max_results: int = 10) -> List[SearchResult]:
        """
        Search Bing for the given query with pagination support.
        
        Args:
            query: The search query
            max_results: Maximum number of results to return
            
        Returns:
            List of SearchResult objects
        """
        if self.use_serp_api:
            return await self._search_with_serpapi(query, max_results)
        else:
            return await self._search_with_playwright(query, max_results)

    async def _search_with_serpapi(self, query: str, max_results: int = 10) -> List[SearchResult]:
        """Search using SerpAPI method."""
        logger.info(f"Searching Bing via SerpApi for: {query} (max {max_results} results)")
        results: List[SearchResult] = []
        seen = set()
        
        async with httpx.AsyncClient(follow_redirects=True) as client:
            # SerpApi Bing can return max 50 per request, so we need pagination for larger requests
            start = 1
            max_start = 200  # SerpApi Bing limitation for start parameter
            
            while len(results) < max_results and start <= max_start:
                remaining = max_results - len(results)
                # Request up to 50 results per API call, but not more than remaining
                num_to_fetch = min(remaining, 50)
                
                logger.debug(f"Making Bing API request: start={start}, num={num_to_fetch}, remaining={remaining}")
                
                data = await self._serpapi_search(client, query, num_to_fetch, start)
                if not data:
                    logger.warning(f"No data returned from SerpApi Bing for start={start}")
                    break
                
                # SerpApi Bing returns 'organic_results'
                organic = data.get('organic_results', []) or []
                if not organic:
                    logger.info(f"No more organic results returned from SerpApi Bing (start={start})")
                    break
                
                logger.debug(f"Received {len(organic)} organic results from SerpApi Bing")
                
                for item in organic:
                    link = item.get('link') or item.get('url')
                    if not link or not isinstance(link, str):
                        continue
                        
                    if link in seen:
                        continue
                        
                    seen.add(link)
                    results.append(SearchResult(url=link, source='bing'))
                    
                    if len(results) >= max_results:
                        break
                
                # If we got fewer items than requested, we've reached the end of available results
                if len(organic) < num_to_fetch:
                    logger.info(f"Received fewer items ({len(organic)}) than requested ({num_to_fetch}), stopping pagination")
                    break
                
                # Move to next page - increment by the number of items we actually got
                start += len(organic)
                
                # Prevent infinite loops - if start would exceed API limits
                if start > max_start:
                    logger.info(f"Reached SerpApi Bing start limit ({max_start}), stopping pagination")
                    break
        
        logger.info(f"Found {len(results)} results from Bing (SerpApi) for: {query}")
        return results

    async def _search_with_playwright(self, query: str, max_results: int = 10) -> List[SearchResult]:
        """Search using Playwright method."""
        logger.info(f"Searching Bing via Playwright for: {query} (max {max_results} results)")
        results: List[SearchResult] = []
        seen = set()
        
        try:
            headers = {
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "accept-language": "en-US,en;q=0.9",
                "cache-control": "no-cache",
                "dnt": "1",
                "pragma": "no-cache",
                "sec-ch-ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
                "sec-fetch-dest": "document",
                "sec-fetch-mode": "navigate",
                "sec-fetch-site": "none",
                "sec-fetch-user": "?1",
                "upgrade-insecure-requests": "1"
            }
            
            page = 1
            results_per_page = 10
            
            while len(results) < max_results:
                # Create fresh browser instance for each page to avoid detection
                async with async_playwright() as p:
                    browser = await p.chromium.launch(
                        headless=True,
                        args=[
                            '--no-sandbox',
                            '--disable-blink-features=AutomationControlled',
                            '--disable-web-security',
                            '--disable-features=VizDisplayCompositor'
                        ]
                    )
                    
                    # Create new context with randomized properties
                    context = await browser.new_context(
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                        viewport={"width": 1366 + random.randint(-100, 100), "height": 768 + random.randint(-50, 50)},
                        ignore_https_errors=True,
                        extra_http_headers={
                            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                            "accept-language": "en-US,en;q=0.9",
                            "cache-control": "no-cache",
                            "sec-ch-ua": '"Google Chrome";v="122", "Chromium";v="122", "Not=A?Brand";v="24"',
                            "sec-ch-ua-mobile": "?0",
                            "sec-ch-ua-platform": '"Windows"',
                            "sec-fetch-dest": "document",
                            "sec-fetch-mode": "navigate",
                            "sec-fetch-site": "none",
                            "sec-fetch-user": "?1",
                            "upgrade-insecure-requests": "1"
                        }
                    )
                    
                    try:
                        page_obj = await context.new_page()
                        
                        # Remove automation indicators
                        await page_obj.add_init_script("""
                            Object.defineProperty(navigator, 'webdriver', {
                                get: () => undefined,
                            });
                            
                            window.chrome = {
                                runtime: {},
                            };
                            
                            Object.defineProperty(navigator, 'plugins', {
                                get: () => [1, 2, 3, 4, 5],
                            });
                            
                            Object.defineProperty(navigator, 'languages', {
                                get: () => ['en-US', 'en'],
                            });
                        """)
                        
                        remaining = max_results - len(results)
                        first = (page - 1) * results_per_page + 1
                        url = f"https://www.bing.com/search?q={query}&first={first}"
                        
                        print(f"Making Bing request: page={page}, first={first}, remaining={remaining}")
                        
                        # Navigate with random delay
                        await asyncio.sleep(random.uniform(2, 4))
                        await page_obj.goto(url, wait_until="domcontentloaded", timeout=60000)
                        
                        # Random mouse movement to simulate human behavior
                        await page_obj.mouse.move(random.randint(100, 500), random.randint(100, 400))
                        await asyncio.sleep(random.uniform(1, 2))
                        
                        try:
                            await page_obj.wait_for_selector("li.b_algo h2 a", timeout=10000)
                        except:
                            print(f"Timeout waiting for results on page {page}")
                            break
                        
                        elements = await page_obj.query_selector_all("li.b_algo h2 a")
                        
                        if not elements:
                            print(f"No more results found on page {page}")
                            break
                        
                        page_results = []
                        for element in elements:
                            try:
                                link = await element.get_attribute("href")
                                if link and isinstance(link, str):
                                    clean = link
                                    if clean not in seen:
                                        seen.add(clean)
                                        page_results.append(SearchResult(url=link, source='bing'))
                                        
                                        if len(results) + len(page_results) >= max_results:
                                            break
                            except Exception as e:
                                print(f"Error extracting link from element: {e}")
                                continue
                        
                        results.extend(page_results)
                        print(f"Found {len(page_results)} results on page {page}")
                        
                        # If we got fewer results than expected, we've reached the end
                        if len(page_results) < results_per_page:
                            print(f"Received fewer results ({len(page_results)}) than expected, stopping pagination")
                            break
                        
                        page += 1
                        
                    finally:
                        await browser.close()
                    
                    # Longer delay between pages to avoid detection
                    if len(results) < max_results:
                        await asyncio.sleep(random.uniform(8, 15))
        
        except Exception as e:
            logger.error(f"Error in Bing Playwright search: {type(e).__name__}: {str(e)}", exc_info=True)
            return []
        
        logger.info(f"Found {len(results)} results from Bing (Playwright) for: {query}")
        return results

    # No HTML parsing required when using SerpApi
