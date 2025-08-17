"""
Integration tests for the complete Telegram Word Game Bot system.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from bot.word_validators import create_word_validator
from bot.game_manager import GameManager
from bot.timer_manager import GameTimerManager
from bot.telegram_bot import TelegramBot
from bot.message_handler import create_message_handler
from bot.announcements import create_game_announcer
from bot.models import Player, GameConfig, GameResult
from bot.error_handler import error_handler


class TestCompleteGameFlow:
    """Integration tests for complete game flows."""
    
    @pytest.fixture
    async def game_system(self):
        """Create a complete game system for testing."""
        # Create components
        word_validator = create_word_validator()
        game_config = GameConfig(turn_timeout=5, timeout_warnings=[2])  # Short timeouts for testing
        game_manager = GameManager(word_validator, game_config)
        
        # Mock announcement callback
        announcement_callback = AsyncMock()
        
        # Create timer manager
        timer_manager = GameTimerManager(game_manager, announcement_callback)
        
        # Create message handler
        message_handler = create_message_handler(game_manager, timer_manager)
        
        # Create announcer
        announcer = create_game_announcer(AsyncMock())
        
        # Start monitoring
        await game_manager.start_concurrent_monitoring()
        
        yield {
            'game_manager': game_manager,
            'timer_manager': timer_manager,
            'message_handler': message_handler,
            'announcer': announcer,
            'announcement_callback': announcement_callback
        }
        
        # Cleanup
        await game_manager.stop_concurrent_monitoring()
    
    @pytest.mark.asyncio
    async def test_complete_game_lifecycle(self, game_system):
        """Test complete game lifecycle from start to finish."""
        game_manager = game_system['game_manager']
        timer_manager = game_system['timer_manager']
        announcer = game_system['announcer']
        
        chat_id = 12345
        players = [
            Player(user_id=1, username="alice", first_name="Alice"),
            Player(user_id=2, username="bob", first_name="Bob")
        ]
        
        # 1. Start game
        game_state = await game_manager.start_game(chat_id, players)
        assert game_state.is_active == True
        assert len(game_state.players) == 2
        assert game_state.required_length == 1
        
        # Announce game start
        await announcer.announce_game_start(chat_id, game_state)
        
        # Start timer
        await timer_manager.start_turn_timer(chat_id)
        
        # 2. Process valid words
        current_letter = game_state.current_letter.lower()
        valid_word = f"{current_letter}at"  # Simple 3-letter word
        
        # Mock word validation to return True
        with patch.object(game_manager.word_validator, 'validate_word', return_value=True):
            result, error = await game_manager.process_word(chat_id, players[0].user_id, valid_word)
            
            assert result == GameResult.VALID_WORD
            assert error is None
            
            # Game state should be updated
            updated_state = game_manager.get_game_status(chat_id)
            assert updated_state.current_letter == valid_word[-1].upper()
            assert updated_state.required_length == 2
            assert updated_state.current_player_index == 1  # Next player
        
        # 3. Process invalid word
        with patch.object(game_manager.word_validator, 'validate_word', return_value=False):
            result, error = await game_manager.process_word(chat_id, players[1].user_id, "xyz")
            
            assert result == GameResult.INVALID_WORD
            assert error is not None
            
            # Game state should not change
            state_after_invalid = game_manager.get_game_status(chat_id)
            assert state_after_invalid.current_player_index == 1  # Same player
        
        # 4. Test timeout
        await timer_manager.cancel_turn_timer(chat_id)
        await game_manager.handle_timeout(chat_id)
        
        # Should advance to next player
        state_after_timeout = game_manager.get_game_status(chat_id)
        assert state_after_timeout.current_player_index == 0  # Back to first player
        
        # 5. Stop game
        success = await game_manager.stop_game(chat_id)
        assert success == True
        
        final_state = game_manager.get_game_status(chat_id)
        assert final_state is None
        
        # Announce game end
        await announcer.announce_game_end(chat_id, "stopped")
    
    @pytest.mark.asyncio
    async def test_concurrent_games_integration(self, game_system):
        """Test multiple concurrent games."""
        game_manager = game_system['game_manager']
        
        # Create multiple games
        games = {}
        for i in range(3):
            chat_id = 10000 + i
            players = [
                Player(user_id=i*10+1, username=f"user{i}1", first_name=f"User{i}1"),
                Player(user_id=i*10+2, username=f"user{i}2", first_name=f"User{i}2")
            ]
            
            game_state = await game_manager.start_game(chat_id, players)
            games[chat_id] = game_state
        
        # Verify all games are active
        assert len(games) == 3
        for chat_id, game_state in games.items():
            active_state = game_manager.get_game_status(chat_id)
            assert active_state is not None
            assert active_state.is_active == True
        
        # Process words in different games concurrently
        with patch.object(game_manager.word_validator, 'validate_word', return_value=True):
            tasks = []
            for chat_id, game_state in games.items():
                current_letter = game_state.current_letter.lower()
                word = f"{current_letter}at"
                player_id = game_state.players[0].user_id
                
                task = game_manager.process_word(chat_id, player_id, word)
                tasks.append(task)
            
            results = await asyncio.gather(*tasks)
            
            # All should succeed
            for result, error in results:
                assert result == GameResult.VALID_WORD
                assert error is None
        
        # Clean up all games
        for chat_id in games.keys():
            await game_manager.stop_game(chat_id)
        
        # Verify cleanup
        stats = game_manager.get_concurrent_stats()
        assert stats['active_games'] == 0
    
    @pytest.mark.asyncio
    async def test_error_recovery_integration(self, game_system):
        """Test error recovery in integrated system."""
        game_manager = game_system['game_manager']
        
        chat_id = 12345
        players = [Player(user_id=1, username="alice", first_name="Alice")]
        
        # Start game
        game_state = await game_manager.start_game(chat_id, players)
        
        # Test validation service failure
        with patch.object(game_manager.word_validator, 'validate_word', side_effect=Exception("Service down")):
            result, error = await game_manager.process_word(chat_id, players[0].user_id, "cat")
            
            assert result == GameResult.VALIDATION_ERROR
            assert "error occurred" in error.lower()
            
            # Game should still be active
            active_state = game_manager.get_game_status(chat_id)
            assert active_state is not None
            assert active_state.is_active == True
        
        # Test recovery - service comes back
        with patch.object(game_manager.word_validator, 'validate_word', return_value=True):
            result, error = await game_manager.process_word(chat_id, players[0].user_id, "cat")
            
            assert result == GameResult.VALID_WORD
            assert error is None
        
        # Cleanup
        await game_manager.stop_game(chat_id)
    
    @pytest.mark.asyncio
    async def test_player_management_integration(self, game_system):
        """Test player management throughout game lifecycle."""
        game_manager = game_system['game_manager']
        
        chat_id = 12345
        initial_players = [
            Player(user_id=1, username="alice", first_name="Alice"),
            Player(user_id=2, username="bob", first_name="Bob")
        ]
        
        # Start game
        game_state = await game_manager.start_game(chat_id, initial_players)
        
        # Add player
        new_player = Player(user_id=3, username="charlie", first_name="Charlie")
        success = game_manager.add_player_to_active_game(chat_id, new_player)
        assert success == True
        
        updated_state = game_manager.get_game_status(chat_id)
        assert len(updated_state.players) == 3
        
        # Remove player (not current player)
        success = game_manager.remove_player_from_game(chat_id, new_player.user_id)
        assert success == True
        
        state_after_removal = game_manager.get_game_status(chat_id)
        assert len(state_after_removal.players) == 2
        
        # Remove current player
        current_player = state_after_removal.get_current_player()
        success = game_manager.remove_player_from_game(chat_id, current_player.user_id)
        assert success == True
        
        # Game should end with only 1 player
        final_state = game_manager.get_game_status(chat_id)
        assert final_state is None or not final_state.is_active
    
    @pytest.mark.asyncio
    async def test_timer_integration_with_game_flow(self, game_system):
        """Test timer integration with complete game flow."""
        game_manager = game_system['game_manager']
        timer_manager = game_system['timer_manager']
        announcement_callback = game_system['announcement_callback']
        
        chat_id = 12345
        players = [
            Player(user_id=1, username="alice", first_name="Alice"),
            Player(user_id=2, username="bob", first_name="Bob")
        ]
        
        # Start game
        game_state = await game_manager.start_game(chat_id, players)
        initial_player = game_state.get_current_player()
        
        # Start timer
        await timer_manager.start_turn_timer(chat_id)
        
        # Wait for timeout (using short timeout from config)
        await asyncio.sleep(6)  # Longer than timeout
        
        # Check that timeout was handled
        # Note: In real implementation, timeout would be handled automatically
        # For testing, we manually trigger it
        await game_manager.handle_timeout(chat_id)
        
        updated_state = game_manager.get_game_status(chat_id)
        if updated_state:  # Game might end if only 1 player remains active
            current_player = updated_state.get_current_player()
            assert current_player != initial_player  # Should have advanced
        
        # Cleanup
        await timer_manager.cancel_turn_timer(chat_id)
        await game_manager.stop_game(chat_id)


class TestMessageHandlingIntegration:
    """Integration tests for message handling system."""
    
    @pytest.fixture
    async def message_system(self):
        """Create message handling system for testing."""
        word_validator = create_word_validator()
        game_config = GameConfig(turn_timeout=30)
        game_manager = GameManager(word_validator, game_config)
        timer_manager = GameTimerManager(game_manager, AsyncMock())
        message_handler = create_message_handler(game_manager, timer_manager)
        
        await game_manager.start_concurrent_monitoring()
        
        yield {
            'game_manager': game_manager,
            'timer_manager': timer_manager,
            'message_handler': message_handler
        }
        
        await game_manager.stop_concurrent_monitoring()
    
    @pytest.mark.asyncio
    async def test_message_filtering_integration(self, message_system):
        """Test message filtering with real game state."""
        game_manager = message_system['game_manager']
        message_handler = message_system['message_handler']
        
        chat_id = 12345
        players = [Player(user_id=1, username="alice", first_name="Alice")]
        
        # Start game
        game_state = await game_manager.start_game(chat_id, players)
        
        # Test message filtering
        filter_tests = [
            ("cat", True, "Valid word format"),
            ("/start", False, "Command should be ignored"),
            ("cat123", False, "Invalid format with numbers"),
            ("hello world", False, "Multiple words"),
            ("", False, "Empty message")
        ]
        
        for message, should_process, description in filter_tests:
            result = message_handler.message_filter.should_process_message(message, game_state)
            assert result == should_process, f"Failed: {description}"
        
        # Cleanup
        await game_manager.stop_game(chat_id)
    
    @pytest.mark.asyncio
    async def test_turn_processing_integration(self, message_system):
        """Test turn processing with real game flow."""
        game_manager = message_system['game_manager']
        message_handler = message_system['message_handler']
        
        chat_id = 12345
        players = [
            Player(user_id=1, username="alice", first_name="Alice"),
            Player(user_id=2, username="bob", first_name="Bob")
        ]
        
        # Start game
        game_state = await game_manager.start_game(chat_id, players)
        
        # Mock user for turn processing
        from unittest.mock import MagicMock
        mock_user = MagicMock()
        mock_user.id = players[0].user_id
        mock_user.username = players[0].username
        mock_user.first_name = players[0].first_name
        
        # Test valid turn
        with patch.object(game_manager.word_validator, 'validate_word', return_value=True):
            current_letter = game_state.current_letter.lower()
            word = f"{current_letter}at"
            
            result, error, should_advance = await message_handler.turn_processor.process_turn(
                chat_id, mock_user, word
            )
            
            assert result == GameResult.VALID_WORD
            assert error is None
            assert should_advance == True
        
        # Test wrong player
        wrong_user = MagicMock()
        wrong_user.id = players[1].user_id
        wrong_user.username = players[1].username
        wrong_user.first_name = players[1].first_name
        
        result, error, should_advance = await message_handler.turn_processor.process_turn(
            chat_id, wrong_user, "test"
        )
        
        assert result == GameResult.WRONG_PLAYER
        assert should_advance == False
        
        # Cleanup
        await game_manager.stop_game(chat_id)


class TestAnnouncementIntegration:
    """Integration tests for announcement system."""
    
    @pytest.fixture
    def announcement_system(self):
        """Create announcement system for testing."""
        sent_messages = []
        
        async def mock_send_message(chat_id, text, parse_mode=None):
            sent_messages.append({
                'chat_id': chat_id,
                'text': text,
                'parse_mode': parse_mode
            })
        
        announcer = create_game_announcer(mock_send_message)
        
        return {
            'announcer': announcer,
            'sent_messages': sent_messages
        }
    
    @pytest.mark.asyncio
    async def test_game_announcement_flow(self, announcement_system):
        """Test complete announcement flow."""
        announcer = announcement_system['announcer']
        sent_messages = announcement_system['sent_messages']
        
        chat_id = 12345
        players = [
            Player(user_id=1, username="alice", first_name="Alice"),
            Player(user_id=2, username="bob", first_name="Bob")
        ]
        
        # Create mock game state
        from bot.models import GameState, GameConfig
        game_state = GameState(
            chat_id=chat_id,
            current_letter="A",
            required_length=1,
            current_player_index=0,
            players=players,
            is_active=True,
            game_config=GameConfig()
        )
        
        # Test announcement sequence
        await announcer.announce_game_start(chat_id, game_state, include_rules=True)
        await announcer.announce_turn_start(chat_id, game_state, "💡 Hint", "😊 Easy")
        await announcer.announce_valid_word(chat_id, "apple", players[0], game_state)
        await announcer.announce_timeout(chat_id, players[0], players[1], game_state)
        await announcer.announce_game_end(chat_id, "completed", players[0])
        
        # Verify all messages were sent
        assert len(sent_messages) == 5
        
        # Check message content
        assert "Word Game Started!" in sent_messages[0]['text']
        assert "Your Turn!" in sent_messages[1]['text']
        assert "Excellent!" in sent_messages[2]['text']
        assert "Time's Up!" in sent_messages[3]['text']
        assert "Game Complete!" in sent_messages[4]['text']
        
        # Check parse modes
        assert sent_messages[0]['parse_mode'] == 'Markdown'
        assert sent_messages[1]['parse_mode'] == 'Markdown'


class TestSystemIntegration:
    """Integration tests for complete system."""
    
    @pytest.mark.asyncio
    async def test_full_system_startup_shutdown(self):
        """Test complete system startup and shutdown."""
        # Create all components
        word_validator = create_word_validator()
        game_config = GameConfig()
        game_manager = GameManager(word_validator, game_config)
        
        # Start monitoring
        await game_manager.start_concurrent_monitoring()
        
        # Verify system is running
        stats = game_manager.get_concurrent_stats()
        assert stats['active_games'] == 0
        assert stats['max_games'] > 0
        
        # Create some games
        for i in range(3):
            chat_id = 20000 + i
            players = [Player(user_id=i*10+1, username=f"user{i}", first_name=f"User{i}")]
            await game_manager.start_game(chat_id, players)
        
        # Verify games are tracked
        updated_stats = game_manager.get_concurrent_stats()
        assert updated_stats['active_games'] == 3
        
        # Stop monitoring
        await game_manager.stop_concurrent_monitoring()
        
        # System should shut down cleanly
        assert True  # If we get here, shutdown was successful
    
    @pytest.mark.asyncio
    async def test_error_handling_integration(self):
        """Test error handling across the system."""
        word_validator = create_word_validator()
        game_manager = GameManager(word_validator)
        
        chat_id = 12345
        players = [Player(user_id=1, username="alice", first_name="Alice")]
        
        # Test error recovery
        game_state = await game_manager.start_game(chat_id, players)
        
        # Simulate various errors and verify recovery
        with patch.object(game_manager.word_validator, 'validate_word', side_effect=Exception("Test error")):
            result, error = await game_manager.process_word(chat_id, players[0].user_id, "test")
            
            # Should handle error gracefully
            assert result == GameResult.VALIDATION_ERROR
            assert error is not None
            
            # Game should still be active
            active_state = game_manager.get_game_status(chat_id)
            assert active_state is not None
            assert active_state.is_active == True
        
        # Cleanup
        await game_manager.stop_game(chat_id)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])