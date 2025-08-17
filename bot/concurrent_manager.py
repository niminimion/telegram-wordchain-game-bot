"""
Concurrent game management and resource monitoring for the Telegram Word Game Bot.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Set, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

from .models import GameState, Player
from .error_handler import error_handler, ErrorType, ErrorSeverity

logger = logging.getLogger(__name__)


class ResourceStatus(Enum):
    """Resource usage status levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class GameMetrics:
    """Metrics for a single game."""
    chat_id: int
    player_count: int
    game_duration: timedelta
    turn_count: int
    words_submitted: int
    timeouts: int
    errors: int
    last_activity: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            'chat_id': self.chat_id,
            'player_count': self.player_count,
            'game_duration_seconds': self.game_duration.total_seconds(),
            'turn_count': self.turn_count,
            'words_submitted': self.words_submitted,
            'timeouts': self.timeouts,
            'errors': self.errors,
            'last_activity': self.last_activity.isoformat()
        }


@dataclass
class SystemMetrics:
    """System-wide metrics."""
    total_games: int
    active_games: int
    total_players: int
    memory_usage_mb: float
    cpu_usage_percent: float
    uptime_seconds: float
    games_per_hour: float
    average_game_duration: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            'total_games': self.total_games,
            'active_games': self.active_games,
            'total_players': self.total_players,
            'memory_usage_mb': self.memory_usage_mb,
            'cpu_usage_percent': self.cpu_usage_percent,
            'uptime_seconds': self.uptime_seconds,
            'games_per_hour': self.games_per_hour,
            'average_game_duration': self.average_game_duration
        }


class ResourceMonitor:
    """Monitors system resources and game performance."""
    
    def __init__(self, max_games: int = 100, max_players_per_game: int = 10):
        self.max_games = max_games
        self.max_players_per_game = max_players_per_game
        self.start_time = datetime.now()
        self.game_metrics: Dict[int, GameMetrics] = {}
        self.historical_games = 0
        self.resource_warnings: List[str] = []
    
    def get_resource_status(self, active_games: int, total_players: int) -> ResourceStatus:
        """Determine current resource usage status."""
        game_usage = active_games / self.max_games
        
        if game_usage >= 0.9:
            return ResourceStatus.CRITICAL
        elif game_usage >= 0.7:
            return ResourceStatus.HIGH
        elif game_usage >= 0.4:
            return ResourceStatus.MEDIUM
        else:
            return ResourceStatus.LOW
    
    def can_create_game(self, active_games: int, requesting_players: int) -> tuple[bool, Optional[str]]:
        """Check if a new game can be created."""
        # Check game limit
        if active_games >= self.max_games:
            return False, f"Maximum concurrent games limit reached ({self.max_games})"
        
        # Check player limit per game
        if requesting_players > self.max_players_per_game:
            return False, f"Too many players for one game (max: {self.max_players_per_game})"
        
        # Check resource status
        status = self.get_resource_status(active_games, 0)
        if status == ResourceStatus.CRITICAL:
            return False, "System resources are critically low"
        
        return True, None
    
    def update_game_metrics(
        self, 
        chat_id: int, 
        game_state: GameState,
        words_submitted: int = 0,
        timeouts: int = 0,
        errors: int = 0
    ) -> None:
        """Update metrics for a specific game."""
        if chat_id not in self.game_metrics:
            self.game_metrics[chat_id] = GameMetrics(
                chat_id=chat_id,
                player_count=len(game_state.players),
                game_duration=timedelta(),
                turn_count=0,
                words_submitted=0,
                timeouts=0,
                errors=0,
                last_activity=datetime.now()
            )
        
        metrics = self.game_metrics[chat_id]
        
        # Update metrics
        if game_state.turn_start_time:
            metrics.game_duration = datetime.now() - game_state.turn_start_time
        
        metrics.words_submitted += words_submitted
        metrics.timeouts += timeouts
        metrics.errors += errors
        metrics.last_activity = datetime.now()
        
        # Estimate turn count based on word length progression
        if game_state.required_length > 1:
            metrics.turn_count = game_state.required_length - 1
    
    def remove_game_metrics(self, chat_id: int) -> None:
        """Remove metrics for a completed game."""
        if chat_id in self.game_metrics:
            self.historical_games += 1
            del self.game_metrics[chat_id]
    
    def get_system_metrics(self, active_games: Dict[int, GameState]) -> SystemMetrics:
        """Get comprehensive system metrics."""
        uptime = (datetime.now() - self.start_time).total_seconds()
        total_games = self.historical_games + len(active_games)
        total_players = sum(len(game.players) for game in active_games.values())
        
        # Calculate games per hour
        games_per_hour = (total_games / uptime * 3600) if uptime > 0 else 0
        
        # Calculate average game duration
        if self.game_metrics:
            avg_duration = sum(m.game_duration.total_seconds() for m in self.game_metrics.values()) / len(self.game_metrics)
        else:
            avg_duration = 0
        
        # Mock resource usage (in a real implementation, you'd use psutil or similar)
        memory_usage = len(active_games) * 2.5  # Rough estimate: 2.5MB per game
        cpu_usage = min(len(active_games) * 1.2, 100)  # Rough estimate
        
        return SystemMetrics(
            total_games=total_games,
            active_games=len(active_games),
            total_players=total_players,
            memory_usage_mb=memory_usage,
            cpu_usage_percent=cpu_usage,
            uptime_seconds=uptime,
            games_per_hour=games_per_hour,
            average_game_duration=avg_duration
        )
    
    def get_inactive_games(self, active_games: Dict[int, GameState], timeout_minutes: int = 30) -> List[int]:
        """Get list of inactive game chat IDs."""
        cutoff_time = datetime.now() - timedelta(minutes=timeout_minutes)
        inactive_games = []
        
        for chat_id, metrics in self.game_metrics.items():
            if metrics.last_activity < cutoff_time:
                inactive_games.append(chat_id)
        
        return inactive_games
    
    def add_resource_warning(self, warning: str) -> None:
        """Add a resource warning."""
        self.resource_warnings.append(f"{datetime.now().isoformat()}: {warning}")
        
        # Keep only last 50 warnings
        if len(self.resource_warnings) > 50:
            self.resource_warnings = self.resource_warnings[-50:]
    
    def get_resource_warnings(self, hours: int = 24) -> List[str]:
        """Get recent resource warnings."""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        cutoff_str = cutoff_time.isoformat()
        
        return [w for w in self.resource_warnings if w.split(":")[0] >= cutoff_str]


