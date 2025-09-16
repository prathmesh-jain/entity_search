import asyncio
import httpx
import os
from app.services.search_engine.google import GoogleSearchEngine

async def test_google_hang():
    """Test Google search to identify hanging point."""
    print("Starting Google search test...")
    
    try:
        # Create Google search engine with short timeouts
        google = GoogleSearchEngine(max_retries=1, request_delay=0.1)
        
        # Test with a query that will likely hit rate limits
        query = "Ashley Smith Daughter of Mark Smith(Commisioner of County Commision of Sarasota, Florida)"
        
        print(f"Testing query: {query}")
        
        # Add timeout to the entire search operation
        results = await asyncio.wait_for(
            google.search(query, max_results=5),
            timeout=30.0  # 30 second timeout
        )
        
        print(f"Results: {len(results)} items")
        
    except asyncio.TimeoutError:
        print("TIMEOUT: Google search hung for more than 30 seconds")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_google_hang())
