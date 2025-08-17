"""
Unit tests for message handling and turn processing.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from telegram import Update, Message, Chat, User

from bot.message_handler import (
    MessageFilter, 
    TurnProcessor, 
    MessageResponseFormatter,
    AdvancedMessageHandler,
    create_message_handler
)
from bot.game_manager import GameManager
from bot.timer_manager import GameTimerManager
from bot.models import Player, GameState, GameConfig, GameResult


class TestMessageFilter:
    """Test cases for MessageFilter class."""
    
    @pytest.fixture
    def message_filter(self):
        """Create a MessageFilter instance."""
        return MessageFilter()
    
    def test_is_potential_word_valid(self, message_filter):
        """Test detection of valid potential words."""
        assert message_filter.is_potential_word("cat") == True
        assert message_filter.is_potential_word("hello") == True
        assert message_filter.is_potential_word("WORD") == True
        assert message_filter.is_potential_word("a") == True
    
    def test_is_potential_word_invalid(self, message_filter):
        """Test rejection of invalid potential words."""
        assert message_filter.is_potential_word("") == False
        assert message_filter.is_potential_word("cat123") == False
        assert message_filter.is_potential_word("hello world") == False
        assert message_filter.is_potential_word("cat!") == False
        assert message_filter.is_potential_word("@user") == False
        assert message_filter.is_potential_word("verylongwordthatexceedslimit") == False
    
    def test_is_command(self, message_filter):
        """Test command detection."""
        assert message_filter.is_command("/start") == True
        assert message_filter.is_command("/help") == True
        assert message_filter.is_command("  /status  ") == True
        assert message_filter.is_command("hello") == False
        assert message_filter.is_command("") == False
    
    def test_extract_word(self, message_filter):
        """Test word extraction from messages."""
        assert message_filter.extract_word("cat") == "cat"
        assert message_filter.extract_word("HELLO") == "hello"
        assert message_filter.extract_word("  word  ") == "word"
        assert message_filter.extract_word("@user hello") == "hello"
        assert message_filter.extract_word("cat123") == None
        assert message_filter.extract_word("") == None
    
    def test_should_process_message(self, message_filter):
        """Test message processing decision."""
        # Mock game state
        active_game = MagicMock()
        active_game.is_active = True
        
        inactive_game = MagicMock()
        inactive_game.is_active = False
        
        # Valid word with active game
        assert message_filter.should_process_message("cat", active_game) == True
        
        # Command should not be processed
        assert message_filter.should_process_message("/start", active_game) == False
        
        # Invalid word should not be processed
        assert message_filter.should_process_message("cat123", active_game) == False
        
        # No game should not be processed
        assert message_filter.should_process_message("cat", None) == False
        
        # Inactive game should not be processed
        assert message_filter.should_process_message("cat", inactive_game) == False


class TestTurnProcessor:
    """Test cases for TurnProcessor class."""
    
    @pytest.fixture
    def mock_game_manager(self):
        """Create a mock GameManager."""
        return MagicMock(spec=GameManager)
    
    @pytest.fixture
    def mock_timer_manager(self):
        """Create a mock GameTimerManager."""
        return MagicMock(spec=GameTimerManager)
    
    @pytest.fixture
    def turn_processor(self, mock_game_manager, mock_timer_manager):
        """Create a TurnProcessor instance."""
        return TurnProcessor(mock_game_manager, mock_timer_manager)
    
    @pytest.fixture
    def mock_user(self):
        """Create a mock Telegram user."""
        user = MagicMock(spec=User)
        user.id = 1
        user.username = "testuser"
        user.first_name = "Test"
        return user
    
    @pytest.fixture
    def mock_game_state(self):
        """Create a mock game state."""
        game_state = MagicMock()
        game_state.is_active = True
        
        current_player = Player(1, "testuser", "Test")
        game_state.get_current_player.return_value = current_player
        game_state.players = [current_player, Player(2, "other", "Other")]
        
        return game_state
    
    @pytest.mark.asyncio
    async def test_process_turn_valid_word(self, turn_processor, mock_game_manager, mock_user, mock_game_state):
        """Test processing valid word submission."""
        mock_game_manager.get_game_status.return_value = mock_game_state
        mock_game_manager.process_word.return_value = (GameResult.VALID_WORD, None)
        
        result, error, should_advance = await turn_processor.process_turn(12345, mock_user, "cat")
        
        assert result == GameResult.VALID_WORD
        assert error is None
        assert should_advance == True
        mock_game_manager.process_word.assert_called_once_with(12345, 1, "cat")
    
    @pytest.mark.asyncio
    async def test_process_turn_invalid_word(self, turn_processor, mock_game_manager, mock_user, mock_game_state):
        """Test processing invalid word submission."""
        mock_game_manager.get_game_status.return_value = mock_game_state
        mock_game_manager.process_word.return_value = (GameResult.INVALID_WORD, "Not a valid word")
        
        result, error, should_advance = await turn_processor.process_turn(12345, mock_user, "xyz")
        
        assert result == GameResult.INVALID_WORD
        assert error == "Not a valid word"
        assert should_advance == False
    
    @pytest.mark.asyncio
    async def test_process_turn_wrong_player(self, turn_processor, mock_game_manager, mock_game_state):
        """Test processing word from wrong player."""
        mock_game_manager.get_game_status.return_value = mock_game_state
        
        # Different user (not current player)
        wrong_user = MagicMock(spec=User)
        wrong_user.id = 2
        
        result, error, should_advance = await turn_processor.process_turn(12345, wrong_user, "cat")
        
        assert result == GameResult.WRONG_PLAYER
        assert "It's @testuser's turn" in error
        assert should_advance == False
    
    @pytest.mark.asyncio
    async def test_process_turn_user_not_in_game(self, turn_processor, mock_game_manager, mock_game_state):
        """Test processing word from user not in game."""
        mock_game_manager.get_game_status.return_value = mock_game_state
        
        # User not in game
        outsider_user = MagicMock(spec=User)
        outsider_user.id = 999
        
        result, error, should_advance = await turn_processor.process_turn(12345, outsider_user, "cat")
        
        assert result == GameResult.WRONG_PLAYER
        assert error is None  # Silent ignore for users not in game
        assert should_advance == False
    
    @pytest.mark.asyncio
    async def test_process_turn_no_game(self, turn_processor, mock_game_manager, mock_user):
        """Test processing word when no game exists."""
        mock_game_manager.get_game_status.return_value = None
        
        result, error, should_advance = await turn_processor.process_turn(12345, mock_user, "cat")
        
        assert result == GameResult.NO_ACTIVE_GAME
        assert "No active game" in error
        assert should_advance == False
    
    @pytest.mark.asyncio
    async def test_handle_turn_advancement(self, turn_processor, mock_game_manager, mock_timer_manager, mock_game_state):
        """Test turn advancement handling."""
        mock_game_manager.get_game_status.return_value = mock_game_state
        mock_timer_manager.cancel_turn_timer = AsyncMock()
        mock_timer_manager.start_turn_timer = AsyncMock()
        
        result = await turn_processor.handle_turn_advancement(12345)
        
        assert result == mock_game_state
        mock_timer_manager.cancel_turn_timer.assert_called_once_with(12345)
        mock_timer_manager.start_turn_timer.assert_called_once_with(12345)
    
    def test_get_turn_context(self, turn_processor, mock_game_manager, mock_game_state):
        """Test getting turn context information."""
        mock_game_state.current_letter = "C"
        mock_game_state.required_length = 3
        mock_game_state.get_next_player.return_value = Player(2, "next", "Next")
        
        mock_game_manager.get_game_status.return_value = mock_game_state
        mock_game_manager.get_turn_time_remaining.return_value = 25.0
        mock_game_manager.get_word_hints.return_value = "💡 Hint"
        mock_game_manager.get_difficulty_assessment.return_value = "😊 Easy"
        
        context = turn_processor.get_turn_context(12345)
        
        assert context is not None
        assert context['letter'] == "C"
        assert context['length'] == 3
        assert context['remaining_time'] == 25.0
        assert context['hints'] == "💡 Hint"
        assert context['difficulty'] == "😊 Easy"


class TestMessageResponseFormatter:
    """Test cases for MessageResponseFormatter class."""
    
    @pytest.fixture
    def mock_game_manager(self):
        """Create a mock GameManager."""
        return MagicMock(spec=GameManager)
    
    @pytest.fixture
    def response_formatter(self, mock_game_manager):
        """Create a MessageResponseFormatter instance."""
        return MessageResponseFormatter(mock_game_manager)
    
    @pytest.fixture
    def mock_game_state(self):
        """Create a mock game state."""
        game_state = MagicMock()
        game_state.current_letter = "T"
        game_state.required_length = 4
        game_state.get_current_player.return_value = Player(2, "next", "Next")
        return game_state
    
    def test_format_valid_word_response(self, response_formatter, mock_game_state):
        """Test formatting valid word response."""
        response = response_formatter.format_valid_word_response("cat", mock_game_state, "💡 Hint")
        
        assert "✅" in response
        assert "cat" in response
        assert "Next" in response
        assert "T" in response
        assert "4" in response
        assert "💡 Hint" in response
    
    def test_format_error_response(self, response_formatter, mock_game_manager):
        """Test formatting error response."""
        mock_game_manager.format_word_feedback.return_value = "❌ Error message"
        
        response = response_formatter.format_error_response(
            GameResult.INVALID_WORD, "Error message", "xyz"
        )
        
        assert response == "❌ Error message"
        mock_game_manager.format_word_feedback.assert_called_once_with(
            GameResult.INVALID_WORD, "Error message", "xyz"
        )
    
    def test_format_turn_reminder(self, response_formatter):
        """Test formatting turn reminder."""
        player = Player(1, "user", "User")
        context = {
            'letter': 'A',
            'length': 2,
            'hints': '💡 Hint'
        }
        
        response = response_formatter.format_turn_reminder(player, context)
        
        assert "⏰" in response
        assert "User" in response
        assert "A" in response
        assert "2" in response
        assert "💡 Hint" in response
    
    def test_format_game_progress(self, response_formatter):
        """Test formatting game progress."""
        game_state = MagicMock()
        game_state.current_letter = "B"
        game_state.required_length = 3
        game_state.current_player_index = 1
        game_state.players = [
            Player(1, "player1", "Alice"),
            Player(2, "player2", "Bob")
        ]
        game_state.get_current_player.return_value = game_state.players[1]
        
        response = response_formatter.format_game_progress(game_state)
        
        assert "🎮 Game Progress" in response
        assert "Bob" in response
        assert "B" in response
        assert "3" in response
        assert "👉" in response  # Current player indicator


class TestAdvancedMessageHandler:
    """Test cases for AdvancedMessageHandler class."""
    
    @pytest.fixture
    def mock_game_manager(self):
        """Create a mock GameManager."""
        return MagicMock(spec=GameManager)
    
    @pytest.fixture
    def mock_timer_manager(self):
        """Create a mock GameTimerManager."""
        return MagicMock(spec=GameTimerManager)
    
    @pytest.fixture
    def message_handler(self, mock_game_manager, mock_timer_manager):
        """Create an AdvancedMessageHandler instance."""
        return AdvancedMessageHandler(mock_game_manager, mock_timer_manager)
    
    @pytest.fixture
    def mock_update(self):
        """Create a mock Telegram Update."""
        update = MagicMock(spec=Update)
        update.effective_chat = MagicMock()
        update.effective_chat.id = 12345
        update.effective_user = MagicMock()
        update.effective_user.id = 1
        update.message = MagicMock()
        update.message.text = "cat"
        update.message.reply_text = AsyncMock()
        return update
    
    @pytest.mark.asyncio
    async def test_handle_message_valid_word(self, message_handler, mock_update):
        """Test handling valid word message."""
        # Mock the turn processor
        message_handler.turn_processor.process_turn = AsyncMock(
            return_value=(GameResult.VALID_WORD, None, True)
        )
        message_handler.turn_processor.handle_turn_advancement = AsyncMock(
            return_value=MagicMock()
        )
        message_handler.game_manager.get_word_hints.return_value = "💡 Hint"
        
        # Execute
        await message_handler.handle_message(mock_update, None)
        
        # Verify processing occurred
        message_handler.turn_processor.process_turn.assert_called_once()
        message_handler.turn_processor.handle_turn_advancement.assert_called_once()
        mock_update.message.reply_text.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_handle_message_invalid_word(self, message_handler, mock_update):
        """Test handling invalid word message."""
        # Mock the turn processor
        message_handler.turn_processor.process_turn = AsyncMock(
            return_value=(GameResult.INVALID_WORD, "Not valid", False)
        )
        
        # Execute
        await message_handler.handle_message(mock_update, None)
        
        # Verify error response
        message_handler.turn_processor.process_turn.assert_called_once()
        mock_update.message.reply_text.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_handle_message_command_ignored(self, message_handler, mock_update):
        """Test that commands are ignored."""
        mock_update.message.text = "/start"
        
        # Mock game state
        message_handler.game_manager.get_game_status.return_value = MagicMock()
        
        # Execute
        await message_handler.handle_message(mock_update, None)
        
        # Verify no processing occurred
        mock_update.message.reply_text.assert_not_called()
    
    def test_get_message_stats(self, message_handler, mock_game_manager):
        """Test getting message statistics."""
        mock_game_manager.get_active_game_count.return_value = 5
        mock_game_manager.get_total_player_count.return_value = 15
        
        stats = message_handler.get_message_stats()
        
        assert stats['active_games'] == 5
        assert stats['total_players'] == 15


class TestMessageHandlerFactory:
    """Test cases for message handler factory function."""
    
    def test_create_message_handler(self):
        """Test factory function creates AdvancedMessageHandler."""
        mock_game_manager = MagicMock(spec=GameManager)
        mock_timer_manager = MagicMock(spec=GameTimerManager)
        
        handler = create_message_handler(mock_game_manager, mock_timer_manager)
        
        assert isinstance(handler, AdvancedMessageHandler)
        assert handler.game_manager == mock_game_manager
        assert handler.timer_manager == mock_timer_manager


if __name__ == "__main__":
    pytest.main([__file__])