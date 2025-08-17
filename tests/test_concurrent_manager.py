"""
Unit tests for concurrent game management system.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

from bot.concurrent_manager import (
    ResourceStatus,
    GameMetrics,
    SystemMetrics,
    ResourceMonitor,
    ConcurrentGameManager,
    ChatIsolationManager,
    create_concurrent_manager
)
from bot.models import GameState, Player, GameConfig


class TestGameMetrics:
    """Test cases for GameMetrics class."""
    
    def test_game_metrics_creation(self):
        """Test creating GameMetrics instance."""
        metrics = GameMetrics(
            chat_id=12345,
            player_count=3,
            game_duration=timedelta(minutes=15),
            turn_count=10,
            words_submitted=8,
            timeouts=2,
            errors=1,
            last_activity=datetime.now()
        )
        
        assert metrics.chat_id == 12345
        assert metrics.player_count == 3
        assert metrics.turn_count == 10
        assert metrics.words_submitted == 8
        assert metrics.timeouts == 2
        assert metrics.errors == 1
    
    def test_game_metrics_to_dict(self):
        """Test converting GameMetrics to dictionary."""
        now = datetime.now()
        metrics = GameMetrics(
            chat_id=12345,
            player_count=3,
            game_duration=timedelta(minutes=15),
            turn_count=10,
            words_submitted=8,
            timeouts=2,
            errors=1,
            last_activity=now
        )
        
        result = metrics.to_dict()
        
        assert result['chat_id'] == 12345
        assert result['player_count'] == 3
        assert result['game_duration_seconds'] == 900  # 15 minutes
        assert result['turn_count'] == 10
        assert result['words_submitted'] == 8
        assert result['timeouts'] == 2
        assert result['errors'] == 1
        assert result['last_activity'] == now.isoformat()


class TestSystemMetrics:
    """Test cases for SystemMetrics class."""
    
    def test_system_metrics_creation(self):
        """Test creating SystemMetrics instance."""
        metrics = SystemMetrics(
            total_games=50,
            active_games=10,
            total_players=25,
            memory_usage_mb=125.5,
            cpu_usage_percent=15.2,
            uptime_seconds=3600,
            games_per_hour=12.5,
            average_game_duration=300.0
        )
        
        assert metrics.total_games == 50
        assert metrics.active_games == 10
        assert metrics.total_players == 25
        assert metrics.memory_usage_mb == 125.5
        assert metrics.cpu_usage_percent == 15.2
    
    def test_system_metrics_to_dict(self):
        """Test converting SystemMetrics to dictionary."""
        metrics = SystemMetrics(
            total_games=50,
            active_games=10,
            total_players=25,
            memory_usage_mb=125.5,
            cpu_usage_percent=15.2,
            uptime_seconds=3600,
            games_per_hour=12.5,
            average_game_duration=300.0
        )
        
        result = metrics.to_dict()
        
        assert result['total_games'] == 50
        assert result['active_games'] == 10
        assert result['total_players'] == 25
        assert result['memory_usage_mb'] == 125.5
        assert result['cpu_usage_percent'] == 15.2


class TestResourceMonitor:
    """Test cases for ResourceMonitor class."""
    
    @pytest.fixture
    def resource_monitor(self):
        """Create a ResourceMonitor instance."""
        return ResourceMonitor(max_games=10, max_players_per_game=5)
    
    def test_get_resource_status(self, resource_monitor):
        """Test resource status calculation."""
        # Low usage (0-40%)
        assert resource_monitor.get_resource_status(2, 10) == ResourceStatus.LOW
        
        # Medium usage (40-70%)
        assert resource_monitor.get_resource_status(5, 20) == ResourceStatus.MEDIUM
        
        # High usage (70-90%)
        assert resource_monitor.get_resource_status(8, 30) == ResourceStatus.HIGH
        
        # Critical usage (90%+)
        assert resource_monitor.get_resource_status(9, 40) == ResourceStatus.CRITICAL
    
    def test_can_create_game_success(self, resource_monitor):
        """Test successful game creation check."""
        can_create, reason = resource_monitor.can_create_game(5, 3)
        
        assert can_create == True
        assert reason is None
    
    def test_can_create_game_max_games_reached(self, resource_monitor):
        """Test game creation when max games reached."""
        can_create, reason = resource_monitor.can_create_game(10, 3)
        
        assert can_create == False
        assert "Maximum concurrent games limit reached" in reason
    
    def test_can_create_game_too_many_players(self, resource_monitor):
        """Test game creation with too many players."""
        can_create, reason = resource_monitor.can_create_game(5, 8)
        
        assert can_create == False
        assert "Too many players for one game" in reason
    
    def test_can_create_game_critical_resources(self, resource_monitor):
        """Test game creation when resources are critical."""
        can_create, reason = resource_monitor.can_create_game(9, 3)  # 90% usage
        
        assert can_create == False
        assert "System resources are critically low" in reason
    
    def test_update_game_metrics(self, resource_monitor):
        """Test updating game metrics."""
        players = [Player(1, "user1", "User1"), Player(2, "user2", "User2")]
        game_state = GameState(
            chat_id=12345,
            current_letter="A",
            required_length=3,
            current_player_index=0,
            players=players,
            turn_start_time=datetime.now()
        )
        
        resource_monitor.update_game_metrics(12345, game_state, words_submitted=2, timeouts=1)
        
        assert 12345 in resource_monitor.game_metrics
        metrics = resource_monitor.game_metrics[12345]
        assert metrics.chat_id == 12345
        assert metrics.player_count == 2
        assert metrics.words_submitted == 2
        assert metrics.timeouts == 1
    
    def test_remove_game_metrics(self, resource_monitor):
        """Test removing game metrics."""
        # Add a game first
        players = [Player(1, "user1", "User1")]
        game_state = GameState(
            chat_id=12345,
            current_letter="A",
            required_length=1,
            current_player_index=0,
            players=players
        )
        
        resource_monitor.update_game_metrics(12345, game_state)
        assert 12345 in resource_monitor.game_metrics
        
        # Remove the game
        resource_monitor.remove_game_metrics(12345)
        assert 12345 not in resource_monitor.game_metrics
        assert resource_monitor.historical_games == 1
    
    def test_get_system_metrics(self, resource_monitor):
        """Test getting system metrics."""
        # Add some game metrics
        players = [Player(1, "user1", "User1"), Player(2, "user2", "User2")]
        game_state = GameState(
            chat_id=12345,
            current_letter="A",
            required_length=1,
            current_player_index=0,
            players=players
        )
        
        resource_monitor.update_game_metrics(12345, game_state)
        
        active_games = {12345: game_state}
        metrics = resource_monitor.get_system_metrics(active_games)
        
        assert metrics.active_games == 1
        assert metrics.total_players == 2
        assert metrics.total_games >= 1
        assert metrics.uptime_seconds > 0
    
    def test_get_inactive_games(self, resource_monitor):
        """Test getting inactive games."""
        # Add a game with old activity
        players = [Player(1, "user1", "User1")]
        game_state = GameState(
            chat_id=12345,
            current_letter="A",
            required_length=1,
            current_player_index=0,
            players=players
        )
        
        resource_monitor.update_game_metrics(12345, game_state)
        
        # Make it appear old
        resource_monitor.game_metrics[12345].last_activity = datetime.now() - timedelta(hours=2)
        
        active_games = {12345: game_state}
        inactive = resource_monitor.get_inactive_games(active_games, timeout_minutes=60)
        
        assert 12345 in inactive
    
    def test_resource_warnings(self, resource_monitor):
        """Test resource warning management."""
        warning1 = "High memory usage"
        warning2 = "CPU usage critical"
        
        resource_monitor.add_resource_warning(warning1)
        resource_monitor.add_resource_warning(warning2)
        
        warnings = resource_monitor.get_resource_warnings(24)
        assert len(warnings) == 2
        assert any(warning1 in w for w in warnings)
        assert any(warning2 in w for w in warnings)


class TestConcurrentGameManager:
    """Test cases for ConcurrentGameManager class."""
    
    @pytest.fixture
    def concurrent_manager(self):
        """Create a ConcurrentGameManager instance."""
        return ConcurrentGameManager(max_games=5, max_players_per_game=3)
    
    def test_can_create_game(self, concurrent_manager):
        """Test game creation validation."""
        active_games = {}
        
        can_create, reason = concurrent_manager.can_create_game(active_games, 2)
        assert can_create == True
        assert reason is None
    
    def test_register_game_start(self, concurrent_manager):
        """Test registering game start."""
        players = [Player(1, "user1", "User1"), Player(2, "user2", "User2")]
        game_state = GameState(
            chat_id=12345,
            current_letter="A",
            required_length=1,
            current_player_index=0,
            players=players
        )
        
        concurrent_manager.register_game_start(12345, game_state)
        
        assert 12345 in concurrent_manager.resource_monitor.game_metrics
    
    def test_register_game_activity(self, concurrent_manager):
        """Test registering game activity."""
        players = [Player(1, "user1", "User1")]
        game_state = GameState(
            chat_id=12345,
            current_letter="A",
            required_length=1,
            current_player_index=0,
            players=players
        )
        
        concurrent_manager.register_game_start(12345, game_state)
        concurrent_manager.register_game_activity(12345, game_state, words_submitted=1)
        
        metrics = concurrent_manager.resource_monitor.game_metrics[12345]
        assert metrics.words_submitted == 1
    
    def test_register_game_end(self, concurrent_manager):
        """Test registering game end."""
        players = [Player(1, "user1", "User1")]
        game_state = GameState(
            chat_id=12345,
            current_letter="A",
            required_length=1,
            current_player_index=0,
            players=players
        )
        
        concurrent_manager.register_game_start(12345, game_state)
        assert 12345 in concurrent_manager.resource_monitor.game_metrics
        
        concurrent_manager.register_game_end(12345)
        assert 12345 not in concurrent_manager.resource_monitor.game_metrics
    
    def test_get_system_status(self, concurrent_manager):
        """Test getting system status."""
        players = [Player(1, "user1", "User1")]
        game_state = GameState(
            chat_id=12345,
            current_letter="A",
            required_length=1,
            current_player_index=0,
            players=players
        )
        
        active_games = {12345: game_state}
        status = concurrent_manager.get_system_status(active_games)
        
        assert 'resource_status' in status
        assert 'metrics' in status
        assert 'limits' in status
        assert status['limits']['max_games'] == 5
        assert status['limits']['max_players_per_game'] == 3
    
    def test_get_game_metrics_specific(self, concurrent_manager):
        """Test getting metrics for specific game."""
        players = [Player(1, "user1", "User1")]
        game_state = GameState(
            chat_id=12345,
            current_letter="A",
            required_length=1,
            current_player_index=0,
            players=players
        )
        
        concurrent_manager.register_game_start(12345, game_state)
        
        metrics = concurrent_manager.get_game_metrics(12345)
        assert metrics['chat_id'] == 12345
        assert metrics['player_count'] == 1
    
    def test_get_game_metrics_all(self, concurrent_manager):
        """Test getting metrics for all games."""
        players = [Player(1, "user1", "User1")]
        game_state = GameState(
            chat_id=12345,
            current_letter="A",
            required_length=1,
            current_player_index=0,
            players=players
        )
        
        concurrent_manager.register_game_start(12345, game_state)
        
        all_metrics = concurrent_manager.get_game_metrics()
        assert '12345' in all_metrics
        assert all_metrics['12345']['chat_id'] == 12345
    
    @pytest.mark.asyncio
    async def test_start_stop_monitoring(self, concurrent_manager):
        """Test starting and stopping monitoring tasks."""
        await concurrent_manager.start_monitoring()
        
        assert concurrent_manager.cleanup_task is not None
        assert concurrent_manager.monitoring_task is not None
        assert not concurrent_manager.cleanup_task.done()
        assert not concurrent_manager.monitoring_task.done()
        
        await concurrent_manager.stop_monitoring()
        
        assert concurrent_manager._shutdown == True
    
    @pytest.mark.asyncio
    async def test_cleanup_inactive_games(self, concurrent_manager):
        """Test cleaning up inactive games."""
        # Mock game manager
        mock_game_manager = MagicMock()
        mock_game_manager.stop_game = AsyncMock()
        
        # Create an inactive game
        players = [Player(1, "user1", "User1")]
        game_state = GameState(
            chat_id=12345,
            current_letter="A",
            required_length=1,
            current_player_index=0,
            players=players
        )
        
        concurrent_manager.register_game_start(12345, game_state)
        
        # Make it appear inactive
        concurrent_manager.resource_monitor.game_metrics[12345].last_activity = datetime.now() - timedelta(hours=2)
        
        active_games = {12345: game_state}
        cleaned_count = await concurrent_manager.cleanup_inactive_games(active_games, mock_game_manager)
        
        assert cleaned_count == 1
        mock_game_manager.stop_game.assert_called_once_with(12345)


class TestChatIsolationManager:
    """Test cases for ChatIsolationManager class."""
    
    @pytest.fixture
    def isolation_manager(self):
        """Create a ChatIsolationManager instance."""
        return ChatIsolationManager()
    
    @pytest.mark.asyncio
    async def test_get_chat_lock(self, isolation_manager):
        """Test getting chat-specific locks."""
        lock1 = await isolation_manager.get_chat_lock(12345)
        lock2 = await isolation_manager.get_chat_lock(12345)
        lock3 = await isolation_manager.get_chat_lock(67890)
        
        # Same chat should get same lock
        assert lock1 is lock2
        
        # Different chat should get different lock
        assert lock1 is not lock3
        
        # Should track activity
        assert 12345 in isolation_manager.chat_activity
        assert 67890 in isolation_manager.chat_activity
    
    @pytest.mark.asyncio
    async def test_execute_with_chat_lock(self, isolation_manager):
        """Test executing operation with chat lock."""
        call_count = 0
        
        async def test_operation():
            nonlocal call_count
            call_count += 1
            return "success"
        
        result = await isolation_manager.execute_with_chat_lock(12345, test_operation)
        
        assert result == "success"
        assert call_count == 1
    
    def test_cleanup_old_locks(self, isolation_manager):
        """Test cleaning up old locks."""
        # Add some locks with old activity
        isolation_manager.chat_locks[12345] = asyncio.Lock()
        isolation_manager.chat_locks[67890] = asyncio.Lock()
        isolation_manager.chat_activity[12345] = datetime.now() - timedelta(hours=25)
        isolation_manager.chat_activity[67890] = datetime.now() - timedelta(minutes=30)
        
        cleaned_count = isolation_manager.cleanup_old_locks(hours=24)
        
        assert cleaned_count == 1
        assert 12345 not in isolation_manager.chat_locks
        assert 67890 in isolation_manager.chat_locks
    
    def test_get_active_chats(self, isolation_manager):
        """Test getting active chat list."""
        isolation_manager.chat_activity[12345] = datetime.now()
        isolation_manager.chat_activity[67890] = datetime.now()
        
        active_chats = isolation_manager.get_active_chats()
        
        assert 12345 in active_chats
        assert 67890 in active_chats
        assert len(active_chats) == 2


class TestConcurrentManagerFactory:
    """Test cases for concurrent manager factory function."""
    
    def test_create_concurrent_manager(self):
        """Test factory function creates ConcurrentGameManager."""
        manager = create_concurrent_manager(max_games=20, max_players_per_game=8)
        
        assert isinstance(manager, ConcurrentGameManager)
        assert manager.max_games == 20
        assert manager.max_players_per_game == 8


if __name__ == "__main__":
    pytest.main([__file__])