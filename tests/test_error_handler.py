"""
Unit tests for comprehensive error handling and logging.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
from telegram.error import TelegramError, NetworkError, TimedOut, BadRequest, Forbidden

from bot.error_handler import (
    ErrorType,
    ErrorSeverity,
    ErrorInfo,
    RetryConfig,
    ErrorTracker,
    TelegramErrorHandler,
    ValidationErrorHandler,
    GameStateErrorHandler,
    ComprehensiveErrorHandler,
    handle_error_decorator
)


class TestErrorInfo:
    """Test cases for ErrorInfo class."""
    
    def test_error_info_creation(self):
        """Test creating ErrorInfo instance."""
        exception = ValueError("test error")
        context = {'key': 'value'}
        
        error_info = ErrorInfo(
            error_type=ErrorType.VALIDATION_SERVICE,
            severity=ErrorSeverity.HIGH,
            message="Test error message",
            exception=exception,
            context=context
        )
        
        assert error_info.error_type == ErrorType.VALIDATION_SERVICE
        assert error_info.severity == ErrorSeverity.HIGH
        assert error_info.message == "Test error message"
        assert error_info.exception == exception
        assert error_info.context == context
        assert isinstance(error_info.timestamp, datetime)
    
    def test_error_info_to_dict(self):
        """Test converting ErrorInfo to dictionary."""
        exception = ValueError("test error")
        error_info = ErrorInfo(
            error_type=ErrorType.NETWORK,
            severity=ErrorSeverity.MEDIUM,
            message="Network error",
            exception=exception
        )
        
        result = error_info.to_dict()
        
        assert result['error_type'] == 'network'
        assert result['severity'] == 'medium'
        assert result['message'] == 'Network error'
        assert result['exception_type'] == 'ValueError'
        assert 'timestamp' in result


class TestRetryConfig:
    """Test cases for RetryConfig class."""
    
    def test_retry_config_defaults(self):
        """Test RetryConfig with default values."""
        config = RetryConfig()
        
        assert config.max_attempts == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 60.0
        assert config.exponential_base == 2.0
    
    def test_retry_config_custom(self):
        """Test RetryConfig with custom values."""
        config = RetryConfig(
            max_attempts=5,
            base_delay=2.0,
            max_delay=120.0,
            exponential_base=3.0
        )
        
        assert config.max_attempts == 5
        assert config.base_delay == 2.0
        assert config.max_delay == 120.0
        assert config.exponential_base == 3.0
    
    def test_get_delay_calculation(self):
        """Test delay calculation."""
        config = RetryConfig(base_delay=1.0, exponential_base=2.0, max_delay=10.0)
        
        assert config.get_delay(1) == 1.0  # 1.0 * 2^0
        assert config.get_delay(2) == 2.0  # 1.0 * 2^1
        assert config.get_delay(3) == 4.0  # 1.0 * 2^2
        assert config.get_delay(4) == 8.0  # 1.0 * 2^3
        assert config.get_delay(5) == 10.0  # Capped at max_delay


class TestErrorTracker:
    """Test cases for ErrorTracker class."""
    
    @pytest.fixture
    def error_tracker(self):
        """Create an ErrorTracker instance."""
        return ErrorTracker(max_errors=10)
    
    def test_record_error(self, error_tracker):
        """Test recording errors."""
        error_info = ErrorInfo(
            error_type=ErrorType.NETWORK,
            severity=ErrorSeverity.MEDIUM,
            message="Network timeout"
        )
        
        error_tracker.record_error(error_info)
        
        assert len(error_tracker.errors) == 1
        assert error_tracker.errors[0] == error_info
        assert "network:Network timeout" in error_tracker.error_counts
        assert error_tracker.error_counts["network:Network timeout"] == 1
    
    def test_error_limit(self, error_tracker):
        """Test error list size limit."""
        # Add more errors than the limit
        for i in range(15):
            error_info = ErrorInfo(
                error_type=ErrorType.NETWORK,
                severity=ErrorSeverity.MEDIUM,
                message=f"Error {i}"
            )
            error_tracker.record_error(error_info)
        
        # Should be limited to max_errors
        assert len(error_tracker.errors) == 10
        # Should contain the most recent errors
        assert error_tracker.errors[-1].message == "Error 14"
    
    def test_get_error_stats(self, error_tracker):
        """Test getting error statistics."""
        # Add some errors
        for i in range(3):
            error_info = ErrorInfo(
                error_type=ErrorType.NETWORK,
                severity=ErrorSeverity.HIGH,
                message=f"Network error {i}"
            )
            error_tracker.record_error(error_info)
        
        for i in range(2):
            error_info = ErrorInfo(
                error_type=ErrorType.VALIDATION_SERVICE,
                severity=ErrorSeverity.MEDIUM,
                message=f"Validation error {i}"
            )
            error_tracker.record_error(error_info)
        
        stats = error_tracker.get_error_stats(24)
        
        assert stats['total_errors'] == 5
        assert stats['error_types']['network'] == 3
        assert stats['error_types']['validation_service'] == 2
        assert stats['error_severities']['high'] == 3
        assert stats['error_severities']['medium'] == 2
    
    def test_is_error_frequent(self, error_tracker):
        """Test frequent error detection."""
        error_type = ErrorType.NETWORK
        message = "Connection timeout"
        
        # Add errors below threshold
        for i in range(3):
            error_info = ErrorInfo(
                error_type=error_type,
                severity=ErrorSeverity.MEDIUM,
                message=message
            )
            error_tracker.record_error(error_info)
        
        assert not error_tracker.is_error_frequent(error_type, message, threshold=5)
        
        # Add more errors to exceed threshold
        for i in range(3):
            error_info = ErrorInfo(
                error_type=error_type,
                severity=ErrorSeverity.MEDIUM,
                message=message
            )
            error_tracker.record_error(error_info)
        
        assert error_tracker.is_error_frequent(error_type, message, threshold=5)


class TestTelegramErrorHandler:
    """Test cases for TelegramErrorHandler class."""
    
    @pytest.fixture
    def error_tracker(self):
        """Create an ErrorTracker instance."""
        return ErrorTracker()
    
    @pytest.fixture
    def telegram_handler(self, error_tracker):
        """Create a TelegramErrorHandler instance."""
        return TelegramErrorHandler(error_tracker)
    
    @pytest.mark.asyncio
    async def test_handle_network_error(self, telegram_handler):
        """Test handling network errors."""
        error = NetworkError("Connection failed")
        
        should_retry = await telegram_handler.handle_telegram_error(
            error, "send_message", {'chat_id': 12345}
        )
        
        assert should_retry == True
        assert len(telegram_handler.error_tracker.errors) == 1
    
    @pytest.mark.asyncio
    async def test_handle_timeout_error(self, telegram_handler):
        """Test handling timeout errors."""
        error = TimedOut("Request timed out")
        
        should_retry = await telegram_handler.handle_telegram_error(
            error, "send_message", {'chat_id': 12345}
        )
        
        assert should_retry == True
    
    @pytest.mark.asyncio
    async def test_handle_bad_request_chat_not_found(self, telegram_handler):
        """Test handling BadRequest with chat not found."""
        error = BadRequest("Chat not found")
        
        should_retry = await telegram_handler.handle_telegram_error(
            error, "send_message", {'chat_id': 12345}
        )
        
        assert should_retry == False  # Don't retry chat not found
    
    @pytest.mark.asyncio
    async def test_handle_forbidden_bot_blocked(self, telegram_handler):
        """Test handling Forbidden when bot is blocked."""
        error = Forbidden("Bot was blocked by the user")
        
        should_retry = await telegram_handler.handle_telegram_error(
            error, "send_message", {'user_id': 123}
        )
        
        assert should_retry == False  # Don't retry when blocked


class TestValidationErrorHandler:
    """Test cases for ValidationErrorHandler class."""
    
    @pytest.fixture
    def error_tracker(self):
        """Create an ErrorTracker instance."""
        return ErrorTracker()
    
    @pytest.fixture
    def validation_handler(self, error_tracker):
        """Create a ValidationErrorHandler instance."""
        return ValidationErrorHandler(error_tracker)
    
    def test_handle_nltk_error_with_wordnik_available(self, validation_handler):
        """Test handling NLTK error when Wordnik is available."""
        error = Exception("NLTK service down")
        
        should_retry = validation_handler.handle_validation_error(
            error, "nltk", "test", {}
        )
        
        assert should_retry == True  # Should fallback to Wordnik
        assert validation_handler.service_status['nltk'] == False
    
    def test_handle_wordnik_error(self, validation_handler):
        """Test handling Wordnik error."""
        error = Exception("Wordnik API error")
        
        should_retry = validation_handler.handle_validation_error(
            error, "wordnik", "test", {}
        )
        
        assert should_retry == False  # No fallback for Wordnik
        assert validation_handler.service_status['wordnik'] == False
    
    def test_is_service_healthy_recovery(self, validation_handler):
        """Test service health recovery."""
        # Mark service as failed
        validation_handler.service_status['nltk'] = False
        validation_handler.last_failure['nltk'] = datetime.now() - timedelta(minutes=10)
        
        # Should be marked as recovered after recovery time
        assert validation_handler.is_service_healthy('nltk', recovery_time_minutes=5) == True
        assert validation_handler.service_status['nltk'] == True


class TestGameStateErrorHandler:
    """Test cases for GameStateErrorHandler class."""
    
    @pytest.fixture
    def error_tracker(self):
        """Create an ErrorTracker instance."""
        return ErrorTracker()
    
    @pytest.fixture
    def game_state_handler(self, error_tracker):
        """Create a GameStateErrorHandler instance."""
        return GameStateErrorHandler(error_tracker)
    
    def test_handle_game_state_error(self, game_state_handler):
        """Test handling game state errors."""
        error = ValueError("Invalid game state")
        
        should_reset = game_state_handler.handle_game_state_error(
            error, 12345, "process_word", {}
        )
        
        assert should_reset == True
        assert len(game_state_handler.error_tracker.errors) == 1
    
    def test_handle_frequent_game_state_error(self, game_state_handler):
        """Test handling frequent game state errors."""
        # Mock frequent error detection
        game_state_handler.error_tracker.is_error_frequent = MagicMock(return_value=True)
        
        error = ValueError("Invalid game state")
        
        should_reset = game_state_handler.handle_game_state_error(
            error, 12345, "process_word", {}
        )
        
        assert should_reset == False  # Don't reset if frequent


class TestComprehensiveErrorHandler:
    """Test cases for ComprehensiveErrorHandler class."""
    
    @pytest.fixture
    def error_handler(self):
        """Create a ComprehensiveErrorHandler instance."""
        return ComprehensiveErrorHandler()
    
    @pytest.mark.asyncio
    async def test_handle_telegram_error(self, error_handler):
        """Test handling Telegram errors."""
        error = NetworkError("Connection failed")
        
        should_retry = await error_handler.handle_error(
            error, "send_message", {'chat_id': 12345}
        )
        
        assert should_retry == True
    
    @pytest.mark.asyncio
    async def test_handle_validation_error(self, error_handler):
        """Test handling validation errors."""
        error = Exception("Service down")
        
        should_retry = await error_handler.handle_error(
            error, "word_validation", {'service': 'nltk', 'word': 'test'}
        )
        
        assert should_retry == True  # Should fallback
    
    @pytest.mark.asyncio
    async def test_handle_game_state_error(self, error_handler):
        """Test handling game state errors."""
        error = ValueError("Invalid state")
        
        should_retry = await error_handler.handle_error(
            error, "game_operation", {'chat_id': 12345}
        )
        
        assert should_retry == True  # Should reset
    
    @pytest.mark.asyncio
    async def test_handle_unknown_error(self, error_handler):
        """Test handling unknown errors."""
        error = RuntimeError("Unknown error")
        
        should_retry = await error_handler.handle_error(
            error, "unknown_operation", {}
        )
        
        assert should_retry == False  # Don't retry unknown
    
    @pytest.mark.asyncio
    async def test_retry_with_backoff_success(self, error_handler):
        """Test retry with backoff - successful retry."""
        call_count = 0
        
        async def failing_operation():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise NetworkError("First attempt fails")
            return "success"
        
        result = await error_handler.retry_with_backoff(
            failing_operation,
            "test_operation",
            RetryConfig(max_attempts=2, base_delay=0.1)
        )
        
        assert result == "success"
        assert call_count == 2
    
    @pytest.mark.asyncio
    async def test_retry_with_backoff_all_fail(self, error_handler):
        """Test retry with backoff - all attempts fail."""
        call_count = 0
        
        async def always_failing_operation():
            nonlocal call_count
            call_count += 1
            raise ValueError("Always fails")
        
        with pytest.raises(ValueError, match="Always fails"):
            await error_handler.retry_with_backoff(
                always_failing_operation,
                "test_operation",
                RetryConfig(max_attempts=2, base_delay=0.1)
            )
        
        assert call_count == 2
    
    def test_get_error_summary(self, error_handler):
        """Test getting error summary."""
        # Add some errors
        error_info = ErrorInfo(
            error_type=ErrorType.NETWORK,
            severity=ErrorSeverity.HIGH,
            message="Network error"
        )
        error_handler.error_tracker.record_error(error_info)
        
        summary = error_handler.get_error_summary(24)
        
        assert 'total_errors' in summary
        assert 'error_types' in summary
        assert 'error_severities' in summary
        assert 'service_health' in summary


class TestErrorDecorator:
    """Test cases for error handling decorator."""
    
    @pytest.mark.asyncio
    async def test_decorator_success(self):
        """Test decorator with successful operation."""
        @handle_error_decorator("test_operation")
        async def successful_operation():
            return "success"
        
        result = await successful_operation()
        assert result == "success"
    
    @pytest.mark.asyncio
    async def test_decorator_with_error(self):
        """Test decorator with error."""
        call_count = 0
        
        @handle_error_decorator("test_operation")
        async def failing_operation():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise NetworkError("First attempt fails")
            return "success"
        
        # Mock the global error handler
        with patch('bot.error_handler.error_handler') as mock_handler:
            mock_handler.handle_error.return_value = True  # Should retry
            
            result = await failing_operation()
            assert result == "success"
            assert call_count == 2


if __name__ == "__main__":
    pytest.main([__file__])