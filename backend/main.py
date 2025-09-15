import os
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import uuid
import asyncio
import logging
from dotenv import load_dotenv

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
            max_search_results=20,
            max_concurrent_requests=10
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
        
        # Save search start to history
        history_db.save_search_start(
            research_id=research_id,
            entity_name=request.entity_name,
            entity_type=request.entity_type,
            search_queries=request.search_queries,
            keywords=request.keywords
        )
        
        # Perform the research synchronously
        results = await research_service.research_entity(
            entity_name=request.entity_name,
            entity_type=request.entity_type,
            search_queries=request.search_queries or None,
            keywords=request.keywords or None
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
            "timestamp": datetime.now(timezone.utc).isoformat()
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
        research_results[research_id] = {
            "status": "pending",
            "phase": "starting",
            "entity_name": request.entity_name,
            "entity_type": request.entity_type,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "results": None,
            "events": []
        }
        
        # Save search start to history
        history_db.save_search_start(
            research_id=research_id,
            entity_name=request.entity_name,
            entity_type=request.entity_type,
            search_queries=request.search_queries,
            keywords=request.keywords
        )
        
        background_tasks.add_task(
            perform_research,
            research_id,
            request.entity_name,
            request.entity_type,
            research_service,
            request.keywords or None,
            request.search_queries or None,
            history_db
        )
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
                    research_results[research_id]["progress"] = {
                        k: payload.get(k) for k in ["pages_crawled", "pages_total", "profiles_count", "search_results_count"] if k in payload
                    }
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
                
                # Update history database with progress
                if history_db:
                    history_db.update_search_progress(research_id, "in_progress", phase)
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
                progress_callback=progress_callback
            )
        finally:
            heartbeat_running = False
            # try:
            #     await asyncio.wait_for(hb_task, timeout=2)
            # except Exception:
            #     hb_task.cancel()

        # Store the results
        research_results[research_id].update({
            "status": "completed",
            "phase": "completed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "results": result
        })
        
        # Save completion to history
        if history_db:
            history_db.save_search_completion(research_id, result, "completed")
        
    except Exception as e:
        logger.error(f"Error in research task {research_id}: {str(e)}", exc_info=True)
        research_results[research_id].update({
            "status": "failed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "error": str(e)
        })
        
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
        
        history = history_db.get_search_history(
            limit=limit,
            offset=offset,
            entity_name=entity_name
        )
        stats = history_db.get_search_stats()
        
        logger.info(f"Retrieved {len(history)} history items and stats: {stats}")
        
        return {
            "history": history,
            "stats": stats,
            "pagination": {
                "limit": limit,
                "offset": offset,
                "has_more": len(history) == limit
            }
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
