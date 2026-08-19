"""Notification channels: Telegram, Discord, Slack, generic webhook.

Tokens and URLs are read only from environment variables, never from CLI
args or config files, so they never end up in shell history, process
listings, or committed config.
"""
import json
import os
import urllib.error
import urllib.request

TIMEOUT = 10


def _post_json(url, payload, timeout=TIMEOUT):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()
        return True, None
    except (urllib.error.URLError, OSError) as e:
        return False, str(e)


def send_telegram(text):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False, "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    return _post_json(url, {"chat_id": chat_id, "text": text})


def send_discord(text):
    url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not url:
        return False, "DISCORD_WEBHOOK_URL not set"
    return _post_json(url, {"content": text[:2000]})


def send_slack(text):
    url = os.environ.get("SLACK_WEBHOOK_URL")
    if not url:
        return False, "SLACK_WEBHOOK_URL not set"
    return _post_json(url, {"text": text})


def send_webhook(text):
    url = os.environ.get("WEBHOOK_URL")
    if not url:
        return False, "WEBHOOK_URL not set"
    return _post_json(url, {"text": text})


CHANNELS = {
    "telegram": send_telegram,
    "discord": send_discord,
    "slack": send_slack,
    "webhook": send_webhook,
}


def notify(channel, text):
    sender = CHANNELS.get(channel)
    if not sender:
        return False, f"unknown notify channel: {channel}"
    return sender(text)
