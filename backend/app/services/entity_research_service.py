import asyncio
import logging
import os
from typing import List, Dict, Any, Optional, Callable
from collections import defaultdict
from difflib import SequenceMatcher
from datetime import datetime
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
        # Cap concurrent LLM calls to avoid rate limits
        try:
            self.llm_semaphore = asyncio.Semaphore(int(os.getenv("LLM_CONCURRENCY", "8")))
        except Exception:
            self.llm_semaphore = asyncio.Semaphore(8)
        self.logger = logging.getLogger(__name__)
    
    async def research_entity(self, entity_name: str, entity_type: str, search_queries: Optional[List[str]] = None, keywords: Optional[List[str]] = None, progress_callback: Optional[Any] = None, should_cancel: Optional[Callable[[], bool]] = None) -> Dict[str, Any]:
        """
        Research an entity by searching the web and analyzing the results.
        
        Args:
            entity_name: Name of the entity to research
            entity_type: Type of entity ('individual' or 'company')
            search_queries: Optional list of search queries to use. If not provided,
                          will generate queries based on the entity name.
            keywords: Optional list of keywords to refine the search
            progress_callback: Optional callback function for progress updates. May receive payload key 'result_snapshot' containing a partial results structure for UI.
            should_cancel: Optional callable to check if the overall job was cancelled externally (e.g., via API). When True, processing stops early.
                          
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
            # Emit an initial crawling update so the UI switches phases immediately
            if progress_callback:
                try:
                    progress_callback(phase="crawling", payload={
                        "message": f"Starting crawling of {total_urls} pages",
                        "pages_crawled": 0,
                        "pages_total": total_urls
                    })
                except Exception:
                    # Non-fatal for progress emissions
                    pass
            
            # Shared data structures for collecting results
            profiles: List[Dict[str, Any]] = []
            clusters: Dict[str, List[Dict[str, Any]]] = {"query_name": [], "uncertain": []}
            per_field_sources: Dict[str, set] = {}
            sources_meta: List[Dict[str, Any]] = []
            source_url_to_id: Dict[str, int] = {}
            early_stop_event = asyncio.Event()

            # Early stop configuration
            def _norm(s: Optional[str]) -> str:
                return (s or '').strip().lower()

            # Determine which fields should be considered for early stop
            env_fields = os.getenv("EARLY_STOP_FIELDS", "").strip()
            if env_fields:
                target_fields = set([f.strip() for f in env_fields.split(',') if f.strip()])
            else:
                try:
                    target_fields = set(self.llm_client._get_fields_for_entity_type(entity_type))
                except Exception:
                    # Fallback minimal field set
                    target_fields = set(["full_name", "age", "date_of_birth", "year_of_birth", "gender", "nationality", "location"]) if entity_type == "individual" else set(["full_name", "date_of_incorporation", "location", "ceo_founder"]) 

            name_match_threshold = float(os.getenv("NAME_MATCH_THRESHOLD", "0.9"))

            # Helper to build a partial results snapshot for UI
            def _build_result_snapshot() -> Dict[str, Any]:
                try:
                    # Shallow copies to avoid concurrent mutation surprises
                    profiles_copy = list(profiles)
                    clusters_copy = {k: list(v) for k, v in clusters.items()}
                    per_field_sources_copy = {k: sorted(list(v)) for k, v in per_field_sources.items()}
                    sources_meta_sorted = sorted(list(sources_meta), key=lambda s: (s.get("source_id") is None, s.get("source_id", 10**9)))

                    # Prefer streaming LLM-consolidated entities if any are available; else show raw profiles
                    try:
                        if consolidated_entities:
                            final_entities_snapshot = {"entities": list(consolidated_entities)}
                        else:
                            final_entities_snapshot = {"entities": self._build_raw_entities(entity_name, profiles_copy, source_url_to_id)}
                    except Exception:
                        final_entities_snapshot = {"entities": self._build_raw_entities(entity_name, profiles_copy, source_url_to_id)}

                    # Enrich snapshot entities with ranked field_sources (same logic as final)
                    try:
                        if isinstance(final_entities_snapshot, dict) and isinstance(final_entities_snapshot.get('entities'), list):
                            def _snap_norm(s: Optional[str]) -> str:
                                return (s or '').strip().lower()

                            for ent in final_entities_snapshot['entities']:
                                combined_fields = ent.get('combined_fields', {}) or {}
                                member_indexes = ent.get('member_profile_indexes')
                                if not member_indexes:
                                    ent_name_norm = _snap_norm(ent.get('canonical_name'))
                                    inferred_idxs: List[int] = []
                                    if ent.get('same_as_query'):
                                        for i, prof in enumerate(profiles_copy):
                                            if bool((prof or {}).get('same_as_input')):
                                                inferred_idxs.append(i)
                                    else:
                                        for i, prof in enumerate(profiles_copy):
                                            pname = _snap_norm((prof or {}).get('detected_entity_name'))
                                            if ent_name_norm and pname:
                                                sim = SequenceMatcher(None, ent_name_norm, pname).ratio()
                                                if sim >= name_match_threshold:
                                                    inferred_idxs.append(i)
                                    member_indexes = sorted(list(set(inferred_idxs)))
                                    ent['member_profile_indexes'] = member_indexes

                                ranked_field_sources: Dict[str, List[int]] = {}
                                for field_name, field_value in combined_fields.items():
                                    candidate_scores: Dict[int, float] = {}
                                    value_norm = str(field_value).strip().lower() if field_value is not None else ""
                                    for idx in member_indexes:
                                        if not isinstance(idx, int) or idx < 0 or idx >= len(profiles_copy):
                                            continue
                                        prof = profiles_copy[idx] or {}
                                        extracted = prof.get('extracted_info') or {}
                                        if field_name not in extracted or extracted[field_name] in (None, "", [], {}):
                                            continue
                                        url = prof.get('source_url')
                                        sid = source_url_to_id.get(url)
                                        if not sid:
                                            continue
                                        score = 0.0
                                        prof_val = extracted.get(field_name)
                                        prof_val_norm = str(prof_val).strip().lower()
                                        if value_norm and prof_val_norm:
                                            if prof_val_norm == value_norm:
                                                score += 5.0
                                            elif value_norm in prof_val_norm or prof_val_norm in value_norm:
                                                score += 2.0

                                        if field_name in ['age', 'date_of_birth', 'year_of_birth']:
                                            prof_val_str = str(prof_val) if prof_val else ""
                                            explicit_patterns = ['(from article)', '(as of 20', '(stated)', '(mentioned)']
                                            calculated_patterns = ['(calculated', '(computed', '(inferred', '(derived', f'(as of {datetime.now().strftime("%Y-%m-%d")})']
                                            is_explicit = any(p in prof_val_str for p in explicit_patterns)
                                            if field_name == 'age' and '(as of 20' in prof_val_str and f'(as of {datetime.now().strftime("%Y-%m-%d")})' not in prof_val_str:
                                                is_explicit = True
                                            is_calculated = any(p in prof_val_str for p in calculated_patterns)
                                            if is_explicit:
                                                score += 3.0
                                            elif is_calculated:
                                                score -= 1.0

                                        field_src_map = prof.get('field_sources') or {}
                                        if isinstance(field_src_map, dict) and field_name in field_src_map:
                                            score += 2.0
                                        try:
                                            score += float(prof.get('confidence') or 0.0) * 1.5
                                        except Exception:
                                            pass
                                        try:
                                            score += float(prof.get('name_similarity_score') or 0.0) * 1.0
                                        except Exception:
                                            pass
                                        candidate_scores[sid] = max(candidate_scores.get(sid, 0.0), score)
                                    if candidate_scores:
                                        ordered = sorted(candidate_scores.items(), key=lambda kv: (-kv[1], kv[0]))
                                        ranked_field_sources[field_name] = [sid for sid, _ in ordered]
                                if ranked_field_sources:
                                    ent['field_sources'] = ranked_field_sources
                    except Exception as e:
                        self.logger.debug(f"snapshot field_sources enrichment error: {e}")

                    # Filter clusters and profiles similarly to final pass to avoid empty noise
                    filtered_clusters = {}
                    for cluster_name, cluster_profiles in clusters_copy.items():
                        filtered_profiles = []
                        for profile in cluster_profiles:
                            if 'extracted_info' in profile:
                                filtered_info = {k: v for k, v in (profile.get('extracted_info') or {}).items() if v not in (None, "", [], {})}
                                if filtered_info:
                                    fp = dict(profile)
                                    fp['extracted_info'] = filtered_info
                                    filtered_profiles.append(fp)
                            elif any(v for k, v in profile.items() if k != 'extracted_info' and v not in (None, "")):
                                filtered_profiles.append(profile)
                        if filtered_profiles:
                            filtered_clusters[cluster_name] = filtered_profiles

                    filtered_profiles = []
                    for profile in profiles_copy:
                        if 'extracted_info' in profile:
                            filtered_info = {k: v for k, v in (profile.get('extracted_info') or {}).items() if v not in (None, "", [], {})}
                            if filtered_info:
                                fp = dict(profile)
                                fp['extracted_info'] = filtered_info
                                filtered_profiles.append(fp)
                        elif any(v for k, v in profile.items() if k != 'extracted_info' and v not in (None, "")):
                            filtered_profiles.append(profile)

                    return {
                        'entity_name': entity_name,
                        'search_queries': search_queries,
                        'search_results_count': len(search_results),
                        'crawled_pages_count': completed_count,
                        'clusters': filtered_clusters,
                        'profiles': filtered_profiles,
                        'final_entities': final_entities_snapshot,
                        'per_field_sources': per_field_sources_copy,
                        'sources': sources_meta_sorted
                    }
                except Exception as e:
                    self.logger.debug(f"snapshot build error: {e}")
                    return {}
            
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
                    # Respect external cancellation / early stop ASAP
                    if (should_cancel and should_cancel()) or early_stop_event.is_set():
                        return
                    # Crawl the page
                    page = await self.crawler._crawl_single(url)
                    # Check cancel after crawl
                    if (should_cancel and should_cancel()) or early_stop_event.is_set():
                        return
                    
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
                            
                            async with self.llm_semaphore:
                                # Short-circuit if cancelled right before heavy LLM call
                                if (should_cancel and should_cancel()) or early_stop_event.is_set():
                                    return
                                llm_result = await asyncio.wait_for(
                                    self.llm_client.extract_entity_info(
                                        content=page.content,
                                        entity_name=entity_name,
                                        entity_type=entity_type,
                                        keywords=keywords,
                                        source_url=page.url
                                    ),
                                    timeout=45  # Reduced to improve responsiveness on cancel
                                )
                            
                            self.logger.info(
                                f"LLM extract done | url={page.url} | keys={list((llm_result or {}).keys())}"
                            )
                            
                            # Discard low keyword-aligned profiles when keywords are provided
                            try:
                                alignment_score = float((llm_result or {}).get("keyword_alignment_score", 0.0) or 0.0)
                            except Exception:
                                alignment_score = 0.0
                            if (keywords and len(keywords) > 0) and alignment_score <= 0.3:
                                if progress_callback:
                                    progress_callback(phase="analyzing", payload={
                                        "message": f"Discarded low-alignment page (score={alignment_score:.2f}): {page.title}",
                                        "pages_analyzed": len(profiles),
                                        "pages_total": total_urls,
                                        "current_page": page.title
                                    })
                                return
                            
                            profile = {
                                **llm_result,
                                "source_url": page.url,
                                "source_title": page.title,
                                "status_code": page.status_code,
                                "source_id": source_id
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
                            
                            # Bucketize profiles
                            detected = (llm_result.get("detected_entity_name") or "").strip()
                            same_as = bool(llm_result.get("same_as_input"))
                            alignment_ok = True
                            if same_as:
                                if alignment_ok:
                                    clusters.setdefault("query_name", []).append(profile)
                                else:
                                    clusters.setdefault("uncertain", []).append(profile)
                            elif detected:
                                if alignment_ok:
                                    clusters.setdefault(detected, []).append(profile)
                                else:
                                    clusters.setdefault("uncertain", []).append(profile)
                            else:
                                clusters.setdefault("uncertain", []).append(profile)
                                
                            # Per-field sources attribution with source IDs
                            for field, value in (llm_result.get("extracted_info") or {}).items():
                                if value is not None and value != "":
                                    per_field_sources.setdefault(field, set()).add(source_id)
                            
                            # Emit a partial snapshot for UI (first page and then periodically)
                            try:
                                if progress_callback and (len(profiles) == 1 or len(profiles) % 3 == 0):
                                    snapshot = _build_result_snapshot()
                                    progress_callback(phase="analyzing", payload={
                                        "message": f"Partial results updated ({len(profiles)} profiles)",
                                        "pages_analyzed": len(profiles),
                                        "pages_total": total_urls,
                                        "result_snapshot": snapshot
                                    })
                            except Exception as e:
                                self.logger.debug(f"partial snapshot emit error: {e}")

                            # Early stop check based on field coverage and name match (no local combine)
                            try:
                                if not early_stop_event.is_set():
                                    # Group profiles by query-name match or detected name
                                    groups_fields: Dict[str, set] = {}
                                    group_names: Dict[str, str] = {}
                                    for p in profiles:
                                        key = '__query__' if p.get('same_as_input') else _norm(p.get('detected_entity_name'))
                                        if not key:
                                            continue
                                        ex = p.get('extracted_info') or {}
                                        present = {k for k, v in (ex.items() if isinstance(ex, dict) else []) if v not in (None, "", [], {})}
                                        if present:
                                            groups_fields.setdefault(key, set()).update(present)
                                            if key not in group_names and p.get('detected_entity_name'):
                                                group_names[key] = p.get('detected_entity_name')
                                    # Evaluate groups for early stop
                                    for gkey, fset in groups_fields.items():
                                        cname = group_names.get(gkey) or (entity_name if gkey == '__query__' else '')
                                        same_as = (gkey == '__query__')
                                        name_ratio = SequenceMatcher(None, _norm(entity_name), _norm(cname)).ratio() if cname else 0.0
                                        if (same_as or name_ratio >= name_match_threshold) and target_fields.issubset(fset):
                                            early_stop_event.set()
                                            if progress_callback:
                                                progress_callback(phase="combining", payload={
                                                    "message": "Early stop: target fields satisfied",
                                                    "profiles_count": len(profiles),
                                                    "result_snapshot": _build_result_snapshot()
                                                })
                                            break
                            except Exception as e:
                                self.logger.debug(f"early stop check error: {e}")
                            
                            # Check if we have enough profiles for streaming consolidation
                            async with consolidation_lock:
                                if ((should_cancel and should_cancel()) or early_stop_event.is_set()):
                                    pass  # Do not start new consolidation when cancelling
                                elif len(profiles) >= consolidation_chunk_size and len(profiles) % consolidation_chunk_size == 0:
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
            # Background watcher to cancel tasks as soon as cancellation is requested
            cancel_watch_task = None
            if should_cancel:
                async def _cancel_watch():
                    try:
                        while not early_stop_event.is_set():
                            try:
                                if should_cancel():
                                    early_stop_event.set()
                                    for rest in tasks:
                                        if not rest.done():
                                            rest.cancel()
                                    break
                            except Exception:
                                pass
                            await asyncio.sleep(0.3)
                    except asyncio.CancelledError:
                        return
                cancel_watch_task = asyncio.create_task(_cancel_watch())
            
            # Process tasks as they complete; cancel remaining on early stop/cancel
            try:
                for t in asyncio.as_completed(tasks):
                    try:
                        await t
                    except Exception:
                        pass
                    # If early stop or external cancel requested, cancel pending tasks
                    if early_stop_event.is_set() or (should_cancel and should_cancel()):
                        for rest in tasks:
                            if not rest.done():
                                rest.cancel()
                        break
            finally:
                await asyncio.gather(*tasks, return_exceptions=True)
                try:
                    if cancel_watch_task:
                        cancel_watch_task.cancel()
                except Exception:
                    pass
            
            # Handle remaining profiles that didn't reach chunk size (unless cancelled)
            async with consolidation_lock:
                if (should_cancel and should_cancel()) or early_stop_event.is_set():
                    remaining_profiles = 0
                else:
                    remaining_profiles = len(profiles) % consolidation_chunk_size
                if remaining_profiles > 0:
                    chunk_profiles = profiles[-remaining_profiles:].copy()
                    consolidation_task = asyncio.create_task(
                        self._consolidate_chunk_async(entity_name, entity_type, chunk_profiles, len(consolidation_tasks))
                    )
                    consolidation_tasks.append(consolidation_task)
                    self.logger.info(f"Started final consolidation task for remaining {remaining_profiles} profiles")
            
            # If cancellation happened, return early with a snapshot of current progress
            if (should_cancel and should_cancel()):
                self.logger.info("Cancellation requested - returning early with best-effort snapshot")
                snapshot = _build_result_snapshot()
                return {
                    'entity_name': entity_name,
                    'search_queries': search_queries,
                    'search_results_count': len(search_results),
                    'crawled_pages_count': completed_count,
                    'clusters': snapshot.get('clusters', {}),
                    'profiles': snapshot.get('profiles', []),
                    'final_entities': snapshot.get('final_entities', {'entities': []}),
                    'per_field_sources': snapshot.get('per_field_sources', {}),
                    'sources': snapshot.get('sources', [])
                }

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
                        "source_url": f"consolidated_chunk_{idx}",
                        # carry forward original member sources so we can map after final pass
                        "origin_member_source_ids": list(entity.get("member_source_ids", []) or []),
                        "origin_member_source_urls": list(entity.get("member_source_urls", []) or []),
                    })
                
                try:
                    final_entities = await self.llm_client.consolidate_clusters(entity_name, entity_type, final_profiles)
                    # Map final member_profile_indexes to original member sources aggregated above
                    try:
                        if isinstance(final_entities, dict) and isinstance(final_entities.get("entities"), list):
                            for ent in final_entities["entities"]:
                                idxs = ent.get("member_profile_indexes") or []
                                ids: List[int] = []
                                urls: List[str] = []
                                for i in idxs:
                                    try:
                                        prof = final_profiles[i]
                                    except Exception:
                                        continue
                                    ids.extend([int(x) for x in (prof.get("origin_member_source_ids") or []) if x is not None])
                                    urls.extend([u for u in (prof.get("origin_member_source_urls") or []) if u])
                                # de-duplicate
                                seen_i = set(); uniq_i: List[int] = []
                                for v in ids:
                                    if v not in seen_i:
                                        uniq_i.append(v); seen_i.add(v)
                                seen_u = set(); uniq_u: List[str] = []
                                for v in urls:
                                    if v not in seen_u:
                                        uniq_u.append(v); seen_u.add(v)
                                ent["member_source_ids"] = uniq_i
                                ent["member_source_urls"] = uniq_u
                    except Exception as me:
                        self.logger.debug(f"final member mapping error: {me}")
                    self.logger.info("Streaming consolidation with final pass completed")
                except Exception as e:
                    self.logger.warning(f"Final consolidation failed: {e}, using streaming results as-is")
                    final_entities = {"entities": consolidated_entities}
            else:
                # Fallback to traditional consolidation
                use_llm_combine = os.getenv("USE_LLM_CONSOLIDATE", "0") in ("1", "true", "True")
                self.logger.info(f"Starting traditional consolidation | mode={'LLM' if use_llm_combine else 'LOCAL'} | profiles={len(profiles)}")

                if not use_llm_combine:
                    # Do not perform local consolidation; return raw profiles as entities
                    final_entities = {"entities": self._build_raw_entities(entity_name, profiles, source_url_to_id)}
                    self.logger.info("LLM consolidation disabled; returning raw profiles as entities")
                    if progress_callback:
                        progress_callback(phase="combining", payload={
                            "message": "Consolidation skipped (raw entities)",
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
                            # Map LLM member_profile_indexes to original profile sources
                            try:
                                if isinstance(final_entities, dict) and isinstance(final_entities.get("entities"), list):
                                    for ent in final_entities["entities"]:
                                        idxs = ent.get("member_profile_indexes") or []
                                        ids: List[int] = []
                                        urls: List[str] = []
                                        for i in idxs:
                                            try:
                                                p = profiles[i]
                                            except Exception:
                                                continue
                                            sid = (p or {}).get("source_id")
                                            surl = (p or {}).get("source_url")
                                            if sid is not None:
                                                ids.append(int(sid))
                                            if surl:
                                                urls.append(surl)
                                        # de-duplicate
                                        si = set(); ui: List[int] = []
                                        for v in ids:
                                            if v not in si:
                                                ui.append(v); si.add(v)
                                        su = set(); uu: List[str] = []
                                        for v in urls:
                                            if v not in su:
                                                uu.append(v); su.add(v)
                                        ent["member_source_ids"] = ui
                                        ent["member_source_urls"] = uu
                            except Exception as mp:
                                self.logger.debug(f"direct member mapping error: {mp}")
                        
                        self.logger.info("Final consolidation completed (LLM)")
                        if not final_entities or not final_entities.get("entities"):
                            self.logger.info("LLM consolidation returned empty; using raw entities fallback")
                            final_entities = {"entities": self._build_raw_entities(entity_name, profiles, source_url_to_id)}
                    except Exception as e:
                        self.logger.error(f"LLM consolidation failed: {e}")
                        self.logger.info("Using raw entities fallback due to LLM error")
                        final_entities = {"entities": self._build_raw_entities(entity_name, profiles, source_url_to_id)}
            
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

            # Filter FINAL ENTITIES: remove entities with unknown/empty name or with no meaningful fields
            try:
                if isinstance(final_entities, dict) and isinstance(final_entities.get('entities'), list):
                    unknown_tokens = {"unknown", "unknown entity", "n/a", "na", "null", "undefined"}
                    kept_entities = []
                    removed = 0
                    for ent in final_entities['entities']:
                        canonical = (ent.get('canonical_name') or '').strip()
                        combined = ent.get('combined_fields') or {}
                        # compute meaningful fields
                        meaningful = {
                            k: v for k, v in (combined.items() if isinstance(combined, dict) else [])
                            if v is not None and v != "" and v != [] and v != {}
                        }
                        drop_for_name = (not canonical) or (canonical.lower() in unknown_tokens)
                        drop_for_empty_fields = (len(meaningful) == 0)
                        # Apply drops (only structural/unknown checks as per requirement)
                        if drop_for_name:
                            self.logger.debug(f"drop_entity reason=unknown_name canonical='{canonical}'")
                            removed += 1
                            continue
                        if drop_for_empty_fields:
                            self.logger.debug(f"drop_entity reason=empty_fields canonical='{canonical}' field_count={len(meaningful)}")
                            removed += 1
                            continue
                        kept_entities.append(ent)
                    if removed:
                        self.logger.info(f"Filtered out {removed} empty/unknown final entities (kept {len(kept_entities)})")
                    final_entities['entities'] = kept_entities
            except Exception as fe:
                self.logger.debug(f"final_entities filtering error: {fe}")

            # Build ranked field_sources per entity using member profiles
            try:
                if isinstance(final_entities, dict) and isinstance(final_entities.get('entities'), list):
                    # De-duplicate near-identical entities by name and cap count
                    try:
                        def _n(s: Optional[str]) -> str:
                            return (s or '').strip().lower()

                        def _dedup_entities_by_name(entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
                            th = float(os.getenv("DEDUP_NAME_THRESHOLD", "0.92"))
                            clusters: List[List[Dict[str, Any]]] = []
                            for e in entities:
                                name = _n(e.get('canonical_name'))
                                placed = False
                                for c in clusters:
                                    base = _n(c[0].get('canonical_name'))
                                    if name and base and SequenceMatcher(None, name, base).ratio() >= th:
                                        c.append(e)
                                        placed = True
                                        break
                                if not placed:
                                    clusters.append([e])

                            merged: List[Dict[str, Any]] = []
                            for c in clusters:
                                if len(c) == 1:
                                    merged.append(c[0])
                                    continue
                                # choose primary with better similarity/coverage
                                def quality(ent: Dict[str, Any]):
                                    fields = ent.get('combined_fields') or {}
                                    non_empty = sum(1 for v in (fields.values() if isinstance(fields, dict) else []) if v not in (None, "", [], {}))
                                    return (
                                        not bool(ent.get('same_as_query')),
                                        -float(ent.get('name_similarity_to_query') or 0.0),
                                        -non_empty,
                                    )
                                primary = sorted(c, key=quality)[0]
                                # merge member indexes and sources
                                mi: List[int] = []
                                srcs: List[str] = []
                                for ent in c:
                                    mi.extend(ent.get('member_profile_indexes') or [])
                                    srcs.extend(ent.get('sources') or [])
                                merged.append({
                                    **primary,
                                    'member_profile_indexes': sorted(list(set([i for i in mi if isinstance(i, int) and i >= 0]))),
                                    'sources': sorted(list(set([s for s in srcs if s]))),
                                    'same_as_query': bool(primary.get('same_as_query')) or any(bool(e.get('same_as_query')) for e in c),
                                    'name_similarity_to_query': max(float(primary.get('name_similarity_to_query') or 0.0), max(float(e.get('name_similarity_to_query') or 0.0) for e in c)),
                                    'consolidation_confidence': max(float(primary.get('consolidation_confidence') or 0.0), max(float(e.get('consolidation_confidence') or 0.0) for e in c)),
                                })
                            # Cap entities
                            cap = int(os.getenv("MAX_FINAL_ENTITIES", "3"))
                            if len(merged) > cap:
                                def rank_ent(ent: Dict[str, Any]):
                                    fields = ent.get('combined_fields') or {}
                                    non_empty = sum(1 for v in (fields.values() if isinstance(fields, dict) else []) if v not in (None, "", [], {}))
                                    return (
                                        not bool(ent.get('same_as_query')),
                                        -float(ent.get('name_similarity_to_query') or 0.0),
                                        -non_empty,
                                    )
                                merged = sorted(merged, key=rank_ent)[:cap]
                            return merged

                        final_entities['entities'] = _dedup_entities_by_name(final_entities['entities'])
                    except Exception as de:
                        self.logger.debug(f"entity de-dup skipped due to error: {de}")

                    # Helper to normalize names
                    def _norm(s: Optional[str]) -> str:
                        return (s or '').strip().lower()

                    # Normalize values to list of comparable lowercase strings
                    def _norm_values(x: Any) -> List[str]:
                        vals: List[str] = []
                        try:
                            if isinstance(x, (list, tuple, set)):
                                for it in x:
                                    vals.extend(_norm_values(it))
                            elif isinstance(x, dict):
                                try:
                                    import json as _json
                                    vals.append(_norm(_json.dumps(x, sort_keys=True, ensure_ascii=False)))
                                except Exception:
                                    vals.append(_norm(str(x)))
                            else:
                                vals.append(_norm(str(x)))
                        except Exception:
                            vals.append(_norm(str(x)))
                        # dedupe while preserving order
                        seen = set()
                        out = []
                        for v in vals:
                            if v not in seen:
                                out.append(v)
                                seen.add(v)
                        return out

                    # Build mapping: source_url -> profile index
                    src_to_idx: Dict[str, int] = {}
                    for i, prof in enumerate(profiles):
                        url = (prof or {}).get('source_url')
                        if url and url not in src_to_idx:
                            src_to_idx[url] = i
                    # Build mapping: source_id -> profile index (stable mapping back to crawled profiles)
                    id_to_idx: Dict[int, int] = {}
                    try:
                        for i, prof in enumerate(profiles):
                            purl = (prof or {}).get('source_url')
                            sid = source_url_to_id.get(purl)
                            if sid is not None and sid not in id_to_idx:
                                id_to_idx[int(sid)] = i
                    except Exception:
                        pass

                    for ent in final_entities['entities']:
                        combined_fields = ent.get('combined_fields', {}) or {}
                        member_indexes = ent.get('member_profile_indexes')
                        # Prefer explicit member_source_ids mapped back to original profiles
                        try:
                            msids = [int(x) for x in (ent.get('member_source_ids') or [])]
                        except Exception:
                            msids = []
                        if msids:
                            mapped = [id_to_idx[s] for s in msids if isinstance(s, int) and s in id_to_idx]
                            if mapped:
                                member_indexes = sorted(list(set(mapped)))
                        if not member_indexes:
                            # Infer members strictly per entity to avoid cross-entity source bleed
                            ent_name_norm = _norm(ent.get('canonical_name'))
                            inferred_idxs: List[int] = []
                            if ent.get('same_as_query'):
                                # Only profiles marked same_as_input
                                for i, prof in enumerate(profiles):
                                    if bool((prof or {}).get('same_as_input')):
                                        inferred_idxs.append(i)
                            else:
                                # High name similarity between entity canonical_name and profile detected name
                                for i, prof in enumerate(profiles):
                                    pname = _norm((prof or {}).get('detected_entity_name'))
                                    if ent_name_norm and pname:
                                        sim = SequenceMatcher(None, ent_name_norm, pname).ratio()
                                        use_member_threshold = max(0.8, name_match_threshold - 0.05)
                                        if sim >= use_member_threshold:
                                            inferred_idxs.append(i)
                            # Field-based fallback if no members by name similarity
                            if not inferred_idxs:
                                try:
                                    for i, prof in enumerate(profiles):
                                        ex = (prof or {}).get('extracted_info') or {}
                                        for f, v in (combined_fields.items() if isinstance(combined_fields, dict) else []):
                                            if f in ex and ex[f] not in (None, "", [], {}):
                                                evs = _norm_values(v)
                                                pvs = _norm_values(ex[f])
                                                if any((ev == pv or ev in pv or pv in ev) for ev in evs for pv in pvs if ev and pv):
                                                    inferred_idxs.append(i)
                                                    break
                                except Exception:
                                    pass
                            member_indexes = sorted(list(set(inferred_idxs)))
                            ent['member_profile_indexes'] = member_indexes
                        ranked_field_sources: Dict[str, List[int]] = {}
                        # aggregate per-entity source scores across all fields
                        agg_source_scores: Dict[int, float] = {}
                        for field_name, field_value in combined_fields.items():
                            # Collect candidate source IDs with scores
                            candidate_scores: Dict[int, float] = {}
                            entity_norm_vals = _norm_values(field_value)
                            for idx in member_indexes:
                                if not isinstance(idx, int) or idx < 0 or idx >= len(profiles):
                                    continue
                                prof = profiles[idx] or {}
                                extracted = prof.get('extracted_info') or {}
                                if field_name not in extracted or extracted[field_name] in (None, "", [], {}):
                                    continue
                                url = prof.get('source_url')
                                sid = source_url_to_id.get(url)
                                if not sid:
                                    continue
                                # Scoring
                                score = 0.0
                                prof_val = extracted.get(field_name)
                                prof_norm_vals = _norm_values(prof_val)
                                if entity_norm_vals and prof_norm_vals:
                                    if any(ev == pv for ev in entity_norm_vals for pv in prof_norm_vals):
                                        score += 5.0
                                    elif any((ev in pv or pv in ev) for ev in entity_norm_vals for pv in prof_norm_vals):
                                        score += 2.0
                                
                                # Enhanced scoring for date-based fields
                                # Check if value is explicitly mentioned vs calculated/inferred
                                if field_name in ['age', 'date_of_birth', 'year_of_birth']:
                                    prof_val_str = str(prof_val) if prof_val else ""
                                    
                                    # Patterns indicating explicitly mentioned in article
                                    explicit_patterns = [
                                        '(from article)',
                                        '(as of 20',  # e.g., "55 (as of 2024)" - directly stated age
                                        '(stated)',
                                        '(mentioned)'
                                    ]
                                    
                                    # Patterns indicating calculated/inferred values
                                    calculated_patterns = [
                                        '(calculated',
                                        '(computed',
                                        '(inferred',
                                        '(derived',
                                        f'(as of {datetime.now().strftime("%Y-%m-%d")})'  # Current date calculation
                                    ]
                                    
                                    # Check if explicitly mentioned (higher priority)
                                    is_explicit = any(pattern in prof_val_str for pattern in explicit_patterns)
                                    # For age, if it has "as of" with a year (not current date), it's from article
                                    if field_name == 'age' and '(as of 20' in prof_val_str and f'(as of {datetime.now().strftime("%Y-%m-%d")})' not in prof_val_str:
                                        is_explicit = True
                                    
                                    # Check if calculated
                                    is_calculated = any(pattern in prof_val_str for pattern in calculated_patterns)
                                    
                                    # Apply bonus/penalty based on source type
                                    if is_explicit:
                                        score += 3.0  # Significant boost for explicitly mentioned values
                                        self.logger.debug(f"Field {field_name}: +3.0 for explicit value in source {sid}")
                                    elif is_calculated:
                                        score -= 1.0  # Slight penalty for calculated values
                                        self.logger.debug(f"Field {field_name}: -1.0 for calculated value in source {sid}")
                                
                                # If this profile explicitly marked this field
                                field_src_map = prof.get('field_sources') or {}
                                if isinstance(field_src_map, dict) and field_name in field_src_map:
                                    score += 2.0
                                # Add confidence/name similarity signals if present
                                try:
                                    score += float(prof.get('confidence') or 0.0) * 1.5
                                except Exception:
                                    pass
                                try:
                                    score += float(prof.get('name_similarity_score') or 0.0) * 1.0
                                except Exception:
                                    pass
                                # Keep max score per source id
                                candidate_scores[sid] = max(candidate_scores.get(sid, 0.0), score)
                            if candidate_scores:
                                # accumulate per-entity aggregate source scores (sum across fields)
                                for _sid, _sc in candidate_scores.items():
                                    agg_source_scores[_sid] = agg_source_scores.get(_sid, 0.0) + _sc
                                ordered = sorted(candidate_scores.items(), key=lambda kv: (-kv[1], kv[0]))
                                ranked_field_sources[field_name] = [sid for sid, _ in ordered]
                        # Replace or set entity field_sources with ranked list
                        if ranked_field_sources:
                            ent['field_sources'] = ranked_field_sources
                        # store aggregate scores for later cross-entity assignment
                        ent['_agg_source_scores'] = agg_source_scores
                    # Enforce uniqueness of sources across entities using best-match assignment (enabled by default)
                    try:
                        if os.getenv("DEDUP_SOURCES_ACROSS_ENTITIES", "true").lower() == "true":
                            # Build global assignment: each source ID -> best entity based on aggregate score
                            def ent_quality(ent: Dict[str, Any]) -> tuple:
                                fields = ent.get('combined_fields') or {}
                                non_empty = sum(1 for v in (fields.values() if isinstance(fields, dict) else []) if v not in (None, "", [], {}))
                                return (not bool(ent.get('same_as_query')), -float(ent.get('name_similarity_to_query') or 0.0), -non_empty)

                            best_for_source: Dict[int, tuple] = {}
                            # (entity_idx, score, tie_quality)
                            for e_idx, ent in enumerate(final_entities['entities']):
                                agg = ent.get('_agg_source_scores') or {}
                                tq = ent_quality(ent)
                                for sid, sc in agg.items():
                                    prev = best_for_source.get(sid)
                                    if not prev:
                                        best_for_source[sid] = (e_idx, float(sc), tq)
                                    else:
                                        p_idx, p_sc, p_tq = prev
                                        # choose by higher score, then better tie quality
                                        if (sc > p_sc) or (abs(sc - p_sc) < 1e-6 and tq < p_tq):
                                            best_for_source[sid] = (e_idx, float(sc), tq)

                            # Now filter each entity's field_sources to keep only assigned sources
                            for e_idx, ent in enumerate(final_entities['entities']):
                                fs = ent.get('field_sources') or {}
                                new_fs: Dict[str, List[int]] = {}
                                assigned_list: set = set()
                                for fname, sids in fs.items():
                                    filtered = [sid for sid in (sids or []) if best_for_source.get(sid, (None,))[0] == e_idx]
                                    if filtered:
                                        new_fs[fname] = filtered
                                        assigned_list.update(filtered)
                                if new_fs:
                                    ent['field_sources'] = new_fs
                                # also expose entity-level unique sources list (sorted by aggregate score desc)
                                agg = ent.get('_agg_source_scores') or {}
                                ent['entity_sources'] = sorted([sid for sid in assigned_list], key=lambda s: -float(agg.get(s, 0.0)))
                                # cleanup temp
                                try:
                                    del ent['_agg_source_scores']
                                except Exception:
                                    pass
                    except Exception:
                        pass
            except Exception as e:
                self.logger.debug(f"field_sources ranking error: {e}")

            # Removed code-based age/YOB/DOB normalization to rely on LLM-provided normalization

            # Final safety: ensure no field retains a value without at least one source,
            # and no entity is returned without sources. If absolutely no sources exist, return empty result.
            try:
                if isinstance(final_entities, dict) and isinstance(final_entities.get('entities'), list):
                    cleaned_entities: List[Dict[str, Any]] = []
                    for ent in final_entities['entities']:
                        cf = ent.get('combined_fields') or {}
                        fs = ent.get('field_sources') or {}
                        new_cf: Dict[str, Any] = {}
                        new_fs: Dict[str, List[int]] = {}
                        used: set = set()
                        # Only keep fields that both have a value and at least one source id assigned
                        if isinstance(cf, dict):
                            for fname, fval in cf.items():
                                if fval in (None, "", [], {}):
                                    continue
                                sids = fs.get(fname) or []
                                sids = [sid for sid in sids if sid is not None]
                                if sids:
                                    new_cf[fname] = fval
                                    new_fs[fname] = sids
                                    for sid in sids:
                                        used.add(sid)
                        # If this entity ends up with no sources, drop the entity entirely
                        if used:
                            ent['combined_fields'] = new_cf
                            ent['field_sources'] = new_fs
                            # expose entity_sources for clarity
                            ent['entity_sources'] = sorted(list(used))
                            cleaned_entities.append(ent)
                    final_entities['entities'] = cleaned_entities
            except Exception as e:
                self.logger.debug(f"entity safety filter failed: {e}")

            # If globally no sources, or no entities left, return an empty result to avoid front-end showing empty details
            try:
                if (not sources_meta) or (not isinstance(final_entities, dict)) or (not final_entities.get('entities')):
                    self.logger.info("No sources or no entities after safety filter; returning empty result")
                    return self._create_empty_result(entity_name, "No verifiable sources for extracted details")
            except Exception:
                pass

            # Ensure deterministic ordering of sources by their assigned ID
            sources_meta_sorted = sorted(sources_meta, key=lambda s: (s.get("source_id") is None, s.get("source_id", 10**9)))

            result = {
                'entity_name': entity_name,
                'search_queries': search_queries,
                'search_results_count': len(search_results),
                'crawled_pages_count': completed_count,
                'clusters': filtered_clusters,
                'profiles': filtered_profiles,
                'final_entities': final_entities,
                'per_field_sources': {k: sorted(list(v)) for k, v in per_field_sources.items()},
                'sources': sources_meta_sorted
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

    def _build_raw_entities(self, entity_name: str, profiles: List[Dict[str, Any]], source_url_to_id: Dict[str, int]) -> List[Dict[str, Any]]:
        """Turn individual profiles into raw entities with per-field source IDs when available.

        This performs no consolidation. Each profile becomes a single entity.
        """
        entities: List[Dict[str, Any]] = []
        for prof in profiles or []:
            if not isinstance(prof, dict):
                continue
            src_url = (prof or {}).get('source_url')
            sid = (source_url_to_id or {}).get(src_url)
            extracted = (prof or {}).get('extracted_info') or {}
            field_srcs: Dict[str, List[int]] = {}
            if sid:
                for f, v in (extracted.items() if isinstance(extracted, dict) else []):
                    if v not in (None, "", [], {}):
                        field_srcs[f] = [sid]
            entities.append({
                "canonical_name": ((prof or {}).get("detected_entity_name") or (entity_name if (prof or {}).get("same_as_input") else "")).strip(),
                "same_as_query": bool((prof or {}).get("same_as_input")),
                "combined_fields": extracted,
                "field_sources": field_srcs,
                "member_profile_indexes": [],
                "sources": [src_url] if src_url else []
            })
        return entities

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
            result = await self.llm_client.consolidate_clusters(
                entity_name,
                entity_type,
                chunk_profiles,
            )
            self.logger.info(f"Chunk {chunk_id} consolidation completed")
            # Map LLM-local member_profile_indexes -> stable source IDs and URLs from chunk_profiles
            try:
                if isinstance(result, dict) and isinstance(result.get("entities"), list):
                    for ent in result["entities"]:
                        idxs = ent.get("member_profile_indexes") or []
                        src_ids: List[int] = []
                        src_urls: List[str] = []
                        for i in idxs:
                            try:
                                prof = chunk_profiles[i]
                            except Exception:
                                continue
                            sid = (prof or {}).get("source_id")
                            surl = (prof or {}).get("source_url")
                            if sid is not None:
                                src_ids.append(int(sid))
                            if surl:
                                src_urls.append(surl)
                        # de-duplicate while preserving order
                        seen_ids = set()
                        ids_unique: List[int] = []
                        for v in src_ids:
                            if v not in seen_ids:
                                ids_unique.append(v)
                                seen_ids.add(v)
                        seen_urls = set()
                        urls_unique: List[str] = []
                        for v in src_urls:
                            if v not in seen_urls:
                                urls_unique.append(v)
                                seen_urls.add(v)
                        ent["member_source_ids"] = ids_unique
                        ent["member_source_urls"] = urls_unique
            except Exception as e:
                self.logger.debug(f"chunk member mapping error: {e}")
            return result
        except Exception as e:
            self.logger.warning(f"Chunk {chunk_id} consolidation failed: {e}, using local fallback")
            # Fallback to raw entities for this chunk (no local consolidation)
            raw_entities = self._build_raw_entities(entity_name, chunk_profiles, {})
            return {"entities": raw_entities}
            
    async def _chunked_consolidation(
        self,
        entity_name: str,
        entity_type: str,
        profiles: List[Dict[str, Any]],
        source_url_to_id: Dict[str, int],
    ) -> Dict[str, Any]:
        """Consolidate large profile sets using chunking strategy."""
        chunk_size = 15  # Process 15 profiles at a time
        chunks = [profiles[i:i + chunk_size] for i in range(0, len(profiles), chunk_size)]

        self.logger.info(f"Using chunked consolidation: {len(profiles)} profiles in {len(chunks)} chunks")

        consolidated_entities: List[Dict[str, Any]] = []

        # Process each chunk sequentially
        for idx, chunk in enumerate(chunks):
            try:
                res = await self._consolidate_chunk_async(
                    entity_name,
                    entity_type,
                    chunk,
                    idx,
                )
                if res and isinstance(res, dict) and res.get("entities"):
                    consolidated_entities.extend(res["entities"])
            except Exception as e:
                self.logger.warning(f"Chunk {idx} consolidation error: {e}")

        # Final consolidation pass on already consolidated entities
        try:
            if consolidated_entities:
                final_profiles = []
                for i, entity in enumerate(consolidated_entities):
                    final_profiles.append({
                        "detected_entity_name": entity.get("canonical_name"),
                        "same_as_input": entity.get("same_as_query", False),
                        "confidence": float(entity.get("consolidation_confidence", 0.8) or 0.8),
                        "extracted_info": entity.get("combined_fields", {}) or {},
                        "source_url": f"consolidated_chunk_{i}",
                    })

                final_result = await self.llm_client.consolidate_clusters(
                    entity_name,
                    entity_type,
                    final_profiles,
                )
                if final_result and final_result.get("entities"):
                    return final_result
        except Exception as e:
            self.logger.warning(f"Final consolidation pass failed: {e}")

        # Return consolidated entities
        return {"entities": consolidated_entities}
