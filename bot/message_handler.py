"""
Advanced message handling and turn processing for the Telegram Word Game Bot.
"""

import logging
import re
from typing import Optional, Tuple, List
from telegram import Update, User
from telegram.ext import ContextTypes

from .models import Player, GameResult, GameState
from .game_manager import GameManager
from .timer_manager import GameTimerManager
from .announcements import AnnouncementFormatter

logger = logging.getLogger(__name__)


class MessageFilter:
    """Filters and validates incoming messages for game processing."""
    
    def __init__(self):
        # Pattern to match potential words (letters only, reasonable length)
        self.word_pattern = re.compile(r'^[a-zA-Z]{1,20}$')
        # Pattern to detect commands (starts with /)
        self.command_pattern = re.compile(r'^/')
        # Pattern to detect bot mentions
        self.mention_pattern = re.compile(r'@\w+')
    
    def is_potential_word(self, text: str) -> bool:
        """Check if message text could be a word submission."""
        if not text:
            return False
        
        # Remove mentions and extra whitespace
        cleaned_text = self.mention_pattern.sub('', text).strip()
        
        # Check if it matches word pattern
        return bool(self.word_pattern.match(cleaned_text))
    
    def is_command(self, text: str) -> bool:
        """Check if message is a command."""
        return bool(self.command_pattern.match(text.strip()))
    
    def extract_word(self, text: str) -> Optional[str]:
        """Extract the word from message text."""
        if not text:
            return None
        
        # Remove mentions and extra whitespace
        cleaned_text = self.mention_pattern.sub('', text).strip()
        
        # Return the cleaned word if it matches pattern
        if self.word_pattern.match(cleaned_text):
            return cleaned_text.lower()
        
        return None
    
    def should_process_message(self, text: str, game_state: Optional[GameState]) -> bool:
        """Determine if message should be processed for word submission."""
        if not text or not game_state or not game_state.is_active:
            return False
        
        # Don't process commands
        if self.is_command(text):
            return False
        
        # Only process potential words
        return self.is_potential_word(text)


class TurnProcessor:
    """Handles turn processing logic and player validation."""
    
    def __init__(self, game_manager: GameManager, timer_manager: GameTimerManager):
        self.game_manager = game_manager
        self.timer_manager = timer_manager
    
    async def process_turn(
        self, 
        chat_id: int, 
        user: User, 
        word: str
    ) -> Tuple[GameResult, Optional[str], bool]:
        """
        Process a player's turn.
        
        Args:
            chat_id: The chat ID
            user: The Telegram user
            word: The submitted word
            
        Returns:
            Tuple of (result, error_message, should_advance_turn)
        """
        try:
            # Get current game state
            game_state = self.game_manager.get_game_status(chat_id)
            if not game_state or not game_state.is_active:
                return GameResult.NO_ACTIVE_GAME, "No active game in this chat", False
            
            # Validate it's the correct player's turn
            current_player = game_state.get_current_player()
            if not current_player:
                return GameResult.NO_ACTIVE_GAME, "No current player found", False
            
            if current_player.user_id != user.id:
                # Check if user is even in the game
                user_in_game = any(p.user_id == user.id for p in game_state.players)
                if user_in_game:
                    return GameResult.WRONG_PLAYER, f"It's {current_player}'s turn, please wait", False
                else:
                    # User not in game - ignore silently
                    return GameResult.WRONG_PLAYER, None, False
            
            # Process the word
            result, error_message = await self.game_manager.process_word(chat_id, user.id, word)
            
            # Determine if turn should advance
            should_advance = (result == GameResult.VALID_WORD)
            
            return result, error_message, should_advance
            
        except Exception as e:
            logger.error(f"Error processing turn for user {user.id} in chat {chat_id}: {e}")
            return GameResult.VALIDATION_ERROR, "An error occurred processing your word", False
    
    async def handle_turn_advancement(self, chat_id: int) -> Optional[GameState]:
        """Handle turn advancement after a valid word."""
        try:
            # Cancel current timer
            await self.timer_manager.cancel_turn_timer(chat_id)
            
            # Get updated game state
            game_state = self.game_manager.get_game_status(chat_id)
            if not game_state or not game_state.is_active:
                return None
            
            # Start timer for next turn
            await self.timer_manager.start_turn_timer(chat_id)
            
            return game_state
            
        except Exception as e:
            logger.error(f"Error handling turn advancement in chat {chat_id}: {e}")
            return None
    
    def get_turn_context(self, chat_id: int) -> Optional[dict]:
        """Get context information about the current turn."""
        game_state = self.game_manager.get_game_status(chat_id)
        if not game_state or not game_state.is_active:
            return None
        
        current_player = game_state.get_current_player()
        next_player = game_state.get_next_player()
        remaining_time = self.game_manager.get_turn_time_remaining(chat_id)
        
        return {
            'current_player': current_player,
            'next_player': next_player,
            'letter': game_state.current_letter,
            'length': game_state.required_length,
            'remaining_time': remaining_time,
            'hints': self.game_manager.get_word_hints(chat_id),
            'difficulty': self.game_manager.get_difficulty_assessment(chat_id)
        }


