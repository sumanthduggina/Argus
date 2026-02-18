# Root folder: firetiger-demo/config.py
# Central config file - all settings live here
# Every other file imports from here instead of reading env directly

import os
from dotenv import load_dotenv

load_dotenv()

# API Keys
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_CHANNEL_ID = os.getenv("SLACK_CHANNEL_ID")

# App settings
APP_PORT = int(os.getenv("APP_PORT", 5000))
COLLECTOR_PORT = int(os.getenv("COLLECTOR_PORT", 8001))
USE_SLOW_QUERY = os.getenv("USE_SLOW_QUERY", "false").lower() == "true"

# Detection thresholds
ANOMALY_THRESHOLD = 3.0        # standard deviations from baseline
CONSECUTIVE_STRIKES = 3        # how many anomalous readings before firing
DETECTION_INTERVAL_SEC = 10    # how often detector checks

# Agent settings
AUTO_MERGE_CONFIDENCE = 0.92   # minimum confidence to auto-merge
HOT_STORE_WINDOW_MIN = 30      # how many minutes to keep in hot store

# Data paths
DATA_DIR = "data/events"
DB_PATH = "store.db"
METRICS_DB_PATH = "metrics.db"
KNOWLEDGE_DB_PATH = "knowledge.db"