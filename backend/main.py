import os
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import uuid
import asyncio
import logging
from dotenv import load_dotenv
import json
from fastapi.responses import StreamingResponse

# Load environment variables
load_dotenv()

# Configure logging: file + console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='research.log',
    filemode='w'
)
logger = logging.getLogger(__name__)
# if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
#     console_handler = logging.StreamHandler()
#     console_handler.setLevel(logging.INFO)
#     console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
#     logging.getLogger().addHandler(console_handler)

app = FastAPI(
    title="Entity Research API",
    description="API for researching entities using web search and AI analysis",
    version="1.0.0",
    docs_url="/docs",
    redoc_url=None
)

# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SearchRequest(BaseModel):
    entity_name: str = Field(..., description="Name of the entity to research")
    entity_type: str = Field(..., description="Type of entity: 'individual' or 'company'")
    keywords: Optional[List[str]] = Field(
        None,
        description="Optional list of search keywords to refine the search"
    )
    search_queries: Optional[List[str]] = Field(
        None,
        description="Optional list of specific search queries to use"
    )
    paragraph: Optional[str] = Field(
        None,
        description="Optional paragraph with detailed context; when provided, LLM will generate search queries from it"
    )
    
    @validator('entity_type')
    def validate_entity_type(cls, v):
        if v not in ['individual', 'company']:
            raise ValueError('entity_type must be either "individual" or "company"')
        return v

# In-memory storage for research results
research_results = {}

# Initialize the research service
from app.services.entity_research_service import EntityResearchService
from app.database.history import HistoryDatabase

# Use a singleton pattern for the research service and history database
_research_service_instance = None
_history_db_instance = None

def get_research_service():
    global _research_service_instance
    if _research_service_instance is None:
        _research_service_instance = EntityResearchService(
            max_search_results=20,  # tune as needed based on engines
            max_concurrent_requests=10  # slightly higher concurrency for faster throughput
        )
    return _research_service_instance

def get_history_db():
    global _history_db_instance
    if _history_db_instance is None:
        _history_db_instance = HistoryDatabase()
    return _history_db_instance

@app.post("/research-entity", response_model=Dict[str, Any])
async def research_entity(
    request: SearchRequest,
    research_service: EntityResearchService = Depends(get_research_service),
    history_db: HistoryDatabase = Depends(get_history_db)
):
    """
    Research an entity by searching the web and analyzing the results.
    
    This endpoint performs the research synchronously and returns the results directly.
    For long-running research, consider using the async version with status checking.
    """
    research_id = str(uuid.uuid4())
    
    try:
        logger.info(f"Starting synchronous research for entity: {request.entity_name}")
        
        # If a paragraph is provided, generate queries from it using LLM
        # Use these as ACTUAL search_queries, and also reuse them as keywords context for LLM
        final_search_queries = request.search_queries or None
        final_keywords = list(request.keywords or [])
        try:
            if request.paragraph and isinstance(request.paragraph, str) and request.paragraph.strip():
                paragraph_queries = await research_service.llm_client.generate_search_queries_from_paragraph(
                    request.entity_name,
                    request.entity_type,
                    request.paragraph,
                    num_queries=4
                )
                # Use paragraph queries for actual search
                final_search_queries = paragraph_queries or request.search_queries or None
                # Also pass them as keywords context (dedupe while preserving order)
                seen = set(k.strip().lower() for k in final_keywords)
                for q in (paragraph_queries or []):
                    qq = (q or '').strip()
                    if qq and qq.lower() not in seen:
                        final_keywords.append(qq)
                        seen.add(qq.lower())
        except Exception as e:
            logger.warning(f"Paragraph-based query generation failed, falling back: {e}")

        # Determine search mode for history/UI
        was_paragraph = bool(request.paragraph and isinstance(request.paragraph, str) and request.paragraph.strip())
        search_mode = 'paragraph' if was_paragraph else 'manual'

        # Save search start to history
        history_db.save_search_start(
            research_id=research_id,
            entity_name=request.entity_name,
            entity_type=request.entity_type,
            search_queries=final_search_queries,
            keywords=final_keywords or request.keywords,
            search_mode=search_mode
        )
        
        # Perform the research synchronously
        results = await research_service.research_entity(
            entity_name=request.entity_name,
            entity_type=request.entity_type,
            search_queries=final_search_queries or None,
            keywords=final_keywords or request.keywords or None
        )
        
        if not results:
            # Save failure to history
            history_db.save_search_completion(research_id, {}, "failed", "No results found")
            raise HTTPException(
                status_code=404,
                detail="No results found for the given search criteria"
            )
        
        # Save completion to history
        history_db.save_search_completion(research_id, results, "completed")
            
        return {
            "status": "completed",
            "entity_name": request.entity_name,
            "results": results,
            "research_id": research_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "search_mode": search_mode,
        }
        
    except Exception as e:
        logger.error(f"Error in research_entity: {str(e)}", exc_info=True)
        
        # Save failure to history
        try:
            history_db.save_search_completion(research_id, {}, "failed", str(e))
        except:
            pass  # Don't fail the main request if history save fails
            
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred while processing your request: {str(e)}"
        )

