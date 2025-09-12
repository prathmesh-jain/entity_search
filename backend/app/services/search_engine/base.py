from abc import ABC, abstractmethod
from typing import List
from dataclasses import dataclass

@dataclass
class SearchResult:
    url: str
    source: str

class BaseSearchEngine(ABC):
    """Base class for search engine implementations."""
    
    def __init__(self, name: str):
        self.name = name
    
    @abstractmethod
    async def search(self, query: str, max_results: int = 10) -> List[SearchResult]:
        """
        Search the engine with the given query.
        
        Args:
            query: The search query
            max_results: Maximum number of results to return
            
        Returns:
            List of SearchResult objects
        """
        pass
    
    @staticmethod
    def clean_url(url: str) -> str:
        """Clean and normalize URLs."""
        # Remove URL parameters, fragments, etc.
        return url.split('?')[0].split('#')[0].rstrip('/')