class MessageResponseFormatter:
    """Formats responses for different message scenarios."""
    
    def __init__(self, game_manager: GameManager):
        self.game_manager = game_manager
    
    def format_valid_word_response(self, word: str, game_state: GameState, hints: str) -> str:
        """Format response for valid word submission."""
        next_player = game_state.get_current_player()
        
        return (
            f"✅ **Great!** '{word}' is accepted!\n\n"
            f"🎯 **Next Challenge:**\n"
            f"📍 Turn: {next_player}\n"
            f"🔤 Letter: **{game_state.current_letter}**\n"
            f"📏 Length: **{game_state.required_length}** letters\n\n"
            f"{hints}"
        )
    
    def format_error_response(self, result: GameResult, error_message: str, word: str) -> str:
        """Format response for invalid word submission."""
        return self.game_manager.format_word_feedback(result, error_message, word)
    
    def format_turn_reminder(self, current_player: Player, context: dict) -> str:
        """Format a gentle turn reminder."""
        return (
            f"⏰ {current_player}, it's your turn!\n\n"
            f"🔤 Letter: **{context['letter']}**\n"
            f"📏 Length: **{context['length']}** letters\n\n"
            f"{context['hints']}"
        )
    
    def format_game_progress(self, game_state: GameState) -> str:
        """Format current game progress information."""
        current_player = game_state.get_current_player()
        
        # Create player list with current player highlighted
        player_list = []
        for i, player in enumerate(game_state.players):
            if i == game_state.current_player_index:
                player_list.append(f"👉 **{player}** (current)")
            else:
                player_list.append(f"   {player}")
        
        return (
            f"🎮 **Game Progress**\n\n"
            f"📍 **Current Turn:** {current_player}\n"
            f"🔤 **Letter:** {game_state.current_letter}\n"
            f"📏 **Length:** {game_state.required_length} letters\n\n"
            f"👥 **Players:**\n" + "\n".join(player_list)
        )


class AdvancedMessageHandler:
    """Advanced message handler with sophisticated turn processing."""
    
    def __init__(self, game_manager: GameManager, timer_manager: GameTimerManager):
        self.game_manager = game_manager
        self.timer_manager = timer_manager
        self.message_filter = MessageFilter()
        self.turn_processor = TurnProcessor(game_manager, timer_manager)
        self.response_formatter = MessageResponseFormatter(game_manager)
        self.announcement_formatter = AnnouncementFormatter()
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle incoming messages with advanced processing.
        
        This is the main entry point for message processing.
        """
        try:
            if not update.effective_chat or not update.effective_user or not update.message:
                return
            
            chat_id = update.effective_chat.id
            user = update.effective_user
            message_text = update.message.text
            
            if not message_text:
                return
            
            # Get current game state
            game_state = self.game_manager.get_game_status(chat_id)
            
            # Check if message should be processed
            if not self.message_filter.should_process_message(message_text, game_state):
                return
            
            # Extract word from message
            word = self.message_filter.extract_word(message_text)
            if not word:
                return
            
            # Process the turn
            result, error_message, should_advance = await self.turn_processor.process_turn(
                chat_id, user, word
            )
            
            # Handle the result
            await self._handle_turn_result(
                update, chat_id, word, result, error_message, should_advance
            )
            
        except Exception as e:
            logger.error(f"Error in advanced message handler: {e}")
            # Don't send error messages to avoid spam
    
    async def _handle_turn_result(
        self,
        update: Update,
        chat_id: int,
        word: str,
        result: GameResult,
        error_message: Optional[str],
        should_advance: bool
    ) -> None:
        """Handle the result of turn processing."""
        try:
            if result == GameResult.VALID_WORD and should_advance:
                # Handle successful word submission
                updated_state = await self.turn_processor.handle_turn_advancement(chat_id)
                
                if updated_state:
                    # Get the submitting player
                    submitting_player = None
                    user_id = update.effective_user.id
                    for player in updated_state.players:
                        if player.user_id == user_id:
                            submitting_player = player
                            break
                    
                    if submitting_player:
                        hints = self.game_manager.get_word_hints(chat_id)
                        # Use the proper announcement format that tags the player
                        response = self.announcement_formatter.format_valid_word_announcement(
                            word, submitting_player, updated_state, hints
                        )
                        
                        await update.message.reply_text(
                            response,
                            parse_mode='Markdown'
                        )
            
            elif result in [GameResult.INVALID_LETTER, GameResult.INVALID_LENGTH, 
                          GameResult.INVALID_WORD, GameResult.VALIDATION_ERROR]:
                # Handle invalid word submission
                if error_message:
                    response = self.response_formatter.format_error_response(
                        result, error_message, word
                    )
                    
                    await update.message.reply_text(response)
            
            elif result == GameResult.WRONG_PLAYER:
                # Handle wrong player turn (only respond if there's a message)
                if error_message:
                    await update.message.reply_text(error_message)
            
            # For NO_ACTIVE_GAME, we silently ignore
            
        except Exception as e:
            logger.error(f"Error handling turn result: {e}")
    
    async def send_turn_reminder(self, chat_id: int) -> bool:
        """Send a gentle reminder to the current player."""
        try:
            context = self.turn_processor.get_turn_context(chat_id)
            if not context or not context['current_player']:
                return False
            
            reminder = self.response_formatter.format_turn_reminder(
                context['current_player'], context
            )
            
            # This would need to be called from the bot instance
            # Implementation depends on how reminders are triggered
            return True
            
        except Exception as e:
            logger.error(f"Error sending turn reminder: {e}")
            return False
    
    def get_message_stats(self) -> dict:
        """Get statistics about message processing."""
        # This could be enhanced with actual statistics tracking
        return {
            'active_games': self.game_manager.get_active_game_count(),
            'total_players': self.game_manager.get_total_player_count()
        }


def create_message_handler(game_manager: GameManager, timer_manager: GameTimerManager) -> AdvancedMessageHandler:
    """Factory function to create an AdvancedMessageHandler."""
    return AdvancedMessageHandler(game_manager, timer_manager)