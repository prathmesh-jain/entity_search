from .google import GoogleSearchEngine
from .bing import BingSearchEngine
# from .yahoo import YahooSearchEngine
from .base import BaseSearchEngine, SearchResult
from typing import List, Dict, Type

class SearchEngineFactory:
    """Factory class to manage search engine instances."""
    
    _engines = {
        'google': GoogleSearchEngine,
        'bing': BingSearchEngine,
        # 'yahoo': YahooSearchEngine
    }
    
    @classmethod
    def get_engine(cls, engine_name: str) -> BaseSearchEngine:
        """
        Get a search engine instance by name.
        
        Args:
            engine_name: Name of the search engine ('google', 'bing', or 'yahoo')
            
        Returns:
            An instance of the requested search engine
            
        Raises:
            ValueError: If the engine name is not supported
        """
        engine_class = cls._engines.get(engine_name.lower())
        if not engine_class:
            raise ValueError(f"Unsupported search engine: {engine_name}")
        return engine_class()
    
    @classmethod
    def get_all_engines(cls) -> List[BaseSearchEngine]:
        """Get instances of all available search engines."""
        return [engine_class() for engine_class in cls._engines.values()]
    
    @classmethod
    def get_available_engines(cls) -> List[str]:
        """Get names of all available search engines."""
        return list(cls._engines.keys())

__all__ = ['SearchEngineFactory', 'BaseSearchEngine', 'SearchResult']
