#!/usr/bin/env python3
"""
Test runner for the Telegram Word Game Bot.
Runs different types of tests with appropriate configurations.
"""

import sys
import subprocess
import argparse
import time
from pathlib import Path


def run_command(cmd, description):
    """Run a command and return success status."""
    print(f"\n{'='*60}")
    print(f"Running: {description}")
    print(f"Command: {' '.join(cmd)}")
    print('='*60)
    
    start_time = time.time()
    result = subprocess.run(cmd, capture_output=False)
    end_time = time.time()
    
    duration = end_time - start_time
    print(f"\n{description} completed in {duration:.2f} seconds")
    
    if result.returncode == 0:
        print(f"✅ {description} PASSED")
    else:
        print(f"❌ {description} FAILED")
    
    return result.returncode == 0


def run_unit_tests():
    """Run all unit tests."""
    unit_test_files = [
        "tests/test_models.py",
        "tests/test_validators.py", 
        "tests/test_word_processor.py",
        "tests/test_game_manager.py",
        "tests/test_timer_manager.py",
        "tests/test_message_handler.py",
        "tests/test_announcements.py",
        "tests/test_error_handler.py",
        "tests/test_concurrent_manager.py",
        "tests/test_telegram_bot.py",
        "tests/test_turn_management.py"
    ]
    
    # Filter to only existing files
    existing_files = [f for f in unit_test_files if Path(f).exists()]
    
    if not existing_files:
        print("No unit test files found")
        return False
    
    cmd = ["python", "-m", "pytest"] + existing_files + [
        "-v",
        "--tb=short",
        "--durations=10"
    ]
    
    return run_command(cmd, "Unit Tests")


def run_integration_tests():
    """Run integration tests."""
    if not Path("tests/test_integration.py").exists():
        print("Integration test file not found")
        return False
    
    cmd = [
        "python", "-m", "pytest", 
        "tests/test_integration.py",
        "-v",
        "--tb=short",
        "-s"  # Don't capture output for integration tests
    ]
    
    return run_command(cmd, "Integration Tests")


def run_performance_tests():
    """Run performance tests."""
    if not Path("tests/test_performance.py").exists():
        print("Performance test file not found")
        return False
    
    cmd = [
        "python", "-m", "pytest",
        "tests/test_performance.py", 
        "-v",
        "--tb=short",
        "-s"  # Don't capture output to see performance metrics
    ]
    
    return run_command(cmd, "Performance Tests")


def run_edge_case_tests():
    """Run edge case tests."""
    if not Path("tests/test_edge_cases.py").exists():
        print("Edge case test file not found")
        return False
    
    cmd = [
        "python", "-m", "pytest",
        "tests/test_edge_cases.py",
        "-v", 
        "--tb=short"
    ]
    
    return run_command(cmd, "Edge Case Tests")


def run_all_tests():
    """Run all test suites."""
    results = []
    
    print("🚀 Starting Comprehensive Test Suite")
    print(f"Python version: {sys.version}")
    print(f"Working directory: {Path.cwd()}")
    
    # Run each test suite
    test_suites = [
        ("Unit Tests", run_unit_tests),
        ("Integration Tests", run_integration_tests), 
        ("Performance Tests", run_performance_tests),
        ("Edge Case Tests", run_edge_case_tests)
    ]
    
    for suite_name, test_func in test_suites:
        try:
            success = test_func()
            results.append((suite_name, success))
        except Exception as e:
            print(f"❌ Error running {suite_name}: {e}")
            results.append((suite_name, False))
    
    # Summary
    print(f"\n{'='*60}")
    print("TEST SUMMARY")
    print('='*60)
    
    total_suites = len(results)
    passed_suites = sum(1 for _, success in results if success)
    
    for suite_name, success in results:
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"{suite_name:20} {status}")
    
    print(f"\nOverall: {passed_suites}/{total_suites} test suites passed")
    
    if passed_suites == total_suites:
        print("🎉 All test suites passed!")
        return True
    else:
        print("⚠️  Some test suites failed")
        return False


def run_coverage():
    """Run tests with coverage reporting."""
    cmd = [
        "python", "-m", "pytest",
        "--cov=bot",
        "--cov-report=html",
        "--cov-report=term-missing",
        "-v"
    ]
    
    return run_command(cmd, "Coverage Analysis")


def main():
    """Main test runner."""
    parser = argparse.ArgumentParser(description="Run tests for Telegram Word Game Bot")
    parser.add_argument(
        "test_type", 
        nargs="?",
        choices=["unit", "integration", "performance", "edge", "all", "coverage"],
        default="all",
        help="Type of tests to run"
    )
    
    args = parser.parse_args()
    
    # Check if pytest is available
    try:
        subprocess.run(["python", "-m", "pytest", "--version"], 
                      capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ pytest not found. Please install it with: pip install pytest pytest-asyncio")
        return 1
    
    # Run requested tests
    if args.test_type == "unit":
        success = run_unit_tests()
    elif args.test_type == "integration":
        success = run_integration_tests()
    elif args.test_type == "performance":
        success = run_performance_tests()
    elif args.test_type == "edge":
        success = run_edge_case_tests()
    elif args.test_type == "coverage":
        success = run_coverage()
    else:  # all
        success = run_all_tests()
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())