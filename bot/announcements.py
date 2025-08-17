"""
Game announcements and user feedback system for the Telegram Word Game Bot.
"""

import logging
from typing import Optional, List, Dict, Any
from enum import Enum
from telegram.constants import ParseMode

from .models import Player, GameState, GameResult

logger = logging.getLogger(__name__)


class AnnouncementType(Enum):
    """Types of game announcements."""
    GAME_START = "game_start"
    GAME_END = "game_end"
    TURN_START = "turn_start"
    TURN_TIMEOUT = "turn_timeout"
    TURN_WARNING = "turn_warning"
    VALID_WORD = "valid_word"
    INVALID_WORD = "invalid_word"
    PLAYER_JOIN = "player_join"
    PLAYER_LEAVE = "player_leave"
    GAME_WINNER = "game_winner"
    GAME_RULES = "game_rules"
    GAME_STATUS = "game_status"


class AnnouncementFormatter:
    """Formats various types of game announcements."""
    
    def __init__(self):
        self.emojis = {
            'game': '🎮',
            'start': '🚀',
            'stop': '🛑',
            'turn': '🎯',
            'time': '⏰',
            'warning': '⚠️',
            'success': '✅',
            'error': '❌',
            'player': '👤',
            'winner': '🏆',
            'rules': '📋',
            'letter': '🔤',
            'length': '📏',
            'hint': '💡',
            'difficulty': '🌟',
            'progress': '📊'
        }
    
    def format_game_start(self, game_state: GameState, rules_included: bool = True) -> str:
        """Format game start announcement."""
        current_player = game_state.get_current_player()
        
        message = (
            f"{self.emojis['game']} **Word Game Started!** {self.emojis['start']}\n\n"
        )
        
        if rules_included:
            message += (
                f"{self.emojis['rules']} **Rules:**\n"
                f"• Take turns creating words\n"
                f"• Each word must start with the given letter\n"
                f"• Word length increases each round\n"
                f"• You have {game_state.game_config.turn_timeout} seconds per turn\n"
                f"• Words must be valid English words\n\n"
            )
        
        message += (
            f"{self.emojis['turn']} **First Challenge:**\n"
            f"{self.emojis['player']} Turn: {current_player}\n"
            f"{self.emojis['letter']} Letter: **{game_state.current_letter}**\n"
            f"{self.emojis['length']} Length: **{game_state.required_length}** letter(s)\n\n"
            f"Good luck! {self.emojis['success']}"
        )
        
        return message
    
    def format_game_end(self, reason: str = "stopped", winner: Optional[Player] = None) -> str:
        """Format game end announcement."""
        if winner:
            return (
                f"{self.emojis['winner']} **Game Complete!**\n\n"
                f"🎉 **Winner: {winner}** 🎉\n\n"
                f"Congratulations! Thanks for playing! {self.emojis['game']}\n"
                f"Use /startgame to play again."
            )
        else:
            return (
                f"{self.emojis['stop']} **Game {reason.title()}**\n\n"
                f"Thanks for playing! {self.emojis['game']}\n"
                f"Use /startgame to start a new game."
            )
    
    def format_turn_announcement(self, game_state: GameState, hints: str = "", difficulty: str = "") -> str:
        """Format turn announcement."""
        current_player = game_state.get_current_player()
        
        message = (
            f"{self.emojis['turn']} **Your Turn!**\n\n"
            f"{self.emojis['player']} Player: {current_player}\n"
            f"{self.emojis['letter']} Letter: **{game_state.current_letter}**\n"
            f"{self.emojis['length']} Length: **{game_state.required_length}** letters\n"
        )
        
        if hints:
            message += f"\n{hints}"
        
        if difficulty:
            message += f"\n{difficulty}"
        
        return message
    
    def format_timeout_announcement(
        self, 
        timed_out_player: Player, 
        next_player: Player, 
        game_state: GameState,
        hints: str = ""
    ) -> str:
        """Format timeout announcement."""
        return (
            f"{self.emojis['time']} **Time's Up!** {timed_out_player}\n\n"
            f"{self.emojis['turn']} **Next Turn:**\n"
            f"{self.emojis['player']} Player: {next_player}\n"
            f"{self.emojis['letter']} Letter: **{game_state.current_letter}**\n"
            f"{self.emojis['length']} Length: **{game_state.required_length}** letters\n\n"
            f"{hints}"
        )
    
    def format_warning_announcement(self, player: Player, remaining_seconds: int) -> str:
        """Format timeout warning announcement."""
        return (
            f"{self.emojis['warning']} {player}, you have **{remaining_seconds}** seconds left!"
        )
    
    def format_valid_word_announcement(
        self, 
        word: str, 
        player: Player, 
        game_state: GameState,
        hints: str = "",
        difficulty: str = ""
    ) -> str:
        """Format valid word acceptance announcement."""
        next_player = game_state.get_current_player()
        
        message = (
            f"{self.emojis['success']} **Excellent!** {player} submitted '{word}'\n\n"
            f"{self.emojis['turn']} **Next Challenge:**\n"
            f"{self.emojis['player']} Turn: {next_player}\n"
            f"{self.emojis['letter']} Letter: **{game_state.current_letter}**\n"
            f"{self.emojis['length']} Length: **{game_state.required_length}** letters\n"
        )
        
        if hints:
            message += f"\n{hints}"
        
        if difficulty:
            message += f"\n{difficulty}"
        
        return message
    
    def format_invalid_word_feedback(self, result: GameResult, error_message: str, word: str) -> str:
        """Format invalid word feedback."""
        emoji_map = {
            GameResult.INVALID_LETTER: self.emojis['error'],
            GameResult.INVALID_LENGTH: self.emojis['error'],
            GameResult.INVALID_WORD: self.emojis['error'],
            GameResult.WRONG_PLAYER: self.emojis['time'],
            GameResult.VALIDATION_ERROR: self.emojis['warning']
        }
        
        emoji = emoji_map.get(result, self.emojis['error'])
        return f"{emoji} {error_message}"
    
    def format_player_join_announcement(self, player: Player, game_state: GameState) -> str:
        """Format player join announcement."""
        return (
            f"{self.emojis['player']} **{player} joined the game!**\n\n"
            f"Players: {len(game_state.players)}/{game_state.game_config.max_players_per_game}"
        )
    
    def format_player_leave_announcement(self, player: Player, game_state: GameState) -> str:
        """Format player leave announcement."""
        return (
            f"{self.emojis['player']} **{player} left the game**\n\n"
            f"Remaining players: {len(game_state.players)}"
        )
    
    def format_game_status(
        self, 
        game_state: GameState, 
        remaining_time: Optional[float] = None,
        hints: str = "",
        difficulty: str = ""
    ) -> str:
        """Format comprehensive game status."""
        current_player = game_state.get_current_player()
        
        # Format remaining time
        time_str = ""
        if remaining_time is not None:
            if remaining_time > 0:
                time_str = f"{self.emojis['time']} {int(remaining_time)}s remaining\n"
            else:
                time_str = f"{self.emojis['time']} Time's up!\n"
        
        # Create player list with current player highlighted
        player_list = []
        for i, player in enumerate(game_state.players):
            if i == game_state.current_player_index:
                player_list.append(f"👉 **{player}** (current)")
            else:
                player_list.append(f"   {player}")
        
        message = (
            f"{self.emojis['game']} **Game Status**\n\n"
            f"{self.emojis['player']} **Current Turn:** {current_player}\n"
            f"{self.emojis['letter']} **Letter:** {game_state.current_letter}\n"
            f"{self.emojis['length']} **Length:** {game_state.required_length} letters\n"
            f"{time_str}\n"
            f"👥 **Players:**\n" + "\n".join(player_list)
        )
        
        if hints:
            message += f"\n\n{hints}"
        
        if difficulty:
            message += f"\n{difficulty}"
        
        return message
    
    def format_game_rules(self) -> str:
        """Format game rules explanation."""
        return (
            f"{self.emojis['game']} **Word Game Rules** {self.emojis['rules']}\n\n"
            f"**How to Play:**\n"
            f"1️⃣ Players take turns submitting words\n"
            f"2️⃣ Each word must start with the given letter\n"
            f"3️⃣ Word length increases by 1 each round\n"
            f"4️⃣ You have 30 seconds per turn\n"
            f"5️⃣ Words must be valid English words\n"
            f"6️⃣ Last letter of your word becomes the next starting letter\n\n"
            f"**Commands:**\n"
            f"• `/startgame` - Start a new game\n"
            f"• `/stopgame` - End current game\n"
            f"• `/status` - Show game status\n"
            f"• `/help` - Show help\n\n"
            f"**Example:**\n"
            f"Letter: C, Length: 3 → \"cat\"\n"
            f"Next: Letter: T, Length: 4 → \"tree\"\n\n"
            f"Good luck! {self.emojis['success']}"
        )


