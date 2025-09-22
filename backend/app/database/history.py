import sqlite3
import json
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class HistoryDatabase:
    def __init__(self, db_path: str = "search_history.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize the SQLite database with required tables."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # First, create the table if it doesn't exist
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS search_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        research_id TEXT UNIQUE NOT NULL,
                        entity_name TEXT NOT NULL,
                        search_queries TEXT,  -- JSON array of search queries
                        keywords TEXT,        -- JSON array of keywords
                        status TEXT NOT NULL DEFAULT 'pending',
                        phase TEXT,
                        started_at TEXT NOT NULL,
                        completed_at TEXT,
                        duration_seconds INTEGER,
                        results_summary TEXT, -- JSON summary of key results
                        total_sources INTEGER DEFAULT 0,
                        crawled_pages INTEGER DEFAULT 0,
                        entities_found INTEGER DEFAULT 0,
                        error_message TEXT,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Then check if we need to add missing columns
                cursor = conn.execute("PRAGMA table_info(search_history)")
                columns = [row[1] for row in cursor.fetchall()]
                
                if 'full_results' not in columns:
                    # Add the full_results column if it doesn't exist
                    conn.execute("ALTER TABLE search_history ADD COLUMN full_results TEXT")
                    logger.info("Added full_results column to existing search_history table")
                
                if 'entity_type' not in columns:
                    # Add the entity_type column if it doesn't exist
                    conn.execute("ALTER TABLE search_history ADD COLUMN entity_type TEXT")
                    logger.info("Added entity_type column to existing search_history table")
                
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_entity_name ON search_history(entity_name);
                """)
                
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_started_at ON search_history(started_at);
                """)
                
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_status ON search_history(status);
                """)
                
                conn.commit()
                logger.info("History database initialized successfully")
                
        except Exception as e:
            logger.error(f"Failed to initialize history database: {e}")
            raise
    
    def save_search_start(self, research_id: str, entity_name: str, 
                         entity_type: str,
                         search_queries: Optional[List[str]] = None,
                         keywords: Optional[List[str]] = None) -> bool:
        """Save the start of a new search to history."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO search_history 
                    (research_id, entity_name, entity_type, search_queries, keywords, status, started_at)
                    VALUES (?, ?, ?, ?, ?, 'pending', ?)
                """, (
                    research_id,
                    entity_name,
                    entity_type,
                    json.dumps(search_queries) if search_queries else None,
                    json.dumps(keywords) if keywords else None,
                    datetime.now(timezone.utc).isoformat()
                ))
                conn.commit()
                logger.info(f"Saved search start for research_id: {research_id}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to save search start: {e}")
            return False
    
    def update_search_progress(self, research_id: str, status: str, phase: str = None) -> bool:
        """Update the progress of an ongoing search."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                if phase:
                    conn.execute("""
                        UPDATE search_history 
                        SET status = ?, phase = ?
                        WHERE research_id = ?
                    """, (status, phase, research_id))
                else:
                    conn.execute("""
                        UPDATE search_history 
                        SET status = ?
                        WHERE research_id = ?
                    """, (status, research_id))
                conn.commit()
                return True
                
        except Exception as e:
            logger.error(f"Failed to update search progress: {e}")
            return False
    
    def save_search_completion(self, research_id: str, results: Dict[str, Any], 
                              status: str = "completed", error_message: str = None) -> bool:
        """Save the completion of a search with results summary."""
        try:
            # Extract key metrics from results
            total_sources = len(results.get('sources', []))
            crawled_pages = results.get('crawled_pages_count', 0)
            entities_found = len(results.get('final_entities', {}).get('entities', []))
            
            # Create a summary of key results (without full content to save space)
            results_summary = {
                'entity_info_keys': list(results.get('entity_info', {}).keys()),
                'clusters_count': len(results.get('clusters', {})),
                'sources_count': total_sources,
                'has_adverse_mentions': len(results.get('adverse_mentions', [])) > 0
            }
            
            with sqlite3.connect(self.db_path) as conn:
                # Get the start time to calculate duration
                cursor = conn.execute("""
                    SELECT started_at FROM search_history WHERE research_id = ?
                """, (research_id,))
                row = cursor.fetchone()
                
                duration_seconds = None
                if row and row[0]:
                    start_time = datetime.fromisoformat(row[0].replace('Z', '+00:00'))
                    duration_seconds = int((datetime.now(timezone.utc) - start_time).total_seconds())
                
                conn.execute("""
                    UPDATE search_history 
                    SET status = ?, completed_at = ?, duration_seconds = ?,
                        results_summary = ?, full_results = ?, total_sources = ?, crawled_pages = ?,
                        entities_found = ?, error_message = ?
                    WHERE research_id = ?
                """, (
                    status,
                    datetime.now(timezone.utc).isoformat(),
                    duration_seconds,
                    json.dumps(results_summary),
                    json.dumps(results) if results else None,
                    total_sources,
                    crawled_pages,
                    entities_found,
                    error_message,
                    research_id
                ))
                conn.commit()
                logger.info(f"Saved search completion for research_id: {research_id}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to save search completion: {e}")
            return False
    
    def get_search_history(self, limit: int = 50, offset: int = 0, 
                          entity_name: str = None) -> Dict[str, Any]:
        """Retrieve search history with optional filtering and pagination metadata."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                # First get the total count for pagination
                count_query = "SELECT COUNT(*) FROM search_history"
                count_params = []
                
                if entity_name:
                    count_query += " WHERE entity_name LIKE ?"
                    count_params.append(f"%{entity_name}%")
                
                cursor = conn.execute(count_query, count_params)
                total_count = cursor.fetchone()[0]
                
                # Then get the actual data
                query = """
                    SELECT * FROM search_history
                """
                params = []
                
                if entity_name:
                    query += " WHERE entity_name LIKE ?"
                    params.append(f"%{entity_name}%")
                
                query += " ORDER BY started_at DESC LIMIT ? OFFSET ?"
                params.extend([limit, offset])
                
                logger.debug(f"Executing query: {query} with params: {params}")
                
                cursor = conn.execute(query, params)
                rows = cursor.fetchall()
                
                logger.debug(f"Found {len(rows)} rows in database, total: {total_count}")
                
                history = []
                for row in rows:
                    item = dict(row)
                    logger.debug(f"Processing row: research_id={item.get('research_id')}, entity_name={item.get('entity_name')}, status={item.get('status')}")
                    
                    # Parse JSON fields safely
                    try:
                        if item.get('search_queries'):
                            item['search_queries'] = json.loads(item['search_queries'])
                    except (json.JSONDecodeError, TypeError):
                        item['search_queries'] = []
                        
                    try:
                        if item.get('keywords'):
                            item['keywords'] = json.loads(item['keywords'])
                    except (json.JSONDecodeError, TypeError):
                        item['keywords'] = []
                        
                    try:
                        if item.get('results_summary'):
                            item['results_summary'] = json.loads(item['results_summary'])
                    except (json.JSONDecodeError, TypeError):
                        item['results_summary'] = {}
                        
                    try:
                        if item.get('full_results'):
                            item['full_results'] = json.loads(item['full_results'])
                    except (json.JSONDecodeError, TypeError):
                        item['full_results'] = None
                    
                    history.append(item)
                
                # Calculate pagination metadata
                total_pages = (total_count + limit - 1) // limit  # Ceiling division
                current_page = (offset // limit) + 1
                has_more = offset + limit < total_count
                
                pagination = {
                    "limit": limit,
                    "offset": offset,
                    "total": total_count,
                    "current_page": current_page,
                    "total_pages": total_pages,
                    "has_more": has_more
                }
                
                logger.info(f"Successfully processed {len(history)} history items with pagination: {pagination}")
                return {
                    "history": history,
                    "pagination": pagination
                }
                
        except Exception as e:
            logger.error(f"Failed to retrieve search history: {e}", exc_info=True)
            return {"history": [], "pagination": {"limit": limit, "offset": offset, "total": 0, "current_page": 1, "total_pages": 0, "has_more": False}}
    
    def get_search_by_id(self, research_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific search by research_id."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT * FROM search_history WHERE research_id = ?
                """, (research_id,))
                row = cursor.fetchone()
                
                if row:
                    item = dict(row)
                    # Parse JSON fields
                    if item['search_queries']:
                        item['search_queries'] = json.loads(item['search_queries'])
                    if item['keywords']:
                        item['keywords'] = json.loads(item['keywords'])
                    if item['results_summary']:
                        item['results_summary'] = json.loads(item['results_summary'])
                    if item['full_results']:
                        item['full_results'] = json.loads(item['full_results'])
                    
                    return item
                
                return None
                
        except Exception as e:
            logger.error(f"Failed to retrieve search by ID: {e}")
            return None
    
    def delete_search(self, research_id: str) -> bool:
        """Delete a search from history."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    DELETE FROM search_history WHERE research_id = ?
                """, (research_id,))
                conn.commit()
                
                if cursor.rowcount > 0:
                    logger.info(f"Deleted search history for research_id: {research_id}")
                    return True
                else:
                    logger.warning(f"No search found with research_id: {research_id}")
                    return False
                
        except Exception as e:
            logger.error(f"Failed to delete search: {e}")
            return False
    
    def get_search_stats(self) -> Dict[str, Any]:
        """Get overall statistics about search history."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT 
                        COUNT(*) as total_searches,
                        COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_searches,
                        COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed_searches,
                        AVG(duration_seconds) as avg_duration_seconds,
                        AVG(total_sources) as avg_sources,
                        AVG(entities_found) as avg_entities
                    FROM search_history
                """)
                row = cursor.fetchone()
                
                if row:
                    return {
                        'total_searches': row[0],
                        'completed_searches': row[1],
                        'failed_searches': row[2],
                        'avg_duration_seconds': round(row[3] or 0, 2),
                        'avg_sources': round(row[4] or 0, 2),
                        'avg_entities': round(row[5] or 0, 2)
                    }
                
                return {}
                
        except Exception as e:
            logger.error(f"Failed to get search stats: {e}")
            return {}
