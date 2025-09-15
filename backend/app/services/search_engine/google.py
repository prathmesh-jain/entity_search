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
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.request_delay:
            wait_time = self.request_delay - time_since_last + random.uniform(0.5, 1.5)
            await asyncio.sleep(wait_time)
        self.last_request_time = time.time()

    async def _google_api_search(self, client: httpx.AsyncClient, query: str, num: int, start: int = 1) -> Optional[Dict[str, Any]]:
        """Make request to Google Custom Search API with proper key rotation."""
        api_key = self.api_key_rotator.get_current_key()
        cx = os.getenv("GOOGLE_CX")
        
        if not api_key or not cx:
            logger.error("GOOGLE_API_KEY or GOOGLE_CX is not set in environment")
            return None
            
        params = {
            'key': api_key,
            'cx': cx,
            'q': query,
            'num': 10,  # Google API max 100 per request
            'start': start,
        }
        
        key_rotation_attempts = 0
        max_key_rotations = len(self.api_key_rotator.keys) * 2  # Try each key twice
        
        for attempt in range(self.max_retries + 1):
            try:
                await self._enforce_rate_limit()
                logger.info(f"Google Custom Search API (attempt {attempt+1}) for: {query} num={params['num']} start={start}")
                
                resp = await client.get(self.base_url, params=params, timeout=30.0)
                
                if resp.status_code == 200:
                    return resp.json()
                elif resp.status_code == 429:
                    # Rate limited - mark key as failed and rotate
                    self.api_key_rotator.mark_key_failed(api_key, f"Rate limit error 429")
                    
                    # Check if we have any available keys left
                    if not self.api_key_rotator.has_available_keys():
                        logger.error(f"All Google API keys exhausted after rate limit errors")
                        return None
                    
                    key_rotation_attempts += 1
                    if key_rotation_attempts >= max_key_rotations:
                        logger.error(f"Exhausted all Google API keys after {key_rotation_attempts} rotations")
                        return None
                    
                    retry_after = int(resp.headers.get('Retry-After', 0)) or int(20 + random.uniform(0, 10))
                    logger.warning(f"Google API rate limited. Rotating key and retrying in {retry_after}s (rotation {key_rotation_attempts})")
                    await asyncio.sleep(retry_after)
                    
                    # Get new key for next attempt
                    api_key = self.api_key_rotator.get_current_key()
                    if api_key:
                        params['key'] = api_key
                    continue
                elif resp.status_code in [401, 403]:
                    # Authentication/authorization errors - mark key as failed and rotate
                    self.api_key_rotator.mark_key_failed(api_key, f"Auth error {resp.status_code}")
                    
                    # Check if we have any available keys left
                    if not self.api_key_rotator.has_available_keys():
                        logger.error(f"All Google API keys exhausted after auth errors")
                        return None
                    
                    key_rotation_attempts += 1
                    if key_rotation_attempts >= max_key_rotations:
                        logger.error(f"Exhausted all Google API keys after {key_rotation_attempts} rotations")
                        return None
                    
                    logger.warning(f"Google API auth error {resp.status_code}. Rotating key (rotation {key_rotation_attempts})")
                    
                    # Get new key for next attempt
                    api_key = self.api_key_rotator.get_current_key()
                    if api_key:
                        params['key'] = api_key
                    await asyncio.sleep(2 ** attempt + random.random())
                else:
                    logger.warning(f"Google API returned status {resp.status_code}: {resp.text[:200]}")
                    await asyncio.sleep(2 ** attempt + random.random())
                    
            except (httpx.ConnectError, httpx.ReadTimeout) as e:
                logger.warning(f"Google API request error: {e}")
                await asyncio.sleep(2 ** attempt + random.uniform(0, 1))
                
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
                    logger.warning(f"No data returned from Google API for start={start}")
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
                
        logger.info(f"Found {len(results)} results from Google (Custom Search API) for: {query}")
        return results
