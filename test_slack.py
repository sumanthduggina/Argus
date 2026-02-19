# test_slack.py
from slack_sdk import WebClient
import os
from dotenv import load_dotenv

load_dotenv()

client = WebClient(token=os.getenv("SLACK_BOT_TOKEN"))

client.chat_postMessage(
    channel=os.getenv("SLACK_CHANNEL_ID"),
    text="✅ Argus connected successfully"
)

print("Slack message sent!")