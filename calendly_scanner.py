"""
Calendly API integration.
Fetches scheduled events and invitee information.
"""

import os
import json
from datetime import datetime, timedelta

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from database import (
    get_session, get_or_create_person, Person, Meeting, TimelineEvent,
    PersonStatus, STAGE_PROBABILITIES, update_sync_status, update_person_stats
)
from parsers import detect_meeting_type, normalize_phone

# Calendly API base URL
CALENDLY_API_BASE = 'https://api.calendly.com'


def get_calendly_headers():
    """Get headers for Calendly API requests."""
    api_key = os.getenv('CALENDLY_API_KEY')
    if not api_key:
        return None

    return {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }


def make_calendly_request(endpoint, params=None):
    """Make a request to Calendly API."""
    headers = get_calendly_headers()
    if not headers:
        print("CALENDLY_API_KEY not set or empty")
        return None

    url = f"{CALENDLY_API_BASE}{endpoint}"
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        if response.status_code != 200:
            print(f"Calendly API error {response.status_code}: {response.text[:200]}")
            return None
        return response.json()
    except Exception as e:
        print(f"Calendly request error: {e}")
        return None


def get_current_user():
    """Get the current Calendly user info."""
    data = make_calendly_request('/users/me')
    if data:
        return data.get('resource', {})
    return None


def get_scheduled_events(days_back=30, days_forward=30):
    """Fetch scheduled events from Calendly."""
    user = get_current_user()
    if not user:
        return []

    user_uri = user.get('uri')
    if not user_uri:
        return []

    try:
        now = datetime.utcnow()
        min_time = (now - timedelta(days=days_back)).strftime('%Y-%m-%dT%H:%M:%SZ')
        max_time = (now + timedelta(days=days_forward)).strftime('%Y-%m-%dT%H:%M:%SZ')

        params = {
            'user': user_uri,
            'min_start_time': min_time,
            'max_start_time': max_time,
            'count': 100,
            'status': 'active'
        }

        data = make_calendly_request('/scheduled_events', params)
        events = data.get('collection', [])

        # Also get canceled events for tracking
        params['status'] = 'canceled'
        canceled_data = make_calendly_request('/scheduled_events', params)
        canceled_events = canceled_data.get('collection', [])

        return events + canceled_events
    except Exception as e:
        print(f"Error fetching Calendly events: {e}")
        return []


def get_event_invitees(event_uri):
    """Get invitees for a specific event."""
    try:
        # Extract event UUID from URI
        event_uuid = event_uri.split('/')[-1]
        endpoint = f'/scheduled_events/{event_uuid}/invitees'

        data = make_calendly_request(endpoint)
        return data.get('collection', [])
    except Exception as e:
        print(f"Error fetching invitees: {e}")
        return []


def process_calendly_event(event, session):
    """Process a single Calendly event and update database."""
    event_uri = event.get('uri', '')
    event_uuid = event_uri.split('/')[-1] if event_uri else None

    if not event_uuid:
        return None

    # Check if event already exists
    existing = session.query(Meeting).filter(
        Meeting.calendly_event_id == event_uuid
    ).first()

    if existing:
        return existing

    # Parse event details
    event_name = event.get('name', '')
    start_time_str = event.get('start_time', '')
    end_time_str = event.get('end_time', '')
    status = event.get('status', 'active')

    # Parse times
    start_time = None
    duration_minutes = 60

    if start_time_str:
        try:
            start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
        except:
            pass

    if start_time_str and end_time_str:
        try:
            end_time = datetime.fromisoformat(end_time_str.replace('Z', '+00:00'))
            duration_minutes = int((end_time - start_time).total_seconds() / 60)
        except:
            pass

    # Get invitees
    invitees = get_event_invitees(event_uri)

    person = None
    attendee_emails = []

    for invitee in invitees:
        name = invitee.get('name', '')
        email = invitee.get('email', '')
        phone = None

        # Get phone from questions_and_answers
        for qa in invitee.get('questions_and_answers', []):
            question = qa.get('question', '').lower()
            if 'phone' in question or 'number' in question:
                phone = normalize_phone(qa.get('answer', ''))
                break

        if email:
            attendee_emails.append(email)

        if name and email:
            person, created = get_or_create_person(session, name, email)
            if created:
                person.status = PersonStatus.SCHEDULED
                person.probability = STAGE_PROBABILITIES[PersonStatus.SCHEDULED]
                print(f"  → New person from Calendly: {name}")

            if phone and not person.phone:
                person.phone = phone

            # Update last contact for past events
            if start_time and start_time < datetime.now():
                if not person.last_contact or start_time > person.last_contact:
                    person.last_contact = start_time

    # Detect meeting type
    meeting_type = detect_meeting_type(event_name)

    # Create meeting record
    meeting = Meeting(
        person_id=person.id if person else None,
        meeting_type=meeting_type,
        date=start_time,
        duration_minutes=duration_minutes,
        source='Calendly',
        calendly_event_id=event_uuid,
        attendees=json.dumps(attendee_emails),
        notes=f"{event_name} (Status: {status})"
    )
    session.add(meeting)

    # Add timeline event for past meetings
    if person and start_time and start_time < datetime.now():
        timeline = TimelineEvent(
            person_id=person.id,
            event_type='MEETING',
            description=f"Calendly {meeting_type}: {event_name}",
            timestamp=start_time
        )
        session.add(timeline)

    return meeting


