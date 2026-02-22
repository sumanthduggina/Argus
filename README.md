# Argus

**AI-Powered Anomaly Detection and Auto-Remediation System**

Argus is an intelligent monitoring and remediation system that automatically detects performance regressions in API endpoints and uses AI to investigate, diagnose, and fix issues autonomously.

## Overview

Argus continuously monitors your API endpoints for performance anomalies. When it detects a regression (like latency spikes or increased database query counts), it automatically:

1. **Investigates** the issue using AI-powered analysis
2. **Hypothesizes** potential root causes
3. **Gathers evidence** from metrics, logs, and code changes
4. **Confirms** the root cause with high confidence
5. **Generates fixes** and can automatically deploy them via GitHub PRs

## Features

- **Time-Aware Baselines**: Understands that 2pm Tuesday has different normal behavior than 2am Sunday
- **Real-Time Detection**: Monitors endpoints every 10 seconds with a "3 strikes" rule to avoid false alarms
- **AI-Powered Investigation**: Uses Claude AI to analyze incidents and generate hypotheses
- **Automatic Remediation**: Can create GitHub PRs with fixes and deploy them automatically (with confidence thresholds)
- **Multi-Layer Storage**: Hot store for real-time metrics, cold store (Parquet) for historical analysis
- **Knowledge Graph**: Learns from past incidents to improve future investigations
- **Slack Integration**: Notifies your team when incidents are detected and resolved
- **GitHub Integration**: Creates PRs with fixes and can auto-merge when confidence is high

## Architecture



## Prerequisites

- Python 3.8+
- SQLite3
- Anthropic API key (for Claude AI)
- GitHub token (optional, for PR creation)
- Slack bot token (optional, for notifications)

## Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd Argus
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   
   # On Windows
   venv\Scripts\activate
   
   # On Linux/Mac
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install flask python-dotenv schedule anthropic requests sqlite3 parquet
   ```

4. **Create `.env` file**
   ```env
   ANTHROPIC_API_KEY=your_anthropic_api_key_here
   GITHUB_TOKEN=your_github_token_here
   GITHUB_REPO=your_org/your_repo
   SLACK_BOT_TOKEN=your_slack_bot_token_here
   SLACK_CHANNEL_ID=your_slack_channel_id_here
   
   APP_PORT=5000
   COLLECTOR_PORT=8001
   USE_SLOW_QUERY=false
   ```

5. **Create necessary directories**
   ```bash
   mkdir -p logs data/events
   ```

## Usage

### Starting the System

**On Windows:**
```bash
python run.py
```

**On Linux/Mac:**
```bash
chmod +x run.sh
./run.sh
```

This starts:
- Flask app on `http://localhost:5000`
- Collector on `http://localhost:8001`
- Agent (detector + orchestrator)

### Initial Setup

1. **Seed the database**
   ```bash
   python scripts/seed_db.py
   ```

2. **Generate load** (in a new terminal)
   ```bash
   python scripts/run_load.py
   ```

3. **Simulate a bad deploy** (to trigger demo)
   ```bash
   python scripts/simulate_bad_deploy.py
   ```

### Monitoring Endpoints

The system monitors these endpoints by default:
- `/checkout` - Checkout endpoint (can have N+1 query issues)
- `/products` - Products listing
- `/health` - Health check endpoint

## Configuration

Edit `config.py` to customize:

```python
# Detection thresholds
ANOMALY_THRESHOLD = 3.0        # Standard deviations from baseline
CONSECUTIVE_STRIKES = 3        # Anomalous readings before firing
DETECTION_INTERVAL_SEC = 10    # How often detector checks

# Agent settings
AUTO_MERGE_CONFIDENCE = 0.92   # Minimum confidence to auto-merge PRs
HOT_STORE_WINDOW_MIN = 30      # Minutes to keep in hot store
```

## Project Structure

