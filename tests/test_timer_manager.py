"""
Unit tests for timer management system.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from bot.timer_manager import TimerManager, GameTimerManager
from bot.game_manager import GameManager
from bot.models import Player, GameConfig


class TestTimerManager:
    """Test cases for TimerManager class."""
    
    @pytest.fixture
    def timer_manager(self):
        """Create a TimerManager instance for testing."""
        return TimerManager()
    
    @pytest.mark.asyncio
    async def test_start_and_cancel_timer(self, timer_manager):
        """Test starting and cancelling a timer."""
        chat_id = 12345
        timeout_callback = AsyncMock()
        
        # Start timer
        timer_task = await timer_manager.start_turn_timer(
            chat_id=chat_id,
            timeout_seconds=2,
            timeout_callback=timeout_callback
        )
        
        assert timer_manager.is_timer_active(chat_id) == True
        assert timer_manager.get_active_timer_count() == 1
        
        # Cancel timer
        cancelled = await timer_manager.cancel_timer(chat_id)
        
        assert cancelled == True
        assert timer_manager.is_timer_active(chat_id) == False
        assert timer_manager.get_active_timer_count() == 0
        
        # Callback should not have been called
        timeout_callback.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_timer_timeout_calls_callback(self, timer_manager):
        """Test that timer calls timeout callback when it expires."""
        chat_id = 12345
        timeout_callback = AsyncMock()
        
        # Start short timer
        await timer_manager.start_turn_timer(
            chat_id=chat_id,
            timeout_seconds=0.1,  # Very short timeout
            timeout_callback=timeout_callback
        )
        
        # Wait for timer to expire
        await asyncio.sleep(0.2)
        
        # Callback should have been called
        timeout_callback.assert_called_once_with(chat_id)
        assert timer_manager.is_timer_active(chat_id) == False
    
    @pytest.mark.asyncio
    async def test_warning_callbacks(self, timer_manager):
        """Test that warning callbacks are called at correct times."""
        chat_id = 12345
        timeout_callback = AsyncMock()
        warning_callback = AsyncMock()
        
        # Start timer with warnings
        await timer_manager.start_turn_timer(
            chat_id=chat_id,
            timeout_seconds=0.3,
            timeout_callback=timeout_callback,
            warning_callback=warning_callback,
            warning_times=[0.2, 0.1]  # Warnings at 0.2s and 0.1s remaining
        )
        
        # Wait for warnings and timeout
        await asyncio.sleep(0.4)
        
        # Should have called warning callback twice and timeout once
        assert warning_callback.call_count >= 1  # At least one warning
        timeout_callback.assert_called_once_with(chat_id)
    
    @pytest.mark.asyncio
    async def test_multiple_concurrent_timers(self, timer_manager):
        """Test managing multiple concurrent timers."""
        chat_id_1 = 12345
        chat_id_2 = 67890
        callback_1 = AsyncMock()
        callback_2 = AsyncMock()
        
        # Start two timers
        await timer_manager.start_turn_timer(chat_id_1, 0.1, callback_1)
        await timer_manager.start_turn_timer(chat_id_2, 0.2, callback_2)
        
        assert timer_manager.get_active_timer_count() == 2
        
        # Wait for first timer to expire
        await asyncio.sleep(0.15)
        
        # First callback should be called, second should not
        callback_1.assert_called_once()
        callback_2.assert_not_called()
        
        # Wait for second timer
        await asyncio.sleep(0.1)
        callback_2.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_replace_existing_timer(self, timer_manager):
        """Test that starting a new timer cancels the existing one."""
        chat_id = 12345
        callback_1 = AsyncMock()
        callback_2 = AsyncMock()
        
        # Start first timer
        await timer_manager.start_turn_timer(chat_id, 1.0, callback_1)
        
        # Start second timer (should cancel first)
        await timer_manager.start_turn_timer(chat_id, 0.1, callback_2)
        
        # Wait for second timer to expire
        await asyncio.sleep(0.2)
        
        # Only second callback should be called
        callback_1.assert_not_called()
        callback_2.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_cancel_nonexistent_timer(self, timer_manager):
        """Test cancelling a timer that doesn't exist."""
        result = await timer_manager.cancel_timer(99999)
        assert result == False
    
    @pytest.mark.asyncio
    async def test_cleanup_completed_timers(self, timer_manager):
        """Test cleanup of completed timer tasks."""
        chat_id = 12345
        callback = AsyncMock()
        
        # Start and let timer complete
        await timer_manager.start_turn_timer(chat_id, 0.1, callback)
        await asyncio.sleep(0.2)
        
        # Timer should be completed but still tracked
        assert len(timer_manager._active_timers) == 1
        
        # Cleanup should remove it
        await timer_manager.cleanup_completed_timers()
        assert len(timer_manager._active_timers) == 0
    
    @pytest.mark.asyncio
    async def test_cancel_all_timers(self, timer_manager):
        """Test cancelling all active timers."""
        callback_1 = AsyncMock()
        callback_2 = AsyncMock()
        
        # Start multiple timers
        await timer_manager.start_turn_timer(12345, 1.0, callback_1)
        await timer_manager.start_turn_timer(67890, 1.0, callback_2)
        
        assert timer_manager.get_active_timer_count() == 2
        
        # Cancel all
        await timer_manager.cancel_all_timers()
        
        assert timer_manager.get_active_timer_count() == 0
        callback_1.assert_not_called()
        callback_2.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_error_handling_in_callbacks(self, timer_manager):
        """Test that errors in callbacks don't crash the timer."""
        chat_id = 12345
        
        def failing_callback(chat_id):
            raise Exception("Test error")
        
        # Start timer with failing callback
        await timer_manager.start_turn_timer(chat_id, 0.1, failing_callback)
        
        # Wait for timer to expire - should not raise exception
        await asyncio.sleep(0.2)
        
        # Timer should be cleaned up despite callback error
        assert timer_manager.is_timer_active(chat_id) == False


