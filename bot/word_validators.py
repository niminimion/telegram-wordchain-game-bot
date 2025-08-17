"""
Word validation system for the Telegram Word Game Bot.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Dict, Optional
import nltk
from nltk.corpus import wordnet

logger = logging.getLogger(__name__)


class ValidationServiceUnavailable(Exception):
    """Raised when word validation services are unavailable."""
    pass


class WordValidator(ABC):
    """Abstract base class for word validators."""
    
    @abstractmethod
    async def validate_word(self, word: str) -> bool:
        """Validate if a word exists in the dictionary."""
        pass
    
    @abstractmethod
    async def is_service_available(self) -> bool:
        """Check if the validation service is available."""
        pass


class NLTKValidator(WordValidator):
    """Word validator using NLTK WordNet corpus."""
    
    def __init__(self):
        self._initialized = False
        self._cache: Dict[str, bool] = {}
        self._max_cache_size = 1000
    
    async def _ensure_initialized(self) -> None:
        """Ensure NLTK data is downloaded and available."""
        if self._initialized:
            return
        
        try:
            # Try to access wordnet to see if it's available
            wordnet.synsets('test')
            self._initialized = True
            logger.info("NLTK WordNet is available")
        except LookupError:
            logger.info("Downloading NLTK WordNet data...")
            # Download in a separate thread to avoid blocking
            await asyncio.get_event_loop().run_in_executor(
                None, nltk.download, 'wordnet'
            )
            await asyncio.get_event_loop().run_in_executor(
                None, nltk.download, 'omw-1.4'
            )
            self._initialized = True
            logger.info("NLTK WordNet data downloaded successfully")
    
    async def validate_word(self, word: str) -> bool:
        """Validate word using NLTK WordNet."""
        if not word or not word.isalpha():
            return False
        
        word_lower = word.lower()
        
        # Check cache first
        if word_lower in self._cache:
            return self._cache[word_lower]
        
        try:
            await self._ensure_initialized()
            
            # Check if word exists in WordNet
            synsets = await asyncio.get_event_loop().run_in_executor(
                None, wordnet.synsets, word_lower
            )
            
            is_valid = len(synsets) > 0
            
            # Cache the result
            if len(self._cache) >= self._max_cache_size:
                # Remove oldest entries (simple FIFO)
                oldest_keys = list(self._cache.keys())[:100]
                for key in oldest_keys:
                    del self._cache[key]
            
            self._cache[word_lower] = is_valid
            return is_valid
            
        except Exception as e:
            logger.error(f"NLTK validation error for word '{word}': {e}")
            raise ValidationServiceUnavailable(f"NLTK validation failed: {e}")
    
    async def is_service_available(self) -> bool:
        """Check if NLTK WordNet is available."""
        try:
            await self._ensure_initialized()
            return True
        except Exception:
            return False


def create_word_validator(wordnik_api_key: Optional[str] = None) -> WordValidator:
    """Factory function to create the appropriate word validator."""
    return NLTKValidator()