```
Argus/
├── app/                    # Flask application being monitored
│   ├── main.py            # Flask routes
│   ├── middleware.py      # Auto-instrumentation
│   └── db.py              # Database queries
│
├── ingestion/             # Event collection
│   ├── collector.py       # Receives events from app
│   └── event_schema.py    # Event data models
│
├── storage/               # Data storage layers
│   ├── hot_store.py       # Real-time metrics (SQLite)
│   ├── cold_store.py      # Historical data (Parquet)
│   └── knowledge_graph.py # Incident knowledge base
│
├── detection/             # Anomaly detection
│   ├── baseline.py        # Time-aware baseline computation
│   └── detector.py        # Regression detection loop
│
├── agent/                 # AI investigation agent
│   ├── orchestrator.py    # Coordinates investigation steps
│   ├── response_parser.py # Parses AI responses
│   └── steps/            # Investigation pipeline
│       ├── characterize.py
│       ├── hypothesize.py
│       ├── gather_evidence.py
│       ├── confirm.py
│       └── fix.py
│
├── actions/               # Remediation actions
│   ├── action_handler.py  # Routes actions
│   ├── slack_notifier.py  # Slack notifications
│   ├── github_pr.py       # GitHub PR creation
│   ├── deployer.py        # Deployment automation
│   └── verifier.py        # Post-deploy verification
│
├── scripts/               # Utility scripts
│   ├── seed_db.py         # Initialize database
│   ├── run_load.py        # Generate traffic
│   ├── simulate_bad_deploy.py
│   └── simulate_good_deploy.py
│
├── main_agent.py          # Main entry point
├── run.py                 # Windows launcher
├── run.sh                 # Linux/Mac launcher
└── config.py              # Configuration
```

## How It Works

### 1. Data Collection
- Middleware automatically instruments all Flask requests
- Events sent to collector with latency, query counts, user IDs, commit SHAs
- Hot store keeps last 30 minutes for real-time detection
- Cold store archives to Parquet for historical analysis

### 2. Baseline Computation
- Analyzes 7 days of historical data
- Groups by hour-of-day and day-of-week
- Computes average latency, P95 latency, and query counts per time slot
- Recomputes hourly as more data accumulates

### 3. Detection
- Every 10 seconds, compares current metrics to baseline
- Uses "3 strikes" rule: 3 consecutive anomalous readings = confirmed regression
- Anomaly score = current_value / baseline_value
- Threshold: 3.0x worse than normal

### 4. Investigation (5-Step Pipeline)
1. **Characterize**: What is happening? (latency spike, query explosion, etc.)
2. **Hypothesize**: Why might it be happening? (N+1 queries, missing index, etc.)
3. **Gather Evidence**: Check code changes, query patterns, affected users
4. **Confirm**: Determine root cause with confidence score
5. **Fix**: Generate code fix with risk assessment

### 5. Remediation
- Creates GitHub PR with fix
- Notifies team via Slack
- Can auto-deploy if confidence > 92%
- Verifies fix worked by monitoring metrics post-deploy

## Logs

Logs are written to:
- `logs/agent.log` - Agent and detector activity
- `logs/app.log` - Flask application logs
- `logs/collector.log` - Event collection logs

## Testing

Test individual components:

```bash
# Test Flask app
python test_flask.py

# Test GitHub integration
python test_github.py

# Test Slack integration
python test_slack.py

# Test Claude AI
python test_claude.py
```

## Security Notes

- Never commit `.env` file to version control
- Store API keys securely
- GitHub token should have minimal required permissions
- Consider using secrets management in production

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.



## Acknowledgments

Built with:
- Flask - Web framework
- Anthropic Claude - AI reasoning
- SQLite - Hot storage
- Parquet - Cold storage

---

**Note**: This is a demo system. For production use, consider:
- Adding authentication/authorization
- Implementing proper error handling and retries
- Using production-grade databases
- Adding monitoring and alerting
- Implementing rate limiting
- Adding comprehensive tests
