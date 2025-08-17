"""
Data models for the Telegram Word Game Bot.
"""

import asyncio
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
from enum import Enum


@dataclass
class Player:
    """Represents a player in the word game."""
    user_id: int
    username: str
    first_name: str
    is_active: bool = True

    def __str__(self) -> str:
        """Return a string representation for mentions."""
        if self.username:
            return f"@{self.username}"
        return self.first_name


@dataclass
class GameConfig:
    """Configuration parameters for the word game."""
    turn_timeout: int = 30
    min_word_length: int = 2
    max_word_length: int = 20
    max_players_per_game: int = 10
    timeout_warnings: List[int] = field(default_factory=lambda: [15, 10, 5])

    @classmethod
    def from_env(cls) -> 'GameConfig':
        """Create GameConfig from environment variables."""
        return cls(
            turn_timeout=int(os.getenv('TURN_TIMEOUT', '30')),
            min_word_length=int(os.getenv('MIN_WORD_LENGTH', '2')),
            max_word_length=int(os.getenv('MAX_WORD_LENGTH', '20')),
            max_players_per_game=int(os.getenv('MAX_PLAYERS', '10')),
            timeout_warnings=[15, 10, 5]  # Fixed warnings at 15, 10 and 5 seconds
        )


class GameResult(Enum):
    """Possible results from word processing."""
    VALID_WORD = "valid"
    INVALID_LETTER = "invalid_letter"
    INVALID_LENGTH = "invalid_length"
    INVALID_WORD = "invalid_word"
    WRONG_PLAYER = "wrong_player"
    NO_ACTIVE_GAME = "no_game"
    VALIDATION_ERROR = "validation_error"


@dataclass
class GameState:
    """Represents the current state of a word game."""
    chat_id: int
    current_letter: str
    required_length: int
    current_player_index: int
    players: List[Player]
    is_active: bool = True
    turn_start_time: Optional[datetime] = None
    timer_task: Optional[asyncio.Task] = None
    game_config: GameConfig = field(default_factory=GameConfig)
    
    # New fields for improved game flow
    is_waiting_for_players: bool = True  # True during 1-minute waiting period
    waiting_timer_task: Optional[asyncio.Task] = None
    rounds_completed: int = 0  # Track completed rounds
    current_round_turns: int = 0  # Track turns in current round

    def get_current_player(self) -> Optional[Player]:
        """Get the player whose turn it currently is."""
        if not self.players or self.current_player_index >= len(self.players):
            return None
        return self.players[self.current_player_index]

    def advance_turn(self) -> None:
        """Advance to the next player's turn."""
        if self.players:
            self.current_player_index = (self.current_player_index + 1) % len(self.players)
            self.turn_start_time = datetime.now()

    def remove_player(self, user_id: int) -> bool:
        """Remove a player from the game. Returns True if player was removed."""
        for i, player in enumerate(self.players):
            if player.user_id == user_id:
                # If we're removing the current player, don't advance the index
                if i < self.current_player_index:
                    self.current_player_index -= 1
                elif i == self.current_player_index and self.current_player_index >= len(self.players) - 1:
                    self.current_player_index = 0
                
                self.players.pop(i)
                return True
        return False

    def add_player(self, player: Player) -> bool:
        """Add a player to the game. Returns True if player was added."""
        # Check if player already exists
        for existing_player in self.players:
            if existing_player.user_id == player.user_id:
                return False
        
        # Check max players limit
        if len(self.players) >= self.game_config.max_players_per_game:
            return False
        
        self.players.append(player)
        return True

    def should_end_game(self) -> bool:
        """Check if the game should end (too few players)."""
        active_players = [p for p in self.players if p.is_active]
        return len(active_players) <= 1

    def get_next_player(self) -> Optional[Player]:
        """Get the next player in the turn order without advancing."""
        if not self.players:
            return None
        next_index = (self.current_player_index + 1) % len(self.players)
        return self.players[next_index]

    def get_player_turn_order(self) -> List[Player]:
        """Get the list of players in turn order starting from current player."""
        if not self.players:
            return []
        
        # Reorder players starting from current player
        current_idx = self.current_player_index
        return self.players[current_idx:] + self.players[:current_idx]

    def get_active_players(self) -> List[Player]:
        """Get list of active players only."""
        return [p for p in self.players if p.is_active]

    def skip_inactive_players(self) -> None:
        """Skip to the next active player if current player is inactive."""
        if not self.players:
            return
        
        attempts = 0
        max_attempts = len(self.players)
        
        while attempts < max_attempts:
            current_player = self.get_current_player()
            if current_player and current_player.is_active:
                break
            
            self.current_player_index = (self.current_player_index + 1) % len(self.players)
            attempts += 1
        
        # Update turn start time
        self.turn_start_time = datetime.now()

    def set_player_active_status(self, user_id: int, is_active: bool) -> bool:
        """Set a player's active status. Returns True if player was found."""
        for player in self.players:
            if player.user_id == user_id:
                player.is_active = is_active
                
                # If we deactivated the current player, skip to next active player
                if not is_active and self.get_current_player() and self.get_current_player().user_id == user_id:
                    self.skip_inactive_players()
                
                return True
        return False

    def get_turn_duration(self) -> Optional[float]:
        """Get the duration of the current turn in seconds."""
        if not self.turn_start_time:
            return None
        return (datetime.now() - self.turn_start_time).total_seconds()

    def get_remaining_turn_time(self) -> Optional[float]:
        """Get remaining time for current turn in seconds."""
        if not self.turn_start_time:
            return None
        
        elapsed = self.get_turn_duration()
        if elapsed is None:
            return None
        
        remaining = self.game_config.turn_timeout - elapsed
        return max(0, remaining)