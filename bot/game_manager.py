"""
Game management system for the Telegram Word Game Bot.
"""

import asyncio
import logging
import random
import string
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

from .models import GameState, Player, GameConfig, GameResult
from . import word_validators as validators
from .word_validators import ValidationServiceUnavailable
from .word_processor import WordProcessor
from .error_handler import error_handler, handle_error_decorator
from .concurrent_manager import create_concurrent_manager, ChatIsolationManager

logger = logging.getLogger(__name__)


class GameManager:
    """Manages word game state and lifecycle."""
    
    def __init__(self, word_validator: validators.WordValidator, game_config: Optional[GameConfig] = None):
        self.word_validator = word_validator
        self.word_processor = WordProcessor(word_validator)
        self.game_config = game_config or GameConfig()
        self._active_games: Dict[int, GameState] = {}
        self._max_games = 100  # Prevent memory issues
        
        # Concurrent game management
        self.concurrent_manager = create_concurrent_manager(
            max_games=self._max_games,
            max_players_per_game=game_config.max_players_per_game if game_config else 10
        )
        self.chat_isolation = ChatIsolationManager()
    
    async def start_game(self, chat_id: int, players: List[Player]) -> GameState:
        """Start a new word game in the specified chat."""
        # Check if game already exists
        if chat_id in self._active_games:
            existing_game = self._active_games[chat_id]
            if existing_game.is_active:
                raise ValueError("A game is already active in this chat")
        
        # Check player count
        if len(players) < 1:
            raise ValueError("At least one player is required to start a game")
        
        if len(players) > self.game_config.max_players_per_game:
            raise ValueError(f"Maximum {self.game_config.max_players_per_game} players allowed")
        
        # Check if we can create a new game
        can_create, reason = self.concurrent_manager.can_create_game(self._active_games, len(players))
        if not can_create:
            # Try cleanup first
            await self._cleanup_inactive_games()
            
            # Check again after cleanup
            can_create, reason = self.concurrent_manager.can_create_game(self._active_games, len(players))
            if not can_create:
                raise ValueError(reason)
        
        # Generate random starting letter (avoid difficult letters)
        common_letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        # Remove very difficult letters
        easy_letters = [l for l in common_letters if l not in 'QXZJ']
        starting_letter = random.choice(easy_letters)
        
        # Create new game state
        game_state = GameState(
            chat_id=chat_id,
            current_letter=starting_letter,
            required_length=self.game_config.min_word_length,
            current_player_index=0,
            players=players.copy(),
            is_active=True,
            turn_start_time=datetime.now(),
            game_config=self.game_config
        )
        
        # Store the game
        self._active_games[chat_id] = game_state
        
        # Register with concurrent manager
        self.concurrent_manager.register_game_start(chat_id, game_state)
        
        logger.info(f"Started new game in chat {chat_id} with {len(players)} players, "
                   f"starting letter: {starting_letter}")
        
        return game_state
    
    @handle_error_decorator("create_waiting_game")
    async def create_waiting_game(self, chat_id: int, initial_player: Player) -> GameState:
        """Create a new game in waiting state for players to join."""
        if chat_id in self._active_games:
            raise ValueError("A game already exists in this chat")
        
        # Check if we can create a new game
        can_create, reason = self.concurrent_manager.can_create_game(self._active_games, 1)
        if not can_create:
            # Try cleanup first
            await self._cleanup_inactive_games()
            
            # Check again after cleanup
            can_create, reason = self.concurrent_manager.can_create_game(self._active_games, 1)
            if not can_create:
                raise ValueError(reason)
        
        # Generate random starting letter
        common_letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        easy_letters = [l for l in common_letters if l not in 'QXZJ']
        starting_letter = random.choice(easy_letters)
        
        # Create new game state in waiting mode
        game_state = GameState(
            chat_id=chat_id,
            current_letter=starting_letter,
            required_length=self.game_config.min_word_length,
            current_player_index=0,
            players=[initial_player],
            is_active=False,  # Not active until started
            is_waiting_for_players=True,
            turn_start_time=None,
            game_config=self.game_config,
            rounds_completed=0,
            current_round_turns=0
        )
        
        # Store the game
        self._active_games[chat_id] = game_state
        
        logger.info(f"Created waiting game in chat {chat_id} with initial player {initial_player.first_name}")
        
        return game_state
    
    @handle_error_decorator("add_player_to_game")
    async def add_player_to_game(self, chat_id: int, player: Player) -> bool:
        """Add a player to a waiting game."""
        game_state = self._active_games.get(chat_id)
        if not game_state or not game_state.is_waiting_for_players:
            return False
        
        return game_state.add_player(player)
    
    @handle_error_decorator("start_actual_game")
    async def start_actual_game(self, chat_id: int) -> GameState:
        """Start the actual game after waiting period."""
        game_state = self._active_games.get(chat_id)
        if not game_state or not game_state.is_waiting_for_players:
            raise ValueError("No waiting game found")
        
        if len(game_state.players) < 2:
            raise ValueError("Need at least 2 players to start")
        
        # Cancel waiting timer if it exists
        if game_state.waiting_timer_task:
            game_state.waiting_timer_task.cancel()
            game_state.waiting_timer_task = None
        
        # Activate the game
        game_state.is_active = True
        game_state.is_waiting_for_players = False
        game_state.turn_start_time = datetime.now()
        
        # Register with concurrent manager
        self.concurrent_manager.register_game_start(chat_id, game_state)
        
        logger.info(f"Started actual game in chat {chat_id} with {len(game_state.players)} players")
        
        return game_state
    
    @handle_error_decorator("process_word")
    async def process_word(self, chat_id: int, player_id: int, word: str) -> Tuple[GameResult, Optional[str]]:
        """
        Process a word submission from a player.
        
        Returns:
            Tuple of (GameResult, error_message)
        """
        # Get game state
        game_state = self.get_game_status(chat_id)
        
        # Process word using word processor
        result, error_message = await self.word_processor.process_word_submission(
            game_state, player_id, word
        )
        
        # If word is valid, update game state
        if result == GameResult.VALID_WORD:
            # Update game state
            normalized_word = word.strip().lower()
            self.word_processor.get_next_game_state(normalized_word, game_state)
            
            # Cancel current timer if it exists
            if game_state.timer_task and not game_state.timer_task.done():
                game_state.timer_task.cancel()
                game_state.timer_task = None
            
            # Register activity with concurrent manager
            self.concurrent_manager.register_game_activity(chat_id, game_state, words_submitted=1)
            
            logger.info(f"Valid word '{normalized_word}' submitted by player {player_id} in chat {chat_id}. "
                       f"Next: letter={game_state.current_letter}, length={game_state.required_length}")
        else:
            # Register error activity
            self.concurrent_manager.register_game_activity(chat_id, game_state, errors=1)
        
        return result, error_message
    
    async def handle_timeout(self, chat_id: int) -> Optional[Player]:
        """Handle turn timeout - eliminate the current player."""
        game_state = self.get_game_status(chat_id)
        if not game_state or not game_state.is_active:
            return None
        
        current_player = game_state.get_current_player()
        if not current_player:
            return None
        
        logger.info(f"Turn timeout for player {current_player.user_id} in chat {chat_id} - eliminating player")
        
        # Clear the timer task
        if game_state.timer_task:
            game_state.timer_task = None
        
        # Register timeout activity
        self.concurrent_manager.register_game_activity(chat_id, game_state, timeouts=1)
        
        # Remove the current player (eliminate them)
        eliminated_player = current_player
        game_state.remove_player(current_player.user_id)
        
        # After removal, current_player_index already points to the next player
        # (or 0 if the removed was the last). Do NOT advance again, just ensure
        # we are pointing at an active player and reset the turn start time.
        if len(game_state.players) > 1:
            game_state.skip_inactive_players()
            game_state.turn_start_time = datetime.now()
        
        # Check if game should end (only one or no players left)
        if len(game_state.players) <= 1:
            # Game ends - mark as inactive but don't delete yet (let announcer handle it)
            game_state.is_active = False
            
        return eliminated_player
    
    def get_winner(self, chat_id: int) -> Optional[Player]:
        """Get the winner of the game (if only one player remains)."""
        game_state = self.get_game_status(chat_id)
        if not game_state:
            return None
        
        if len(game_state.players) == 1:
            return game_state.players[0]
        
        return None
    
    def get_game_status(self, chat_id: int) -> Optional[GameState]:
        """Get the current game state for a chat."""
        return self._active_games.get(chat_id)
    
    async def stop_game(self, chat_id: int) -> bool:
        """Stop the game in the specified chat."""
        if chat_id not in self._active_games:
            return False
        
        game_state = self._active_games[chat_id]
        
        # Cancel any active timer
        if game_state.timer_task and not game_state.timer_task.done():
            game_state.timer_task.cancel()
        
        # Mark game as inactive and remove from active games
        game_state.is_active = False
        del self._active_games[chat_id]
        
        # Register with concurrent manager
        self.concurrent_manager.register_game_end(chat_id)
        
        logger.info(f"Stopped game in chat {chat_id}")
        return True
    
    def add_player_to_active_game(self, chat_id: int, player: Player) -> bool:
        """Add a player to an existing active game."""
        game_state = self.get_game_status(chat_id)
        if not game_state or not game_state.is_active:
            return False
        
        success = game_state.add_player(player)
        if success:
            logger.info(f"Added player {player.user_id} to game in chat {chat_id}")
        
        return success
    
    def remove_player_from_game(self, chat_id: int, user_id: int) -> bool:
        """Remove a player from an existing game."""
        game_state = self.get_game_status(chat_id)
        if not game_state or not game_state.is_active:
            return False
        
        success = game_state.remove_player(user_id)
        if success:
            logger.info(f"Removed player {user_id} from game in chat {chat_id}")
            
            # Check if game should end due to too few players
            if game_state.should_end_game():
                logger.info(f"Ending game in chat {chat_id} due to insufficient players")
                asyncio.create_task(self.stop_game(chat_id))
        
        return success
    
    def set_player_active_status(self, chat_id: int, user_id: int, is_active: bool) -> bool:
        """Set a player's active status in a game."""
        game_state = self.get_game_status(chat_id)
        if not game_state or not game_state.is_active:
            return False
        
        success = game_state.set_player_active_status(user_id, is_active)
        if success:
            status = "activated" if is_active else "deactivated"
            logger.info(f"Player {user_id} {status} in game {chat_id}")
            
            # Check if game should end due to too few active players
            if game_state.should_end_game():
                logger.info(f"Ending game in chat {chat_id} due to insufficient active players")
                asyncio.create_task(self.stop_game(chat_id))
        
        return success
    
    def get_turn_order(self, chat_id: int) -> List[Player]:
        """Get the current turn order for a game."""
        game_state = self.get_game_status(chat_id)
        if not game_state or not game_state.is_active:
            return []
        
        return game_state.get_player_turn_order()
    
    def get_next_player(self, chat_id: int) -> Optional[Player]:
        """Get the next player in turn order without advancing."""
        game_state = self.get_game_status(chat_id)
        if not game_state or not game_state.is_active:
            return None
        
        return game_state.get_next_player()
    
    def get_turn_time_remaining(self, chat_id: int) -> Optional[float]:
        """Get remaining time for current turn in seconds."""
        game_state = self.get_game_status(chat_id)
        if not game_state or not game_state.is_active:
            return None
        
        return game_state.get_remaining_turn_time()
    
    def set_timer_task(self, chat_id: int, timer_task: Optional[asyncio.Task]) -> bool:
        """Set the timer task for a game."""
        game_state = self.get_game_status(chat_id)
        if not game_state:
            return False
        
        game_state.timer_task = timer_task
        return True
    
    def get_timer_task(self, chat_id: int) -> Optional[asyncio.Task]:
        """Get the current timer task for a game."""
        game_state = self.get_game_status(chat_id)
        if not game_state:
            return None
        
        return game_state.timer_task
    
    def get_word_hints(self, chat_id: int) -> Optional[str]:
        """Get helpful hints for the current word requirements."""
        game_state = self.get_game_status(chat_id)
        if not game_state or not game_state.is_active:
            return None
        
        return self.word_processor.get_word_hints(game_state)
    
    def get_difficulty_assessment(self, chat_id: int) -> Optional[str]:
        """Get difficulty assessment for current word requirements."""
        game_state = self.get_game_status(chat_id)
        if not game_state or not game_state.is_active:
            return None
        
        return self.word_processor.check_word_difficulty(game_state)
    
    def format_word_feedback(self, result: GameResult, error_message: Optional[str], word: str) -> str:
        """Format user-friendly feedback for word submissions."""
        return self.word_processor.format_word_feedback(result, error_message, word)
    
    async def start_concurrent_monitoring(self) -> None:
        """Start concurrent game monitoring."""
        await self.concurrent_manager.start_monitoring()
        logger.info("Started concurrent game monitoring")
    
    async def stop_concurrent_monitoring(self) -> None:
        """Stop concurrent game monitoring."""
        await self.concurrent_manager.stop_monitoring()
        logger.info("Stopped concurrent game monitoring")
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive system status."""
        return self.concurrent_manager.get_system_status(self._active_games)
    
    def get_game_metrics(self, chat_id: Optional[int] = None) -> Dict[str, Any]:
        """Get game metrics."""
        return self.concurrent_manager.get_game_metrics(chat_id)
    
    async def cleanup_inactive_games_manual(self) -> int:
        """Manually trigger cleanup of inactive games."""
        return await self.concurrent_manager.cleanup_inactive_games(self._active_games, self)
    
    async def execute_with_chat_isolation(self, chat_id: int, operation, *args, **kwargs):
        """Execute operation with chat-specific isolation."""
        return await self.chat_isolation.execute_with_chat_lock(chat_id, operation, *args, **kwargs)
    
    def get_concurrent_stats(self) -> Dict[str, Any]:
        """Get concurrent game statistics."""
        system_status = self.get_system_status()
        
        return {
            'active_games': len(self._active_games),
            'max_games': self._max_games,
            'resource_status': system_status['resource_status'],
            'total_players': sum(len(game.players) for game in self._active_games.values()),
            'active_chats': self.chat_isolation.get_active_chats(),
            'system_metrics': system_status['metrics']
        }
    
    async def cleanup_chat(self, chat_id: int) -> None:
        """Clean up game state for a chat (e.g., when bot is removed from chat)."""
        if chat_id in self._active_games:
            await self.stop_game(chat_id)
            logger.info(f"Cleaned up game state for chat {chat_id}")
    
    async def _cleanup_inactive_games(self) -> None:
        """Remove inactive games to free up memory."""
        # Use concurrent manager for cleanup
        cleaned_count = await self.concurrent_manager.cleanup_inactive_games(self._active_games, self)
        
        # Also clean up chat isolation locks
        self.chat_isolation.cleanup_old_locks(hours=24)
        
        if cleaned_count > 0:
            logger.info(f"Cleaned up {cleaned_count} inactive games")
    
    def get_active_game_count(self) -> int:
        """Get the number of currently active games."""
        return len([g for g in self._active_games.values() if g.is_active])
    
    def get_total_player_count(self) -> int:
        """Get the total number of players across all active games."""
        return sum(len(g.players) for g in self._active_games.values() if g.is_active)