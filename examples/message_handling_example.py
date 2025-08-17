"""
Example demonstrating advanced message handling and turn processing.
"""

import asyncio
import logging
from unittest.mock import MagicMock

from bot.validators import create_word_validator
from bot.game_manager import GameManager
from bot.timer_manager import GameTimerManager
from bot.message_handler import create_message_handler
from bot.models import Player, GameConfig

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MockTelegramUser:
    """Mock Telegram user for testing."""
    def __init__(self, user_id: int, username: str, first_name: str):
        self.id = user_id
        self.username = username
        self.first_name = first_name


async def simulate_message_handling():
    """Simulate message handling scenarios."""
    # Create components
    word_validator = create_word_validator()
    game_config = GameConfig(turn_timeout=30, timeout_warnings=[10, 5])
    game_manager = GameManager(word_validator, game_config)
    
    # Mock announcement callback
    async def mock_announcement(chat_id, event_type, **kwargs):
        logger.info(f"📢 Announcement in chat {chat_id}: {event_type}")
    
    timer_manager = GameTimerManager(game_manager, mock_announcement)
    message_handler = create_message_handler(game_manager, timer_manager)
    
    # Create test players
    players = [
        Player(user_id=1, username="alice", first_name="Alice"),
        Player(user_id=2, username="bob", first_name="Bob")
    ]
    
    chat_id = 12345
    
    try:
        # Start a game
        logger.info("🎮 Starting game...")
        game_state = await game_manager.start_game(chat_id, players)
        logger.info(f"Game started! Letter: {game_state.current_letter}, "
                   f"Length: {game_state.required_length}, "
                   f"Current player: {game_state.get_current_player()}")
        
        # Test message filtering
        logger.info("\n📝 Testing message filtering...")
        
        test_messages = [
            "cat",           # Valid word
            "/start",        # Command (should be ignored)
            "cat123",        # Invalid format
            "hello world",   # Multiple words
            "a",             # Single letter
            "@alice cat",    # Word with mention
        ]
        
        for msg in test_messages:
            should_process = message_handler.message_filter.should_process_message(msg, game_state)
            extracted = message_handler.message_filter.extract_word(msg)
            logger.info(f"Message: '{msg}' -> Process: {should_process}, Extracted: '{extracted}'")
        
        # Simulate turn processing
        logger.info("\n🔄 Simulating turn processing...")
        
        # Create mock users
        alice_user = MockTelegramUser(1, "alice", "Alice")
        bob_user = MockTelegramUser(2, "bob", "Bob")
        outsider_user = MockTelegramUser(999, "outsider", "Outsider")
        
        # Test scenarios
        scenarios = [
            (alice_user, f"{game_state.current_letter.lower()}at", "Valid word from correct player"),
            (bob_user, "cat", "Word from wrong player"),
            (outsider_user, "cat", "Word from user not in game"),
            (alice_user, "xyz", "Invalid word from correct player"),
            (alice_user, f"{game_state.current_letter.lower()}ats", "Wrong length word"),
        ]
        
        for user, word, description in scenarios:
            logger.info(f"\n📤 {description}: {user.first_name} -> '{word}'")
            
            result, error, should_advance = await message_handler.turn_processor.process_turn(
                chat_id, user, word
            )
            
            logger.info(f"   Result: {result.value}")
            if error:
                logger.info(f"   Error: {error}")
            logger.info(f"   Should advance: {should_advance}")
            
            if should_advance:
                # Handle turn advancement
                updated_state = await message_handler.turn_processor.handle_turn_advancement(chat_id)
                if updated_state:
                    logger.info(f"   Turn advanced! Next: {updated_state.get_current_player()}, "
                               f"Letter: {updated_state.current_letter}, "
                               f"Length: {updated_state.required_length}")
        
        # Test turn context
        logger.info("\n📊 Getting turn context...")
        context = message_handler.turn_processor.get_turn_context(chat_id)
        if context:
            logger.info(f"Current player: {context['current_player']}")
            logger.info(f"Next player: {context['next_player']}")
            logger.info(f"Letter: {context['letter']}, Length: {context['length']}")
            logger.info(f"Hints: {context['hints']}")
            logger.info(f"Difficulty: {context['difficulty']}")
        
        # Test response formatting
        logger.info("\n💬 Testing response formatting...")
        
        current_state = game_manager.get_game_status(chat_id)
        if current_state:
            # Valid word response
            hints = game_manager.get_word_hints(chat_id)
            valid_response = message_handler.response_formatter.format_valid_word_response(
                "test", current_state, hints
            )
            logger.info(f"Valid word response:\n{valid_response}")
            
            # Error response
            error_response = message_handler.response_formatter.format_error_response(
                game_manager.GameResult.INVALID_WORD, "Not a valid word", "xyz"
            )
            logger.info(f"Error response: {error_response}")
            
            # Game progress
            progress = message_handler.response_formatter.format_game_progress(current_state)
            logger.info(f"Game progress:\n{progress}")
        
        # Get statistics
        logger.info("\n📈 Message handler statistics:")
        stats = message_handler.get_message_stats()
        logger.info(f"Active games: {stats['active_games']}")
        logger.info(f"Total players: {stats['total_players']}")
        
    except Exception as e:
        logger.error(f"Error in simulation: {e}")
    
    finally:
        # Cleanup
        logger.info("\n🧹 Cleaning up...")
        await timer_manager.cleanup()
        await game_manager.stop_game(chat_id)
        logger.info("Simulation complete!")


if __name__ == "__main__":
    asyncio.run(simulate_message_handling())