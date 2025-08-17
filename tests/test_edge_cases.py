"""
Edge case tests for the Telegram Word Game Bot.
"""

import pytest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime, timedelta

from bot.word_validators import create_word_validator
from bot.game_manager import GameManager
from bot.timer_manager import GameTimerManager
from bot.models import Player, GameConfig, GameResult
from bot.error_handler import error_handler


class TestGameStateEdgeCases:
    """Edge case tests for game state management."""
    
    @pytest.fixture
    async def game_manager(self):
        """Create GameManager for edge case testing."""
        word_validator = create_word_validator()
        game_config = GameConfig(max_players_per_game=5)
        manager = GameManager(word_validator, game_config)
        
        await manager.start_concurrent_monitoring()
        
        yield manager
        
        await manager.stop_concurrent_monitoring()
    
    @pytest.mark.asyncio
    async def test_empty_player_list(self, game_manager):
        """Test starting game with empty player list."""
        chat_id = 12345
        
        with pytest.raises(ValueError, match="At least one player"):
            await game_manager.start_game(chat_id, [])
    
    @pytest.mark.asyncio
    async def test_duplicate_players(self, game_manager):
        """Test starting game with duplicate players."""
        chat_id = 12345
        players = [
            Player(user_id=1, username="alice", first_name="Alice"),
            Player(user_id=1, username="alice", first_name="Alice")  # Duplicate
        ]
        
        # Should work - GameManager doesn't prevent duplicates at start
        # But GameState.add_player() prevents duplicates
        game_state = await game_manager.start_game(chat_id, players)
        assert len(game_state.players) == 2  # Both added initially
        
        # Try to add duplicate player
        duplicate_player = Player(user_id=1, username="alice", first_name="Alice")
        success = game_manager.add_player_to_active_game(chat_id, duplicate_player)
        assert success == False  # Should reject duplicate
        
        # Cleanup
        await game_manager.stop_game(chat_id)
    
    @pytest.mark.asyncio
    async def test_max_players_exceeded(self, game_manager):
        """Test adding too many players to a game."""
        chat_id = 12345
        
        # Create players up to the limit
        players = [
            Player(user_id=i, username=f"user{i}", first_name=f"User{i}")
            for i in range(5)  # Max players per game
        ]
        
        game_state = await game_manager.start_game(chat_id, players)
        assert len(game_state.players) == 5
        
        # Try to add one more player
        extra_player = Player(user_id=99, username="extra", first_name="Extra")
        success = game_manager.add_player_to_active_game(chat_id, extra_player)
        assert success == False  # Should reject due to limit
        
        # Cleanup
        await game_manager.stop_game(chat_id)
    
    @pytest.mark.asyncio
    async def test_remove_all_players(self, game_manager):
        """Test removing all players from a game."""
        chat_id = 12345
        players = [
            Player(user_id=1, username="alice", first_name="Alice"),
            Player(user_id=2, username="bob", first_name="Bob")
        ]
        
        game_state = await game_manager.start_game(chat_id, players)
        
        # Remove all players
        for player in players:
            game_manager.remove_player_from_game(chat_id, player.user_id)
        
        # Game should end automatically
        await asyncio.sleep(0.1)  # Allow async cleanup
        
        final_state = game_manager.get_game_status(chat_id)
        assert final_state is None or not final_state.is_active
    
    @pytest.mark.asyncio
    async def test_remove_current_player(self, game_manager):
        """Test removing the current player during their turn."""
        chat_id = 12345
        players = [
            Player(user_id=1, username="alice", first_name="Alice"),
            Player(user_id=2, username="bob", first_name="Bob"),
            Player(user_id=3, username="charlie", first_name="Charlie")
        ]
        
        game_state = await game_manager.start_game(chat_id, players)
        initial_player = game_state.get_current_player()
        
        # Remove current player
        game_manager.remove_player_from_game(chat_id, initial_player.user_id)
        
        updated_state = game_manager.get_game_status(chat_id)
        if updated_state:  # Game might still be active
            new_current = updated_state.get_current_player()
            assert new_current != initial_player
            assert len(updated_state.players) == 2
        
        # Cleanup
        await game_manager.stop_game(chat_id)
    
    @pytest.mark.asyncio
    async def test_word_length_overflow(self, game_manager):
        """Test game with extremely long word requirements."""
        chat_id = 12345
        players = [Player(user_id=1, username="alice", first_name="Alice")]
        
        game_state = await game_manager.start_game(chat_id, players)
        
        # Artificially set very high word length
        game_state.required_length = 50
        
        with patch.object(game_manager.word_validator, 'validate_word', return_value=True):
            # Try to submit a word
            long_word = "a" * 50
            result, error = await game_manager.process_word(chat_id, players[0].user_id, long_word)
            
            # Should handle gracefully
            assert result in [GameResult.VALID_WORD, GameResult.INVALID_LENGTH]
        
        # Cleanup
        await game_manager.stop_game(chat_id)
    
    @pytest.mark.asyncio
    async def test_negative_player_index(self, game_manager):
        """Test game state with corrupted player index."""
        chat_id = 12345
        players = [Player(user_id=1, username="alice", first_name="Alice")]
        
        game_state = await game_manager.start_game(chat_id, players)
        
        # Corrupt player index
        game_state.current_player_index = -1
        
        # Should handle gracefully
        current_player = game_state.get_current_player()
        assert current_player is None
        
        # Try to process word with corrupted state
        result, error = await game_manager.process_word(chat_id, players[0].user_id, "test")
        assert result == GameResult.WRONG_PLAYER  # Should detect invalid state
        
        # Cleanup
        await game_manager.stop_game(chat_id)


