"""
Unit tests for word processing and validation logic.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from bot.word_processor import WordProcessor, WordValidationError, create_word_processor
from bot.models import GameState, Player, GameConfig, GameResult
from bot.word_validators import ValidationServiceUnavailable


class TestWordProcessor:
    """Test cases for WordProcessor class."""
    
    @pytest.fixture
    def mock_validator(self):
        """Create a mock word validator."""
        validator = AsyncMock()
        validator.validate_word.return_value = True
        return validator
    
    @pytest.fixture
    def word_processor(self, mock_validator):
        """Create a WordProcessor instance for testing."""
        return WordProcessor(mock_validator)
    
    @pytest.fixture
    def game_state(self):
        """Create a test game state."""
        players = [
            Player(user_id=1, username="player1", first_name="Alice"),
            Player(user_id=2, username="player2", first_name="Bob")
        ]
        
        return GameState(
            chat_id=12345,
            current_letter="C",
            required_length=3,
            current_player_index=0,
            players=players,
            is_active=True,
            turn_start_time=datetime.now(),
            game_config=GameConfig()
        )
    
    @pytest.mark.asyncio
    async def test_valid_word_submission(self, word_processor, game_state, mock_validator):
        """Test processing a valid word submission."""
        mock_validator.validate_word.return_value = True
        
        result, error = await word_processor.process_word_submission(
            game_state, 1, "cat"
        )
        
        assert result == GameResult.VALID_WORD
        assert error is None
        mock_validator.validate_word.assert_called_once_with("cat")
    
    @pytest.mark.asyncio
    async def test_wrong_player_turn(self, word_processor, game_state):
        """Test word submission from wrong player."""
        result, error = await word_processor.process_word_submission(
            game_state, 2, "cat"  # Player 2 when it's player 1's turn
        )
        
        assert result == GameResult.WRONG_PLAYER
        assert "It's @player1's turn" in error
    
    @pytest.mark.asyncio
    async def test_invalid_starting_letter(self, word_processor, game_state):
        """Test word with wrong starting letter."""
        result, error = await word_processor.process_word_submission(
            game_state, 1, "bat"  # Should start with 'C', not 'B'
        )
        
        assert result == GameResult.INVALID_LETTER
        assert "must start with 'C'" in error
    
    @pytest.mark.asyncio
    async def test_invalid_word_length(self, word_processor, game_state):
        """Test word with wrong length."""
        # Too short
        result, error = await word_processor.process_word_submission(
            game_state, 1, "co"  # Should be 3 letters, not 2
        )
        
        assert result == GameResult.INVALID_LENGTH
        assert "must be exactly 3 letters long" in error
        
        # Too long
        result, error = await word_processor.process_word_submission(
            game_state, 1, "cats"  # Should be 3 letters, not 4
        )
        
        assert result == GameResult.INVALID_LENGTH
        assert "must be exactly 3 letters long" in error
    
    @pytest.mark.asyncio
    async def test_invalid_word_format(self, word_processor, game_state):
        """Test words with invalid format."""
        # Empty word
        result, error = await word_processor.process_word_submission(
            game_state, 1, ""
        )
        
        assert result == GameResult.INVALID_WORD
        assert "Please enter a word" in error
        
        # Word with numbers
        result, error = await word_processor.process_word_submission(
            game_state, 1, "c4t"
        )
        
        assert result == GameResult.INVALID_WORD
        assert "only contain letters" in error
        
        # Word with special characters
        result, error = await word_processor.process_word_submission(
            game_state, 1, "c@t"
        )
        
        assert result == GameResult.INVALID_WORD
        assert "only contain letters" in error
    
    @pytest.mark.asyncio
    async def test_word_not_in_dictionary(self, word_processor, game_state, mock_validator):
        """Test word that's not in dictionary."""
        mock_validator.validate_word.return_value = False
        
        result, error = await word_processor.process_word_submission(
            game_state, 1, "cxz"
        )
        
        assert result == GameResult.INVALID_WORD
        assert "not a valid English word" in error
    
    @pytest.mark.asyncio
    async def test_validation_service_unavailable(self, word_processor, game_state, mock_validator):
        """Test handling of validation service errors."""
        mock_validator.validate_word.side_effect = ValidationServiceUnavailable("Service down")
        
        result, error = await word_processor.process_word_submission(
            game_state, 1, "cat"
        )
        
        assert result == GameResult.VALIDATION_ERROR
        assert "temporarily unavailable" in error
    
    @pytest.mark.asyncio
    async def test_no_active_game(self, word_processor, game_state):
        """Test word submission when no active game."""
        game_state.is_active = False
        
        result, error = await word_processor.process_word_submission(
            game_state, 1, "cat"
        )
        
        assert result == GameResult.NO_ACTIVE_GAME
        assert "No active game" in error
    
    @pytest.mark.asyncio
    async def test_word_normalization(self, word_processor, game_state, mock_validator):
        """Test that words are properly normalized."""
        mock_validator.validate_word.return_value = True
        
        # Test with extra whitespace and mixed case
        result, error = await word_processor.process_word_submission(
            game_state, 1, "  CAT  "
        )
        
        assert result == GameResult.VALID_WORD
        # Should call validator with normalized lowercase word
        mock_validator.validate_word.assert_called_once_with("cat")
    
    def test_get_next_game_state(self, word_processor, game_state):
        """Test game state updates after valid word."""
        original_letter = game_state.current_letter
        original_length = game_state.required_length
        original_player = game_state.current_player_index
        
        # Process word "cat"
        updated_state = word_processor.get_next_game_state("cat", game_state)
        
        # Should update to last letter of word
        assert updated_state.current_letter == "T"
        # Should increase length
        assert updated_state.required_length == original_length + 1
        # Should advance player
        assert updated_state.current_player_index == (original_player + 1) % len(game_state.players)
    
    def test_format_word_feedback(self, word_processor):
        """Test formatting of word feedback messages."""
        # Valid word
        feedback = word_processor.format_word_feedback(GameResult.VALID_WORD, None, "cat")
        assert "✅" in feedback and "cat" in feedback
        
        # Invalid letter
        feedback = word_processor.format_word_feedback(
            GameResult.INVALID_LETTER, "Must start with 'C'", "bat"
        )
        assert "❌" in feedback and "Must start with 'C'" in feedback
        
        # Invalid length
        feedback = word_processor.format_word_feedback(
            GameResult.INVALID_LENGTH, "Must be 3 letters", "ca"
        )
        assert "❌" in feedback and "Must be 3 letters" in feedback
        
        # Wrong player
        feedback = word_processor.format_word_feedback(
            GameResult.WRONG_PLAYER, "Not your turn", "cat"
        )
        assert "⏳" in feedback and "Not your turn" in feedback
    
    def test_get_word_hints(self, word_processor, game_state):
        """Test generation of word hints."""
        # Test different lengths
        game_state.required_length = 1
        hint = word_processor.get_word_hints(game_state)
        assert "1-letter word" in hint and "C" in hint
        
        game_state.required_length = 3
        hint = word_processor.get_word_hints(game_state)
        assert "3-letter word" in hint and "C" in hint
        
        game_state.required_length = 10
        hint = word_processor.get_word_hints(game_state)
        assert "10-letter word" in hint and "C" in hint
    
    def test_check_word_difficulty(self, word_processor, game_state):
        """Test difficulty assessment."""
        # Easy case
        game_state.required_length = 3
        game_state.current_letter = "C"
        difficulty = word_processor.check_word_difficulty(game_state)
        assert "manageable" in difficulty.lower()
        
        # Difficult letter
        game_state.current_letter = "Q"
        difficulty = word_processor.check_word_difficulty(game_state)
        assert "tricky" in difficulty.lower()
        
        # Long word
        game_state.required_length = 10
        difficulty = word_processor.check_word_difficulty(game_state)
        assert "challenging" in difficulty.lower()
    
    def test_word_format_validation_edge_cases(self, word_processor):
        """Test edge cases in word format validation."""
        # Whitespace only
        normalized, error = word_processor._validate_word_format("   ")
        assert error is not None
        assert error.result == GameResult.INVALID_WORD
        
        # Mixed valid and invalid characters
        normalized, error = word_processor._validate_word_format("cat123")
        assert error is not None
        assert error.result == GameResult.INVALID_WORD
        
        # Valid word with whitespace
        normalized, error = word_processor._validate_word_format("  cat  ")
        assert error is None
        assert normalized == "cat"
    
    def test_starting_letter_validation(self, word_processor):
        """Test starting letter validation."""
        # Correct letter
        error = word_processor._validate_starting_letter("cat", "C")
        assert error is None
        
        # Wrong letter
        error = word_processor._validate_starting_letter("bat", "C")
        assert error is not None
        assert error.result == GameResult.INVALID_LETTER
        
        # Case insensitive
        error = word_processor._validate_starting_letter("cat", "c")
        assert error is None
    
    def test_word_length_validation(self, word_processor):
        """Test word length validation."""
        # Correct length
        error = word_processor._validate_word_length("cat", 3)
        assert error is None
        
        # Too short
        error = word_processor._validate_word_length("ca", 3)
        assert error is not None
        assert error.result == GameResult.INVALID_LENGTH
        
        # Too long
        error = word_processor._validate_word_length("cats", 3)
        assert error is not None
        assert error.result == GameResult.INVALID_LENGTH


class TestWordProcessorFactory:
    """Test cases for word processor factory function."""
    
    def test_create_word_processor(self):
        """Test factory function creates WordProcessor instance."""
        mock_validator = MagicMock()
        processor = create_word_processor(mock_validator)
        
        assert isinstance(processor, WordProcessor)
        assert processor.word_validator == mock_validator


if __name__ == "__main__":
    pytest.main([__file__])