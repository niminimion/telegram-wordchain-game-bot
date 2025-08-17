"""
Example demonstrating the game announcements and user feedback system.
"""

import asyncio
import logging
from unittest.mock import AsyncMock

from bot.announcements import create_game_announcer, AnnouncementType
from bot.models import Player, GameState, GameConfig, GameResult

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MockTelegramBot:
    """Mock Telegram bot for demonstration."""
    
    def __init__(self):
        self.sent_messages = []
    
    async def send_message(self, chat_id: int, text: str, parse_mode=None):
        """Mock send message method."""
        self.sent_messages.append({
            'chat_id': chat_id,
            'text': text,
            'parse_mode': parse_mode
        })
        logger.info(f"📤 Sent to chat {chat_id}:")
        logger.info(f"   {text[:100]}{'...' if len(text) > 100 else ''}")


async def demonstrate_announcements():
    """Demonstrate various announcement types."""
    # Create mock bot and announcer
    mock_bot = MockTelegramBot()
    announcer = create_game_announcer(mock_bot.send_message)
    
    # Create test data
    players = [
        Player(user_id=1, username="alice", first_name="Alice"),
        Player(user_id=2, username="bob", first_name="Bob"),
        Player(user_id=3, username="charlie", first_name="Charlie")
    ]
    
    game_state = GameState(
        chat_id=12345,
        current_letter="C",
        required_length=3,
        current_player_index=0,
        players=players,
        is_active=True,
        game_config=GameConfig(turn_timeout=30)
    )
    
    chat_id = 12345
    
    logger.info("🎮 Demonstrating Game Announcements System\n")
    
    # 1. Game Start Announcement
    logger.info("1️⃣ Game Start Announcement:")
    await announcer.announce_game_start(chat_id, game_state, include_rules=True)
    await asyncio.sleep(0.1)
    
    # 2. Turn Start Announcement
    logger.info("\n2️⃣ Turn Start Announcement:")
    hints = "💡 Need a 3-letter word starting with 'C' (like 'cat')"
    difficulty = "😊 This should be manageable"
    await announcer.announce_turn_start(chat_id, game_state, hints, difficulty)
    await asyncio.sleep(0.1)
    
    # 3. Valid Word Announcement
    logger.info("\n3️⃣ Valid Word Announcement:")
    # Simulate game state after valid word
    game_state.current_letter = "T"
    game_state.required_length = 4
    game_state.advance_turn()
    
    await announcer.announce_valid_word(
        chat_id, "cat", players[0], game_state, 
        "💡 Need a 4-letter word starting with 'T'",
        "📈 Moderate difficulty"
    )
    await asyncio.sleep(0.1)
    
    # 4. Invalid Word Feedback
    logger.info("\n4️⃣ Invalid Word Feedback:")
    await announcer.send_invalid_word_feedback(
        chat_id, GameResult.INVALID_LETTER, "Word must start with 'T'", "cat"
    )
    await announcer.send_invalid_word_feedback(
        chat_id, GameResult.INVALID_LENGTH, "Word must be exactly 4 letters long", "to"
    )
    await announcer.send_invalid_word_feedback(
        chat_id, GameResult.INVALID_WORD, "'txyz' is not a valid English word", "txyz"
    )
    await asyncio.sleep(0.1)
    
    # 5. Timeout Warning
    logger.info("\n5️⃣ Timeout Warning:")
    current_player = game_state.get_current_player()
    await announcer.announce_warning(chat_id, current_player, 10)
    await announcer.announce_warning(chat_id, current_player, 5)
    await asyncio.sleep(0.1)
    
    # 6. Timeout Announcement
    logger.info("\n6️⃣ Timeout Announcement:")
    timed_out_player = current_player
    game_state.advance_turn()
    next_player = game_state.get_current_player()
    
    await announcer.announce_timeout(
        chat_id, timed_out_player, next_player, game_state,
        "💡 Need a 4-letter word starting with 'T'"
    )
    await asyncio.sleep(0.1)
    
    # 7. Player Join/Leave Announcements
    logger.info("\n7️⃣ Player Management Announcements:")
    new_player = Player(user_id=4, username="diana", first_name="Diana")
    await announcer.announce_player_join(chat_id, new_player, game_state)
    
    await announcer.announce_player_leave(chat_id, players[2], game_state)
    await asyncio.sleep(0.1)
    
    # 8. Game Status
    logger.info("\n8️⃣ Game Status:")
    await announcer.send_game_status(
        chat_id, game_state, 
        remaining_time=15.5,
        hints="💡 Need a 4-letter word starting with 'T'",
        difficulty="📈 Moderate difficulty"
    )
    await asyncio.sleep(0.1)
    
    # 9. Game Rules
    logger.info("\n9️⃣ Game Rules:")
    await announcer.send_game_rules(chat_id)
    await asyncio.sleep(0.1)
    
    # 10. Game End Announcements
    logger.info("\n🔟 Game End Announcements:")
    # Game stopped
    await announcer.announce_game_end(chat_id, "stopped")
    await asyncio.sleep(0.1)
    
    # Game completed with winner
    winner = players[0]
    await announcer.announce_game_end(chat_id, "completed", winner)
    await asyncio.sleep(0.1)
    
    # Show announcement statistics
    logger.info("\n📊 Announcement Statistics:")
    stats = announcer.get_announcement_stats(chat_id)
    logger.info(f"Chat {chat_id} stats:")
    logger.info(f"  Total announcements: {stats['total_announcements']}")
    logger.info(f"  Recent announcements: {stats['recent_announcements'][-5:]}")
    
    global_stats = announcer.get_announcement_stats()
    logger.info(f"Global stats:")
    logger.info(f"  Total chats: {global_stats['total_chats']}")
    logger.info(f"  Total announcements: {global_stats['total_announcements']}")
    
    # Show message summary
    logger.info(f"\n📈 Summary: Sent {len(mock_bot.sent_messages)} messages")
    
    # Show different announcement types used
    announcement_types = set()
    for i in range(len(mock_bot.sent_messages)):
        if i < len(stats['recent_announcements']):
            announcement_types.add(stats['recent_announcements'][i])
    
    logger.info(f"Announcement types demonstrated: {len(announcement_types)}")
    for ann_type in sorted(announcement_types):
        logger.info(f"  • {ann_type}")


