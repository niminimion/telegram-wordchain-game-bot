"""
Word processing and validation logic for the Telegram Word Game Bot.
"""

import logging
import re
from typing import Tuple, Optional
from enum import Enum

from .models import GameState, GameResult
from . import word_validators as validators
from .word_validators import ValidationServiceUnavailable

logger = logging.getLogger(__name__)


class WordValidationError(Exception):
    """Raised when word validation fails for a specific reason."""
    
    def __init__(self, result: GameResult, message: str):
        self.result = result
        self.message = message
        super().__init__(message)


class WordProcessor:
    """Handles word processing and validation logic."""
    
    def __init__(self, word_validator: validators.WordValidator):
        self.word_validator = word_validator
        self._word_pattern = re.compile(r'^[a-zA-Z]+$')
    
    async def process_word_submission(
        self, 
        game_state: GameState, 
        player_id: int, 
        word: str
    ) -> Tuple[GameResult, Optional[str]]:
        """
        Process a word submission and return the result.
        
        Args:
            game_state: Current game state
            player_id: ID of the player submitting the word
            word: The submitted word
            
        Returns:
            Tuple of (GameResult, error_message)
        """
        try:
            # Validate game state
            if not game_state or not game_state.is_active:
                return GameResult.NO_ACTIVE_GAME, "No active game in this chat"
            
            # Validate player turn
            current_player = game_state.get_current_player()
            if not current_player:
                return GameResult.NO_ACTIVE_GAME, "No current player found"
            
            if current_player.user_id != player_id:
                return GameResult.WRONG_PLAYER, f"It's {current_player}'s turn, not yours"
            
            # Validate and normalize word
            normalized_word, validation_error = self._validate_word_format(word)
            if validation_error:
                return validation_error.result, validation_error.message

            # Enforce no-repeat rule (words are case-insensitive; we store normalized)
            if normalized_word in game_state.used_words:
                return GameResult.INVALID_WORD, f"'{word}' has already been used"
            
            # Check game-specific requirements
            letter_error = self._validate_starting_letter(normalized_word, game_state.current_letter)
            if letter_error:
                return letter_error.result, letter_error.message
            
            length_error = self._validate_word_length(normalized_word, game_state.required_length)
            if length_error:
                return length_error.result, length_error.message
            
            # Validate word exists in dictionary
            try:
                is_valid_word = await self.word_validator.validate_word(normalized_word)
                if not is_valid_word:
                    return GameResult.INVALID_WORD, f"'{word}' is not a valid English word"
            
            except ValidationServiceUnavailable as e:
                logger.error(f"Word validation service unavailable: {e}")
                return GameResult.VALIDATION_ERROR, "Word validation service is temporarily unavailable"
            
            # Word is valid
            logger.info(f"Valid word '{normalized_word}' submitted by player {player_id}")
            # Record word as used only on success
            game_state.used_words.add(normalized_word)
            return GameResult.VALID_WORD, None
        
        except Exception as e:
            logger.error(f"Unexpected error processing word '{word}': {e}")
            return GameResult.VALIDATION_ERROR, "An error occurred while processing your word"
    
    def _validate_word_format(self, word: str) -> Tuple[str, Optional[WordValidationError]]:
        """
        Validate and normalize word format.
        
        Returns:
            Tuple of (normalized_word, error)
        """
        if not word:
            return "", WordValidationError(
                GameResult.INVALID_WORD, 
                "Please enter a word"
            )
        
        # Normalize: strip whitespace and convert to lowercase
        normalized = word.strip().lower()
        
        if not normalized:
            return "", WordValidationError(
                GameResult.INVALID_WORD, 
                "Please enter a valid word"
            )
        
        # Check if word contains only letters
        if not self._word_pattern.match(normalized):
            return normalized, WordValidationError(
                GameResult.INVALID_WORD, 
                "Words can only contain letters (no numbers, spaces, or special characters)"
            )
        
        return normalized, None
    
    def _validate_starting_letter(self, word: str, required_letter: str) -> Optional[WordValidationError]:
        """Validate that word starts with the required letter."""
        if not word.startswith(required_letter.lower()):
            return WordValidationError(
                GameResult.INVALID_LETTER,
                f"Word must start with '{required_letter.upper()}'"
            )
        return None
    
    def _validate_word_length(self, word: str, required_length: int) -> Optional[WordValidationError]:
        """Validate that word meets the minimum length requirement."""
        actual_length = len(word)
        
        # Allow words that exceed the minimum length
        if actual_length < required_length:
            return WordValidationError(
                GameResult.INVALID_LENGTH,
                f"Word must be at least {required_length} letters long (yours is {actual_length})"
            )
        
        return None
    
    def get_next_game_state(self, word: str, game_state: GameState) -> GameState:
        """
        Calculate the next game state after a valid word submission.
        
        Args:
            word: The valid word that was submitted
            game_state: Current game state
            
        Returns:
            Updated game state (note: this modifies the original state)
        """
        # Update letter to last letter of the word (only for valid words)
        game_state.current_letter = word[-1].upper()
        
        # Advance to next player
        game_state.advance_turn()
        
        # Track turns and rounds
        game_state.current_round_turns += 1
        
        # Check if we completed a full round (all players have played)
        if game_state.current_round_turns >= len(game_state.players):
            game_state.rounds_completed += 1
            game_state.current_round_turns = 0
            
            # Increase minimum word length only after 2 complete rounds
            if game_state.rounds_completed >= 2 and game_state.rounds_completed % 2 == 0:
                game_state.required_length += 1
                logger.info(f"Completed {game_state.rounds_completed} rounds, "
                           f"increased minimum length to {game_state.required_length}")
        
        logger.info(f"Game state updated: next letter='{game_state.current_letter}', "
                   f"min_length={game_state.required_length}, "
                   f"player={game_state.get_current_player()}, "
                   f"rounds={game_state.rounds_completed}, "
                   f"round_turns={game_state.current_round_turns}")
        
        return game_state
    
    def format_word_feedback(self, result: GameResult, error_message: Optional[str], word: str) -> str:
        """
        Format user-friendly feedback for word submissions.
        
        Args:
            result: The validation result
            error_message: Optional error message
            word: The submitted word
            
        Returns:
            Formatted feedback message
        """
        if result == GameResult.VALID_WORD:
            return f"✅ Great! '{word}' is accepted."
        
        elif result == GameResult.INVALID_LETTER:
            return f"❌ {error_message}"
        
        elif result == GameResult.INVALID_LENGTH:
            return f"❌ {error_message}"
        
        elif result == GameResult.INVALID_WORD:
            return f"❌ {error_message}"
        
        elif result == GameResult.WRONG_PLAYER:
            return f"⏳ {error_message}"
        
        elif result == GameResult.NO_ACTIVE_GAME:
            return f"🎮 {error_message}"
        
        elif result == GameResult.VALIDATION_ERROR:
            return f"⚠️ {error_message}"
        
        else:
            return f"❓ Unknown error occurred with word '{word}'"
    
    def get_word_hints(self, game_state: GameState) -> str:
        """
        Generate helpful hints for the current word requirements.
        
        Args:
            game_state: Current game state
            
        Returns:
            Formatted hint message
        """
        letter = game_state.current_letter.upper()
        length = game_state.required_length
        
        if length == 1:
            return f"💡 Need a {length}-letter word starting with '{letter}' (like '{letter.lower()}')"
        elif length == 2:
            return f"💡 Need a {length}-letter word starting with '{letter}' (like '{letter.lower()}o')"
        elif length == 3:
            return f"💡 Need a {length}-letter word starting with '{letter}' (like '{letter.lower()}at')"
        else:
            return f"💡 Need a {length}-letter word starting with '{letter}'"
    
    def check_word_difficulty(self, game_state: GameState) -> str:
        """
        Assess the difficulty of the current word requirement.
        
        Args:
            game_state: Current game state
            
        Returns:
            Difficulty assessment message
        """
        length = game_state.required_length
        letter = game_state.current_letter.upper()
        
        # Difficult letters
        difficult_letters = {'Q', 'X', 'Z', 'J'}
        
        if length >= 10:
            return "🔥 This is getting very challenging!"
        elif length >= 7:
            return "🌶️ Getting difficult now!"
        elif length >= 5:
            return "📈 Moderate difficulty"
        elif letter in difficult_letters:
            return f"🤔 '{letter}' can be tricky!"
        else:
            return "😊 This should be manageable"


def create_word_processor(word_validator: validators.WordValidator) -> WordProcessor:
    """Factory function to create a WordProcessor instance."""
    return WordProcessor(word_validator)