class ConcurrentGameManager:
    """Manages concurrent games with resource monitoring and cleanup."""
    
    def __init__(self, max_games: int = 100, max_players_per_game: int = 10):
        self.max_games = max_games
        self.max_players_per_game = max_players_per_game
        self.resource_monitor = ResourceMonitor(max_games, max_players_per_game)
        self.cleanup_task: Optional[asyncio.Task] = None
        self.monitoring_task: Optional[asyncio.Task] = None
        self._shutdown = False
    
    async def start_monitoring(self) -> None:
        """Start background monitoring tasks."""
        if not self.cleanup_task or self.cleanup_task.done():
            self.cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        if not self.monitoring_task or self.monitoring_task.done():
            self.monitoring_task = asyncio.create_task(self._monitoring_loop())
        
        logger.info("Started concurrent game monitoring")
    
    async def stop_monitoring(self) -> None:
        """Stop background monitoring tasks."""
        self._shutdown = True
        
        if self.cleanup_task and not self.cleanup_task.done():
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
        
        if self.monitoring_task and not self.monitoring_task.done():
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Stopped concurrent game monitoring")
    
    def can_create_game(self, active_games: Dict[int, GameState], requesting_players: int) -> tuple[bool, Optional[str]]:
        """Check if a new game can be created."""
        return self.resource_monitor.can_create_game(len(active_games), requesting_players)
    
    def register_game_start(self, chat_id: int, game_state: GameState) -> None:
        """Register a new game start."""
        self.resource_monitor.update_game_metrics(chat_id, game_state)
        
        # Check resource status
        active_count = len(self.resource_monitor.game_metrics)
        status = self.resource_monitor.get_resource_status(active_count, 0)
        
        if status in [ResourceStatus.HIGH, ResourceStatus.CRITICAL]:
            warning = f"High resource usage: {active_count}/{self.max_games} games active"
            self.resource_monitor.add_resource_warning(warning)
            logger.warning(warning)
    
    def register_game_activity(
        self, 
        chat_id: int, 
        game_state: GameState,
        words_submitted: int = 0,
        timeouts: int = 0,
        errors: int = 0
    ) -> None:
        """Register game activity."""
        self.resource_monitor.update_game_metrics(
            chat_id, game_state, words_submitted, timeouts, errors
        )
    
    def register_game_end(self, chat_id: int) -> None:
        """Register a game end."""
        self.resource_monitor.remove_game_metrics(chat_id)
    
    def get_system_status(self, active_games: Dict[int, GameState]) -> Dict[str, Any]:
        """Get comprehensive system status."""
        metrics = self.resource_monitor.get_system_metrics(active_games)
        status = self.resource_monitor.get_resource_status(metrics.active_games, metrics.total_players)
        
        return {
            'resource_status': status.value,
            'metrics': metrics.to_dict(),
            'limits': {
                'max_games': self.max_games,
                'max_players_per_game': self.max_players_per_game
            },
            'warnings': self.resource_monitor.get_resource_warnings(24)
        }
    
    def get_game_metrics(self, chat_id: Optional[int] = None) -> Dict[str, Any]:
        """Get metrics for specific game or all games."""
        if chat_id:
            metrics = self.resource_monitor.game_metrics.get(chat_id)
            return metrics.to_dict() if metrics else {}
        else:
            return {
                str(cid): metrics.to_dict() 
                for cid, metrics in self.resource_monitor.game_metrics.items()
            }
    
    async def cleanup_inactive_games(self, active_games: Dict[int, GameState], game_manager) -> int:
        """Clean up inactive games."""
        inactive_games = self.resource_monitor.get_inactive_games(active_games, timeout_minutes=60)
        cleaned_count = 0
        
        for chat_id in inactive_games:
            try:
                if chat_id in active_games:
                    logger.info(f"Cleaning up inactive game in chat {chat_id}")
                    await game_manager.stop_game(chat_id)
                    cleaned_count += 1
            except Exception as e:
                await error_handler.handle_error(
                    e, "cleanup_inactive_game", 
                    {'chat_id': chat_id}
                )
        
        if cleaned_count > 0:
            logger.info(f"Cleaned up {cleaned_count} inactive games")
        
        return cleaned_count
    
    async def _cleanup_loop(self) -> None:
        """Background cleanup loop."""
        while not self._shutdown:
            try:
                await asyncio.sleep(300)  # Run every 5 minutes
                
                # This would be called by the main game manager
                # For now, just log that cleanup would run
                logger.debug("Cleanup loop iteration (would clean inactive games)")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                await error_handler.handle_error(e, "cleanup_loop", {})
                await asyncio.sleep(60)  # Wait before retrying
    
    async def _monitoring_loop(self) -> None:
        """Background monitoring loop."""
        while not self._shutdown:
            try:
                await asyncio.sleep(600)  # Run every 10 minutes
                
                # Log system status
                active_count = len(self.resource_monitor.game_metrics)
                status = self.resource_monitor.get_resource_status(active_count, 0)
                
                logger.info(f"System status: {status.value}, Active games: {active_count}/{self.max_games}")
                
                # Check for resource warnings
                if status == ResourceStatus.CRITICAL:
                    warning = f"CRITICAL: System at capacity ({active_count}/{self.max_games} games)"
                    self.resource_monitor.add_resource_warning(warning)
                    logger.critical(warning)
                elif status == ResourceStatus.HIGH:
                    warning = f"HIGH: System under heavy load ({active_count}/{self.max_games} games)"
                    self.resource_monitor.add_resource_warning(warning)
                    logger.warning(warning)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                await error_handler.handle_error(e, "monitoring_loop", {})
                await asyncio.sleep(60)  # Wait before retrying