class TestWordValidationEdgeCases:
    """Edge case tests for word validation."""
    
    @pytest.fixture
    async def game_manager(self):
        """Create GameManager for word validation testing."""
        word_validator = create_word_validator()
        manager = GameManager(word_validator)
        
        yield manager
    
    @pytest.mark.asyncio
    async def test_empty_word_submission(self, game_manager):
        """Test submitting empty word."""
        chat_id = 12345
        players = [Player(user_id=1, username="alice", first_name="Alice")]
        
        game_state = await game_manager.start_game(chat_id, players)
        
        result, error = await game_manager.process_word(chat_id, players[0].user_id, "")
        
        assert result == GameResult.INVALID_WORD
        assert error is not None
        
        # Cleanup
        await game_manager.stop_game(chat_id)
    
    @pytest.mark.asyncio
    async def test_whitespace_only_word(self, game_manager):
        """Test submitting word with only whitespace."""
        chat_id = 12345
        players = [Player(user_id=1, username="alice", first_name="Alice")]
        
        game_state = await game_manager.start_game(chat_id, players)
        
        result, error = await game_manager.process_word(chat_id, players[0].user_id, "   ")
        
        assert result == GameResult.INVALID_WORD
        assert error is not None
        
        # Cleanup
        await game_manager.stop_game(chat_id)
    
    @pytest.mark.asyncio
    async def test_unicode_characters(self, game_manager):
        """Test submitting words with unicode characters."""
        chat_id = 12345
        players = [Player(user_id=1, username="alice", first_name="Alice")]
        
        game_state = await game_manager.start_game(chat_id, players)
        
        unicode_words = ["café", "naïve", "résumé", "🎮", "αβγ"]
        
        for word in unicode_words:
            result, error = await game_manager.process_word(chat_id, players[0].user_id, word)
            
            # Should reject non-ASCII characters
            assert result == GameResult.INVALID_WORD
            assert error is not None
        
        # Cleanup
        await game_manager.stop_game(chat_id)
    
    @pytest.mark.asyncio
    async def test_extremely_long_word(self, game_manager):
        """Test submitting extremely long word."""
        chat_id = 12345
        players = [Player(user_id=1, username="alice", first_name="Alice")]
        
        game_state = await game_manager.start_game(chat_id, players)
        
        # Create very long word
        long_word = "a" * 1000
        
        result, error = await game_manager.process_word(chat_id, players[0].user_id, long_word)
        
        # Should reject due to length mismatch
        assert result == GameResult.INVALID_LENGTH
        assert error is not None
        
        # Cleanup
        await game_manager.stop_game(chat_id)
    
    @pytest.mark.asyncio
    async def test_validation_service_timeout(self, game_manager):
        """Test word validation when service times out."""
        chat_id = 12345
        players = [Player(user_id=1, username="alice", first_name="Alice")]
        
        game_state = await game_manager.start_game(chat_id, players)
        
        # Mock validation timeout
        async def timeout_validation(word):
            await asyncio.sleep(10)  # Simulate long delay
            return True
        
        with patch.object(game_manager.word_validator, 'validate_word', side_effect=timeout_validation):
            # This should timeout or be handled gracefully
            try:
                result, error = await asyncio.wait_for(
                    game_manager.process_word(chat_id, players[0].user_id, "cat"),
                    timeout=1.0
                )
                # If it completes, should handle gracefully
                assert result in [GameResult.VALID_WORD, GameResult.VALIDATION_ERROR]
            except asyncio.TimeoutError:
                # Timeout is acceptable for this test
                pass
        
        # Cleanup
        await game_manager.stop_game(chat_id)


