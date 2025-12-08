"""
Google Calendar API integration.
Fetches calendar events and tracks meetings with prospects/clients.
"""

import os
import json
from datetime import datetime, timedelta

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from database import (
    get_session, get_or_create_person, Person, Meeting, TimelineEvent,
    PersonStatus, STAGE_PROBABILITIES, update_sync_status, update_person_stats
)
from parsers import parse_calendar_event, detect_meeting_type, extract_name_from_email

# Calendar API scopes
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']


def get_calendar_credentials():
    """Get or refresh credentials for Google Calendar."""
    token_json = os.getenv('GOOGLE_CALENDAR_TOKEN')

    if not token_json:
        print("No calendar token found. OAuth setup required.")
        return None

    try:
        token_data = json.loads(token_json)
        creds = Credentials.from_authorized_user_info(token_data, SCOPES)

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            print("Calendar token refreshed")

        return creds
    except Exception as e:
        print(f"Error loading calendar credentials: {e}")
        return None


def run_calendar_oauth_flow(client_secrets_file):
    """Run OAuth flow for Google Calendar."""
    print("\n=== OAuth Setup for Google Calendar ===")
    print("A browser window will open. Sign in with the Google account whose calendar you want to track.")

    flow = InstalledAppFlow.from_client_secrets_file(client_secrets_file, SCOPES)
    creds = flow.run_local_server(port=8091)

    token_data = {
        'token': creds.token,
        'refresh_token': creds.refresh_token,
        'token_uri': creds.token_uri,
        'client_id': creds.client_id,
        'client_secret': creds.client_secret,
        'scopes': creds.scopes
    }

    token_json = json.dumps(token_data)
    print("\n=== Calendar Token ===")
    print("Set this as GOOGLE_CALENDAR_TOKEN environment variable:\n")
    print(token_json)
    print("\n" + "="*50)

    return creds


def get_calendar_service():
    """Get Google Calendar API service."""
    creds = get_calendar_credentials()
    if not creds:
        return None

    try:
        service = build('calendar', 'v3', credentials=creds)
        return service
    except Exception as e:
        print(f"Error building Calendar service: {e}")
        return None


def fetch_events(service, days_back=30, days_forward=30):
    """Fetch calendar events within a date range."""
    try:
        now = datetime.utcnow()
        time_min = (now - timedelta(days=days_back)).isoformat() + 'Z'
        time_max = (now + timedelta(days=days_forward)).isoformat() + 'Z'

        events_result = service.events().list(
            calendarId='primary',
            timeMin=time_min,
            timeMax=time_max,
            maxResults=500,
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])
        return events
    except HttpError as e:
        print(f"Error fetching calendar events: {e}")
        return []


def process_calendar_event(event_data, session):
    """Process a single calendar event and update database."""
    parsed = parse_calendar_event(event_data)

    if not parsed['start']:
        return None

    # Check if event already exists
    existing = session.query(Meeting).filter(
        Meeting.calendar_event_id == parsed['event_id']
    ).first()

    if existing:
        # Update existing meeting if needed
        if existing.date != parsed['start']:
            existing.date = parsed['start']
            existing.duration_minutes = parsed['duration_minutes']
        return existing

    # Determine meeting type
    meeting_type = detect_meeting_type(parsed['summary'], parsed['description'])

    # Try to find or create person based on attendees
    person = None
    for attendee in parsed['attendees']:
        email = attendee.get('email', '')
        name = attendee.get('name') or extract_name_from_email(email)

        if name and email:
            # Skip common system emails
            if any(skip in email.lower() for skip in ['calendar', 'noreply', 'google', 'zoom', 'microsoft']):
                continue

            person, created = get_or_create_person(session, name, email)
            if created:
                person.status = PersonStatus.SCHEDULED
                person.probability = STAGE_PROBABILITIES[PersonStatus.SCHEDULED]
                print(f"  → New person from calendar: {name}")
            break

    # Create meeting record
    meeting = Meeting(
        person_id=person.id if person else None,
        meeting_type=meeting_type,
        date=parsed['start'],
        duration_minutes=parsed['duration_minutes'] or 60,
        source='Calendar',
        calendar_event_id=parsed['event_id'],
        attendees=json.dumps([a['email'] for a in parsed['attendees']]),
        notes=parsed['summary']
    )
    session.add(meeting)

    # Update person's last contact if this is a past meeting
    if person and parsed['start'] < datetime.now():
        if not person.last_contact or parsed['start'] > person.last_contact:
            person.last_contact = parsed['start']

    # Add timeline event for past meetings with a person
    if person and parsed['start'] < datetime.now():
        timeline = TimelineEvent(
            person_id=person.id,
            event_type='MEETING',
            description=f"{meeting_type}: {parsed['summary']}",
            timestamp=parsed['start']
        )
        session.add(timeline)

    return meeting


