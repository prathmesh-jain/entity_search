import logging
import random
import asyncio
from typing import List, Optional, Dict, Any
import httpx
import os
import time

from .base import BaseSearchEngine, SearchResult
from ...utils.api_key_rotator import get_google_rotator

# Set up logging
logger = logging.getLogger(__name__)

class GoogleSearchEngine(BaseSearchEngine):
    """Google search engine implementation using Google Custom Search API."""
    
    def __init__(self, max_retries: int = 3, request_delay: float = 2.0):
        """
        Initialize the Google search engine.
        
        Args:
            max_retries: Maximum number of retry attempts for failed requests
            request_delay: Base delay between requests in seconds
        """
        super().__init__("google")
        self.base_url = "https://www.googleapis.com/customsearch/v1"
        self.max_retries = max_retries
        self.request_delay = request_delay
        self.last_request_time = 0
        self.api_key_rotator = get_google_rotator()
    
    async def _enforce_rate_limit(self):
        """Enforce rate limiting by waiting if needed."""
        logger.debug("_enforce_rate_limit: START")
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.request_delay:
            wait_time = min(2.0, self.request_delay - time_since_last + random.uniform(0.1, 0.5))  # Cap at 2 seconds
            logger.debug(f"_enforce_rate_limit: waiting {wait_time:.2f}s")
            await asyncio.wait_for(asyncio.sleep(wait_time), timeout=3.0)
        self.last_request_time = time.time()
        logger.debug("_enforce_rate_limit: END")

    async def _google_api_search(self, client: httpx.AsyncClient, query: str, num: int, start: int = 1) -> Optional[Dict[str, Any]]:
        """Make request to Google Custom Search API with proper key rotation."""
        cx = os.getenv("GOOGLE_CX")
        
        if not cx:
            logger.error("GOOGLE_CX is not set in environment")
            return None
        
        # Try all available API keys before giving up
        max_key_attempts = len(self.api_key_rotator.keys)
        
        for key_attempt in range(max_key_attempts):
            api_key = self.api_key_rotator.get_current_key()
            
            if not api_key:
                logger.error("No available Google API keys")
                return None
                
            params = {
                'key': api_key,
                'cx': cx,
                'q': query,
                'num': 10,
                'start': start,
            }
            
            try:
                logger.debug(f"Trying Google API key {key_attempt + 1}/{max_key_attempts}")
                await asyncio.wait_for(self._enforce_rate_limit(), timeout=5.0)
                
                resp = await client.get(self.base_url, params=params, timeout=10.0)
                logger.debug(f"API response received: {resp.status_code}")
                
                if resp.status_code == 200:
                    logger.debug("Success response, returning JSON")
                    return resp.json()
                elif resp.status_code == 429:
                    # Rate limited - mark key as failed and try next key
                    logger.debug("Rate limit detected, marking key as failed")
                    self.api_key_rotator.mark_key_failed(api_key, f"Rate limit error 429")
                    logger.warning(f"Google API rate limited on key {key_attempt + 1}, trying next key")
                    
                    # Check if we have more keys to try
                    if not self.api_key_rotator.has_available_keys():
                        logger.error("All Google API keys are rate limited")
                        return None
                    continue
                    
                elif resp.status_code in [401, 403]:
                    # Auth errors - mark key as failed and try next key
                    logger.debug(f"Auth error {resp.status_code}, marking key as failed")
                    self.api_key_rotator.mark_key_failed(api_key, f"Auth error {resp.status_code}")
                    logger.warning(f"Google API auth error {resp.status_code} on key {key_attempt + 1}, trying next key")
                    
                    # Check if we have more keys to try
                    if not self.api_key_rotator.has_available_keys():
                        logger.error("All Google API keys have auth errors")
                        return None
                    continue
                    
                else:
                    logger.warning(f"Google API returned status {resp.status_code}: {resp.text[:200]}")
                    return None
                    
            except asyncio.TimeoutError:
                logger.error("Timeout in Google API search - trying next key")
                self.api_key_rotator.mark_key_failed(api_key, "Timeout error")
                if not self.api_key_rotator.has_available_keys():
                    return None
                continue
            except (httpx.ConnectError, httpx.ReadTimeout) as e:
                logger.warning(f"Google API request error: {e} - trying next key")
                self.api_key_rotator.mark_key_failed(api_key, f"Connection error: {e}")
                if not self.api_key_rotator.has_available_keys():
                    return None
                continue
            except Exception as e:
                logger.error(f"Unexpected Google API error: {e}")
                return None
        
        logger.error(f"All {max_key_attempts} Google API keys exhausted")
        return None

    async def search(self, query: str, max_results: int = 10) -> List[SearchResult]:
        """
        Search Google for the given query using Custom Search API with pagination.
        
        Args:
            query: The search query
            max_results: Maximum number of results to return
            
        Returns:
            List of SearchResult objects
        """
        logger.info(f"Searching Google via Custom Search API for: {query} (max {max_results} results)")
        
        results: List[SearchResult] = []
        seen = set()
        
        async with httpx.AsyncClient(follow_redirects=True) as client:
            # Google API can return max 100 per request, but we need pagination for larger requests
            start = 1
            max_start = 91  # Google API limitation: start parameter can't exceed 91
            
            while len(results) < max_results and start <= max_start:
                remaining = max_results - len(results)
                # Request up to 100 results per API call, but not more than remaining
                num_to_fetch = min(remaining, 100)
                
                logger.debug(f"Making API request: start={start}, num={num_to_fetch}, remaining={remaining}")
                
                data = await self._google_api_search(client, query, num_to_fetch, start)
                if not data:
                    logger.warning(f"No data returned from Google API for start={start} - API keys may be exhausted")
                    break
                    
                items = data.get('items', []) or []
                if not items:
                    logger.info(f"No more items returned from Google API (start={start})")
                    break
                
                logger.debug(f"Received {len(items)} items from Google API")
                    
                for item in items:
                    link = item.get('link')
                    if not link or not isinstance(link, str):
                        continue
                        
                    if link in seen:
                        continue
                        
                    seen.add(link)
                    results.append(SearchResult(url=link, source='google'))
                    
                    if len(results) >= max_results:
                        break
                        
                # If we got fewer items than requested, we've reached the end of available results
                # if len(items) < num_to_fetch:
                #     logger.info(f"Received fewer items ({len(items)}) than requested ({num_to_fetch}), stopping pagination")
                #     break
                    
                # Move to next page - increment by the number of items we actually got
                start += len(items)
                
                # Prevent infinite loops - if start would exceed API limits
                if start > max_start:
                    logger.info(f"Reached Google API start limit ({max_start}), stopping pagination")
                    break
                
        if results:
            logger.info(f"Found {len(results)} results from Google (Custom Search API) for: {query}")
        else:
            logger.warning(f"Google search returned no results for: {query} - API keys may be exhausted")
        return results