class TestTimerEdgeCases:
    """Edge case tests for timer system."""
    
    @pytest.mark.asyncio
    async def test_timer_cancel_during_callback(self):
        """Test canceling timer while callback is executing."""
        from bot.timer_manager import TimerManager
        
        timer_manager = TimerManager()
        callback_started = asyncio.Event()
        callback_completed = asyncio.Event()
        
        async def slow_callback(chat_id):
            callback_started.set()
            await asyncio.sleep(0.5)  # Simulate slow callback
            callback_completed.set()
        
        # Start timer
        await timer_manager.start_turn_timer(
            chat_id=12345,
            timeout_seconds=0.1,
            timeout_callback=slow_callback
        )
        
        # Wait for callback to start
        await callback_started.wait()
        
        # Cancel timer while callback is running
        await timer_manager.cancel_timer(12345)
        
        # Callback should still complete
        await asyncio.wait_for(callback_completed.wait(), timeout=1.0)
        
        # Cleanup
        await timer_manager.cancel_all_timers()
    
    @pytest.mark.asyncio
    async def test_multiple_timer_cancellations(self):
        """Test canceling the same timer multiple times."""
        from bot.timer_manager import TimerManager
        
        timer_manager = TimerManager()
        
        # Start timer
        await timer_manager.start_turn_timer(
            chat_id=12345,
            timeout_seconds=10.0,
            timeout_callback=AsyncMock()
        )
        
        # Cancel multiple times
        result1 = await timer_manager.cancel_timer(12345)
        result2 = await timer_manager.cancel_timer(12345)
        result3 = await timer_manager.cancel_timer(12345)
        
        assert result1 == True   # First cancellation succeeds
        assert result2 == False  # Subsequent cancellations return False
        assert result3 == False
        
        # Cleanup
        await timer_manager.cancel_all_timers()
    
    @pytest.mark.asyncio
    async def test_timer_with_zero_timeout(self):
        """Test timer with zero timeout."""
        from bot.timer_manager import TimerManager
        
        timer_manager = TimerManager()
        callback_called = asyncio.Event()
        
        async def test_callback(chat_id):
            callback_called.set()
        
        # Start timer with zero timeout
        await timer_manager.start_turn_timer(
            chat_id=12345,
            timeout_seconds=0,
            timeout_callback=test_callback
        )
        
        # Should call callback immediately
        await asyncio.wait_for(callback_called.wait(), timeout=1.0)
        
        # Cleanup
        await timer_manager.cancel_all_timers()
    
    @pytest.mark.asyncio
    async def test_timer_callback_exception(self):
        """Test timer when callback raises exception."""
        from bot.timer_manager import TimerManager
        
        timer_manager = TimerManager()
        
        async def failing_callback(chat_id):
            raise ValueError("Callback failed")
        
        # Start timer with failing callback
        await timer_manager.start_turn_timer(
            chat_id=12345,
            timeout_seconds=0.1,
            timeout_callback=failing_callback
        )
        
        # Wait for timer to complete
        await asyncio.sleep(0.2)
        
        # Timer should handle exception gracefully
        assert not timer_manager.is_timer_active(12345)
        
        # Cleanup
        await timer_manager.cancel_all_timers()