def scan_calendly(days_back=30, days_forward=30):
    """Scan Calendly for scheduled events."""
    print("\n" + "="*50)
    print("Starting Calendly scan...")
    print("="*50)

    if not os.getenv('CALENDLY_API_KEY'):
        print("CALENDLY_API_KEY not set. Skipping Calendly scan.")
        return

    session = get_session()
    processed_count = 0
    new_meetings = 0

    try:
        # Verify API connection
        user = get_current_user()
        if not user:
            update_sync_status(session, 'calendly', success=False, error_message="Failed to authenticate")
            print("Failed to authenticate with Calendly")
            return

        print(f"Connected as: {user.get('name', 'Unknown')}")

        # Fetch events
        events = get_scheduled_events(days_back, days_forward)
        print(f"Found {len(events)} Calendly events")

        for event in events:
            result = process_calendly_event(event, session)
            if result:
                processed_count += 1
                # Check if it was newly created
                event_uuid = event.get('uri', '').split('/')[-1]
                if not session.query(Meeting).filter(
                    Meeting.calendly_event_id == event_uuid
                ).first():
                    new_meetings += 1

        session.commit()

        # Update stats for all people
        for person in session.query(Person).all():
            update_person_stats(session, person.id)
        session.commit()

        update_sync_status(session, 'calendly', success=True, items_processed=processed_count)
        print(f"Processed {processed_count} events, {new_meetings} new meetings")

    except Exception as e:
        session.rollback()
        update_sync_status(session, 'calendly', success=False, error_message=str(e))
        print(f"Error scanning Calendly: {e}")
    finally:
        session.close()

    print("Calendly scan complete.")


def get_calendly_event_types():
    """Get all event types for the user."""
    user = get_current_user()
    if not user:
        return []

    user_uri = user.get('uri')
    if not user_uri:
        return []

    try:
        params = {'user': user_uri}
        data = make_calendly_request('/event_types', params)
        return data.get('collection', [])
    except Exception as e:
        print(f"Error fetching event types: {e}")
        return []


if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1:
        if sys.argv[1] == 'test':
            # Test API connection
            user = get_current_user()
            if user:
                print(f"Connected to Calendly as: {user.get('name')}")
                print(f"Email: {user.get('email')}")
                print(f"URI: {user.get('uri')}")

                # List event types
                event_types = get_calendly_event_types()
                print(f"\nEvent Types ({len(event_types)}):")
                for et in event_types:
                    print(f"  - {et.get('name')} ({et.get('duration')} min)")
            else:
                print("Failed to connect to Calendly. Check your API key.")

        elif sys.argv[1] == 'scan':
            days_back = int(sys.argv[2]) if len(sys.argv) > 2 else 30
            days_forward = int(sys.argv[3]) if len(sys.argv) > 3 else 30
            scan_calendly(days_back, days_forward)

        elif sys.argv[1] == 'events':
            events = get_scheduled_events()
            print(f"\nScheduled Events ({len(events)}):")
            for e in events[:10]:  # Show first 10
                print(f"  - {e.get('name')} on {e.get('start_time')}")
    else:
        print("Calendly Scanner")
        print("Usage:")
        print("  python calendly_scanner.py test  - Test API connection")
        print("  python calendly_scanner.py scan [days_back] [days_forward]  - Scan events")
        print("  python calendly_scanner.py events  - List scheduled events")
