import logging
import time
import random
import asyncio
from typing import List
from .base import BaseSearchEngine, SearchResult

logger = logging.getLogger(__name__)

class YahooSearchEngine(BaseSearchEngine):
    """Yahoo search engine implementation - currently disabled due to API limitations."""
    
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
    
    async def search(self, query: str, max_results: int = 10) -> List[SearchResult]:
        """
        Search Yahoo - currently returns empty results due to API limitations.
        
        Args:
            query: The search query
            max_results: Maximum number of results to return
            
        Returns:
            Empty list (Yahoo search currently disabled)
        """
        logger.warning("Yahoo search is currently disabled due to API limitations")
        return []
