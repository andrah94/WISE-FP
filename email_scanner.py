"""
Gmail API integration for scanning multiple email accounts.
Handles OAuth authentication and email fetching for:
- gwindomfinance@gmail.com
- WISEfinancialpartners@gmail.com
"""

import os
import json
import base64
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from database import (
    get_session, get_or_create_person, Person, Application, TimelineEvent,
    PersonStatus, ApplicationStatus, STAGE_PROBABILITIES,
    check_email_processed, mark_email_processed, update_sync_status, update_person_stats
)
from parsers import parse_application_email, parse_status_update_email, parse_calendly_email

# Gmail API scopes
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# Email accounts configuration
EMAIL_ACCOUNTS = {
    'gwindomfinance': {
        'email': 'gwindomfinance@gmail.com',
        'token_env': 'GMAIL_TOKEN_GWINDOMFINANCE'
    },
    'wisefinancial': {
        'email': 'WISEfinancialpartners@gmail.com',
        'token_env': 'GMAIL_TOKEN_WISEFINANCIAL'
    }
}

# Search queries for relevant emails
SEARCH_QUERIES = [
    'subject:"Application Received"',
    'subject:"Application Approved"',
    'subject:"Underwriting"',
    'subject:"Policy Approved"',
    'subject:"Delivery Receipt"',
    'from:transamerica.com',
    'from:nationwide.com',
    'from:calendly.com',
    'subject:"New Event"',
    'subject:"Booking Confirmed"',
]


def get_gmail_credentials(account_key):
    """Get or refresh credentials for a Gmail account."""
    account = EMAIL_ACCOUNTS.get(account_key)
    if not account:
        raise ValueError(f"Unknown account: {account_key}")

    token_env = account['token_env']
    token_json = os.getenv(token_env)

    if not token_json:
        print(f"No token found for {account['email']}. OAuth setup required.")
        return None

    try:
        token_data = json.loads(token_json)
        creds = Credentials.from_authorized_user_info(token_data, SCOPES)

        # Refresh if expired
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Update the environment variable with refreshed token
            # In production, you'd want to update Railway's env vars
            print(f"Token refreshed for {account['email']}")

        return creds
    except Exception as e:
        print(f"Error loading credentials for {account['email']}: {e}")
        return None


def run_oauth_flow(client_secrets_file, account_key):
    """
    Run OAuth flow for a specific account.
    This is used during initial setup.
    """
    account = EMAIL_ACCOUNTS.get(account_key)
    if not account:
        raise ValueError(f"Unknown account: {account_key}")

    print(f"\n=== OAuth Setup for {account['email']} ===")
    print("A browser window will open. Sign in with the correct Google account.")

    flow = InstalledAppFlow.from_client_secrets_file(client_secrets_file, SCOPES)
    creds = flow.run_local_server(port=8090)

    # Output the token JSON to be stored as environment variable
    token_data = {
        'token': creds.token,
        'refresh_token': creds.refresh_token,
        'token_uri': creds.token_uri,
        'client_id': creds.client_id,
        'client_secret': creds.client_secret,
        'scopes': creds.scopes
    }

    token_json = json.dumps(token_data)
    print(f"\n=== Token for {account['email']} ===")
    print(f"Set this as {account['token_env']} environment variable:\n")
    print(token_json)
    print("\n" + "="*50)

    return creds


def get_gmail_service(account_key):
    """Get Gmail API service for an account."""
    creds = get_gmail_credentials(account_key)
    if not creds:
        return None

    try:
        service = build('gmail', 'v1', credentials=creds)
        return service
    except Exception as e:
        print(f"Error building Gmail service: {e}")
        return None


def search_emails(service, query, max_results=100):
    """Search for emails matching a query."""
    try:
        results = service.users().messages().list(
            userId='me',
            q=query,
            maxResults=max_results
        ).execute()

        messages = results.get('messages', [])
        return messages
    except HttpError as e:
        print(f"Error searching emails: {e}")
        return []


def get_email_content(service, message_id):
    """Get full email content including body."""
    try:
        message = service.users().messages().get(
            userId='me',
            id=message_id,
            format='full'
        ).execute()

        # Extract headers
        headers = message.get('payload', {}).get('headers', [])
        header_dict = {h['name'].lower(): h['value'] for h in headers}

        # Extract body
        body = extract_email_body(message.get('payload', {}))

        return {
            'id': message['id'],
            'threadId': message.get('threadId'),
            'subject': header_dict.get('subject', ''),
            'from': header_dict.get('from', ''),
            'to': header_dict.get('to', ''),
            'date': header_dict.get('date', ''),
            'body': body,
            'snippet': message.get('snippet', '')
        }
    except HttpError as e:
        print(f"Error getting email {message_id}: {e}")
        return None


