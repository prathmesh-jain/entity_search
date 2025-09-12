"""
Search engine factory for creating and managing search engine instances.
"""
from typing import Dict, Type
from .base import BaseSearchEngine
from .google import GoogleSearchEngine
from .bing import BingSearchEngine
# from .yahoo import YahooSearchEngine

class SearchEngineFactory:
    """Factory class for creating search engine instances."""
    
    # Map of search engine names to their corresponding classes
    _engines: Dict[str, Type[BaseSearchEngine]] = {
        'google': GoogleSearchEngine,
        'bing': BingSearchEngine,
        # 'yahoo': YahooSearchEngine,
    }
    
    @classmethod
    def create_engine(cls, engine_name: str, **kwargs) -> BaseSearchEngine:
        """
        Create a search engine instance.
        
        Args:
            engine_name: Name of the search engine ('google', 'bing', or 'yahoo')
            **kwargs: Additional arguments to pass to the search engine constructor
            
        Returns:
            An instance of the specified search engine
            
        Raises:
            ValueError: If the engine name is not supported
        """
        engine_class = cls._engines.get(engine_name.lower())
        if not engine_class:
            raise ValueError(f"Unsupported search engine: {engine_name}")
            
        return engine_class(**kwargs)
    
    @classmethod
    def get_available_engines(cls) -> list:
        """
        Get a list of available search engine names.
        
        Returns:
            List of available search engine names
        """
        return list(cls._engines.keys())
    
    @classmethod
    def create_all_engines(cls, **kwargs) -> Dict[str, BaseSearchEngine]:
        """
        Create instances of all available search engines.
        
        Args:
            **kwargs: Additional arguments to pass to the search engine constructors
            
        Returns:
            Dictionary mapping engine names to their instances
        """
        return {
            name: engine_class(**kwargs)
            for name, engine_class in cls._engines.items()
        }
