#!/bin/bash

# Health check script for Telegram Word Game Bot
# Usage: ./health_check.sh

set -e

APP_NAME="telegram-word-game-bot"
SERVICE_NAME="${APP_NAME}.service"
APP_DIR="/opt/${APP_NAME}"
LOG_FILE="$APP_DIR/logs/bot.log"

echo "🏥 Health Check for ${APP_NAME}"
echo "================================"

# Check if service is running
echo "📊 Service Status:"
if systemctl is-active --quiet "$SERVICE_NAME"; then
    echo "✅ Service is running"
    systemctl status "$SERVICE_NAME" --no-pager -l
else
    echo "❌ Service is not running"
    systemctl status "$SERVICE_NAME" --no-pager -l
    exit 1
fi

echo ""
echo "📈 Resource Usage:"
# Get process info
PID=$(systemctl show "$SERVICE_NAME" --property=MainPID --value)
if [ "$PID" != "0" ] && [ -n "$PID" ]; then
    echo "🔢 Process ID: $PID"
    
    # Memory usage
    MEM_KB=$(ps -o rss= -p "$PID" 2>/dev/null || echo "0")
    MEM_MB=$((MEM_KB / 1024))
    echo "💾 Memory Usage: ${MEM_MB} MB"
    
    # CPU usage
    CPU=$(ps -o %cpu= -p "$PID" 2>/dev/null || echo "0")
    echo "⚡ CPU Usage: ${CPU}%"
    
    # Uptime
    UPTIME=$(ps -o etime= -p "$PID" 2>/dev/null || echo "unknown")
    echo "⏰ Uptime: $UPTIME"
else
    echo "❌ Process not found"
fi

echo ""
echo "📋 Recent Logs (last 20 lines):"
if [ -f "$LOG_FILE" ]; then
    tail -20 "$LOG_FILE"
else
    echo "⚠️  Log file not found: $LOG_FILE"
fi

echo ""
echo "🔍 Error Check (last 100 lines):"
if [ -f "$LOG_FILE" ]; then
    ERROR_COUNT=$(tail -100 "$LOG_FILE" | grep -i "error\|exception\|failed" | wc -l)
    if [ "$ERROR_COUNT" -gt 0 ]; then
        echo "⚠️  Found $ERROR_COUNT recent errors:"
        tail -100 "$LOG_FILE" | grep -i "error\|exception\|failed" | tail -5
    else
        echo "✅ No recent errors found"
    fi
else
    echo "⚠️  Cannot check errors - log file not found"
fi

echo ""
echo "💾 Disk Usage:"
df -h "$APP_DIR" | tail -1

echo ""
echo "🏥 Health Check Complete"