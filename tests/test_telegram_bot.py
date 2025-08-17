"""
Unit tests for Telegram bot command handlers.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from telegram import Update, Message, Chat, User
from telegram.ext import ContextTypes

from bot.telegram_bot import TelegramBot, create_telegram_bot
from bot.game_manager import GameManager
from bot.models import Player, GameState, GameConfig, GameResult
from bot.word_validators import WordValidator


class TestTelegramBot:
    """Test cases for TelegramBot class."""
    
    @pytest.fixture
    def mock_game_manager(self):
        """Create a mock GameManager."""
        return MagicMock(spec=GameManager)
    
    @pytest.fixture
    def telegram_bot(self, mock_game_manager):
        """Create a TelegramBot instance for testing."""
        return TelegramBot(mock_game_manager)
    
    @pytest.fixture
    def mock_update(self):
        """Create a mock Telegram Update."""
        update = MagicMock(spec=Update)
        update.effective_chat = MagicMock(spec=Chat)
        update.effective_chat.id = 12345
        update.effective_chat.type = 'group'
        update.effective_user = MagicMock(spec=User)
        update.effective_user.id = 1
        update.effective_user.username = "testuser"
        update.effective_user.first_name = "Test"
        update.message = MagicMock(spec=Message)
        update.message.reply_text = AsyncMock()
        update.message.text = "test message"
        return update
    
    @pytest.fixture
    def mock_context(self):
        """Create a mock Telegram context."""
        return MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    
    @pytest.mark.asyncio
    async def test_start_game_command_success(self, telegram_bot, mock_game_manager, mock_update, mock_context):
        """Test successful game start."""
        # Mock game manager responses
        mock_game_manager.get_game_status.return_value = None  # No existing game
        
        mock_game_state = MagicMock()
        mock_game_state.current_letter = "A"
        mock_game_state.required_length = 1
        mock_game_state.get_current_player.return_value = Player(1, "testuser", "Test")
        mock_game_manager.start_game.return_value = mock_game_state
        mock_game_manager.get_word_hints.return_value = "💡 Need a 1-letter word starting with 'A'"
        
        # Mock timer manager
        telegram_bot.timer_manager.start_turn_timer = AsyncMock(return_value=True)
        
        # Execute command
        await telegram_bot.start_game_command(mock_update, mock_context)
        
        # Verify game was started
        mock_game_manager.start_game.assert_called_once()
        telegram_bot.timer_manager.start_turn_timer.assert_called_once_with(12345)
        
        # Verify response was sent
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args[0][0]
        assert "Word Game Started!" in call_args
    
    @pytest.mark.asyncio
    async def test_start_game_command_existing_game(self, telegram_bot, mock_game_manager, mock_update, mock_context):
        """Test starting game when one already exists."""
        # Mock existing active game
        mock_game_state = MagicMock()
        mock_game_state.is_active = True
        mock_game_state.current_letter = "B"
        mock_game_state.required_length = 2
        mock_game_state.get_current_player.return_value = Player(1, "testuser", "Test")
        mock_game_manager.get_game_status.return_value = mock_game_state
        
        # Execute command
        await telegram_bot.start_game_command(mock_update, mock_context)
        
        # Verify game was not started
        mock_game_manager.start_game.assert_not_called()
        
        # Verify appropriate response
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args[0][0]
        assert "already in progress" in call_args
    
    @pytest.mark.asyncio
    async def test_start_game_command_private_chat(self, telegram_bot, mock_update, mock_context):
        """Test starting game in private chat (should be rejected)."""
        mock_update.effective_chat.type = 'private'
        
        # Execute command
        await telegram_bot.start_game_command(mock_update, mock_context)
        
        # Verify appropriate response
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args[0][0]
        assert "group chats" in call_args
    
    @pytest.mark.asyncio
    async def test_stop_game_command_success(self, telegram_bot, mock_game_manager, mock_update, mock_context):
        """Test successful game stop."""
        mock_game_manager.stop_game.return_value = True
        telegram_bot.timer_manager.cancel_turn_timer = AsyncMock(return_value=True)
        
        # Execute command
        await telegram_bot.stop_game_command(mock_update, mock_context)
        
        # Verify game was stopped
        mock_game_manager.stop_game.assert_called_once_with(12345)
        telegram_bot.timer_manager.cancel_turn_timer.assert_called_once_with(12345)
        
        # Verify response
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args[0][0]
        assert "Game Stopped" in call_args
    
    @pytest.mark.asyncio
    async def test_stop_game_command_no_game(self, telegram_bot, mock_game_manager, mock_update, mock_context):
        """Test stopping game when none exists."""
        mock_game_manager.stop_game.return_value = False
        
        # Execute command
        await telegram_bot.stop_game_command(mock_update, mock_context)
        
        # Verify appropriate response
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args[0][0]
        assert "No active game" in call_args
    
    @pytest.mark.asyncio
    async def test_status_command_active_game(self, telegram_bot, mock_game_manager, mock_update, mock_context):
        """Test status command with active game."""
        # Mock active game state
        mock_game_state = MagicMock()
        mock_game_state.is_active = True
        mock_game_state.current_letter = "C"
        mock_game_state.required_length = 3
        mock_game_state.players = [
            Player(1, "player1", "Alice"),
            Player(2, "player2", "Bob")
        ]
        mock_game_state.get_current_player.return_value = mock_game_state.players[0]
        
        mock_game_manager.get_game_status.return_value = mock_game_state
        mock_game_manager.get_turn_time_remaining.return_value = 25.0
        mock_game_manager.get_word_hints.return_value = "💡 Hint"
        mock_game_manager.get_difficulty_assessment.return_value = "😊 Easy"
        
        # Execute command
        await telegram_bot.status_command(mock_update, mock_context)
        
        # Verify response contains game info
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args[0][0]
        assert "Game Status" in call_args
        assert "Alice" in call_args
        assert "C" in call_args
        assert "25s remaining" in call_args
    
    @pytest.mark.asyncio
    async def test_status_command_no_game(self, telegram_bot, mock_game_manager, mock_update, mock_context):
        """Test status command with no active game."""
        mock_game_manager.get_game_status.return_value = None
        
        # Execute command
        await telegram_bot.status_command(mock_update, mock_context)
        
        # Verify appropriate response
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args[0][0]
        assert "No Active Game" in call_args
    
    @pytest.mark.asyncio
    async def test_help_command(self, telegram_bot, mock_update, mock_context):
        """Test help command."""
        # Execute command
        await telegram_bot.help_command(mock_update, mock_context)
        
        # Verify response contains help info
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args[0][0]
        assert "Word Game Bot Help" in call_args
        assert "/startgame" in call_args
        assert "/stopgame" in call_args
        assert "/status" in call_args
    
    @pytest.mark.asyncio
    async def test_handle_message_valid_word(self, telegram_bot, mock_game_manager, mock_update, mock_context):
        """Test handling valid word submission."""
        # Mock active game
        mock_game_state = MagicMock()
        mock_game_state.is_active = True
        mock_game_state.current_letter = "C"
        mock_game_state.required_length = 4
        mock_game_state.get_current_player.return_value = Player(2, "player2", "Bob")
        
        mock_game_manager.get_game_status.return_value = mock_game_state
        mock_game_manager.process_word.return_value = (GameResult.VALID_WORD, None)
        mock_game_manager.format_word_feedback.return_value = "✅ Great! 'cats' is accepted."
        mock_game_manager.get_word_hints.return_value = "💡 Hint"
        
        telegram_bot.timer_manager.cancel_turn_timer = AsyncMock()
        telegram_bot.timer_manager.start_turn_timer = AsyncMock()
        
        mock_update.message.text = "cats"
        
        # Execute message handler
        await telegram_bot.handle_message(mock_update, mock_context)
        
        # Verify word was processed
        mock_game_manager.process_word.assert_called_once_with(12345, 1, "cats")
        
        # Verify timer operations
        telegram_bot.timer_manager.cancel_turn_timer.assert_called_once_with(12345)
        telegram_bot.timer_manager.start_turn_timer.assert_called_once_with(12345)
        
        # Verify response
        mock_update.message.reply_text.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_handle_message_invalid_word(self, telegram_bot, mock_game_manager, mock_update, mock_context):
        """Test handling invalid word submission."""
        # Mock active game
        mock_game_state = MagicMock()
        mock_game_state.is_active = True
        mock_game_manager.get_game_status.return_value = mock_game_state
        
        mock_game_manager.process_word.return_value = (GameResult.INVALID_WORD, "Not a valid word")
        mock_game_manager.format_word_feedback.return_value = "❌ Not a valid word"
        
        mock_update.message.text = "xyz"
        
        # Execute message handler
        await telegram_bot.handle_message(mock_update, mock_context)
        
        # Verify word was processed
        mock_game_manager.process_word.assert_called_once_with(12345, 1, "xyz")
        
        # Verify error response
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args[0][0]
        assert "❌" in call_args
    
    @pytest.mark.asyncio
    async def test_handle_message_no_game(self, telegram_bot, mock_game_manager, mock_update, mock_context):
        """Test handling message when no game is active."""
        mock_game_manager.get_game_status.return_value = None
        
        mock_update.message.text = "test"
        
        # Execute message handler
        await telegram_bot.handle_message(mock_update, mock_context)
        
        # Verify no processing occurred
        mock_game_manager.process_word.assert_not_called()
        mock_update.message.reply_text.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_send_announcement_timeout(self, telegram_bot):
        """Test timeout announcement."""
        # Mock application
        telegram_bot.application = MagicMock()
        telegram_bot.application.bot.send_message = AsyncMock()
        
        # Mock game state
        mock_game_state = MagicMock()
        mock_game_state.current_letter = "D"
        mock_game_state.required_length = 4
        telegram_bot.game_manager.get_game_status.return_value = mock_game_state
        telegram_bot.game_manager.get_word_hints.return_value = "💡 Hint"
        
        current_player = Player(1, "player1", "Alice")
        next_player = Player(2, "player2", "Bob")
        
        # Execute announcement
        await telegram_bot._send_announcement(
            12345, "timeout", 
            current_player=current_player, 
            next_player=next_player
        )
        
        # Verify message was sent
        telegram_bot.application.bot.send_message.assert_called_once()
        call_args = telegram_bot.application.bot.send_message.call_args
        assert call_args[1]['chat_id'] == 12345
        assert "Time's up!" in call_args[1]['text']
    
    @pytest.mark.asyncio
    async def test_send_announcement_warning(self, telegram_bot):
        """Test warning announcement."""
        # Mock application
        telegram_bot.application = MagicMock()
        telegram_bot.application.bot.send_message = AsyncMock()
        
        current_player = Player(1, "player1", "Alice")
        
        # Execute announcement
        await telegram_bot._send_announcement(
            12345, "warning", 
            current_player=current_player, 
            remaining_seconds=10
        )
        
        # Verify message was sent
        telegram_bot.application.bot.send_message.assert_called_once()
        call_args = telegram_bot.application.bot.send_message.call_args
        assert call_args[1]['chat_id'] == 12345
        assert "10 seconds left" in call_args[1]['text']
    
    @pytest.mark.asyncio
    async def test_shutdown(self, telegram_bot):
        """Test bot shutdown."""
        telegram_bot.timer_manager.cleanup = AsyncMock()
        
        # Execute shutdown
        await telegram_bot.shutdown()
        
        # Verify cleanup was called
        telegram_bot.timer_manager.cleanup.assert_called_once()
    
    def test_setup_application(self, telegram_bot):
        """Test application setup."""
        with patch('bot.telegram_bot.config') as mock_config:
            mock_config.telegram_bot_token = "test_token"
            
            # Setup application
            app = telegram_bot.setup_application()
            
            # Verify application was created
            assert app is not None
            assert telegram_bot.application == app


class TestTelegramBotFactory:
    """Test cases for Telegram bot factory function."""
    
    def test_create_telegram_bot(self):
        """Test factory function creates TelegramBot instance."""
        mock_game_manager = MagicMock(spec=GameManager)
        bot = create_telegram_bot(mock_game_manager)
        
        assert isinstance(bot, TelegramBot)
        assert bot.game_manager == mock_game_manager


if __name__ == "__main__":
    pytest.main([__file__])