class TestGameTimerManager:
    """Test cases for GameTimerManager class."""
    
    @pytest.fixture
    def mock_game_manager(self):
        """Create a mock GameManager."""
        return MagicMock(spec=GameManager)
    
    @pytest.fixture
    def mock_announcement_callback(self):
        """Create a mock announcement callback."""
        return AsyncMock()
    
    @pytest.fixture
    def game_timer_manager(self, mock_game_manager, mock_announcement_callback):
        """Create a GameTimerManager instance for testing."""
        return GameTimerManager(mock_game_manager, mock_announcement_callback)
    
    @pytest.fixture
    def mock_game_state(self):
        """Create a mock game state."""
        game_state = MagicMock()
        game_state.is_active = True
        game_state.timer_task = None
        game_state.game_config = GameConfig(turn_timeout=30, timeout_warnings=[10, 5])
        
        # Mock players
        current_player = Player(user_id=1, username="player1", first_name="Alice")
        next_player = Player(user_id=2, username="player2", first_name="Bob")
        game_state.get_current_player.return_value = current_player
        
        return game_state
    
    @pytest.mark.asyncio
    async def test_start_turn_timer_success(self, game_timer_manager, mock_game_manager, mock_game_state):
        """Test successfully starting a turn timer."""
        chat_id = 12345
        mock_game_manager.get_game_status.return_value = mock_game_state
        
        result = await game_timer_manager.start_turn_timer(chat_id)
        
        assert result == True
        assert mock_game_state.timer_task is not None
    
    @pytest.mark.asyncio
    async def test_start_timer_no_active_game(self, game_timer_manager, mock_game_manager):
        """Test starting timer when no active game exists."""
        chat_id = 12345
        mock_game_manager.get_game_status.return_value = None
        
        result = await game_timer_manager.start_turn_timer(chat_id)
        
        assert result == False
    
    @pytest.mark.asyncio
    async def test_start_timer_inactive_game(self, game_timer_manager, mock_game_manager, mock_game_state):
        """Test starting timer for inactive game."""
        chat_id = 12345
        mock_game_state.is_active = False
        mock_game_manager.get_game_status.return_value = mock_game_state
        
        result = await game_timer_manager.start_turn_timer(chat_id)
        
        assert result == False
    
    @pytest.mark.asyncio
    async def test_cancel_turn_timer(self, game_timer_manager, mock_game_manager, mock_game_state):
        """Test cancelling a turn timer."""
        chat_id = 12345
        mock_game_manager.get_game_status.return_value = mock_game_state
        
        # Start timer first
        await game_timer_manager.start_turn_timer(chat_id)
        
        # Cancel timer
        result = await game_timer_manager.cancel_turn_timer(chat_id)
        
        assert result == True
        assert mock_game_state.timer_task is None
    
    @pytest.mark.asyncio
    async def test_timeout_handling(self, game_timer_manager, mock_game_manager, mock_game_state, mock_announcement_callback):
        """Test timeout handling calls game manager and sends announcements."""
        chat_id = 12345
        mock_game_manager.get_game_status.return_value = mock_game_state
        mock_game_manager.handle_timeout = AsyncMock()
        
        # Simulate timeout
        await game_timer_manager._handle_timeout(chat_id)
        
        # Should call game manager timeout handler
        mock_game_manager.handle_timeout.assert_called_once_with(chat_id)
        
        # Should call announcement callback
        mock_announcement_callback.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_warning_handling(self, game_timer_manager, mock_game_manager, mock_game_state, mock_announcement_callback):
        """Test warning handling sends announcements."""
        chat_id = 12345
        remaining_seconds = 10
        mock_game_manager.get_game_status.return_value = mock_game_state
        
        # Simulate warning
        await game_timer_manager._handle_warning(chat_id, remaining_seconds)
        
        # Should call announcement callback with warning
        mock_announcement_callback.assert_called_once_with(
            chat_id, 
            "warning", 
            current_player=mock_game_state.get_current_player(),
            remaining_seconds=remaining_seconds
        )
    
    @pytest.mark.asyncio
    async def test_cleanup(self, game_timer_manager):
        """Test cleanup cancels all timers."""
        # Start a timer
        chat_id = 12345
        mock_game_state = MagicMock()
        mock_game_state.is_active = True
        mock_game_state.timer_task = None
        mock_game_state.game_config = GameConfig()
        
        game_timer_manager.game_manager.get_game_status.return_value = mock_game_state
        
        await game_timer_manager.start_turn_timer(chat_id)
        
        # Cleanup should cancel all timers
        await game_timer_manager.cleanup()
        
        assert game_timer_manager.timer_manager.get_active_timer_count() == 0
    
    @pytest.mark.asyncio
    async def test_error_handling_in_timeout(self, game_timer_manager, mock_game_manager):
        """Test error handling in timeout callback."""
        chat_id = 12345
        mock_game_manager.get_game_status.side_effect = Exception("Test error")
        
        # Should not raise exception
        await game_timer_manager._handle_timeout(chat_id)
    
    @pytest.mark.asyncio
    async def test_error_handling_in_warning(self, game_timer_manager, mock_announcement_callback):
        """Test error handling in warning callback."""
        chat_id = 12345
        mock_announcement_callback.side_effect = Exception("Test error")
        
        # Should not raise exception
        await game_timer_manager._handle_warning(chat_id, 10)


if __name__ == "__main__":
    pytest.main([__file__])