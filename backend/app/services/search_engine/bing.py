import logging
import random
import asyncio
from typing import List, Optional, Dict, Any
import httpx
import os
import time

from .base import BaseSearchEngine, SearchResult

# Set up logging
logger = logging.getLogger(__name__)

class BingSearchEngine(BaseSearchEngine):
    """Bing search engine implementation using SerpApi."""
    
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
                        
                    clean = self.clean_url(link)
                    if not clean or clean in seen:
                        continue
                        
                    seen.add(clean)
                    results.append(SearchResult(url=clean, source='bing'))
                    
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

    # No HTML parsing required when using SerpApi
