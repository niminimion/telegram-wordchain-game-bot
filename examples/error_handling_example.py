"""
Example demonstrating comprehensive error handling and logging.
"""

import asyncio
import logging
from unittest.mock import AsyncMock
from telegram.error import NetworkError, BadRequest, Forbidden

from bot.error_handler import (
    error_handler,
    handle_error_decorator,
    ErrorType,
    ErrorSeverity,
    RetryConfig
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MockTelegramAPI:
    """Mock Telegram API for demonstration."""
    
    def __init__(self):
        self.call_count = 0
        self.should_fail = True
    
    async def send_message(self, chat_id: int, text: str):
        """Mock send message that sometimes fails."""
        self.call_count += 1
        
        if self.should_fail and self.call_count <= 2:
            if self.call_count == 1:
                raise NetworkError("Connection timeout")
            else:
                raise BadRequest("Rate limit exceeded")
        
        return f"Message sent to {chat_id}: {text[:20]}..."


class MockValidationService:
    """Mock validation service for demonstration."""
    
    def __init__(self):
        self.call_count = 0
    
    async def validate_word(self, word: str):
        """Mock validation that fails initially."""
        self.call_count += 1
        
        if self.call_count <= 1:
            raise Exception("Service temporarily unavailable")
        
        return word.isalpha() and len(word) > 2


async def demonstrate_telegram_error_handling():
    """Demonstrate Telegram API error handling."""
    logger.info("🔧 Demonstrating Telegram Error Handling\n")
    
    mock_api = MockTelegramAPI()
    
    async def send_message_operation():
        return await mock_api.send_message(12345, "Hello, world!")
    
    try:
        # This will fail initially but succeed after retries
        result = await error_handler.retry_with_backoff(
            send_message_operation,
            "send_telegram_message",
            RetryConfig(max_attempts=3, base_delay=0.1),
            context={'chat_id': 12345, 'operation': 'send_message'}
        )
        
        logger.info(f"✅ Success: {result}")
        logger.info(f"📊 Total API calls: {mock_api.call_count}")
        
    except Exception as e:
        logger.error(f"❌ Failed after all retries: {e}")


async def demonstrate_validation_error_handling():
    """Demonstrate validation service error handling."""
    logger.info("\n🔍 Demonstrating Validation Error Handling\n")
    
    mock_service = MockValidationService()
    
    async def validate_word_operation():
        return await mock_service.validate_word("hello")
    
    try:
        result = await error_handler.retry_with_backoff(
            validate_word_operation,
            "word_validation",
            RetryConfig(max_attempts=3, base_delay=0.1),
            context={'service': 'nltk', 'word': 'hello'}
        )
        
        logger.info(f"✅ Validation result: {result}")
        logger.info(f"📊 Total validation calls: {mock_service.call_count}")
        
    except Exception as e:
        logger.error(f"❌ Validation failed: {e}")


@handle_error_decorator("decorated_operation")
async def decorated_failing_operation(should_succeed_on_retry=True):
    """Example of using the error handling decorator."""
    if not hasattr(decorated_failing_operation, 'call_count'):
        decorated_failing_operation.call_count = 0
    
    decorated_failing_operation.call_count += 1
    
    if decorated_failing_operation.call_count == 1:
        raise NetworkError("First attempt always fails")
    elif decorated_failing_operation.call_count == 2 and should_succeed_on_retry:
        return "Success on retry!"
    else:
        raise Exception("Persistent failure")


async def demonstrate_decorator_usage():
    """Demonstrate error handling decorator."""
    logger.info("\n🎯 Demonstrating Error Handling Decorator\n")
    
    try:
        # Reset call count
        if hasattr(decorated_failing_operation, 'call_count'):
            delattr(decorated_failing_operation, 'call_count')
        
        result = await decorated_failing_operation(should_succeed_on_retry=True)
        logger.info(f"✅ Decorator result: {result}")
        
    except Exception as e:
        logger.error(f"❌ Decorator failed: {e}")


async def demonstrate_error_classification():
    """Demonstrate error classification and tracking."""
    logger.info("\n📊 Demonstrating Error Classification\n")
    
    # Simulate various types of errors
    errors_to_simulate = [
        (NetworkError("Connection failed"), "telegram_operation"),
        (BadRequest("Chat not found"), "send_message"),
        (Forbidden("Bot was blocked"), "send_message"),
        (Exception("NLTK service down"), "word_validation"),
        (ValueError("Invalid game state"), "game_operation"),
        (RuntimeError("Unknown error"), "unknown_operation")
    ]
    
    for error, operation in errors_to_simulate:
        try:
            context = {
                'operation': operation,
                'error_type': type(error).__name__
            }
            
            should_retry = await error_handler.handle_error(error, operation, context)
            logger.info(f"🔍 {type(error).__name__} in {operation}: retry={should_retry}")
            
        except Exception as e:
            logger.error(f"❌ Error handling failed: {e}")
    
    # Show error statistics
    logger.info("\n📈 Error Statistics:")
    stats = error_handler.get_error_summary(1)  # Last 1 hour
    
    logger.info(f"Total errors: {stats['total_errors']}")
    
    if stats['error_types']:
        logger.info("Error types:")
        for error_type, count in stats['error_types'].items():
            logger.info(f"  {error_type}: {count}")
    
    if stats['error_severities']:
        logger.info("Error severities:")
        for severity, count in stats['error_severities'].items():
            logger.info(f"  {severity}: {count}")
    
    logger.info("Service health:")
    for service, healthy in stats['service_health'].items():
        status = "✅" if healthy else "❌"
        logger.info(f"  {service}: {status}")


async def demonstrate_specific_error_scenarios():
    """Demonstrate specific error scenarios."""
    logger.info("\n🎭 Demonstrating Specific Error Scenarios\n")
    
    # Scenario 1: Chat deleted
    logger.info("Scenario 1: Chat deleted")
    chat_deleted_error = BadRequest("Chat not found")
    should_retry = await error_handler.handle_error(
        chat_deleted_error, 
        "send_message", 
        {'chat_id': 12345}
    )
    logger.info(f"  Should retry: {should_retry} (expected: False)")
    
    # Scenario 2: Bot blocked by user
    logger.info("Scenario 2: Bot blocked by user")
    bot_blocked_error = Forbidden("Bot was blocked by the user")
    should_retry = await error_handler.handle_error(
        bot_blocked_error, 
        "send_message", 
        {'user_id': 123}
    )
    logger.info(f"  Should retry: {should_retry} (expected: False)")
    
    # Scenario 3: Network timeout
    logger.info("Scenario 3: Network timeout")
    network_error = NetworkError("Connection timeout")
    should_retry = await error_handler.handle_error(
        network_error, 
        "send_message", 
        {'chat_id': 12345}
    )
    logger.info(f"  Should retry: {should_retry} (expected: True)")
    
    # Scenario 4: Validation service down
    logger.info("Scenario 4: Validation service down")
    validation_error = Exception("Service unavailable")
    should_retry = await error_handler.handle_error(
        validation_error, 
        "word_validation", 
        {'service': 'nltk', 'word': 'test'}
    )
    logger.info(f"  Should retry: {should_retry} (expected: True - fallback)")


async def demonstrate_retry_configurations():
    """Demonstrate different retry configurations."""
    logger.info("\n⚙️ Demonstrating Retry Configurations\n")
    
    # Fast retry for quick operations
    fast_config = RetryConfig(
        max_attempts=2,
        base_delay=0.1,
        max_delay=1.0,
        exponential_base=2.0
    )
    
    # Slow retry for heavy operations
    slow_config = RetryConfig(
        max_attempts=5,
        base_delay=1.0,
        max_delay=30.0,
        exponential_base=2.0
    )
    
    logger.info("Fast retry delays:")
    for attempt in range(1, fast_config.max_attempts + 1):
        delay = fast_config.get_delay(attempt)
        logger.info(f"  Attempt {attempt}: {delay:.1f}s")
    
    logger.info("Slow retry delays:")
    for attempt in range(1, slow_config.max_attempts + 1):
        delay = slow_config.get_delay(attempt)
        logger.info(f"  Attempt {attempt}: {delay:.1f}s")


async def main():
    """Run all error handling demonstrations."""
    logger.info("🚀 Starting Error Handling Demonstrations\n")
    
    try:
        await demonstrate_telegram_error_handling()
        await demonstrate_validation_error_handling()
        await demonstrate_decorator_usage()
        await demonstrate_error_classification()
        await demonstrate_specific_error_scenarios()
        await demonstrate_retry_configurations()
        
        logger.info("\n🎉 All demonstrations completed successfully!")
        
        # Final error summary
        logger.info("\n📋 Final Error Summary:")
        error_handler.log_error_summary(1)
        
    except Exception as e:
        logger.error(f"❌ Demonstration failed: {e}")


if __name__ == "__main__":
    asyncio.run(main())