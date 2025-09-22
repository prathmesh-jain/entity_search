import asyncio
import logging
import os
from typing import List, Dict, Any, Optional, Callable
from collections import defaultdict
from difflib import SequenceMatcher
import aiohttp

from .search_engine.factory import SearchEngineFactory
from .crawler.base import BaseCrawler, CrawledPage
from .llm.gemini_client import GeminiClient
import json
from urllib.parse import urlparse

class EntityResearchService:
    """Service for researching entities using multiple search engines and LLM analysis."""
    
    def __init__(self, max_search_results: int = 10, max_concurrent_requests: int = 8):
        """
        Initialize the research service.
        
        Args:
            max_search_results: Maximum number of search results to process per engine
            max_concurrent_requests: Maximum number of concurrent HTTP requests
        """
        self.max_search_results = max_search_results
        self.max_concurrent_requests = max_concurrent_requests
        # Create all search engine instances with configuration
        self.search_engines = SearchEngineFactory.create_all_engines(
            max_retries=2,
            request_delay=0.5
        )
        self.crawler = BaseCrawler(max_concurrent=max_concurrent_requests, request_delay=0.1)
        self.llm_client = GeminiClient()
        self.logger = logging.getLogger(__name__)
    
    async def research_entity(self, entity_name: str, entity_type: str, search_queries: Optional[List[str]] = None, keywords: Optional[List[str]] = None, progress_callback: Optional[Any] = None) -> Dict[str, Any]:
        """
        Research an entity by searching the web and analyzing the results.
        
        Args:
            entity_name: Name of the entity to research
            entity_type: Type of entity ('individual' or 'company')
            search_queries: Optional list of search queries to use. If not provided,
                          will generate queries based on the entity name.
            keywords: Optional list of keywords to refine the search
            progress_callback: Optional callback function for progress updates
                          
        Returns:
            Dictionary containing research results
        """
        self.logger.info(f"Starting research for entity: {entity_name}")
        try:
            # Generate search queries if not provided
            if not search_queries:
                search_queries = await self._generate_search_queries(entity_name, entity_type, keywords=keywords)
            
            self.logger.info(f"Generated search queries: {search_queries}")
            
            # Step 1: Search across all engines
            self.logger.info("Starting search across all engines...")
            search_results = await self._search_all_engines(entity_name, search_queries)
            self.logger.info(f"Found {len(search_results)} total search results")
            if progress_callback:
                progress_callback(phase="searching", payload={
                    "message": "Search completed",
                    "search_results_count": len(search_results),
                    "queries": search_queries
                })
            
            if not search_results:
                self.logger.warning("No search results found for the given queries")
                return self._create_empty_result(entity_name, "No search results found")
            
            # Step 2: Crawl and analyze in parallel - start LLM analysis immediately after each page is crawled
            self.logger.info("Starting parallel crawling and LLM analysis...")
            urls = [r["url"] for r in search_results]
            total_urls = len(urls)
            
            # Shared data structures for collecting results
            profiles: List[Dict[str, Any]] = []
            clusters: Dict[str, List[Dict[str, Any]]] = {"query_name": [], "uncertain": []}
            per_field_sources: Dict[str, set] = {}
            sources_meta: List[Dict[str, Any]] = []
            source_url_to_id: Dict[str, int] = {}
            
            # Progress tracking for parallel processing
            completed_count = 0
            completed_lock = asyncio.Lock()
            
            # Streaming consolidation setup
            consolidation_chunk_size = 10
            consolidated_entities = []
            consolidation_tasks = []
            consolidation_lock = asyncio.Lock()
            
            # Create tasks for parallel crawling and LLM processing
            async def process_single_url(url: str, url_index: int) -> None:
                """Crawl a single URL and immediately process with LLM."""
                try:
                    # Crawl the page
                    page = await self.crawler._crawl_single(url)
                    
                    # Assign source ID based on URL index for consistent ordering
                    source_id = url_index + 1
                    source_url_to_id[page.url] = source_id
                    
                    # Record source meta with ID
                    source_meta = {
                        "source_id": source_id,
                        "url": page.url,
                        "title": page.title,
                        "status_code": page.status_code,
                        "success": page.status_code == 200 and not page.error
                    }
                    sources_meta.append(source_meta)
                    
                    # Update progress counter and notify frontend
                    async with completed_lock:
                        nonlocal completed_count
                        completed_count += 1
                        print(f"Crawled and analyzing ({completed_count}/{total_urls}): {page.title}")
                        
                        if progress_callback:
                            progress_callback(phase="crawling", payload={
                                "message": f"Processing page {completed_count} of {total_urls}",
                                "pages_crawled": completed_count,
                                "pages_total": total_urls,
                                "current_page": page.title
                            })
                    
                    if page.status_code == 200 and not page.error and page.content:
                        try:
                            # Process with LLM immediately after crawling
                            content_len = len(page.content or "")
                            self.logger.info(f"LLM extract start | url={page.url} | content_len={content_len}")
                            
                            llm_result = await asyncio.wait_for(
                                self.llm_client.extract_entity_info(
                                    content=page.content,
                                    entity_name=entity_name,
                                    entity_type=entity_type,
                                    keywords=keywords
                                ),
                                timeout=60  # Reduced from 100s to 30s
                            )
                            
                            self.logger.info(
                                f"LLM extract done | url={page.url} | keys={list((llm_result or {}).keys())}"
                            )
                            
                            profile = {
                                **llm_result,
                                "source_url": page.url,
                                "source_title": page.title,
                                "status_code": page.status_code
                            }
                            profiles.append(profile)
                            
                            # Update progress with LLM completion
                            if progress_callback:
                                progress_callback(phase="analyzing", payload={
                                    "message": f"Analyzed page {completed_count} of {total_urls}",
                                    "pages_analyzed": len(profiles),
                                    "pages_total": total_urls,
                                    "current_page": page.title
                                })
                            
                            # Bucketize
                            detected = (llm_result.get("detected_entity_name") or "").strip()
                            same_as = bool(llm_result.get("same_as_input"))
                            if same_as:
                                clusters.setdefault("query_name", []).append(profile)
                            elif detected:
                                clusters.setdefault(detected, []).append(profile)
                            else:
                                clusters.setdefault("uncertain", []).append(profile)
                                
                            # Per-field sources attribution with source IDs
                            for field, value in (llm_result.get("extracted_info") or {}).items():
                                if value is not None and value != "":
                                    per_field_sources.setdefault(field, set()).add(source_id)
                            
                            # Check if we have enough profiles for streaming consolidation
                            async with consolidation_lock:
                                if len(profiles) >= consolidation_chunk_size and len(profiles) % consolidation_chunk_size == 0:
                                    # Start consolidation for this chunk
                                    chunk_profiles = profiles[-consolidation_chunk_size:].copy()
                                    consolidation_task = asyncio.create_task(
                                        self._consolidate_chunk_async(entity_name, entity_type, chunk_profiles, len(consolidation_tasks))
                                    )
                                    consolidation_tasks.append(consolidation_task)
                                    self.logger.info(f"Started consolidation task {len(consolidation_tasks)} for profiles {len(profiles)-consolidation_chunk_size+1}-{len(profiles)}")
                                    
                        except asyncio.TimeoutError:
                            self.logger.warning(f"LLM extraction timed out for {page.url}")
                        except Exception as e:
                            self.logger.error(f"Error in LLM processing for {page.url}: {str(e)}", exc_info=True)
                    
                except Exception as e:
                    self.logger.error(f"Error processing URL {url}: {str(e)}", exc_info=True)
            
            # Create all tasks and run them in parallel
            tasks = [
                asyncio.create_task(process_single_url(url, i)) 
                for i, url in enumerate(urls)
            ]
            
            # Wait for all crawling and LLM processing to complete
            await asyncio.gather(*tasks, return_exceptions=True)
            
            # Handle remaining profiles that didn't reach chunk size
            async with consolidation_lock:
                remaining_profiles = len(profiles) % consolidation_chunk_size
                if remaining_profiles > 0:
                    chunk_profiles = profiles[-remaining_profiles:].copy()
                    consolidation_task = asyncio.create_task(
                        self._consolidate_chunk_async(entity_name, entity_type, chunk_profiles, len(consolidation_tasks))
                    )
                    consolidation_tasks.append(consolidation_task)
                    self.logger.info(f"Started final consolidation task for remaining {remaining_profiles} profiles")
            
            # Wait for all consolidation tasks to complete
            if consolidation_tasks:
                self.logger.info(f"Waiting for {len(consolidation_tasks)} consolidation tasks to complete...")
                consolidation_results = await asyncio.gather(*consolidation_tasks, return_exceptions=True)
                
                # Collect all consolidated entities
                for i, result in enumerate(consolidation_results):
                    if isinstance(result, dict) and result.get("entities"):
                        consolidated_entities.extend(result["entities"])
                        self.logger.info(f"Consolidation task {i+1} completed with {len(result['entities'])} entities")
                    elif isinstance(result, Exception):
                        self.logger.error(f"Consolidation task {i+1} failed: {result}")
            
            self.logger.info(f"Parallel processing completed. Processed {len(urls)} URLs with {len(profiles)} successful extractions")
            if not profiles:
                return self._create_empty_result(entity_name, "No valid pages processed by LLM")

            # Step 3: Final combine/segregate
            if progress_callback:
                progress_callback(phase="combining", payload={
                    "message": "Consolidating profiles into final entities",
                    "profiles_count": len(profiles)
                })

            # If we have streaming consolidated entities, do final consolidation on them
            if consolidated_entities:
                self.logger.info(f"Starting final consolidation of {len(consolidated_entities)} streaming results")
                
                # Convert consolidated entities back to profile format for final pass
                final_profiles = []
                for idx, entity in enumerate(consolidated_entities):
                    final_profiles.append({
                        "detected_entity_name": entity.get("canonical_name"),
                        "same_as_input": entity.get("same_as_query", False),
                        "confidence": 0.8,  # High confidence for already consolidated entities
                        "extracted_info": entity.get("combined_fields", {}),
                        "source_url": f"consolidated_chunk_{idx}"
                    })
                
                try:
                    final_entities = await self.llm_client.consolidate_clusters(entity_name, entity_type, final_profiles)
                    self.logger.info("Streaming consolidation with final pass completed")
                except Exception as e:
                    self.logger.warning(f"Final consolidation failed: {e}, using streaming results as-is")
                    final_entities = {"entities": consolidated_entities}
            else:
                # Fallback to traditional consolidation
                use_llm_combine = os.getenv("USE_LLM_CONSOLIDATE", "0") in ("1", "true", "True")
                self.logger.info(f"Starting traditional consolidation | mode={'LLM' if use_llm_combine else 'LOCAL'} | profiles={len(profiles)}")

                if not use_llm_combine:
                    final_entities = {"entities": self._local_consolidate(entity_name, profiles, source_url_to_id)}
                    self.logger.info("Local consolidation completed")
                    if progress_callback:
                        progress_callback(phase="combining", payload={
                            "message": "Consolidation completed (local)",
                            "profiles_count": len(profiles)
                        })
                else:
                    try:
                        if len(profiles) > 20:
                            # Use chunking strategy for large profile sets
                            final_entities = await self._chunked_consolidation(entity_name, entity_type, profiles, source_url_to_id)
                        else:
                            # Direct consolidation for smaller sets
                            final_entities = await self.llm_client.consolidate_clusters(entity_name, entity_type, profiles)
                        
                        self.logger.info("Final consolidation completed (LLM)")
                        if not final_entities or not final_entities.get("entities"):
                            self.logger.info("LLM consolidation returned empty; using local consolidation fallback")
                            final_entities = {"entities": self._local_consolidate(entity_name, profiles, source_url_to_id)}
                    except Exception as e:
                        self.logger.error(f"LLM consolidation failed: {e}")
                        self.logger.info("Using local consolidation fallback due to LLM error")
                        final_entities = {"entities": self._local_consolidate(entity_name, profiles, source_url_to_id)}
            
            # Prepare the final result
            # Include final entities produced by combine pass
            # Filter out null/empty values from clusters before sending to frontend
            filtered_clusters = {}
            for cluster_name, cluster_profiles in clusters.items():
                filtered_profiles = []
                for profile in cluster_profiles:
                    # Filter extracted_info to remove null/empty values
                    if 'extracted_info' in profile:
                        filtered_info = {
                            k: v for k, v in profile['extracted_info'].items() 
                            if v is not None and v != "" and v != [] and v != {}
                        }
                        if filtered_info:  # Only include profile if it has meaningful data
                            filtered_profile = profile.copy()
                            filtered_profile['extracted_info'] = filtered_info
                            filtered_profiles.append(filtered_profile)
                    elif any(v for k, v in profile.items() if k != 'extracted_info' and v is not None and v != ""):
                        # Include profile if it has other meaningful data
                        filtered_profiles.append(profile)
                
                if filtered_profiles:  # Only include cluster if it has profiles with data
                    filtered_clusters[cluster_name] = filtered_profiles
            
            # Filter profiles to remove null/empty values
            filtered_profiles = []
            for profile in profiles:
                if 'extracted_info' in profile:
                    filtered_info = {
                        k: v for k, v in profile['extracted_info'].items() 
                        if v is not None and v != "" and v != [] and v != {}
                    }
                    if filtered_info:  # Only include profile if it has meaningful data
                        filtered_profile = profile.copy()
                        filtered_profile['extracted_info'] = filtered_info
                        filtered_profiles.append(filtered_profile)
                elif any(v for k, v in profile.items() if k != 'extracted_info' and v is not None and v != ""):
                    # Include profile if it has other meaningful data
                    filtered_profiles.append(profile)

            result = {
                'entity_name': entity_name,
                'search_queries': search_queries,
                'search_results_count': len(search_results),
                'crawled_pages_count': pages_crawled,
                'clusters': filtered_clusters,
                'profiles': filtered_profiles,
                'final_entities': final_entities,
                'per_field_sources': {k: sorted(list(v)) for k, v in per_field_sources.items()},
                'sources': sources_meta
            }
            
            self.logger.info(f"Research completed for {entity_name}")
            return result
            
        except Exception as e:
            self.logger.error(f"Error researching entity {entity_name}: {str(e)}", exc_info=True)
            return {
                'entity_name': entity_name,
                'error': str(e),
                'search_results_count': 0,
                'crawled_pages_count': 0,
                'entity_info': {}
            }
    
    def _create_empty_result(self, entity_name: str, error_message: str) -> Dict[str, Any]:
        """Create a result dictionary for error cases."""
        return {
            'entity_name': entity_name,
            'error': error_message,
            'search_results_count': 0,
            'crawled_pages_count': 0,
            'entity_info': {},
            'sources': []
        }

    async def _generate_search_queries(self, entity_name: str, entity_type: str, keywords: Optional[List[str]] = None) -> List[str]:
        """Generate search queries for the given entity name and optional keywords.
        
        Args:
            entity_name: Name of the entity to research
            entity_type: Type of entity ('individual' or 'company')
            keywords: Optional list of keywords to include in the search queries
            
        Returns:
            List of search query strings
        """
        # Check if LLM query generation is enabled
        use_llm_generation = os.getenv("LLM_QUERY_GENERATION", "false").lower() == "true"
        print("use_llm_generation", use_llm_generation)
        
        if use_llm_generation:
            try:
                self.logger.info("Using LLM-based query generation")
                llm_queries = await self.llm_client.generate_search_queries(
                    entity_name=entity_name,
                    entity_type=entity_type,
                    keywords=keywords,
                    num_queries=4
                )
                if llm_queries:
                    return llm_queries
                else:
                    self.logger.warning("LLM query generation returned empty, falling back to traditional method")
            except Exception as e:
                self.logger.error(f"LLM query generation failed: {e}, falling back to traditional method")
        
        # Traditional query generation (fallback or when LLM is disabled)
        self.logger.info("Using traditional query generation")
        return self._generate_traditional_queries(entity_name, entity_type, keywords)
    
    def _generate_traditional_queries(self, entity_name: str, entity_type: str, keywords: Optional[List[str]] = None) -> List[str]:
        """Generate traditional search queries without LLM."""
        base_queries = []
        
        # Add keyword-enhanced queries if keywords are provided
        if keywords and isinstance(keywords, list):
            keyword_queries = []
            for keyword in keywords:
                if keyword and isinstance(keyword, str) and keyword.strip():
                    keyword = keyword.strip()
                    keyword_queries.extend([
                        f"{entity_name} {keyword}",
                    ])
            base_queries.extend(keyword_queries)
        
        # Add entity-type specific queries
        # if entity_type == "individual":
        #     base_queries.extend([
        #         f'"{entity_name}" biography',
        #         f'"{entity_name}" profile background',
        #         f'"{entity_name}" news recent'
        #     ])
        # else:  # company
        #     base_queries.extend([
        #         f'"{entity_name}" company information',
        #         f'"{entity_name}" business registration',
        #         f'"{entity_name}" executives leadership'
        #     ])
        
        # Ensure we have at least the entity name as a query
        if not base_queries:
            base_queries = [entity_name]
            
        return base_queries[:4]  # Limit to 4 queries
    
    async def _search_all_engines(self, entity_name: str, queries: List[str]) -> List[Dict]:
        """
        Search all available search engines in parallel with the given queries.
        
        Args:
            entity_name: Name of the entity being searched for (for logging)
            queries: List of search queries to execute
            
        Returns:
            List of deduplicated search results from all engines
        """
        all_results = []
        seen_urls = set()
        
        # Log the start of the search
        engine_names = list(self.search_engines.keys())
        self.logger.info(f"Starting parallel search across {len(engine_names)} engines: {', '.join(engine_names)}")
        self.logger.info(f"Using search queries: {queries}")
        
        # Create tasks for all queries across all engines
        search_tasks = []
        for engine_name, engine in self.search_engines.items():
            for query in queries:
                task = asyncio.create_task(
                    self._search_engine(engine, query),
                    name=f"{engine_name}_search"
                )
                search_tasks.append(task)
        
        # Process results as they complete
        completed = 0
        total_tasks = len(search_tasks)
        
        # Use asyncio.as_completed to process results as they come in
        for task in asyncio.as_completed(search_tasks):
            try:
                engine_results = await task
                completed += 1
                
                # Log progress
                task_name = str(task)
                result_count = len(engine_results) if not isinstance(engine_results, Exception) else 0
                self.logger.info(f"[{completed}/{total_tasks}] {task_name} completed with {result_count} results")
                
                # Skip if there was an error
                if isinstance(engine_results, Exception):
                    self.logger.warning(f"Search error in {task_name}: {str(engine_results)}")
                    continue
                
                # Process successful results
                new_results = 0
                for result in engine_results:
                    # Handle both dict and SearchResult objects
                    url = result.get('url') if isinstance(result, dict) else getattr(result, 'url', '')
                    source = result.get('source') if isinstance(result, dict) else getattr(result, 'source', '')
                    
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_results.append({
                            'url': url,
                            'source': source
                        })
                        new_results += 1
                        
                        # Limit total results per engine to distribute results fairly
                        if len([r for r in all_results if r.get('source') == source]) >= self.max_search_results:
                            break
                
                self.logger.debug(f"Added {new_results} new results from {task_name}")
                
                # Early exit if we have enough results
                if len(all_results) >= self.max_search_results * len(self.search_engines):
                    # Cancel remaining tasks
                    for t in search_tasks:
                        if not t.done():
                            t.cancel()
                    break
                    
            except Exception as e:
                completed += 1
                self.logger.error(f"Unexpected error processing search task: {str(e)}", exc_info=True)
        
        self.logger.info(f"Search completed. Found {len(all_results)} unique results from {completed} search tasks")
        self.logger.info(f"All search results: {all_results}")
        return all_results
    
    def _is_crawlable_url(self, url: str) -> bool:
        """
        Check if a URL is crawlable by filtering out non-crawlable sites.
        
        Args:
            url: The URL to check
            
        Returns:
            True if the URL is crawlable, False otherwise
        """
        if not url:
            return False
            
        url_lower = url.lower()
        
        # Filter out non-crawlable domains and file types
        blocked_patterns = [
            # Social media platforms
            'facebook.com', 'fb.com', 'instagram.com', 'twitter.com', 'x.com',
            'linkedin.com', 'tiktok.com', 'snapchat.com', 'pinterest.com',
            'youtube.com', 'youtu.be', 'reddit.com', 'discord.com',
            
            # Editable/Wiki sites
            'wikipedia.org', 'wikimedia.org', 'wikidata.org', 'fandom.com',
            'wikia.com', 'wiki.', '/wiki/', 'mediawiki.org',
            
            # File types that can't be crawled effectively
            '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
            '.zip', '.rar', '.tar', '.gz', '.mp3', '.mp4', '.avi', '.mov',
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg',
            
            # Other non-crawlable or problematic sites
            'google.com/search', 'bing.com/search', 'yahoo.com/search',
            'amazon.com', 'amazon.com/gp/', 'ebay.com/itm/','amazon',
            'paywall', 'subscription', 'login', 'signin', 'register','/question'
        ]
        
        # Check if URL contains any blocked patterns
        for pattern in blocked_patterns:
            if pattern in url_lower:
                self.logger.debug(f"Filtered out non-crawlable URL: {url} due to pattern: {pattern}")
                return False
                
        return True

    async def _search_engine(self, engine, query: str) -> List[Dict]:
        """
        Execute a search on a single search engine.
        
        Args:
            engine: The search engine instance to use
            query: The search query string
            
        Returns:
            List of search results or empty list on error
        """
        start_time = asyncio.get_event_loop().time()
        engine_name = engine.name
        
        try:
            self.logger.debug(f"Starting search on {engine_name} with query: {query}")
            
            # Execute the search with timeout
            results = await asyncio.wait_for(
                engine.search(query, max_results=self.max_search_results),
                timeout=60.0  # 60 second timeout per search engine
            )
            
            # Filter out non-crawlable URLs
            filtered_results = []
            for result in results:
                # Handle SearchResult object - access url attribute directly
                url = result.url if hasattr(result, 'url') else result.get('url', '') if isinstance(result, dict) else ''
                if self._is_crawlable_url(url):
                    # Convert SearchResult to dict format for consistency
                    if hasattr(result, 'url'):
                        result_dict = {
                            'url': result.url,
                            'source': getattr(result, 'source', ''),
                            'title': getattr(result, 'title', ''),
                            'snippet': getattr(result, 'snippet', '')
                        }
                        filtered_results.append(result_dict)
                    else:
                        filtered_results.append(result)
                else:
                    self.logger.debug(f"Filtered out non-crawlable URL: {url}")
            
            # Log success metrics
            duration = asyncio.get_event_loop().time() - start_time
            self.logger.info(
                f"{engine_name} search completed in {duration:.2f}s. "
                f"Found {len(results)} results, {len(filtered_results)} crawlable for query: {query[:50]}{'...' if len(query) > 50 else ''}"
            )
            
            return filtered_results
            
        except asyncio.CancelledError:
            # Task was cancelled, just propagate the cancellation
            self.logger.debug(f"Search task for {engine_name} was cancelled")
            raise
            
        except Exception as e:
            # Log detailed error information
            duration = asyncio.get_event_loop().time() - start_time
            
            # Get more detailed error information
            error_type = type(e).__name__
            error_str = str(e) if str(e) else "No error message"
            error_repr = repr(e)
            
            error_msg = (
                f"Error searching {engine_name} after {duration:.2f}s. "
                f"Query: '{query}'. Error Type: {error_type}. "
                f"Error: {error_str}. Full Error: {error_repr[:300]}"
            )
            self.logger.error(error_msg, exc_info=True)  # Always include stack trace for debugging
            return []
    
    async def _crawl_search_results(self, search_results: List[Dict]) -> List[CrawledPage]:
        """Crawl the URLs from search results."""
        if not search_results:
            return []
            
        # Extract unique URLs
        urls = [result['url'] for result in search_results]
        
        # Crawl the pages
        return await self.crawler.crawl(urls)
    
    async def _process_with_llm(self, entity_name: str, crawled_pages: List[CrawledPage]) -> Dict[str, Any]:
        """Process crawled pages with the LLM to extract entity information."""
        if not crawled_pages:
            return {}
        
        # Filter out error pages
        valid_pages = [page for page in crawled_pages if page.status_code == 200 and not page.error]
        
        if not valid_pages:
            return {}
        
        # Convert to search result format expected by the LLM client
        search_results = [
            {
                'title': page.title,
                'url': page.url,
                'snippet': page.content[:500]  # Use first 500 chars as snippet
            }
            for page in valid_pages
        ]
        
        # Process with LLM
        return await self.llm_client.process_search_results(entity_name, search_results)

    def _local_consolidate(self, entity_name: str, profiles: List[Dict[str, Any]], source_url_to_id: Dict[str, int]) -> List[Dict[str, Any]]:
        """Deterministic, fast consolidation when LLM combine is disabled/unavailable.

        Strategy:
        - Group profiles by:
          1) same_as_input=True => group key '__query__'
          2) else by normalized detected_entity_name
          3) fall back to '__uncertain__'
        - Merge fields: prefer non-empty values; lists are unioned; scalars keep first non-empty.
        """
        def norm_name(n: Optional[str]) -> str:
            return (n or '').strip().lower()

        groups: Dict[str, Dict[str, Any]] = {}
        index_map: Dict[str, List[int]] = {}

        for idx, p in enumerate(profiles):
            key = '__uncertain__'
            if p.get('same_as_input'):
                key = '__query__'
            else:
                dn = norm_name(p.get('detected_entity_name'))
                if dn:
                    key = dn

            groups.setdefault(key, {"combined_fields": {}, "same_as_query": key == '__query__', "canonical_name": None})
            index_map.setdefault(key, []).append(idx)

            # canonical name
            if not groups[key]["canonical_name"] and p.get("detected_entity_name"):
                groups[key]["canonical_name"] = p.get("detected_entity_name")

            fields = (p.get('extracted_info') or {})
            for f, v in fields.items():
                if v in (None, ""):
                    continue
                existing = groups[key]["combined_fields"].get(f)
                if existing is None:
                    groups[key]["combined_fields"][f] = v
                else:
                    # Merge: lists => union; scalars => coerce to list and union
                    if isinstance(existing, list) or isinstance(v, list):
                        a = existing if isinstance(existing, list) else [existing]
                        b = v if isinstance(v, list) else [v]
                        merged = []
                        seen = set()
                        for it in a + b:
                            try:
                                marker = json.dumps(it, sort_keys=True) if isinstance(it, (dict, list)) else str(it)
                            except Exception:
                                marker = str(it)
                            if marker not in seen:
                                merged.append(it)
                                seen.add(marker)
                        groups[key]["combined_fields"][f] = merged

        entities: List[Dict[str, Any]] = []
        for k, data in groups.items():
            # Filter out entities with no meaningful data
            combined_fields = data["combined_fields"]
            if not combined_fields or len(combined_fields) == 0:
                continue
                
            # Build field-specific sources mapping with source IDs
            field_sources = {}
            member_indexes = index_map.get(k, [])
            
            for field_name, field_value in combined_fields.items():
                if field_value is not None and field_value != "":
                    # Find source IDs for this specific field from member profiles
                    field_source_ids = set()
                    for idx in member_indexes:
                        if idx < len(profiles):
                            profile = profiles[idx]
                            extracted_info = profile.get("extracted_info", {})
                            if field_name in extracted_info and extracted_info[field_name] == field_value:
                                source_url = profile.get("source_url")
                                if source_url and source_url in source_url_to_id:
                                    field_source_ids.add(source_url_to_id[source_url])
                    
                    field_sources[field_name] = sorted(list(field_source_ids))
            
            entities.append({
                "canonical_name": data["canonical_name"] or (entity_name if k == '__query__' else None),
                "same_as_query": data["same_as_query"],
                "combined_fields": combined_fields,
                "field_sources": field_sources,  # Sources tied to specific fields
                "member_profile_indexes": member_indexes,
                "sources": [profiles[i].get("source_url", "") for i in member_indexes if i < len(profiles) and profiles[i].get("source_url")]
            })

        # Sort entities by fuzzy matching similarity to query name
        entities = self._sort_entities_by_similarity(entity_name, entities)
        return entities

    def _sort_entities_by_similarity(self, query_name: str, entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Sort entities by name similarity to query using fuzzy matching."""
        def similarity_score(entity):
            name = entity.get("canonical_name", "")
            if not name:
                return 0.0
            return SequenceMatcher(None, query_name.lower(), name.lower()).ratio()
        
        return sorted(entities, key=similarity_score, reverse=True)

    async def _consolidate_chunk_async(self, entity_name: str, entity_type: str, chunk_profiles: List[Dict[str, Any]], chunk_id: int) -> Dict[str, Any]:
        """Consolidate a single chunk of profiles asynchronously."""
        try:
            self.logger.info(f"Starting consolidation for chunk {chunk_id} with {len(chunk_profiles)} profiles")
            result = await self.llm_client.consolidate_clusters(entity_name, entity_type, chunk_profiles)
            self.logger.info(f"Chunk {chunk_id} consolidation completed")
            return result
        except Exception as e:
            self.logger.warning(f"Chunk {chunk_id} consolidation failed: {e}, using local fallback")
            # Fallback to local consolidation for this chunk
            local_entities = self._local_consolidate(entity_name, chunk_profiles, {})
            return {"entities": local_entities}

    async def _chunked_consolidation(self, entity_name: str, entity_type: str, profiles: List[Dict[str, Any]], source_url_to_id: Dict[str, int]) -> Dict[str, Any]:
        """Consolidate large profile sets using chunking strategy."""
        chunk_size = 15  # Process 15 profiles at a time
        chunks = [profiles[i:i + chunk_size] for i in range(0, len(profiles), chunk_size)]
        
        self.logger.info(f"Using chunked consolidation: {len(profiles)} profiles in {len(chunks)} chunks")
        
        consolidated_entities = []
        
        # Process each chunk
        for i, chunk in enumerate(chunks):
            self.logger.info(f"Processing chunk {i+1}/{len(chunks)} with {len(chunk)} profiles")
            try:
                chunk_result = await self.llm_client.consolidate_clusters(entity_name, entity_type, chunk)
                if chunk_result and chunk_result.get("entities"):
                    consolidated_entities.extend(chunk_result["entities"])
            except Exception as e:
                self.logger.warning(f"Chunk {i+1} consolidation failed: {e}, using local fallback")
                # Fallback to local consolidation for this chunk
                local_entities = self._local_consolidate(entity_name, chunk, source_url_to_id)
                consolidated_entities.extend(local_entities)
        
        # If we have multiple chunks, do a final consolidation pass on the results
        if len(chunks) > 1 and consolidated_entities:
            self.logger.info(f"Final consolidation pass on {len(consolidated_entities)} intermediate entities")
            try:
                # Convert consolidated entities back to profile format for final pass
                final_profiles = []
                for idx, entity in enumerate(consolidated_entities):
                    final_profiles.append({
                        "detected_entity_name": entity.get("canonical_name"),
                        "same_as_input": entity.get("same_as_query", False),
                        "confidence": 0.8,  # High confidence for already consolidated entities
                        "extracted_info": entity.get("combined_fields", {}),
                        "source_url": f"consolidated_chunk_{idx}"
                    })
                
                final_result = await self.llm_client.consolidate_clusters(entity_name, entity_type, final_profiles)
                if final_result and final_result.get("entities"):
                    return final_result
            except Exception as e:
                self.logger.warning(f"Final consolidation pass failed: {e}")
        
        # Return consolidated entities
        return {"entities": consolidated_entities}