def extract_email_body(payload):
    """Extract text body from email payload."""
    body = ''

    if 'body' in payload and payload['body'].get('data'):
        body = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='ignore')
    elif 'parts' in payload:
        for part in payload['parts']:
            mime_type = part.get('mimeType', '')
            if mime_type == 'text/plain':
                data = part.get('body', {}).get('data', '')
                if data:
                    body = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                    break
            elif mime_type == 'text/html' and not body:
                data = part.get('body', {}).get('data', '')
                if data:
                    body = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
            elif 'parts' in part:
                # Nested parts (multipart)
                body = extract_email_body(part)
                if body:
                    break

    return body


def process_email(email_data, account_email, session):
    """Process a single email and update database accordingly."""
    subject = email_data.get('subject', '')
    body = email_data.get('body', '')
    from_addr = email_data.get('from', '')
    date_str = email_data.get('date', '')

    # Parse date
    try:
        email_date = parsedate_to_datetime(date_str)
    except:
        email_date = datetime.now()

    results = {
        'type': None,
        'person': None,
        'application': None,
        'created': False
    }

    # Check for application emails
    if 'application received' in subject.lower():
        app_data = parse_application_email(subject, body)
        if app_data:
            results['type'] = 'application'

            # Get or create person
            person, created = get_or_create_person(
                session,
                name=app_data.get('insured_name'),
                email=app_data.get('email')
            )
            results['person'] = person
            results['created'] = created

            # Update person status
            person.status = PersonStatus.APPLICATION
            person.probability = STAGE_PROBABILITIES[PersonStatus.APPLICATION]
            person.last_contact = email_date

            # Create application
            application = Application(
                person_id=person.id,
                policy_number=app_data.get('policy_number'),
                carrier=app_data.get('carrier', 'Unknown'),
                product=app_data.get('product'),
                face_amount=app_data.get('face_amount'),
                status=ApplicationStatus.SUBMITTED,
                submitted_date=email_date.date(),
                email_source=account_email
            )
            application.calculate_commission()
            session.add(application)
            results['application'] = application

            # Update person's commission
            person.estimated_commission = application.estimated_commission
            person.update_weighted_value()

            # Add timeline event
            timeline = TimelineEvent(
                person_id=person.id,
                event_type='APPLICATION',
                description=f"Application received - {app_data.get('product', 'Policy')} - ${app_data.get('face_amount', 0):,.0f}",
                timestamp=email_date
            )
            session.add(timeline)

            print(f"  → New application: {person.name} - ${app_data.get('face_amount', 0):,.0f}")

    # Check for status updates (enhanced with blocker/urgency detection)
    elif any(kw in subject.lower() for kw in ['approved', 'underwriting', 'pending', 'delivery', 'requirements', 'signature', 'additional']):
        status_data = parse_status_update_email(subject, body)
        if status_data and status_data.get('policy_number'):
            results['type'] = 'status_update'

            # Find application by policy number
            application = session.query(Application).filter(
                Application.policy_number == status_data['policy_number']
            ).first()

            if application:
                new_status = status_data.get('new_status')
                if new_status:
                    application.status = new_status
                    application.blocker = status_data.get('blocker')  # What's blocking progress
                    application.urgency = status_data.get('urgency')  # URGENT, HIGH, MEDIUM, LOW

                    # Update based on specific status
                    if new_status == ApplicationStatus.APPROVED:
                        application.approval_date = email_date.date()
                        application.person.status = PersonStatus.APPROVED
                        application.person.probability = 100

                    elif new_status == ApplicationStatus.SIGNATURE_NEEDED:
                        # Money on the table! High priority
                        application.person.status = PersonStatus.APPROVED
                        application.person.probability = 100
                        print(f"  🚨 SIGNATURE NEEDED: {application.person.name} - ${application.estimated_commission:,.0f}")

                    elif new_status == ApplicationStatus.STALLED:
                        # Application blocked - needs follow-up
                        blocker_msg = status_data.get('blocker', 'Unknown requirements')
                        print(f"  ⚠️ STALLED: {application.person.name} - {blocker_msg}")

                    elif new_status == ApplicationStatus.DELIVERED:
                        # Money received!
                        from database import track_monthly_revenue
                        application.delivered_date = email_date.date()
                        track_monthly_revenue(session, application.id)
                        print(f"  ✅ DELIVERED: {application.person.name} - ${application.estimated_commission:,.0f}")

                    # Add timeline event
                    timeline_desc = f"Status updated to {new_status}"
                    if status_data.get('blocker'):
                        timeline_desc += f" - {status_data.get('blocker')}"

                    timeline = TimelineEvent(
                        person_id=application.person_id,
                        event_type='STATUS_CHANGE',
                        description=timeline_desc,
                        timestamp=email_date
                    )
                    session.add(timeline)
                    print(f"  → Status update: {application.person.name} - {new_status}")

    # Check for Calendly emails
    elif 'calendly.com' in from_addr.lower() or 'new event' in subject.lower():
        calendly_data = parse_calendly_email(subject, body)
        if calendly_data:
            results['type'] = 'calendly'
            # This will be handled by the calendly_scanner for more detailed info
            print(f"  → Calendly notification detected: {calendly_data.get('attendee_name', 'Unknown')}")

    return results


