"""
Unit tests for game state management.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from bot.game_manager import GameManager
from bot.models import Player, GameConfig, GameResult
from bot.word_validators import ValidationServiceUnavailable


class TestGameManager:
    """Test cases for GameManager class."""
    
    @pytest.fixture
    def mock_validator(self):
        """Create a mock word validator."""
        validator = AsyncMock()
        validator.validate_word.return_value = True
        return validator
    
    @pytest.fixture
    def game_config(self):
        """Create a test game configuration."""
        return GameConfig(
            turn_timeout=30,
            min_word_length=1,
            max_word_length=20,
            max_players_per_game=5
        )
    
    @pytest.fixture
    def game_manager(self, mock_validator, game_config):
        """Create a GameManager instance for testing."""
        return GameManager(mock_validator, game_config)
    
    @pytest.fixture
    def test_players(self):
        """Create test players."""
        return [
            Player(user_id=1, username="player1", first_name="Alice"),
            Player(user_id=2, username="player2", first_name="Bob"),
            Player(user_id=3, username="player3", first_name="Charlie")
        ]
    
    @pytest.mark.asyncio
    async def test_start_game_creates_valid_state(self, game_manager, test_players):
        """Test that starting a game creates valid game state."""
        chat_id = 12345
        
        game_state = await game_manager.start_game(chat_id, test_players)
        
        assert game_state.chat_id == chat_id
        assert game_state.is_active == True
        assert game_state.required_length == 1
        assert len(game_state.players) == 3
        assert game_state.current_player_index == 0
        assert game_state.current_letter.isalpha()
        assert game_state.turn_start_time is not None
    
    @pytest.mark.asyncio
    async def test_start_game_prevents_duplicate_games(self, game_manager, test_players):
        """Test that starting a game in a chat with active game raises error."""
        chat_id = 12345
        
        # Start first game
        await game_manager.start_game(chat_id, test_players)
        
        # Try to start second game in same chat
        with pytest.raises(ValueError, match="already active"):
            await game_manager.start_game(chat_id, test_players)
    
    @pytest.mark.asyncio
    async def test_start_game_validates_player_count(self, game_manager):
        """Test player count validation when starting games."""
        chat_id = 12345
        
        # Test empty player list
        with pytest.raises(ValueError, match="At least one player"):
            await game_manager.start_game(chat_id, [])
        
        # Test too many players
        too_many_players = [
            Player(user_id=i, username=f"player{i}", first_name=f"Player{i}")
            for i in range(10)  # More than max_players_per_game (5)
        ]
        with pytest.raises(ValueError, match="Maximum .* players allowed"):
            await game_manager.start_game(chat_id, too_many_players)
    
    @pytest.mark.asyncio
    async def test_valid_word_advances_game(self, game_manager, test_players, mock_validator):
        """Test that valid word submission advances the game state."""
        chat_id = 12345
        mock_validator.validate_word.return_value = True
        
        # Start game
        game_state = await game_manager.start_game(chat_id, test_players)
        initial_letter = game_state.current_letter
        initial_length = game_state.required_length
        initial_player = game_state.current_player_index
        
        # Submit valid word
        word = f"{initial_letter.lower()}at"  # Simple word starting with required letter
        result, error = await game_manager.process_word(chat_id, test_players[0].user_id, word)
        
        assert result == GameResult.VALID_WORD
        assert error is None
        assert game_state.current_letter == word[-1].upper()  # Last letter of submitted word
        assert game_state.required_length == initial_length + 1
        assert game_state.current_player_index == (initial_player + 1) % len(test_players)
    
    @pytest.mark.asyncio
    async def test_invalid_word_maintains_state(self, game_manager, test_players, mock_validator):
        """Test that invalid word submission maintains game state."""
        chat_id = 12345
        mock_validator.validate_word.return_value = False
        
        # Start game
        game_state = await game_manager.start_game(chat_id, test_players)
        initial_letter = game_state.current_letter
        initial_length = game_state.required_length
        initial_player = game_state.current_player_index
        
        # Submit invalid word
        word = f"{initial_letter.lower()}xyz"
        result, error = await game_manager.process_word(chat_id, test_players[0].user_id, word)
        
        assert result == GameResult.INVALID_WORD
        assert error is not None
        assert game_state.current_letter == initial_letter
        assert game_state.required_length == initial_length
        assert game_state.current_player_index == initial_player
    
    @pytest.mark.asyncio
    async def test_wrong_player_turn_rejected(self, game_manager, test_players):
        """Test that word submission from wrong player is rejected."""
        chat_id = 12345
        
        # Start game
        await game_manager.start_game(chat_id, test_players)
        
        # Try to submit word from wrong player (player 2 when it's player 1's turn)
        result, error = await game_manager.process_word(chat_id, test_players[1].user_id, "cat")
        
        assert result == GameResult.WRONG_PLAYER
        assert error is not None
    
    @pytest.mark.asyncio
    async def test_word_format_validation(self, game_manager, test_players):
        """Test validation of word format (letter, length requirements)."""
        chat_id = 12345
        
        # Start game
        game_state = await game_manager.start_game(chat_id, test_players)
        player_id = test_players[0].user_id
        
        # Test wrong starting letter
        wrong_letter = 'Z' if game_state.current_letter != 'Z' else 'A'
        result, error = await game_manager.process_word(chat_id, player_id, f"{wrong_letter.lower()}at")
        assert result == GameResult.INVALID_LETTER
        
        # Test wrong length (too short)
        if game_state.required_length > 1:
            short_word = game_state.current_letter.lower()
            result, error = await game_manager.process_word(chat_id, player_id, short_word)
            assert result == GameResult.INVALID_LENGTH
        
        # Test wrong length (too long)
        long_word = game_state.current_letter.lower() + "a" * (game_state.required_length + 5)
        result, error = await game_manager.process_word(chat_id, player_id, long_word)
        assert result == GameResult.INVALID_LENGTH
    
    @pytest.mark.asyncio
    async def test_validation_service_error_handling(self, game_manager, test_players, mock_validator):
        """Test handling of validation service errors."""
        chat_id = 12345
        mock_validator.validate_word.side_effect = ValidationServiceUnavailable("Service down")
        
        # Start game
        game_state = await game_manager.start_game(chat_id, test_players)
        
        # Submit word when validation service is down
        word = f"{game_state.current_letter.lower()}at"
        result, error = await game_manager.process_word(chat_id, test_players[0].user_id, word)
        
        assert result == GameResult.VALIDATION_ERROR
        assert error is not None
    
    @pytest.mark.asyncio
    async def test_timeout_skips_player(self, game_manager, test_players):
        """Test that timeout advances to next player."""
        chat_id = 12345
        
        # Start game
        game_state = await game_manager.start_game(chat_id, test_players)
        initial_player = game_state.current_player_index
        initial_letter = game_state.current_letter
        initial_length = game_state.required_length
        
        # Handle timeout
        await game_manager.handle_timeout(chat_id)
        
        # Should advance to next player but keep same letter and length
        assert game_state.current_player_index == (initial_player + 1) % len(test_players)
        assert game_state.current_letter == initial_letter
        assert game_state.required_length == initial_length
    
    @pytest.mark.asyncio
    async def test_stop_game_cleanup(self, game_manager, test_players):
        """Test that stopping a game properly cleans up state."""
        chat_id = 12345
        
        # Start game
        await game_manager.start_game(chat_id, test_players)
        assert game_manager.get_game_status(chat_id) is not None
        
        # Stop game
        result = await game_manager.stop_game(chat_id)
        
        assert result == True
        assert game_manager.get_game_status(chat_id) is None
    
    @pytest.mark.asyncio
    async def test_stop_nonexistent_game(self, game_manager):
        """Test stopping a game that doesn't exist."""
        chat_id = 12345
        
        result = await game_manager.stop_game(chat_id)
        
        assert result == False
    
    @pytest.mark.asyncio
    async def test_player_management(self, game_manager, test_players):
        """Test adding and removing players from active games."""
        chat_id = 12345
        
        # Start game with 2 players
        initial_players = test_players[:2]
        await game_manager.start_game(chat_id, initial_players)
        
        # Add third player
        new_player = test_players[2]
        result = game_manager.add_player_to_active_game(chat_id, new_player)
        
        assert result == True
        game_state = game_manager.get_game_status(chat_id)
        assert len(game_state.players) == 3
        
        # Remove a player
        result = game_manager.remove_player_from_game(chat_id, test_players[0].user_id)
        
        assert result == True
        assert len(game_state.players) == 2
    
    @pytest.mark.asyncio
    async def test_game_end_conditions(self, game_manager, test_players):
        """Test that games end when too few players remain."""
        chat_id = 12345
        
        # Start game with 2 players
        await game_manager.start_game(chat_id, test_players[:2])
        
        # Remove one player (should trigger game end)
        game_manager.remove_player_from_game(chat_id, test_players[0].user_id)
        
        # Give a moment for async cleanup
        await asyncio.sleep(0.1)
        
        # Game should be stopped
        game_state = game_manager.get_game_status(chat_id)
        assert game_state is None or not game_state.is_active
    
    def test_game_statistics(self, game_manager, test_players):
        """Test game statistics methods."""
        # Initially no games
        assert game_manager.get_active_game_count() == 0
        assert game_manager.get_total_player_count() == 0
    
    @pytest.mark.asyncio
    async def test_concurrent_games_support(self, game_manager, test_players):
        """Test support for multiple concurrent games."""
        chat_id_1 = 12345
        chat_id_2 = 67890
        
        # Start games in different chats
        await game_manager.start_game(chat_id_1, test_players[:2])
        await game_manager.start_game(chat_id_2, test_players[1:])
        
        # Both games should be active
        assert game_manager.get_game_status(chat_id_1) is not None
        assert game_manager.get_game_status(chat_id_2) is not None
        assert game_manager.get_active_game_count() == 2
    
    def test_turn_order_management(self, game_manager, test_players):
        """Test turn order retrieval."""
        chat_id = 12345
        
        # No game initially
        turn_order = game_manager.get_turn_order(chat_id)
        assert turn_order == []
        
        # Start game and check turn order
        asyncio.run(game_manager.start_game(chat_id, test_players[:3]))
        turn_order = game_manager.get_turn_order(chat_id)
        assert len(turn_order) == 3
        assert turn_order[0] == test_players[0]  # First player should be current
    
    def test_next_player_lookup(self, game_manager, test_players):
        """Test getting next player without advancing turn."""
        chat_id = 12345
        
        # No game initially
        next_player = game_manager.get_next_player(chat_id)
        assert next_player is None
        
        # Start game and check next player
        asyncio.run(game_manager.start_game(chat_id, test_players[:3]))
        next_player = game_manager.get_next_player(chat_id)
        assert next_player == test_players[1]  # Second player should be next
        
        # Current player should not change
        game_state = game_manager.get_game_status(chat_id)
        assert game_state.get_current_player() == test_players[0]
    
    def test_player_active_status_management(self, game_manager, test_players):
        """Test setting player active/inactive status."""
        chat_id = 12345
        
        # Start game
        asyncio.run(game_manager.start_game(chat_id, test_players[:3]))
        
        # Deactivate a player
        result = game_manager.set_player_active_status(chat_id, test_players[1].user_id, False)
        assert result == True
        
        game_state = game_manager.get_game_status(chat_id)
        assert test_players[1].is_active == False
        
        # Reactivate the player
        result = game_manager.set_player_active_status(chat_id, test_players[1].user_id, True)
        assert result == True
        assert test_players[1].is_active == True
    
    def test_turn_time_tracking(self, game_manager, test_players):
        """Test turn time remaining functionality."""
        chat_id = 12345
        
        # No game initially
        remaining = game_manager.get_turn_time_remaining(chat_id)
        assert remaining is None
        
        # Start game and check time remaining
        asyncio.run(game_manager.start_game(chat_id, test_players[:2]))
        remaining = game_manager.get_turn_time_remaining(chat_id)
        
        # Should have some time remaining (close to full timeout)
        assert remaining is not None
        assert 25 <= remaining <= 30  # Allow some variance for test execution time


if __name__ == "__main__":
    pytest.main([__file__])