async def demonstrate_formatting():
    """Demonstrate announcement formatting options."""
    logger.info("\n🎨 Demonstrating Announcement Formatting\n")
    
    from bot.announcements import AnnouncementFormatter
    
    formatter = AnnouncementFormatter()
    
    # Create test data
    players = [
        Player(user_id=1, username="alice", first_name="Alice"),
        Player(user_id=2, username="bob", first_name="Bob")
    ]
    
    game_state = GameState(
        chat_id=12345,
        current_letter="S",
        required_length=5,
        current_player_index=1,
        players=players,
        is_active=True,
        game_config=GameConfig()
    )
    
    # Test different formatting scenarios
    scenarios = [
        ("Game Start (with rules)", lambda: formatter.format_game_start(game_state, True)),
        ("Game Start (no rules)", lambda: formatter.format_game_start(game_state, False)),
        ("Turn Announcement", lambda: formatter.format_turn_announcement(
            game_state, "💡 Try 'snake' or 'smile'", "🌶️ Getting difficult now!"
        )),
        ("Valid Word", lambda: formatter.format_valid_word_announcement(
            "snake", players[1], game_state, "💡 Next hint", "🔥 Very challenging!"
        )),
        ("Timeout", lambda: formatter.format_timeout_announcement(
            players[1], players[0], game_state, "💡 Your turn now"
        )),
        ("Game Status", lambda: formatter.format_game_status(
            game_state, 12.3, "💡 Hint here", "🌟 Difficulty here"
        )),
        ("Game Rules", lambda: formatter.format_game_rules()),
    ]
    
    for name, formatter_func in scenarios:
        logger.info(f"📝 {name}:")
        message = formatter_func()
        # Show first few lines
        lines = message.split('\n')[:4]
        for line in lines:
            logger.info(f"   {line}")
        if len(message.split('\n')) > 4:
            logger.info("   ...")
        logger.info("")


if __name__ == "__main__":
    async def main():
        await demonstrate_announcements()
        await demonstrate_formatting()
        logger.info("🎉 Announcements demonstration complete!")
    
    asyncio.run(main())