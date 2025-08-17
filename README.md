# Telegram Word Game Bot

A Telegram bot that manages turn-based word games in group chats.

## Features

- Turn-based word game with increasing word length requirements
- Word validation using NLTK and optional Wordnik API
- 30-second turn timers with automatic skipping
- Support for multiple concurrent games across different chats
- Commands: `/startgame`, `/stopgame`, `/status`

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Create a `.env` file at the project root and add your Telegram bot token and optional settings:
   ```
   TELEGRAM_BOT_TOKEN=your_bot_token_here
   LOG_LEVEL=INFO
   MAX_GAMES=100
   WORDNIK_API_KEY=
   TURN_TIMEOUT=30
   MIN_WORD_LENGTH=2
   MAX_WORD_LENGTH=20
   MAX_PLAYERS=10
   ```

4. Run the bot:
   ```bash
   python main.py
   ```
   If you see a configuration error, ensure `.env` exists and `TELEGRAM_BOT_TOKEN` is set. The bot reads env vars via `python-dotenv` in `bot/config.py`.

## Requirements

- Python 3.10+
- Telegram Bot Token (get from @BotFather)
- Optional: Wordnik API key for enhanced word validation

## Game Rules

1. Players take turns submitting words
2. Each word must start with the specified letter
3. Word length increases by 1 each round
4. Players have 30 seconds per turn
5. Words must be valid English dictionary words

## Testing

The bot includes a comprehensive test suite with multiple types of tests:

### Running Tests

```bash
# Run all tests
python run_tests.py

# Run specific test types
python run_tests.py unit          # Unit tests only
python run_tests.py integration   # Integration tests only
python run_tests.py performance   # Performance tests only
python run_tests.py edge          # Edge case tests only
python run_tests.py coverage      # Run with coverage reporting
```

### Test Types

1. **Unit Tests** - Test individual components in isolation
   - Models and data structures
   - Word validation system
   - Game logic and state management
   - Timer system
   - Message handling
   - Error handling
   - Concurrent game management

2. **Integration Tests** - Test complete workflows
   - Full game lifecycle (start → play → end)
   - Multiple concurrent games
   - Error recovery scenarios
   - Timer integration with game flow
   - Message processing pipeline

3. **Performance Tests** - Validate system performance
   - Concurrent game creation (50+ games)
   - Word processing throughput
   - Timer accuracy and concurrent timers
   - Memory usage stability
   - Resource monitoring performance

4. **Edge Case Tests** - Handle unusual scenarios
   - Empty/invalid inputs
   - Corrupted game states
   - Concurrent operations
   - Resource exhaustion
   - Network failures

### Test Coverage

The test suite covers:
- ✅ All core game mechanics
- ✅ Word validation with fallback services
- ✅ Timer system with timeout handling
- ✅ Concurrent game management
- ✅ Error handling and recovery
- ✅ Telegram bot integration
- ✅ Performance under load
- ✅ Edge cases and error conditions

### Running Individual Tests

```bash
# Run specific test files
python -m pytest tests/test_game_manager.py -v
python -m pytest tests/test_integration.py -v -s

# Run with coverage
python -m pytest --cov=bot --cov-report=html

# Run performance tests with output
python -m pytest tests/test_performance.py -v -s
```