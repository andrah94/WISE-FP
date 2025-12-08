"""
Utility functions for the financial dashboard.
"""

import os
import json
import requests
from datetime import datetime
from functools import wraps
import logging

logger = logging.getLogger(__name__)


def send_notification(message, title="Dashboard Alert"):
    """
    Send a notification via webhook (Slack, Discord, etc.)
    Configure NOTIFICATION_WEBHOOK_URL in environment.
    """
    webhook_url = os.getenv('NOTIFICATION_WEBHOOK_URL')
    if not webhook_url:
        return False

    try:
        # Format for Slack-compatible webhooks
        payload = {
            "text": f"*{title}*\n{message}",
            "username": "Financial Dashboard",
            "icon_emoji": ":chart_with_upwards_trend:"
        }

        response = requests.post(
            webhook_url,
            json=payload,
            timeout=10
        )
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Failed to send notification: {e}")
        return False


def notify_new_application(person_name, face_amount, carrier=None):
    """Send notification for new application."""
    carrier_str = f" ({carrier})" if carrier else ""
    message = f"🎉 New Application!\n" \
              f"*{person_name}*{carrier_str}\n" \
              f"Face Amount: ${face_amount:,.0f}"
    return send_notification(message, "New Application Received")


def notify_status_change(person_name, old_status, new_status):
    """Send notification for status change."""
    emoji = "✅" if new_status == "APPROVED" else "📋"
    message = f"{emoji} Status Update\n" \
              f"*{person_name}*\n" \
              f"{old_status} → {new_status}"
    return send_notification(message, "Status Change")


def format_phone(phone):
    """Format phone number for display."""
    if not phone:
        return None

    # Remove all non-digits
    digits = ''.join(c for c in phone if c.isdigit())

    # Format as (XXX) XXX-XXXX
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    elif len(digits) == 11 and digits[0] == '1':
        return f"({digits[1:4]}) {digits[4:7]}-{digits[7:]}"

    return phone


def days_until(target_date):
    """Calculate days until a target date."""
    if not target_date:
        return None

    if isinstance(target_date, str):
        target_date = datetime.fromisoformat(target_date)

    delta = target_date - datetime.now()
    return delta.days


def days_since(past_date):
    """Calculate days since a past date."""
    if not past_date:
        return None

    if isinstance(past_date, str):
        past_date = datetime.fromisoformat(past_date)

    delta = datetime.now() - past_date
    return delta.days


def get_greeting():
    """Get time-appropriate greeting."""
    hour = datetime.now().hour

    if hour < 12:
        return "Good morning"
    elif hour < 17:
        return "Good afternoon"
    else:
        return "Good evening"


def calculate_commission_estimate(face_amount, product_type=None):
    """
    Calculate estimated first-year commission.

    Standard IUL commission calculation:
    - Monthly premium based on face amount
    - 45% first-year commission rate
    """
    if not face_amount:
        return 0

    face = float(face_amount)

    # Estimate monthly premium
    if face >= 100000:
        monthly = face * 0.0025  # ~$250/mo for $100K
    elif face >= 50000:
        monthly = face * 0.003
    else:
        monthly = face * 0.0035

    annual_premium = monthly * 12
    commission = annual_premium * 0.45  # 45% first-year

    return round(commission, 2)


def get_probability_for_stage(stage):
    """Get default probability for a pipeline stage."""
    probabilities = {
        'SCHEDULED': 15,
        'NEW': 20,
        'ACTIVE': 30,
        'WARM': 40,
        'APPLICATION': 70,
        'APPROVED': 100,
        'COLD': 5
    }
    return probabilities.get(stage.upper(), 20)


def apply_probability_decay(base_probability, days_since_contact):
    """
    Apply probability decay based on days since last contact.

    - After 7 days: -10%
    - After 14 days: -20% total
    - After 30 days: -50% total
    """
    if days_since_contact is None:
        return base_probability

    if days_since_contact > 30:
        return int(base_probability * 0.5)
    elif days_since_contact > 14:
        return int(base_probability * 0.8)
    elif days_since_contact > 7:
        return int(base_probability * 0.9)

    return base_probability


def truncate_string(s, max_length=50):
    """Truncate string with ellipsis if too long."""
    if not s:
        return ""
    if len(s) <= max_length:
        return s
    return s[:max_length-3] + "..."


def safe_json_loads(s, default=None):
    """Safely load JSON with default value."""
    if not s:
        return default
    try:
        return json.loads(s)
    except:
        return default


def retry_on_failure(max_retries=3, delay=1):
    """Decorator to retry a function on failure."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            import time
            last_error = None

            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    if attempt < max_retries - 1:
                        time.sleep(delay * (2 ** attempt))  # Exponential backoff
                        logger.warning(f"Retry {attempt + 1}/{max_retries} for {func.__name__}: {e}")

            raise last_error

        return wrapper
    return decorator


class RateLimiter:
    """Simple rate limiter for API calls."""

    def __init__(self, calls_per_minute=60):
        self.calls_per_minute = calls_per_minute
        self.calls = []

    def wait_if_needed(self):
        """Wait if rate limit would be exceeded."""
        import time

        now = datetime.now()
        minute_ago = now.timestamp() - 60

        # Remove old calls
        self.calls = [c for c in self.calls if c > minute_ago]

        if len(self.calls) >= self.calls_per_minute:
            # Wait until oldest call expires
            sleep_time = self.calls[0] - minute_ago
            if sleep_time > 0:
                time.sleep(sleep_time)

        self.calls.append(now.timestamp())


# Export commonly used utilities
__all__ = [
    'send_notification',
    'notify_new_application',
    'notify_status_change',
    'format_phone',
    'days_until',
    'days_since',
    'get_greeting',
    'calculate_commission_estimate',
    'get_probability_for_stage',
    'apply_probability_decay',
    'truncate_string',
    'safe_json_loads',
    'retry_on_failure',
    'RateLimiter'
]
