"""
Comprehensive error handling and logging for the Telegram Word Game Bot.
"""

import logging
import traceback
import asyncio
from typing import Optional, Dict, Any, Callable, List
from enum import Enum
from datetime import datetime, timedelta
from telegram.error import TelegramError, NetworkError, TimedOut, BadRequest, Forbidden

logger = logging.getLogger(__name__)


class ErrorType(Enum):
    """Types of errors that can occur in the bot."""
    TELEGRAM_API = "telegram_api"
    NETWORK = "network"
    VALIDATION_SERVICE = "validation_service"
    GAME_STATE = "game_state"
    TIMER = "timer"
    DATABASE = "database"
    CONFIGURATION = "configuration"
    UNKNOWN = "unknown"


class ErrorSeverity(Enum):
    """Severity levels for errors."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorInfo:
    """Information about an error occurrence."""
    
    def __init__(
        self,
        error_type: ErrorType,
        severity: ErrorSeverity,
        message: str,
        exception: Optional[Exception] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        self.error_type = error_type
        self.severity = severity
        self.message = message
        self.exception = exception
        self.context = context or {}
        self.timestamp = datetime.now()
        self.traceback = traceback.format_exc() if exception else None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert error info to dictionary."""
        return {
            'error_type': self.error_type.value,
            'severity': self.severity.value,
            'message': self.message,
            'exception_type': type(self.exception).__name__ if self.exception else None,
            'context': self.context,
            'timestamp': self.timestamp.isoformat(),
            'traceback': self.traceback
        }


