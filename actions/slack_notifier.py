# Folder: firetiger-demo/actions/slack_notifier.py
#
# Sends rich Slack messages for incidents.
# Uses Slack Block Kit for professional formatting.
# Two types: incident alert and resolution confirmation.

import logging
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from ingestion.event_schema import IncidentReport, RegressionEvent
import config

logger = logging.getLogger(__name__)
client = WebClient(token=config.SLACK_BOT_TOKEN)


def send_incident_alert(report: IncidentReport, pr_url: str = None):
    """
    Send a rich Slack alert when a regression is found.
    Includes root cause, confidence, and fix preview.
    """
    
    confidence_pct = f"{report.root_cause.confidence_score:.0%}"
    latency_change = (
        f"{report.characterization.latency_before_ms:.0f}ms → "
        f"{report.characterization.latency_after_ms:.0f}ms"
    )
    
    blocks = [
        # Header
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"🚨 Regression Detected: {report.regression.affected_endpoint}"
            }
        },
        # Incident details
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Endpoint*\n`{report.regression.affected_endpoint}`"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Latency*\n{latency_change}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*DB Queries*\n"
                           f"{report.characterization.query_count_before:.0f} → "
                           f"{report.characterization.query_count_after:.0f} per request"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Customers Affected*\n"
                           f"{len(report.regression.affected_user_ids)} users"
                }
            ]
        },
        {"type": "divider"},
        # Root cause
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Root Cause* ({confidence_pct} confidence)\n"
                    f"{report.root_cause.confirmed_hypothesis_title}\n\n"
                    f"_{report.fix.fix_summary}_"
                )
            }
        },
        # Fix preview
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Fix Preview*\n```{report.fix.fixed_code[:300]}```"
            }
        }
    ]
    
    # Add PR button if PR was created
    if pr_url:
        blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Review & Merge PR"},
                    "url": pr_url,
                    "style": "primary"
                },
                {
                    "type": "button", 
                    "text": {"type": "plain_text", "text": "View Evidence"},
                    "value": f"evidence_{report.incident_id}"
                }
            ]
        })
    
    try:
        client.chat_postMessage(
            channel=config.SLACK_CHANNEL_ID,
            blocks=blocks,
            text=f"Regression detected on {report.regression.affected_endpoint}"
        )
        logger.info(f"Slack alert sent for incident {report.incident_id}")
        
    except SlackApiError as e:
        logger.error(f"Slack error: {e}")


def send_resolution_message(incident_id: str, endpoint: str,
                             time_to_resolve_sec: float):
    """Send a confirmation when the incident is resolved"""
    minutes = int(time_to_resolve_sec / 60)
    seconds = int(time_to_resolve_sec % 60)
    
    try:
        client.chat_postMessage(
            channel=config.SLACK_CHANNEL_ID,
            blocks=[
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"✅ *Incident Resolved*\n"
                            f"Endpoint `{endpoint}` is back to normal.\n"
                            f"*Total time: {minutes}m {seconds}s* | "
                            f"Zero humans paged."
                        )
                    }
                }
            ],
            text=f"Incident resolved: {endpoint}"
        )
    except SlackApiError as e:
        logger.error(f"Slack error: {e}")


def send_failure_alert(regression: RegressionEvent, error: str):
    """Send alert when automated investigation fails - needs human"""
    try:
        client.chat_postMessage(
            channel=config.SLACK_CHANNEL_ID,
            text=(
                f"⚠️ Automated investigation failed for "
                f"`{regression.affected_endpoint}`. "
                f"Manual investigation needed. Error: {error[:200]}"
            )
        )
    except SlackApiError as e:
        logger.error(f"Slack error: {e}")