class ChatIsolationManager:
    """Manages chat-specific game isolation."""
    
    def __init__(self):
        self.chat_locks: Dict[int, asyncio.Lock] = {}
        self.chat_activity: Dict[int, datetime] = {}
    
    async def get_chat_lock(self, chat_id: int) -> asyncio.Lock:
        """Get or create a lock for a specific chat."""
        if chat_id not in self.chat_locks:
            self.chat_locks[chat_id] = asyncio.Lock()
        
        self.chat_activity[chat_id] = datetime.now()
        return self.chat_locks[chat_id]
    
    async def execute_with_chat_lock(self, chat_id: int, operation, *args, **kwargs):
        """Execute an operation with chat-specific locking."""
        lock = await self.get_chat_lock(chat_id)
        
        async with lock:
            return await operation(*args, **kwargs)
    
    def cleanup_old_locks(self, hours: int = 24) -> int:
        """Clean up locks for inactive chats."""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        old_chats = []
        
        for chat_id, last_activity in self.chat_activity.items():
            if last_activity < cutoff_time:
                old_chats.append(chat_id)
        
        for chat_id in old_chats:
            if chat_id in self.chat_locks:
                del self.chat_locks[chat_id]
            if chat_id in self.chat_activity:
                del self.chat_activity[chat_id]
        
        if old_chats:
            logger.info(f"Cleaned up {len(old_chats)} old chat locks")
        
        return len(old_chats)
    
    def get_active_chats(self) -> List[int]:
        """Get list of currently active chat IDs."""
        return list(self.chat_activity.keys())


def create_concurrent_manager(max_games: int = 100, max_players_per_game: int = 10) -> ConcurrentGameManager:
    """Factory function to create a ConcurrentGameManager."""
    return ConcurrentGameManager(max_games, max_players_per_game)