# In-memory SSE subscribers per research_id
research_streams: Dict[str, set] = {}

def _sse_broadcast(research_id: str, event: str, data: Dict[str, Any]):
    """Broadcast an event to all SSE subscribers for a research_id."""
    try:
        subscribers = list(research_streams.get(research_id, set()))
        # Build the message once
        payload = {
            "event": event,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        for q in subscribers:
            try:
                q.put_nowait(payload)
            except Exception:
                # Drop message for slow/broken subscribers
                pass
    except Exception as e:
        logger.debug(f"SSE broadcast error: {e}")

@app.post("/research-entity-async", response_model=Dict[str, Any])
async def research_entity_async(
    request: SearchRequest,
    background_tasks: BackgroundTasks,
    research_service: EntityResearchService = Depends(get_research_service),
    history_db: HistoryDatabase = Depends(get_history_db)
):
    """Start research asynchronously and stream progress via /research-status."""
    try:
        research_id = str(uuid.uuid4())
        # Determine search mode
        was_paragraph = bool(request.paragraph and isinstance(request.paragraph, str) and request.paragraph.strip())
        search_mode = 'paragraph' if was_paragraph else 'manual'

        research_results[research_id] = {
            "status": "pending",
            "phase": "starting",
            "entity_name": request.entity_name,
            "entity_type": request.entity_type,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "results": None,
            "live_results": None,
            "events": [],
            "cancelled": False,
            "search_mode": search_mode,
        }
        
        # If a paragraph is provided, generate queries from it using LLM
        # Use these as ACTUAL search_queries, and also reuse them as keywords context for LLM
        final_search_queries = request.search_queries or None
        final_keywords = list(request.keywords or [])
        try:
            if request.paragraph and isinstance(request.paragraph, str) and request.paragraph.strip():
                paragraph_queries = await research_service.llm_client.generate_search_queries_from_paragraph(
                    request.entity_name,
                    request.entity_type,
                    request.paragraph,
                    num_queries=4
                )
                # Use paragraph queries for actual search
                final_search_queries = paragraph_queries or request.search_queries or None
                # Also pass them as keywords context (dedupe)
                seen = set(k.strip().lower() for k in final_keywords)
                for q in (paragraph_queries or []):
                    qq = (q or '').strip()
                    if qq and qq.lower() not in seen:
                        final_keywords.append(qq)
                        seen.add(qq.lower())
        except Exception as e:
            logger.warning(f"Paragraph-based query generation failed, falling back: {e}")

        # Save search start to history
        history_db.save_search_start(
            research_id=research_id,
            entity_name=request.entity_name,
            entity_type=request.entity_type,
            search_queries=final_search_queries,
            keywords=final_keywords or request.keywords
        )
        
        background_tasks.add_task(
            perform_research,
            research_id,
            request.entity_name,
            request.entity_type,
            research_service,
            final_keywords or request.keywords or None,
            final_search_queries or None,
            history_db
        )
        # Initial SSE state push (if listeners present)
        _sse_broadcast(research_id, "state", {
            "status": "pending",
            "phase": "starting",
            "progress": {},
            "events": [],
            "entity_name": request.entity_name,
            "started_at": research_results[research_id]["started_at"],
            "live_results": None,
            "search_mode": search_mode,
        })

        return {"research_id": research_id, "status": "started"}
    except Exception as e:
        logger.error(f"Error starting async research: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to start research: {str(e)}")
@app.get("/research-status/{research_id}", response_model=Dict[str, Any])
async def get_research_status(
    research_id: str,
    history_db: HistoryDatabase = Depends(get_history_db)
):
    """Get the status and results of a research task."""
    # First check in-memory storage for active research
    if research_id in research_results:
        result = research_results[research_id]
        
        # Calculate duration if completed
        if result["status"] == "completed" and "started_at" in result:
            started_at = datetime.fromisoformat(result["started_at"])
            completed_at = datetime.fromisoformat(result.get("completed_at", datetime.now(timezone.utc).isoformat()))
            result["duration_seconds"] = (completed_at - started_at).total_seconds()
        
        return {
            "research_id": research_id,
            "status": result["status"],
            "phase": result.get("phase"),
            "progress": result.get("progress"),
            "events": result.get("events", []),
            "clusters_summary": result.get("clusters_summary"),
            "entity_name": result["entity_name"],
            "started_at": result["started_at"],
            "completed_at": result.get("completed_at"),
            "results": result.get("results"),
            "live_results": result.get("live_results"),
            "cancelled": result.get("cancelled", False),
            "search_mode": result.get("search_mode", "manual"),
            "error": result.get("error")
        }
    
    # If not in memory, check database for completed research
    try:
        db_search = history_db.get_search_by_id(research_id)
        if not db_search:
            raise HTTPException(status_code=404, detail="Research not found")
        
        return {
            "research_id": research_id,
            "status": db_search["status"],
            "phase": db_search.get("phase"),
            "progress": {},
            "events": [],
            "clusters_summary": {},
            "entity_name": db_search["entity_name"],
            "started_at": db_search["started_at"],
            "completed_at": db_search.get("completed_at"),
            "results": db_search.get("full_results"),  # Now retrieve full results from DB
            "search_mode": db_search.get("search_mode", "manual"),
            "error": db_search.get("error_message")
        }
    except Exception as e:
        logger.error(f"Error retrieving research from database: {e}")
        raise HTTPException(status_code=404, detail="Research not found")

async def perform_research(
    research_id: str,
    entity_name: str,
    entity_type: str,
    research_service: EntityResearchService,
    keywords: Optional[List[str]] = None,
    search_queries: Optional[List[str]] = None,
    history_db: Optional[HistoryDatabase] = None
):
    """Perform the actual research in the background."""
    try:
        # Update status to in-progress
        research_results[research_id]["status"] = "in_progress"
        research_results[research_id]["phase"] = "searching"

        # Define a simple progress callback to stream partials
        def progress_callback(phase: str, payload: Dict[str, Any]):
            try:
                research_results[research_id]["phase"] = phase
                # lightweight normalization of known progress fields
                if phase in ("searching", "crawling", "analyzing", "combining"):
                    prev_progress = research_results[research_id].get("progress", {}) or {}
                    merged = dict(prev_progress)
                    for k in [
                        "pages_crawled",
                        "pages_analyzed",
                        "pages_total",
                        "profiles_count",
                        "search_results_count",
                        "current_page",
                    ]:
                        if isinstance(payload, dict) and k in payload:
                            merged[k] = payload.get(k)
                    research_results[research_id]["progress"] = merged
                msg = payload.get("message") if isinstance(payload, dict) else None
                if msg:
                    events = research_results[research_id].setdefault("events", [])
                    events.append({
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "phase": phase,
                        "message": msg
                    })
                    # cap events to last 50 to avoid frontend overload
                    if len(events) > 50:
                        del events[:-50]
                # Optionally expose small deltas for UI
                if "clusters_summary" in payload:
                    research_results[research_id]["clusters_summary"] = payload["clusters_summary"]
                # Live partial results (keep same shape as final 'results')
                if isinstance(payload, dict) and payload.get("result_snapshot"):
                    research_results[research_id]["live_results"] = payload.get("result_snapshot")
                # Broadcast SSE state and snapshot if present
                try:
                    _sse_broadcast(research_id, "state", {
                        "status": research_results[research_id].get("status", "in_progress"),
                        "phase": phase,
                        "progress": research_results[research_id].get("progress", {}),
                        "events": research_results[research_id].get("events", []),
                        "entity_name": research_results[research_id]["entity_name"],
                        "started_at": research_results[research_id]["started_at"],
                        "live_results": research_results[research_id].get("live_results"),
                    })
                    if isinstance(payload, dict) and payload.get("result_snapshot"):
                        _sse_broadcast(research_id, "snapshot", {
                            "result": payload.get("result_snapshot")
                        })
                except Exception:
                    pass
                
                # Update history database with progress
                if history_db:
                    try:
                        current_status = research_results.get(research_id, {}).get("status", "in_progress")
                        # Keep DB status in sync; do not revert to in_progress if cancelled/failed
                        if current_status in ("cancelled", "failed", "completed"):
                            history_db.update_search_progress(research_id, current_status, current_status)
                        else:
                            history_db.update_search_progress(research_id, "in_progress", phase)
                    except Exception:
                        pass
            except Exception as e:
                logger.debug(f"progress_callback error: {e}")

        # Heartbeat task to ensure UI gets periodic updates
        heartbeat_running = True
        # async def heartbeat():
        #     while heartbeat_running:
        #         try:
        #             progress = research_results[research_id].get("progress", {})
        #             events = research_results[research_id].setdefault("events", [])
        #             events.append({
        #                 "timestamp": datetime.now(timezone.utc).isoformat(),
        #                 "phase": research_results[research_id].get("phase", "starting"),
        #                 "message": "heartbeat"
        #             })
        #             if len(events) > 50:
        #                 del events[:-50]
        #         except Exception:
        #             pass
        #         await asyncio.sleep(10)

        # hb_task = asyncio.create_task(heartbeat())
        try:
            # Perform the research with progress callback
            result = await research_service.research_entity(
                entity_name=entity_name,
                entity_type=entity_type,
                search_queries=search_queries,
                keywords=keywords,
                progress_callback=progress_callback,
                should_cancel=lambda: bool(research_results.get(research_id, {}).get("cancelled", False))
            )
        finally:
            heartbeat_running = False
            # try:
            #     await asyncio.wait_for(hb_task, timeout=2)
            # except Exception:
            #     hb_task.cancel()

        # Store the results (respect cancellation)
        is_cancelled = bool(research_results.get(research_id, {}).get("cancelled", False))
        research_results[research_id].update({
            "status": "cancelled" if is_cancelled else "completed",
            "phase": "cancelled" if is_cancelled else "completed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "results": result if not is_cancelled else research_results[research_id].get("live_results") or result
        })
        # SSE final event
        try:
            _sse_broadcast(research_id, "done", {
                "status": research_results[research_id]["status"],
                "results": research_results[research_id].get("results"),
                "completed_at": research_results[research_id].get("completed_at"),
                "error": None
            })
        except Exception:
            pass
        
        # Save completion to history (ensure results is a dict)
        if history_db:
            _res = research_results[research_id].get("results")
            if not isinstance(_res, dict):
                _res = {}
            history_db.save_search_completion(research_id, _res, "cancelled" if is_cancelled else "completed")
        
    except Exception as e:
        logger.error(f"Error in research task {research_id}: {str(e)}", exc_info=True)
        research_results[research_id].update({
            "status": "failed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "error": str(e)
        })
        try:
            _sse_broadcast(research_id, "done", {
                "status": "failed",
                "results": None,
                "completed_at": research_results[research_id].get("completed_at"),
                "error": str(e)
            })
        except Exception:
            pass
        
        # Save failure to history
        if history_db:
            history_db.save_search_completion(research_id, {}, "failed", str(e))
        
    # Clean up old research results (keep last 100)
    if len(research_results) > 100:
        oldest_ids = sorted(
            research_results.keys(),
            key=lambda k: research_results[k].get("started_at", ""),
            reverse=False
        )[:len(research_results) - 100]
        for rid in oldest_ids:
            research_results.pop(rid, None)

# History API endpoints
@app.get("/history", response_model=Dict[str, Any])
async def get_search_history(
    limit: int = 50,
    offset: int = 0,
    entity_name: Optional[str] = None,
    history_db: HistoryDatabase = Depends(get_history_db)
):
    """Get search history with optional filtering."""
    try:
        logger.info(f"Fetching history with limit={limit}, offset={offset}, entity_name={entity_name}")
        
        result = history_db.get_search_history(
            limit=limit,
            offset=offset,
            entity_name=entity_name
        )
        stats = history_db.get_search_stats()
        
        logger.info(f"Retrieved {len(result['history'])} history items and stats: {stats}")
        
        return {
            "history": result["history"],
            "stats": stats,
            "pagination": result["pagination"]
        }
    except Exception as e:
        logger.error(f"Error retrieving search history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve search history")

@app.get("/history/{research_id}", response_model=Dict[str, Any])
async def get_search_by_id(
    research_id: str,
    history_db: HistoryDatabase = Depends(get_history_db)
):
    """Get a specific search from history by research_id."""
    try:
        search = history_db.get_search_by_id(research_id)
        if not search:
            raise HTTPException(status_code=404, detail="Search not found in history")
        
        return {"search": search}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving search by ID: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve search")

@app.delete("/history/{research_id}")
async def delete_search_history(
    research_id: str,
    history_db: HistoryDatabase = Depends(get_history_db)
):
    """Delete a search from history."""
    try:
        success = history_db.delete_search(research_id)
        if not success:
            raise HTTPException(status_code=404, detail="Search not found in history")
        
        return {"message": "Search deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting search: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete search")

@app.get("/health", include_in_schema=False)
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "active_researches": sum(
            1 for r in research_results.values() 
            if r["status"] in ["pending", "in_progress"]
        )
    }

