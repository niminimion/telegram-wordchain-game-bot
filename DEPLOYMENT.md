# Deployment Guide

This guide covers deploying the Telegram Word Game Bot in various environments.

## Prerequisites

### System Requirements

- **Python**: 3.10 or higher
- **Memory**: Minimum 512MB RAM (1GB+ recommended for production)
- **Storage**: 100MB for application + logs
- **Network**: Stable internet connection for Telegram API

### Required Accounts

1. **Telegram Bot Token**
   - Create a bot via [@BotFather](https://t.me/BotFather)
   - Use `/newbot` command and follow instructions
   - Save the bot token securely

2. **Wordnik API Key** (Optional but recommended)
   - Sign up at [Wordnik Developer Portal](https://developer.wordnik.com/)
   - Create an API key for enhanced word validation
   - Free tier provides 15,000 requests/hour

## Local Development Setup

### 1. Clone and Setup

```bash
# Clone the repository
git clone <repository-url>
cd telegram-word-game-bot

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration

```bash
# Copy environment template
cp .env.example .env

# Edit .env file with your configuration
# Required:
TELEGRAM_BOT_TOKEN=your_bot_token_here

# Optional:
WORDNIK_API_KEY=your_wordnik_api_key_here
LOG_LEVEL=INFO
TURN_TIMEOUT=30
MAX_GAMES=100
```

### 3. Run the Bot

```bash
# Run directly
python main.py

# Or with explicit Python version
python3.10 main.py
```

### 4. Test the Bot

```bash
# Run test suite
python run_tests.py

# Run specific test types
python run_tests.py unit
python run_tests.py integration
python run_tests.py performance
```

## Production Deployment

### Docker Deployment

Create `Dockerfile`:

```dockerfile
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create logs directory
RUN mkdir -p logs

# Create non-root user
RUN useradd --create-home --shell /bin/bash botuser
RUN chown -R botuser:botuser /app
USER botuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import asyncio; from main import health_check; print(asyncio.run(health_check()))"

# Run the bot
CMD ["python", "main.py"]
```

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  telegram-bot:
    build: .
    container_name: telegram-word-game-bot
    restart: unless-stopped
    environment:
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
      - WORDNIK_API_KEY=${WORDNIK_API_KEY}
      - LOG_LEVEL=INFO
      - TURN_TIMEOUT=30
      - MAX_GAMES=100
    volumes:
      - ./logs:/app/logs
    healthcheck:
      test: ["CMD", "python", "-c", "import asyncio; from main import health_check; print(asyncio.run(health_check()))"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
```

Deploy with Docker:

```bash
# Build and run
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

### Systemd Service (Linux)

Create `/etc/systemd/system/telegram-word-bot.service`:

```ini
[Unit]
Description=Telegram Word Game Bot
After=network.target

[Service]
Type=simple
User=botuser
Group=botuser
WorkingDirectory=/opt/telegram-word-bot
Environment=PATH=/opt/telegram-word-bot/venv/bin
ExecStart=/opt/telegram-word-bot/venv/bin/python main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

# Environment file
EnvironmentFile=/opt/telegram-word-bot/.env

[Install]
WantedBy=multi-user.target
```

Deploy with systemd:

```bash
# Copy files to deployment directory
sudo cp -r . /opt/telegram-word-bot/
sudo chown -R botuser:botuser /opt/telegram-word-bot/

# Create virtual environment
cd /opt/telegram-word-bot
sudo -u botuser python -m venv venv
sudo -u botuser venv/bin/pip install -r requirements.txt

# Enable and start service
sudo systemctl enable telegram-word-bot
sudo systemctl start telegram-word-bot

# Check status
sudo systemctl status telegram-word-bot

# View logs
sudo journalctl -u telegram-word-bot -f
```

### Cloud Deployment

#### Heroku

Create `Procfile`:

```
worker: python main.py
```

Create `runtime.txt`:

```
python-3.11.0
```

Deploy to Heroku:

```bash
# Install Heroku CLI and login
heroku login

# Create app
heroku create your-telegram-bot-name

# Set environment variables
heroku config:set TELEGRAM_BOT_TOKEN=your_token_here
heroku config:set WORDNIK_API_KEY=your_api_key_here
heroku config:set LOG_LEVEL=INFO

# Deploy
git push heroku main

# Scale worker
heroku ps:scale worker=1

# View logs
heroku logs --tail
```

#### AWS EC2

1. Launch EC2 instance (t3.micro or larger)
2. Install Python 3.10+
3. Follow systemd deployment steps above
4. Configure security groups for outbound HTTPS (Telegram API)

#### Google Cloud Run

Create `cloudbuild.yaml`:

```yaml
steps:
  - name: 'gcr.io/cloud-builders/docker'
    args: ['build', '-t', 'gcr.io/$PROJECT_ID/telegram-word-bot', '.']
  - name: 'gcr.io/cloud-builders/docker'
    args: ['push', 'gcr.io/$PROJECT_ID/telegram-word-bot']
  - name: 'gcr.io/cloud-builders/gcloud'
    args:
      - 'run'
      - 'deploy'
      - 'telegram-word-bot'
      - '--image'
      - 'gcr.io/$PROJECT_ID/telegram-word-bot'
      - '--region'
      - 'us-central1'
      - '--platform'
      - 'managed'
      - '--allow-unauthenticated'
```

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes | - | Bot token from @BotFather |
| `WORDNIK_API_KEY` | No | - | Wordnik API key for enhanced validation |
| `LOG_LEVEL` | No | INFO | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `TURN_TIMEOUT` | No | 30 | Turn timeout in seconds |
| `MAX_GAMES` | No | 100 | Maximum concurrent games |
| `MIN_WORD_LENGTH` | No | 1 | Minimum word length |
| `MAX_WORD_LENGTH` | No | 20 | Maximum word length |
| `MAX_PLAYERS` | No | 10 | Maximum players per game |

### Configuration Validation

The bot validates configuration on startup:

- Checks required environment variables
- Validates numeric ranges
- Tests service availability
- Reports configuration issues clearly

## Monitoring and Maintenance

### Health Monitoring

The bot provides built-in health monitoring:

```bash
# Check bot status (if running locally)
curl http://localhost:8080/health  # If health endpoint is implemented

# Check logs
tail -f logs/bot_$(date +%Y%m%d).log

# Check system resources
python -c "
import asyncio
from main import health_check
print(asyncio.run(health_check()))
"
```

### Log Management

Logs are written to:
- **Console**: INFO level and above
- **File**: `logs/bot_YYYYMMDD.log` (DEBUG level and above)
- **Errors**: `bot_errors.log` (ERROR level and above)

Log rotation recommendations:
```bash
# Add to crontab for daily log rotation
0 0 * * * find /path/to/bot/logs -name "bot_*.log" -mtime +7 -delete
```

### Performance Monitoring

Monitor these metrics:
- Active games count
- Total players
- Memory usage
- Error rates
- Response times

### Backup and Recovery

**What to backup:**
- Configuration files (`.env`)
- Custom word lists (if any)
- Log files (for debugging)

**Recovery:**
- Games are stored in memory (no persistence)
- Bot restart clears all game states
- Players can restart games with `/startgame`

## Troubleshooting

### Common Issues

1. **Bot not responding**
   ```bash
   # Check if bot is running
   ps aux | grep python
   
   # Check logs
   tail -f logs/bot_*.log
   
   # Restart bot
   sudo systemctl restart telegram-word-bot
   ```

2. **Word validation errors**
   ```bash
   # Test NLTK installation
   python -c "import nltk; nltk.download('wordnet')"
   
   # Test Wordnik API
   python -c "
   import asyncio
   from bot.validators import WordnikValidator
   validator = WordnikValidator('your_api_key')
   print(asyncio.run(validator.validate_word('test')))
   "
   ```

3. **Memory issues**
   ```bash
   # Check memory usage
   ps aux | grep python
   
   # Check game statistics
   # (View logs for periodic system status reports)
   ```

4. **High error rates**
   ```bash
   # Check error logs
   grep ERROR logs/bot_*.log | tail -20
   
   # Check network connectivity
   ping api.telegram.org
   ```

### Performance Tuning

1. **Adjust concurrent game limits**
   ```bash
   # In .env file
   MAX_GAMES=50  # Reduce for lower memory usage
   ```

2. **Optimize word validation**
   ```bash
   # Use Wordnik API for better performance
   WORDNIK_API_KEY=your_api_key
   ```

3. **Adjust timeouts**
   ```bash
   # Shorter timeouts for faster games
   TURN_TIMEOUT=20
   ```

## Security Considerations

### Bot Token Security

- Never commit bot tokens to version control
- Use environment variables or secure secret management
- Rotate tokens periodically
- Monitor for unauthorized usage

### API Rate Limits

- Telegram: 30 messages/second per bot
- Wordnik: 15,000 requests/hour (free tier)
- Bot includes automatic retry logic with backoff

### Input Validation

- All user inputs are validated and sanitized
- SQL injection not applicable (no database)
- XSS not applicable (Telegram handles rendering)

## Scaling

### Horizontal Scaling

For multiple bot instances:
- Use different bot tokens
- Deploy to different servers/containers
- No shared state between instances

### Vertical Scaling

Resource requirements scale with:
- ~2.5MB RAM per active game
- ~1.2% CPU per active game
- Network I/O for Telegram API calls

### Load Testing

```bash
# Run performance tests
python run_tests.py performance

# Monitor during load
watch -n 5 'ps aux | grep python'
```

## Support

### Getting Help

1. Check logs first: `logs/bot_*.log`
2. Run health check: `python -c "import asyncio; from main import health_check; print(asyncio.run(health_check()))"`
3. Test components: `python run_tests.py`
4. Check configuration: Ensure all required environment variables are set

### Reporting Issues

Include in bug reports:
- Bot version
- Python version
- Operating system
- Configuration (without sensitive data)
- Relevant log entries
- Steps to reproduce