import os
import logging
import time
from typing import List, Dict, Optional
from threading import Lock
from collections import defaultdict

logger = logging.getLogger(__name__)

class APIKeyRotator:
    """
    Utility class for rotating API keys with error handling and failover.
    Supports round-robin rotation and automatic key switching on errors.
    """
    
    def __init__(self, key_prefix: str, cooldown_seconds: int = 300):
        """
        Initialize the API key rotator.
        
        Args:
            key_prefix: Environment variable prefix (e.g., 'GEMINI_API_KEY', 'GOOGLE_API_KEY')
            cooldown_seconds: Time to wait before retrying a failed key
        """
        self.key_prefix = key_prefix
        self.cooldown_seconds = cooldown_seconds
        self.keys: List[str] = []
        self.current_index = 0
        self.failed_keys: Dict[str, float] = {}  # key -> timestamp of failure
        self.error_counts: Dict[str, int] = defaultdict(int)
        self.lock = Lock()
        
        self._load_keys()
        
    def _load_keys(self):
        """Load API keys from environment variables."""
        self.keys = []
        
        # Check for base key (without number)
        base_key = os.getenv(self.key_prefix)
        if base_key:
            self.keys.append(base_key)
            
        # Check for numbered keys (1, 2, 3, etc.)
        index = 1
        while True:
            key = os.getenv(f"{self.key_prefix}{index}")
            if key:
                self.keys.append(key)
                index += 1
            else:
                break
                
        if not self.keys:
            logger.warning(f"No API keys found for prefix: {self.key_prefix}")
        else:
            logger.info(f"Loaded {len(self.keys)} API keys for {self.key_prefix}")
            
    def get_current_key(self) -> Optional[str]:
        """
        Get the current API key to use.
        
        Returns:
            Current API key or None if no keys available
        """
        if not self.keys:
            return None
            
        with self.lock:
            # Clean up expired failed keys
            current_time = time.time()
            expired_keys = [
                key for key, fail_time in self.failed_keys.items()
                if current_time - fail_time > self.cooldown_seconds
            ]
            for key in expired_keys:
                del self.failed_keys[key]
                self.error_counts[key] = 0
                logger.info(f"Restored API key after cooldown: {self.key_prefix} (errors cleared)")
                
            # Find next available key
            attempts = 0
            while attempts < len(self.keys):
                key = self.keys[self.current_index]
                
                if key not in self.failed_keys:
                    return key
                    
                # Move to next key
                self.current_index = (self.current_index + 1) % len(self.keys)
                attempts += 1
                
            # All keys are failed, return None to indicate no available keys
            if len(self.failed_keys) >= len(self.keys):
                logger.error(f"All {self.key_prefix} keys are currently failed. No available keys.")
                return None
                
            return self.keys[self.current_index]
            
    def rotate_key(self):
        """Move to the next API key in rotation."""
        if len(self.keys) <= 1:
            return
            
        with self.lock:
            self.current_index = (self.current_index + 1) % len(self.keys)
            logger.debug(f"Rotated to next {self.key_prefix} key (index: {self.current_index})")
            
    def mark_key_failed(self, key: str, error_message: str = ""):
        """
        Mark an API key as failed and move to next key.
        
        Args:
            key: The failed API key
            error_message: Optional error message for logging
        """
        if not key or key not in self.keys:
            return
            
        with self.lock:
            self.failed_keys[key] = time.time()
            self.error_counts[key] += 1
            
            key_index = self.keys.index(key)
            logger.warning(
                f"Marked {self.key_prefix} key as failed (index: {key_index}, "
                f"errors: {self.error_counts[key]}): {error_message[:100]}"
            )
            
            # Move to next available key
            if len(self.keys) > 1:
                self.current_index = (self.current_index + 1) % len(self.keys)
                # Check if next key is available without calling get_current_key (avoid deadlock)
                next_key = self.keys[self.current_index]
                if next_key not in self.failed_keys:
                    logger.info(f"Switched to next {self.key_prefix} key")
                else:
                    logger.error(f"All {self.key_prefix} keys are now failed!")
    
    def has_available_keys(self) -> bool:
        """
        Check if there are any available (non-failed) keys.
        
        Returns:
            True if there are available keys, False otherwise
        """
        with self.lock:
            # Clean up expired failed keys first
            current_time = time.time()
            expired_keys = [
                key for key, fail_time in self.failed_keys.items()
                if current_time - fail_time > self.cooldown_seconds
            ]
            for key in expired_keys:
                del self.failed_keys[key]
                self.error_counts[key] = 0
                
            return len(self.failed_keys) < len(self.keys)
                    
    def get_stats(self) -> Dict:
        """
        Get statistics about API key usage.
        
        Returns:
            Dictionary with key statistics
        """
        with self.lock:
            return {
                "total_keys": len(self.keys),
                "current_index": self.current_index,
                "failed_keys": len(self.failed_keys),
                "error_counts": dict(self.error_counts),
                "available_keys": len(self.keys) - len(self.failed_keys)
            }
            
    def reset_failures(self):
        """Reset all failed keys (for manual recovery)."""
        with self.lock:
            self.failed_keys.clear()
            self.error_counts.clear()
            logger.info(f"Reset all failed {self.key_prefix} keys")


# Global instances for different API services
_gemini_rotator = None
_google_rotator = None

def get_gemini_rotator() -> APIKeyRotator:
    """Get the global Gemini API key rotator."""
    global _gemini_rotator
    if _gemini_rotator is None:
        _gemini_rotator = APIKeyRotator("GEMINI_API_KEY")
    return _gemini_rotator

def get_google_rotator() -> APIKeyRotator:
    """Get the global Google API key rotator."""
    global _google_rotator
    if _google_rotator is None:
        _google_rotator = APIKeyRotator("GOOGLE_API_KEY")
    return _google_rotator