class GameAnnouncer:
    """Manages game announcements and user feedback."""
    
    def __init__(self, send_message_callback):
        """
        Initialize the announcer.
        
        Args:
            send_message_callback: Async function to send messages (chat_id, text, parse_mode)
        """
        self.send_message = send_message_callback
        self.formatter = AnnouncementFormatter()
        self._announcement_history: Dict[int, List[str]] = {}
    
    async def announce_game_start(
        self, 
        chat_id: int, 
        game_state: GameState, 
        include_rules: bool = True
    ) -> bool:
        """Announce game start."""
        try:
            message = self.formatter.format_game_start(game_state, include_rules)
            await self.send_message(chat_id, message, ParseMode.MARKDOWN)
            self._log_announcement(chat_id, AnnouncementType.GAME_START)
            return True
        except Exception as e:
            logger.error(f"Error announcing game start in chat {chat_id}: {e}")
            return False
    
    async def announce_game_end(
        self, 
        chat_id: int, 
        reason: str = "stopped", 
        winner: Optional[Player] = None
    ) -> bool:
        """Announce game end."""
        try:
            message = self.formatter.format_game_end(reason, winner)
            await self.send_message(chat_id, message, ParseMode.MARKDOWN)
            self._log_announcement(chat_id, AnnouncementType.GAME_END)
            return True
        except Exception as e:
            logger.error(f"Error announcing game end in chat {chat_id}: {e}")
            return False
    
    async def announce_turn_start(
        self, 
        chat_id: int, 
        game_state: GameState,
        hints: str = "",
        difficulty: str = ""
    ) -> bool:
        """Announce turn start."""
        try:
            message = self.formatter.format_turn_announcement(game_state, hints, difficulty)
            await self.send_message(chat_id, message, ParseMode.MARKDOWN)
            self._log_announcement(chat_id, AnnouncementType.TURN_START)
            return True
        except Exception as e:
            logger.error(f"Error announcing turn start in chat {chat_id}: {e}")
            return False
    
    async def announce_timeout(
        self, 
        chat_id: int, 
        timed_out_player: Player, 
        next_player: Player,
        game_state: GameState,
        hints: str = ""
    ) -> bool:
        """Announce turn timeout."""
        try:
            message = self.formatter.format_timeout_announcement(
                timed_out_player, next_player, game_state, hints
            )
            await self.send_message(chat_id, message, ParseMode.MARKDOWN)
            self._log_announcement(chat_id, AnnouncementType.TURN_TIMEOUT)
            return True
        except Exception as e:
            logger.error(f"Error announcing timeout in chat {chat_id}: {e}")
            return False
    
    async def announce_warning(
        self, 
        chat_id: int, 
        player: Player, 
        remaining_seconds: int
    ) -> bool:
        """Announce timeout warning."""
        try:
            message = self.formatter.format_warning_announcement(player, remaining_seconds)
            await self.send_message(chat_id, message, ParseMode.MARKDOWN)
            self._log_announcement(chat_id, AnnouncementType.TURN_WARNING)
            return True
        except Exception as e:
            logger.error(f"Error announcing warning in chat {chat_id}: {e}")
            return False
    
    async def announce_valid_word(
        self, 
        chat_id: int, 
        word: str, 
        player: Player,
        game_state: GameState,
        hints: str = "",
        difficulty: str = ""
    ) -> bool:
        """Announce valid word acceptance."""
        try:
            message = self.formatter.format_valid_word_announcement(
                word, player, game_state, hints, difficulty
            )
            await self.send_message(chat_id, message, ParseMode.MARKDOWN)
            self._log_announcement(chat_id, AnnouncementType.VALID_WORD)
            return True
        except Exception as e:
            logger.error(f"Error announcing valid word in chat {chat_id}: {e}")
            return False
    
    async def send_invalid_word_feedback(
        self, 
        chat_id: int, 
        result: GameResult, 
        error_message: str, 
        word: str
    ) -> bool:
        """Send invalid word feedback."""
        try:
            message = self.formatter.format_invalid_word_feedback(result, error_message, word)
            await self.send_message(chat_id, message, None)  # No markdown for simple feedback
            self._log_announcement(chat_id, AnnouncementType.INVALID_WORD)
            return True
        except Exception as e:
            logger.error(f"Error sending invalid word feedback in chat {chat_id}: {e}")
            return False
    
    async def announce_player_join(
        self, 
        chat_id: int, 
        player: Player, 
        game_state: GameState
    ) -> bool:
        """Announce player joining."""
        try:
            message = self.formatter.format_player_join_announcement(player, game_state)
            await self.send_message(chat_id, message, ParseMode.MARKDOWN)
            self._log_announcement(chat_id, AnnouncementType.PLAYER_JOIN)
            return True
        except Exception as e:
            logger.error(f"Error announcing player join in chat {chat_id}: {e}")
            return False
    
    async def announce_player_leave(
        self, 
        chat_id: int, 
        player: Player, 
        game_state: GameState
    ) -> bool:
        """Announce player leaving."""
        try:
            message = self.formatter.format_player_leave_announcement(player, game_state)
            await self.send_message(chat_id, message, ParseMode.MARKDOWN)
            self._log_announcement(chat_id, AnnouncementType.PLAYER_LEAVE)
            return True
        except Exception as e:
            logger.error(f"Error announcing player leave in chat {chat_id}: {e}")
            return False
    
    async def send_game_status(
        self, 
        chat_id: int, 
        game_state: GameState,
        remaining_time: Optional[float] = None,
        hints: str = "",
        difficulty: str = ""
    ) -> bool:
        """Send comprehensive game status."""
        try:
            message = self.formatter.format_game_status(
                game_state, remaining_time, hints, difficulty
            )
            await self.send_message(chat_id, message, ParseMode.MARKDOWN)
            self._log_announcement(chat_id, AnnouncementType.GAME_STATUS)
            return True
        except Exception as e:
            logger.error(f"Error sending game status in chat {chat_id}: {e}")
            return False
    
    async def send_game_rules(self, chat_id: int) -> bool:
        """Send game rules explanation."""
        try:
            message = self.formatter.format_game_rules()
            await self.send_message(chat_id, message, ParseMode.MARKDOWN)
            self._log_announcement(chat_id, AnnouncementType.GAME_RULES)
            return True
        except Exception as e:
            logger.error(f"Error sending game rules in chat {chat_id}: {e}")
            return False
    
    async def announce_player_eliminated(
        self, 
        chat_id: int, 
        eliminated_player: Player,
        reason: str = "timeout"
    ) -> bool:
        """Announce player elimination."""
        try:
            if reason == "timeout":
                message = (
                    f"⏰ **Time's up!**\n\n"
                    f"❌ {eliminated_player.first_name} has been **eliminated** for taking too long!\n\n"
                    f"💔 Better luck next time!"
                )
            else:
                message = (
                    f"❌ **Player Eliminated**\n\n"
                    f"💔 {eliminated_player.first_name} has been eliminated ({reason})\n\n"
                    f"Game continues with remaining players..."
                )
            
            await self.send_message(chat_id, message, ParseMode.MARKDOWN)
            logger.info(f"Player {eliminated_player.first_name} eliminated in chat {chat_id}")
            return True
        except Exception as e:
            logger.error(f"Error announcing player elimination in chat {chat_id}: {e}")
            return False
    
    async def announce_winner(
        self, 
        chat_id: int, 
        winner: Optional[Player] = None
    ) -> bool:
        """Announce game winner."""
        try:
            if winner:
                message = (
                    f"🏆 **GAME OVER!** 🏆\n\n"
                    f"🎉 **Congratulations {winner.first_name}!** 🎉\n\n"
                    f"👑 You are the **WORD GAME CHAMPION!** 👑\n\n"
                    f"🎮 Thanks for playing! Use /join to start a new game."
                )
            else:
                message = (
                    f"🏁 **GAME OVER!** 🏁\n\n"
                    f"😅 No winner this time - all players were eliminated!\n\n"
                    f"🎮 Use /join to start a new game."
                )
            
            await self.send_message(chat_id, message, ParseMode.MARKDOWN)
            logger.info(f"Game ended in chat {chat_id}, winner: {winner.first_name if winner else 'None'}")
            return True
        except Exception as e:
            logger.error(f"Error announcing winner in chat {chat_id}: {e}")
            return False
    
    def _log_announcement(self, chat_id: int, announcement_type: AnnouncementType) -> None:
        """Log announcement for tracking."""
        if chat_id not in self._announcement_history:
            self._announcement_history[chat_id] = []
        
        self._announcement_history[chat_id].append(announcement_type.value)
        
        # Keep only last 50 announcements per chat
        if len(self._announcement_history[chat_id]) > 50:
            self._announcement_history[chat_id] = self._announcement_history[chat_id][-50:]
        
        logger.debug(f"Logged {announcement_type.value} announcement for chat {chat_id}")
    
    def get_announcement_stats(self, chat_id: Optional[int] = None) -> Dict[str, Any]:
        """Get announcement statistics."""
        if chat_id:
            history = self._announcement_history.get(chat_id, [])
            return {
                'chat_id': chat_id,
                'total_announcements': len(history),
                'recent_announcements': history[-10:] if history else []
            }
        else:
            total_chats = len(self._announcement_history)
            total_announcements = sum(len(h) for h in self._announcement_history.values())
            return {
                'total_chats': total_chats,
                'total_announcements': total_announcements,
                'active_chats': list(self._announcement_history.keys())
            }


def create_game_announcer(send_message_callback) -> GameAnnouncer:
    """Factory function to create a GameAnnouncer."""
    return GameAnnouncer(send_message_callback)