def scan_account(account_key, days_back=7):
    """Scan a single Gmail account for relevant emails."""
    account = EMAIL_ACCOUNTS.get(account_key)
    if not account:
        print(f"Unknown account: {account_key}")
        return

    print(f"\nScanning {account['email']}...")

    service = get_gmail_service(account_key)
    if not service:
        update_sync_status(
            get_session(),
            f"gmail_{account_key}",
            success=False,
            error_message="Failed to authenticate"
        )
        return

    session = get_session()
    processed_count = 0
    new_items = 0

    try:
        # Build date filter
        date_filter = (datetime.now() - timedelta(days=days_back)).strftime('%Y/%m/%d')

        for query in SEARCH_QUERIES:
            full_query = f"{query} after:{date_filter}"
            messages = search_emails(service, full_query)

            for msg in messages:
                msg_id = msg['id']

                # Skip if already processed
                if check_email_processed(session, msg_id):
                    continue

                # Get full email content
                email_data = get_email_content(service, msg_id)
                if not email_data:
                    continue

                # Process the email
                result = process_email(email_data, account['email'], session)

                # Mark as processed
                mark_email_processed(session, msg_id, account['email'], email_data.get('subject'))
                processed_count += 1

                if result.get('created') or result.get('type'):
                    new_items += 1

        session.commit()

        # Update people stats
        for person in session.query(Person).all():
            update_person_stats(session, person.id)
        session.commit()

        update_sync_status(
            session,
            f"gmail_{account_key}",
            success=True,
            items_processed=processed_count
        )

        print(f"  Processed {processed_count} emails, {new_items} new items")

    except Exception as e:
        session.rollback()
        update_sync_status(
            session,
            f"gmail_{account_key}",
            success=False,
            error_message=str(e)
        )
        print(f"  Error scanning {account['email']}: {e}")
    finally:
        session.close()


def scan_all_accounts(days_back=7):
    """Scan all configured Gmail accounts."""
    print("\n" + "="*50)
    print("Starting Gmail scan...")
    print("="*50)

    for account_key in EMAIL_ACCOUNTS.keys():
        scan_account(account_key, days_back)

    print("\nGmail scan complete.")


if __name__ == '__main__':
    # For testing/setup
    import sys

    if len(sys.argv) > 1:
        if sys.argv[1] == 'oauth':
            # Run OAuth setup
            if len(sys.argv) < 4:
                print("Usage: python email_scanner.py oauth <client_secrets.json> <account_key>")
                print("Account keys: gwindomfinance, wisefinancial")
                sys.exit(1)

            client_secrets = sys.argv[2]
            account_key = sys.argv[3]
            run_oauth_flow(client_secrets, account_key)
        elif sys.argv[1] == 'scan':
            days = int(sys.argv[2]) if len(sys.argv) > 2 else 7
            scan_all_accounts(days)
    else:
        print("Gmail Scanner")
        print("Usage:")
        print("  python email_scanner.py oauth <client_secrets.json> <account_key>  - Run OAuth setup")
        print("  python email_scanner.py scan [days_back]                           - Scan all accounts")
