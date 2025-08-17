"""
Health check and monitoring endpoints for the Telegram Word Game Bot.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from .config import config
from . import word_validators as validators
from .error_handler import error_handler

logger = logging.getLogger(__name__)


class HealthChecker:
    """Performs comprehensive health checks."""
    
    def __init__(self, game_manager=None):
        self.game_manager = game_manager
        self.start_time = datetime.now()
    
    async def check_configuration(self) -> Dict[str, Any]:
        """Check configuration health."""
        try:
            config.validate()
            return {
                'status': 'healthy',
                'bot_token_configured': bool(config.telegram_bot_token),
                'wordnik_api_configured': bool(config.wordnik_api_key),
                'log_level': config.log_level,
                'max_games': config.max_concurrent_games
            }
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e)
            }
    
    async def check_word_validator(self) -> Dict[str, Any]:
        """Check word validation services."""
        try:
            word_validator = validators.create_word_validator(config.wordnik_api_key)
            
            # Test basic validation
            test_result = await asyncio.wait_for(
                word_validator.validate_word("test"),
                timeout=5.0
            )
            
            service_available = await word_validator.is_service_available()
            
            return {
                'status': 'healthy' if service_available else 'degraded',
                'service_available': service_available,
                'test_validation_result': test_result,
                'has_wordnik_fallback': bool(config.wordnik_api_key)
            }
        except asyncio.TimeoutError:
            return {
                'status': 'unhealthy',
                'error': 'Word validation timeout'
            }
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e)
            }
    
    async def check_game_system(self) -> Dict[str, Any]:
        """Check game system health."""
        try:
            if not self.game_manager:
                return {
                    'status': 'unknown',
                    'error': 'Game manager not available'
                }
            
            stats = self.game_manager.get_concurrent_stats()
            
            return {
                'status': 'healthy',
                'active_games': stats['active_games'],
                'max_games': stats['max_games'],
                'total_players': stats['total_players'],
                'resource_status': stats['resource_status'],
                'utilization_percent': (stats['active_games'] / stats['max_games']) * 100
            }
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e)
            }
    
    async def check_error_rates(self) -> Dict[str, Any]:
        """Check error rates and system stability."""
        try:
            error_summary = error_handler.get_error_summary(1)  # Last hour
            
            # Calculate error rate
            total_errors = error_summary['total_errors']
            uptime_hours = (datetime.now() - self.start_time).total_seconds() / 3600
            error_rate = total_errors / max(uptime_hours, 0.1)  # Errors per hour
            
            # Determine health status
            if error_rate > 100:
                status = 'unhealthy'
            elif error_rate > 50:
                status = 'degraded'
            else:
                status = 'healthy'
            
            return {
                'status': status,
                'total_errors_last_hour': total_errors,
                'error_rate_per_hour': round(error_rate, 2),
                'error_types': error_summary['error_types'],
                'service_health': error_summary['service_health']
            }
        except Exception as e:
            return {
                'status': 'unknown',
                'error': str(e)
            }
    
    async def perform_full_health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check."""
        logger.info("Performing full health check...")
        
        # Run all health checks
        checks = await asyncio.gather(
            self.check_configuration(),
            self.check_word_validator(),
            self.check_game_system(),
            self.check_error_rates(),
            return_exceptions=True
        )
        
        config_health, validator_health, game_health, error_health = checks
        
        # Determine overall health
        component_statuses = []
        if isinstance(config_health, dict):
            component_statuses.append(config_health.get('status', 'unknown'))
        if isinstance(validator_health, dict):
            component_statuses.append(validator_health.get('status', 'unknown'))
        if isinstance(game_health, dict):
            component_statuses.append(game_health.get('status', 'unknown'))
        if isinstance(error_health, dict):
            component_statuses.append(error_health.get('status', 'unknown'))
        
        # Overall status logic
        if any(status == 'unhealthy' for status in component_statuses):
            overall_status = 'unhealthy'
        elif any(status == 'degraded' for status in component_statuses):
            overall_status = 'degraded'
        elif all(status == 'healthy' for status in component_statuses):
            overall_status = 'healthy'
        else:
            overall_status = 'unknown'
        
        uptime_seconds = (datetime.now() - self.start_time).total_seconds()
        
        health_report = {
            'timestamp': datetime.now().isoformat(),
            'overall_status': overall_status,
            'uptime_seconds': round(uptime_seconds, 2),
            'version': '1.0.0',
            'components': {
                'configuration': config_health if isinstance(config_health, dict) else {'status': 'error', 'error': str(config_health)},
                'word_validator': validator_health if isinstance(validator_health, dict) else {'status': 'error', 'error': str(validator_health)},
                'game_system': game_health if isinstance(game_health, dict) else {'status': 'error', 'error': str(game_health)},
                'error_tracking': error_health if isinstance(error_health, dict) else {'status': 'error', 'error': str(error_health)}
            }
        }
        
        logger.info(f"Health check completed: {overall_status}")
        return health_report


# Global health checker instance
health_checker = HealthChecker()


def set_game_manager(game_manager):
    """Set the game manager for health checks."""
    global health_checker
    health_checker.game_manager = game_manager


async def get_health_status() -> Dict[str, Any]:
    """Get current health status."""
    return await health_checker.perform_full_health_check()