def scan_calendar(days_back=30, days_forward=30):
    """Scan Google Calendar for events."""
    print("\n" + "="*50)
    print("Starting Calendar scan...")
    print("="*50)

    service = get_calendar_service()
    if not service:
        print("Failed to connect to Google Calendar")
        session = get_session()
        update_sync_status(session, 'calendar', success=False, error_message="Failed to authenticate")
        session.close()
        return

    session = get_session()
    processed_count = 0
    new_meetings = 0

    try:
        events = fetch_events(service, days_back, days_forward)
        print(f"Found {len(events)} calendar events")

        for event in events:
            # Skip all-day events and declined events
            if 'dateTime' not in event.get('start', {}):
                continue

            # Skip if organizer declined
            self_status = event.get('attendees', [{}])[0].get('responseStatus') if event.get('attendees') else None

            meeting = process_calendar_event(event, session)
            if meeting:
                processed_count += 1
                if not session.query(Meeting).filter(
                    Meeting.calendar_event_id == event['id']
                ).first():
                    new_meetings += 1

        session.commit()

        # Update stats for all people
        for person in session.query(Person).all():
            update_person_stats(session, person.id)
        session.commit()

        update_sync_status(session, 'calendar', success=True, items_processed=processed_count)
        print(f"Processed {processed_count} events, {new_meetings} new meetings")

    except Exception as e:
        session.rollback()
        update_sync_status(session, 'calendar', success=False, error_message=str(e))
        print(f"Error scanning calendar: {e}")
    finally:
        session.close()

    print("Calendar scan complete.")


def get_upcoming_meetings(days=7):
    """Get upcoming meetings for the next N days."""
    session = get_session()
    try:
        now = datetime.now()
        future = now + timedelta(days=days)

        meetings = session.query(Meeting).filter(
            Meeting.date >= now,
            Meeting.date <= future
        ).order_by(Meeting.date).all()

        result = []
        for m in meetings:
            result.append({
                'id': m.id,
                'date': m.date,
                'type': m.meeting_type,
                'duration': m.duration_minutes,
                'person_name': m.person.name if m.person else 'Unknown',
                'person_id': m.person_id,
                'notes': m.notes
            })

        return result
    finally:
        session.close()


if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1:
        if sys.argv[1] == 'oauth':
            if len(sys.argv) < 3:
                print("Usage: python calendar_scanner.py oauth <client_secrets.json>")
                sys.exit(1)
            run_calendar_oauth_flow(sys.argv[2])
        elif sys.argv[1] == 'scan':
            days_back = int(sys.argv[2]) if len(sys.argv) > 2 else 30
            days_forward = int(sys.argv[3]) if len(sys.argv) > 3 else 30
            scan_calendar(days_back, days_forward)
        elif sys.argv[1] == 'upcoming':
            days = int(sys.argv[2]) if len(sys.argv) > 2 else 7
            meetings = get_upcoming_meetings(days)
            for m in meetings:
                print(f"{m['date']} - {m['type']} with {m['person_name']}")
    else:
        print("Calendar Scanner")
        print("Usage:")
        print("  python calendar_scanner.py oauth <client_secrets.json>  - Run OAuth setup")
        print("  python calendar_scanner.py scan [days_back] [days_forward]  - Scan calendar")
        print("  python calendar_scanner.py upcoming [days]  - Show upcoming meetings")