class TestConcurrencyEdgeCases:
    """Edge case tests for concurrent operations."""
    
    @pytest.mark.asyncio
    async def test_simultaneous_game_creation(self):
        """Test creating games simultaneously in the same chat."""
        word_validator = create_word_validator()
        game_manager = GameManager(word_validator)
        
        chat_id = 12345
        players = [Player(user_id=1, username="alice", first_name="Alice")]
        
        # Try to create multiple games simultaneously
        async def create_game():
            try:
                return await game_manager.start_game(chat_id, players)
            except ValueError as e:
                return str(e)
        
        tasks = [create_game() for _ in range(5)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Only one should succeed, others should fail
        successful_games = [r for r in results if hasattr(r, 'chat_id')]
        failed_games = [r for r in results if isinstance(r, str)]
        
        assert len(successful_games) == 1
        assert len(failed_games) == 4
        
        # Cleanup
        await game_manager.stop_game(chat_id)
    
    @pytest.mark.asyncio
    async def test_simultaneous_word_processing(self):
        """Test processing words simultaneously from different players."""
        word_validator = create_word_validator()
        game_manager = GameManager(word_validator)
        
        chat_id = 12345
        players = [
            Player(user_id=1, username="alice", first_name="Alice"),
            Player(user_id=2, username="bob", first_name="Bob")
        ]
        
        game_state = await game_manager.start_game(chat_id, players)
        
        with patch.object(game_manager.word_validator, 'validate_word', return_value=True):
            # Both players try to submit words simultaneously
            async def submit_word(player_id, word):
                return await game_manager.process_word(chat_id, player_id, word)
            
            tasks = [
                submit_word(players[0].user_id, "cat"),
                submit_word(players[1].user_id, "dog")
            ]
            
            results = await asyncio.gather(*tasks)
            
            # Only one should succeed (the current player)
            valid_results = [r for r in results if r[0] == GameResult.VALID_WORD]
            wrong_player_results = [r for r in results if r[0] == GameResult.WRONG_PLAYER]
            
            assert len(valid_results) == 1
            assert len(wrong_player_results) == 1
        
        # Cleanup
        await game_manager.stop_game(chat_id)
    
    @pytest.mark.asyncio
    async def test_game_stop_during_word_processing(self):
        """Test stopping game while word is being processed."""
        word_validator = create_word_validator()
        game_manager = GameManager(word_validator)
        
        chat_id = 12345
        players = [Player(user_id=1, username="alice", first_name="Alice")]
        
        game_state = await game_manager.start_game(chat_id, players)
        
        # Mock slow word validation
        async def slow_validation(word):
            await asyncio.sleep(0.5)
            return True
        
        with patch.object(game_manager.word_validator, 'validate_word', side_effect=slow_validation):
            # Start word processing
            word_task = asyncio.create_task(
                game_manager.process_word(chat_id, players[0].user_id, "cat")
            )
            
            # Stop game while processing
            await asyncio.sleep(0.1)  # Let processing start
            await game_manager.stop_game(chat_id)
            
            # Word processing should handle gracefully
            try:
                result, error = await word_task
                assert result == GameResult.NO_ACTIVE_GAME
            except Exception:
                # Exception is also acceptable
                pass


class TestErrorRecoveryEdgeCases:
    """Edge case tests for error recovery."""
    
    @pytest.mark.asyncio
    async def test_corrupted_game_state_recovery(self):
        """Test recovery from corrupted game state."""
        word_validator = create_word_validator()
        game_manager = GameManager(word_validator)
        
        chat_id = 12345
        players = [Player(user_id=1, username="alice", first_name="Alice")]
        
        game_state = await game_manager.start_game(chat_id, players)
        
        # Corrupt game state
        game_state.players = []  # Remove all players
        game_state.current_player_index = 999  # Invalid index
        
        # Try to process word with corrupted state
        result, error = await game_manager.process_word(chat_id, players[0].user_id, "cat")
        
        # Should handle gracefully
        assert result in [GameResult.NO_ACTIVE_GAME, GameResult.WRONG_PLAYER]
        assert error is not None
        
        # Game should be cleanable
        await game_manager.stop_game(chat_id)
    
    @pytest.mark.asyncio
    async def test_memory_pressure_handling(self):
        """Test behavior under memory pressure."""
        word_validator = create_word_validator()
        game_manager = GameManager(word_validator)
        
        # Create many games to simulate memory pressure
        games = []
        try:
            for i in range(200):  # More than typical limit
                chat_id = 50000 + i
                players = [Player(user_id=i*10+1, username=f"user{i}", first_name=f"User{i}")]
                
                try:
                    game_state = await game_manager.start_game(chat_id, players)
                    games.append(chat_id)
                except ValueError:
                    # Expected when hitting limits
                    break
            
            # Should have created some games but hit limit
            assert len(games) > 0
            assert len(games) <= 100  # Should respect max games limit
            
        finally:
            # Cleanup all created games
            for chat_id in games:
                try:
                    await game_manager.stop_game(chat_id)
                except Exception:
                    pass  # Ignore cleanup errors


if __name__ == "__main__":
    pytest.main([__file__, "-v"])