@app.post("/research-cancel/{research_id}")
async def cancel_research(research_id: str, history_db: HistoryDatabase = Depends(get_history_db)):
    """Request cancellation of an active research task."""
    try:
        if research_id not in research_results:
            raise HTTPException(status_code=404, detail="Research not found")
        # Mark as cancelled; workers will observe and stop soon
        research_results[research_id]["cancelled"] = True
        # If already completed/failed, reflect that
        if research_results[research_id]["status"] in ("completed", "failed", "cancelled"):
            return {"status": research_results[research_id]["status"]}

        # Immediately finalize as cancelled so UI and history reflect the state
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            snapshot = research_results[research_id].get("live_results") or research_results[research_id].get("results") or {}
            if not isinstance(snapshot, dict):
                snapshot = {}

            research_results[research_id].update({
                "status": "cancelled",
                "phase": "cancelled",
                "completed_at": now_iso,
                "results": snapshot
            })

            # Persist to history DB
            try:
                history_db.save_search_completion(research_id, snapshot, "cancelled")
            except Exception as db_e:
                logger.warning(f"Failed to save cancelled state to history for {research_id}: {db_e}")

            # Notify subscribers
            try:
                _sse_broadcast(research_id, "state", {
                    "status": research_results[research_id]["status"],
                    "phase": research_results[research_id]["phase"],
                    "progress": research_results[research_id].get("progress", {}),
                    "events": research_results[research_id].get("events", []),
                    "entity_name": research_results[research_id].get("entity_name"),
                    "started_at": research_results[research_id].get("started_at"),
                    "live_results": research_results[research_id].get("live_results"),
                })
                _sse_broadcast(research_id, "done", {
                    "status": research_results[research_id]["status"],
                    "results": research_results[research_id].get("results"),
                    "completed_at": research_results[research_id].get("completed_at"),
                    "error": None
                })
            except Exception:
                pass
        except Exception as e:
            logger.debug(f"Immediate cancellation finalize error: {e}")

        return {"status": "cancelled"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling research {research_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to cancel research")

@app.get("/research-stream/{research_id}")
async def research_stream(research_id: str, request: Request):
    """Server-Sent Events stream for a research task."""
    if research_id not in research_results:
        raise HTTPException(status_code=404, detail="Research not found")

    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    research_streams.setdefault(research_id, set()).add(q)

    async def event_generator():
        try:
            # Send initial state
            state = research_results.get(research_id, {})
            initial = {
                "event": "state",
                "data": {
                    "status": state.get("status"),
                    "phase": state.get("phase"),
                    "progress": state.get("progress", {}),
                    "events": state.get("events", []),
                    "entity_name": state.get("entity_name"),
                    "started_at": state.get("started_at"),
                    "live_results": state.get("live_results"),
                }
            }
            yield f"event: {initial['event']}\n" + f"data: {json.dumps(initial['data'])}\n\n"

            while True:
                # client disconnected
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=10.0)
                except asyncio.TimeoutError:
                    # keep-alive comment to prevent proxies from closing
                    yield ": keep-alive\n\n"
                    continue
                try:
                    evt = msg.get("event", "message")
                    data = msg.get("data", {})
                    yield f"event: {evt}\n" + f"data: {json.dumps(data)}\n\n"
                except Exception:
                    continue
        except asyncio.CancelledError:
            pass
        finally:
            # Cleanup subscriber
            try:
                research_streams.get(research_id, set()).discard(q)
                if not research_streams.get(research_id):
                    research_streams.pop(research_id, None)
            except Exception:
                pass

    return StreamingResponse(event_generator(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no"  # for nginx
    })

# Install Playwright browsers on startup
@app.on_event("startup")
async def startup_event():
    """Install Playwright browsers on startup if not already installed."""
    import sys
    from playwright.async_api import async_playwright
    
    try:
        async with async_playwright() as p:
            for browser_type in [p.chromium, p.firefox, p.webkit]:
                try:
                    browser = await browser_type.launch()
                    await browser.close()
                    logger.info(f"{browser_type.name} browser is ready")
                except Exception as e:
                    logger.warning(f"Failed to launch {browser_type.name}: {str(e)}")
                    logger.info("Installing browsers...")
                    import sys
                    from playwright.__main__ import main
                    sys.argv = ['', 'install', 'chromium', '--with-deps']
                    main()
                    break
    except Exception as e:
        logger.error(f"Error during browser installation: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", 8000)),
        reload=True,
        workers=1  # Playwright doesn't work well with multiple workers
    )
