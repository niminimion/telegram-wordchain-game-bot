"""
Unit tests for word validation system.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import aiohttp

from bot.word_validators import (
    NLTKValidator, 
    ValidationServiceUnavailable,
    create_word_validator
)


class TestNLTKValidator:
    """Test cases for NLTK word validator."""
    
    @pytest.fixture
    def validator(self):
        return NLTKValidator()
    
    @pytest.mark.asyncio
    async def test_valid_english_words(self, validator):
        """Test validation of common English words."""
        # Mock NLTK to avoid actual downloads in tests
        with patch('bot.validators.wordnet') as mock_wordnet:
            mock_wordnet.synsets.return_value = [MagicMock()]  # Non-empty list = valid word
            validator._initialized = True
            
            assert await validator.validate_word("cat") == True
            assert await validator.validate_word("dog") == True
            assert await validator.validate_word("house") == True
    
    @pytest.mark.asyncio
    async def test_invalid_words_rejected(self, validator):
        """Test rejection of invalid words."""
        with patch('bot.validators.wordnet') as mock_wordnet:
            mock_wordnet.synsets.return_value = []  # Empty list = invalid word
            validator._initialized = True
            
            assert await validator.validate_word("xyz123") == False
            assert await validator.validate_word("notarealword") == False
    
    @pytest.mark.asyncio
    async def test_empty_and_non_alpha_words(self, validator):
        """Test handling of empty and non-alphabetic inputs."""
        assert await validator.validate_word("") == False
        assert await validator.validate_word("123") == False
        assert await validator.validate_word("cat123") == False
        assert await validator.validate_word("cat-dog") == False
    
    @pytest.mark.asyncio
    async def test_caching_functionality(self, validator):
        """Test that validation results are cached."""
        with patch('bot.validators.wordnet') as mock_wordnet:
            mock_wordnet.synsets.return_value = [MagicMock()]
            validator._initialized = True
            
            # First call
            result1 = await validator.validate_word("test")
            # Second call should use cache
            result2 = await validator.validate_word("test")
            
            assert result1 == result2 == True
            # Should only call wordnet once due to caching
            assert mock_wordnet.synsets.call_count == 1


# WordnikValidator and CompositeWordValidator tests are commented out
# because these classes don't exist in the current implementation

# class TestWordnikValidator:
#     """Test cases for Wordnik API validator."""
#     ...

# class TestCompositeWordValidator:
#     """Test cases for composite validator."""
#     ...
    



class TestValidatorFactory:
    """Test cases for validator factory function."""
    
    def test_create_nltk_only_validator(self):
        """Test creating validator without Wordnik API key."""
        validator = create_word_validator()
        
        assert isinstance(validator, NLTKValidator)
    
    def test_create_validator_with_api_key(self):
        """Test creating validator with API key (currently returns NLTK only)."""
        validator = create_word_validator("test_api_key")
        
        # Currently only NLTK validator is implemented
        assert isinstance(validator, NLTKValidator)


if __name__ == "__main__":
    pytest.main([__file__])