class RetryConfig:
    """Configuration for retry logic."""
    
    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0
    ):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
    
    def get_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt number."""
        delay = self.base_delay * (self.exponential_base ** (attempt - 1))
        return min(delay, self.max_delay)


class ErrorTracker:
    """Tracks error occurrences and patterns."""
    
    def __init__(self, max_errors: int = 1000):
        self.max_errors = max_errors
        self.errors: List[ErrorInfo] = []
        self.error_counts: Dict[str, int] = {}
        self.last_error_time: Dict[str, datetime] = {}
    
    def record_error(self, error_info: ErrorInfo) -> None:
        """Record an error occurrence."""
        # Add to error list
        self.errors.append(error_info)
        
        # Maintain size limit
        if len(self.errors) > self.max_errors:
            self.errors = self.errors[-self.max_errors:]
        
        # Update counts
        error_key = f"{error_info.error_type.value}:{error_info.message}"
        self.error_counts[error_key] = self.error_counts.get(error_key, 0) + 1
        self.last_error_time[error_key] = error_info.timestamp
    
    def get_error_stats(self, hours: int = 24) -> Dict[str, Any]:
        """Get error statistics for the last N hours."""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        recent_errors = [e for e in self.errors if e.timestamp > cutoff_time]
        
        # Count by type
        type_counts = {}
        severity_counts = {}
        
        for error in recent_errors:
            type_counts[error.error_type.value] = type_counts.get(error.error_type.value, 0) + 1
            severity_counts[error.severity.value] = severity_counts.get(error.severity.value, 0) + 1
        
        return {
            'total_errors': len(recent_errors),
            'error_types': type_counts,
            'error_severities': severity_counts,
            'time_period_hours': hours
        }
    
    def is_error_frequent(self, error_type: ErrorType, message: str, threshold: int = 5, minutes: int = 10) -> bool:
        """Check if an error is occurring frequently."""
        error_key = f"{error_type.value}:{message}"
        count = self.error_counts.get(error_key, 0)
        last_time = self.last_error_time.get(error_key)
        
        if not last_time:
            return False
        
        time_diff = datetime.now() - last_time
        return count >= threshold and time_diff.total_seconds() <= (minutes * 60)


class TelegramErrorHandler:
    """Handles Telegram-specific errors with retry logic."""
    
    def __init__(self, error_tracker: ErrorTracker):
        self.error_tracker = error_tracker
        self.retry_configs = {
            NetworkError: RetryConfig(max_attempts=3, base_delay=2.0),
            TimedOut: RetryConfig(max_attempts=2, base_delay=1.0),
            TelegramError: RetryConfig(max_attempts=2, base_delay=0.5)
        }
    
    async def handle_telegram_error(
        self,
        error: TelegramError,
        operation: str,
        context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Handle Telegram API errors.
        
        Returns:
            True if error was handled and operation should be retried
            False if error is unrecoverable
        """
        error_info = self._classify_telegram_error(error, operation, context)
        self.error_tracker.record_error(error_info)
        
        # Log the error
        logger.error(f"Telegram error in {operation}: {error}", extra={
            'error_type': error_info.error_type.value,
            'severity': error_info.severity.value,
            'context': context
        })
        
        # Handle specific error types
        if isinstance(error, BadRequest):
            return self._handle_bad_request(error, context)
        elif isinstance(error, Forbidden):
            return self._handle_forbidden(error, context)
        elif isinstance(error, NetworkError):
            return True  # Retry network errors
        elif isinstance(error, TimedOut):
            return True  # Retry timeouts
        else:
            return False  # Don't retry unknown errors
    
    def _classify_telegram_error(
        self,
        error: TelegramError,
        operation: str,
        context: Optional[Dict[str, Any]]
    ) -> ErrorInfo:
        """Classify a Telegram error."""
        if isinstance(error, (NetworkError, TimedOut)):
            severity = ErrorSeverity.MEDIUM
            error_type = ErrorType.NETWORK
        elif isinstance(error, BadRequest):
            severity = ErrorSeverity.LOW
            error_type = ErrorType.TELEGRAM_API
        elif isinstance(error, Forbidden):
            severity = ErrorSeverity.HIGH
            error_type = ErrorType.TELEGRAM_API
        else:
            severity = ErrorSeverity.MEDIUM
            error_type = ErrorType.TELEGRAM_API
        
        return ErrorInfo(
            error_type=error_type,
            severity=severity,
            message=f"{operation}: {str(error)}",
            exception=error,
            context=context
        )
    
    def _handle_bad_request(self, error: BadRequest, context: Optional[Dict[str, Any]]) -> bool:
        """Handle BadRequest errors."""
        error_message = str(error).lower()
        
        if "chat not found" in error_message:
            # Chat was deleted - clean up game state
            if context and 'chat_id' in context:
                logger.warning(f"Chat {context['chat_id']} not found - cleaning up")
                # This would trigger cleanup in the game manager
            return False  # Don't retry
        
        elif "message is not modified" in error_message:
            # Message edit failed - not critical
            return False  # Don't retry
        
        elif "message to edit not found" in error_message:
            # Message to edit doesn't exist - not critical
            return False  # Don't retry
        
        else:
            # Other bad requests might be temporary
            return True  # Retry once
    
    def _handle_forbidden(self, error: Forbidden, context: Optional[Dict[str, Any]]) -> bool:
        """Handle Forbidden errors."""
        error_message = str(error).lower()
        
        if "bot was blocked by the user" in error_message:
            # User blocked the bot - clean up
            if context and 'user_id' in context:
                logger.warning(f"Bot blocked by user {context['user_id']}")
            return False  # Don't retry
        
        elif "bot was kicked from the group" in error_message:
            # Bot was removed from group - clean up
            if context and 'chat_id' in context:
                logger.warning(f"Bot kicked from chat {context['chat_id']}")
            return False  # Don't retry
        
        else:
            return False  # Don't retry forbidden errors


class ValidationErrorHandler:
    """Handles word validation service errors."""
    
    def __init__(self, error_tracker: ErrorTracker):
        self.error_tracker = error_tracker
        self.service_status = {
            'nltk': True,
            'wordnik': True
        }
        self.last_failure = {
            'nltk': None,
            'wordnik': None
        }
    
    def handle_validation_error(
        self,
        error: Exception,
        service: str,
        word: str,
        context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Handle validation service errors.
        
        Returns:
            True if validation should be retried with fallback
            False if validation should fail
        """
        error_info = ErrorInfo(
            error_type=ErrorType.VALIDATION_SERVICE,
            severity=ErrorSeverity.MEDIUM,
            message=f"{service} validation failed for '{word}': {str(error)}",
            exception=error,
            context=context
        )
        
        self.error_tracker.record_error(error_info)
        
        # Update service status
        self.service_status[service] = False
        self.last_failure[service] = datetime.now()
        
        logger.error(f"Validation service {service} failed for word '{word}': {error}")
        
        # Check if we should try fallback
        if service == 'nltk' and self.service_status.get('wordnik', False):
            logger.info("Falling back to Wordnik API for validation")
            return True
        
        return False
    
    def is_service_healthy(self, service: str, recovery_time_minutes: int = 5) -> bool:
        """Check if a service has recovered."""
        if self.service_status.get(service, True):
            return True
        
        last_failure = self.last_failure.get(service)
        if not last_failure:
            return True
        
        time_since_failure = datetime.now() - last_failure
        if time_since_failure.total_seconds() > (recovery_time_minutes * 60):
            # Mark as potentially recovered
            self.service_status[service] = True
            logger.info(f"Marking {service} service as potentially recovered")
            return True
        
        return False


class GameStateErrorHandler:
    """Handles game state corruption and recovery."""
    
    def __init__(self, error_tracker: ErrorTracker):
        self.error_tracker = error_tracker
    
    def handle_game_state_error(
        self,
        error: Exception,
        chat_id: int,
        operation: str,
        context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Handle game state errors.
        
        Returns:
            True if game state should be reset
            False if error is not recoverable
        """
        error_info = ErrorInfo(
            error_type=ErrorType.GAME_STATE,
            severity=ErrorSeverity.HIGH,
            message=f"Game state error in chat {chat_id} during {operation}: {str(error)}",
            exception=error,
            context=context
        )
        
        self.error_tracker.record_error(error_info)
        
        logger.error(f"Game state corruption in chat {chat_id}: {error}")
        
        # Check if this is a frequent issue
        if self.error_tracker.is_error_frequent(ErrorType.GAME_STATE, operation):
            logger.critical(f"Frequent game state errors in operation {operation}")
            return False  # Don't reset if it keeps happening
        
        logger.info(f"Resetting game state for chat {chat_id}")
        return True  # Reset game state


class ComprehensiveErrorHandler:
    """Main error handler that coordinates all error handling."""
    
    def __init__(self):
        self.error_tracker = ErrorTracker()
        self.telegram_handler = TelegramErrorHandler(self.error_tracker)
        self.validation_handler = ValidationErrorHandler(self.error_tracker)
        self.game_state_handler = GameStateErrorHandler(self.error_tracker)
        
        # Setup logging
        self._setup_error_logging()
    
    def _setup_error_logging(self) -> None:
        """Setup comprehensive error logging."""
        # Create error logger
        error_logger = logging.getLogger('bot.errors')
        error_logger.setLevel(logging.ERROR)
        
        # Create file handler for errors
        try:
            error_handler = logging.FileHandler('bot_errors.log')
            error_handler.setLevel(logging.ERROR)
            
            # Create formatter
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            error_handler.setFormatter(formatter)
            
            error_logger.addHandler(error_handler)
            logger.info("Error logging to file enabled")
        except Exception as e:
            logger.warning(f"Could not setup file logging: {e}")
    
    async def handle_error(
        self,
        error: Exception,
        operation: str,
        context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Handle any error with appropriate strategy.
        
        Returns:
            True if operation should be retried
            False if operation should be abandoned
        """
        try:
            # Handle Telegram errors
            if isinstance(error, TelegramError):
                return await self.telegram_handler.handle_telegram_error(error, operation, context)
            
            # Handle validation errors
            elif "validation" in operation.lower():
                service = context.get('service', 'unknown') if context else 'unknown'
                word = context.get('word', '') if context else ''
                return self.validation_handler.handle_validation_error(error, service, word, context)
            
            # Handle game state errors
            elif "game" in operation.lower() or "state" in operation.lower():
                chat_id = context.get('chat_id', 0) if context else 0
                return self.game_state_handler.handle_game_state_error(error, chat_id, operation, context)
            
            # Handle unknown errors
            else:
                error_info = ErrorInfo(
                    error_type=ErrorType.UNKNOWN,
                    severity=ErrorSeverity.MEDIUM,
                    message=f"Unknown error in {operation}: {str(error)}",
                    exception=error,
                    context=context
                )
                
                self.error_tracker.record_error(error_info)
                logger.error(f"Unknown error in {operation}: {error}")
                
                return False  # Don't retry unknown errors
        
        except Exception as handler_error:
            logger.critical(f"Error in error handler: {handler_error}")
            return False
    
    async def retry_with_backoff(
        self,
        operation: Callable,
        operation_name: str,
        retry_config: Optional[RetryConfig] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Retry an operation with exponential backoff.
        
        Args:
            operation: Async function to retry
            operation_name: Name of the operation for logging
            retry_config: Retry configuration
            context: Additional context for error handling
        
        Returns:
            Result of the operation
        
        Raises:
            Last exception if all retries fail
        """
        if retry_config is None:
            retry_config = RetryConfig()
        
        last_exception = None
        
        for attempt in range(1, retry_config.max_attempts + 1):
            try:
                return await operation()
            
            except Exception as e:
                last_exception = e
                
                # Handle the error
                should_retry = await self.handle_error(e, operation_name, context)
                
                if not should_retry or attempt >= retry_config.max_attempts:
                    break
                
                # Calculate delay and wait
                delay = retry_config.get_delay(attempt)
                logger.info(f"Retrying {operation_name} in {delay:.1f}s (attempt {attempt + 1}/{retry_config.max_attempts})")
                await asyncio.sleep(delay)
        
        # All retries failed
        logger.error(f"All retries failed for {operation_name}")
        raise last_exception
    
    def get_error_summary(self, hours: int = 24) -> Dict[str, Any]:
        """Get comprehensive error summary."""
        stats = self.error_tracker.get_error_stats(hours)
        
        # Add service health status
        stats['service_health'] = {
            'nltk': self.validation_handler.is_service_healthy('nltk'),
            'wordnik': self.validation_handler.is_service_healthy('wordnik')
        }
        
        return stats
    
    def log_error_summary(self, hours: int = 24) -> None:
        """Log error summary."""
        summary = self.get_error_summary(hours)
        
        logger.info(f"Error Summary (last {hours}h):")
        logger.info(f"  Total errors: {summary['total_errors']}")
        
        if summary['error_types']:
            logger.info("  Error types:")
            for error_type, count in summary['error_types'].items():
                logger.info(f"    {error_type}: {count}")
        
        if summary['error_severities']:
            logger.info("  Error severities:")
            for severity, count in summary['error_severities'].items():
                logger.info(f"    {severity}: {count}")
        
        logger.info("  Service health:")
        for service, healthy in summary['service_health'].items():
            status = "✓" if healthy else "✗"
            logger.info(f"    {service}: {status}")


# Global error handler instance
error_handler = ComprehensiveErrorHandler()


def handle_error_decorator(operation_name: str):
    """Decorator for automatic error handling."""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                context = {
                    'function': func.__name__,
                    'args': str(args)[:100],  # Limit length
                    'kwargs': str(kwargs)[:100]
                }
                
                should_retry = await error_handler.handle_error(e, operation_name, context)
                
                if should_retry:
                    # Simple single retry
                    try:
                        return await func(*args, **kwargs)
                    except Exception:
                        pass  # Let original exception propagate
                
                raise e
        
        return wrapper
    return decorator