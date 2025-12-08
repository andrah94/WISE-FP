"""
Email and event parsing logic.
Extracts structured data from emails, calendar events, and Calendly bookings.
"""

import re
from decimal import Decimal
from datetime import datetime
from bs4 import BeautifulSoup


def clean_html(html_content):
    """Remove HTML tags and clean up text."""
    if not html_content:
        return ''
    soup = BeautifulSoup(html_content, 'lxml')
    return soup.get_text(separator=' ', strip=True)


def parse_application_email(subject, body):
    """
    Parse application received emails.

    Example subject: "Application Received PROPOSED INSURED: CARBAJAL, POLICY #: xxxxx61042"

    Example body content:
    - File Number: 6602261042
    - Proposed Insured's Name: CARLOS CARBAJAL
    - Product Applied for: Financial Foundation IUL II 2025 GPT California
    - Face Amount Applied for: $144,000.00
    """
    result = {
        'insured_name': None,
        'policy_number': None,
        'product': None,
        'face_amount': None,
        'carrier': None,
        'email': None
    }

    # Clean body if it's HTML
    clean_body = clean_html(body) if '<' in body else body
    combined_text = f"{subject}\n{clean_body}"

    # Extract name from subject or body
    # Pattern: "PROPOSED INSURED: NAME" or "Proposed Insured's Name: NAME"
    name_patterns = [
        r"PROPOSED INSURED[:\s]+([A-Z\s,]+?)(?:,|\s+POLICY|$)",
        r"Proposed Insured'?s? Name[:\s]+([A-Za-z\s,]+?)(?:\n|$)",
        r"Insured[:\s]+([A-Za-z\s,]+?)(?:\n|,|$)"
    ]

    for pattern in name_patterns:
        match = re.search(pattern, combined_text, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            # Clean up name format (LAST, FIRST -> First Last)
            if ',' in name:
                parts = [p.strip() for p in name.split(',')]
                if len(parts) >= 2:
                    name = f"{parts[1]} {parts[0]}"
            result['insured_name'] = name.title()
            break

    # Extract policy/file number
    policy_patterns = [
        r"POLICY\s*#?[:\s]+(?:x+)?(\d+)",
        r"File\s*Number[:\s]+(\d+)",
        r"Policy\s*Number[:\s]+(\d+)",
        r"Application\s*#?[:\s]+(\d+)"
    ]

    for pattern in policy_patterns:
        match = re.search(pattern, combined_text, re.IGNORECASE)
        if match:
            result['policy_number'] = match.group(1)
            break

    # Extract product name
    product_patterns = [
        r"Product(?:\s+Applied\s+for)?[:\s]+(.+?)(?:\n|Face|$)",
        r"Plan[:\s]+(.+?)(?:\n|$)",
        r"(Financial Foundation IUL[^,\n]+)",
        r"(Indexed Universal Life[^,\n]+)",
        r"(Term Life[^,\n]+)",
        r"(Whole Life[^,\n]+)"
    ]

    for pattern in product_patterns:
        match = re.search(pattern, combined_text, re.IGNORECASE)
        if match:
            result['product'] = match.group(1).strip()
            break

    # Extract face amount
    face_patterns = [
        r"Face\s*Amount(?:\s+Applied\s+for)?[:\s]+\$?([\d,]+(?:\.\d{2})?)",
        r"Coverage\s*Amount[:\s]+\$?([\d,]+(?:\.\d{2})?)",
        r"Death\s*Benefit[:\s]+\$?([\d,]+(?:\.\d{2})?)",
        r"\$\s*([\d,]+(?:\.\d{2})?)\s*(?:face|coverage|death benefit)",
    ]

    for pattern in face_patterns:
        match = re.search(pattern, combined_text, re.IGNORECASE)
        if match:
            amount_str = match.group(1).replace(',', '')
            try:
                result['face_amount'] = Decimal(amount_str)
            except:
                pass
            break

    # Detect carrier
    carrier_keywords = {
        'transamerica': 'Transamerica',
        'nationwide': 'Nationwide',
        'prudential': 'Prudential',
        'lincoln': 'Lincoln Financial',
        'principal': 'Principal',
        'aig': 'AIG',
        'john hancock': 'John Hancock',
        'pacific life': 'Pacific Life',
        'protective': 'Protective',
        'mutual of omaha': 'Mutual of Omaha'
    }

    lower_text = combined_text.lower()
    for keyword, carrier_name in carrier_keywords.items():
        if keyword in lower_text:
            result['carrier'] = carrier_name
            break

    # Extract email if present
    email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', combined_text)
    if email_match:
        result['email'] = email_match.group(0).lower()

    return result if result['insured_name'] or result['policy_number'] else None


def parse_status_update_email(subject, body):
    """
    Parse status update emails (approved, underwriting, etc.)
    """
    result = {
        'policy_number': None,
        'new_status': None,
        'insured_name': None
    }

    clean_body = clean_html(body) if '<' in body else body
    combined_text = f"{subject}\n{clean_body}"
    lower_text = combined_text.lower()

    # Extract policy number
    policy_patterns = [
        r"Policy\s*#?[:\s]+(?:x+)?(\d+)",
        r"File\s*(?:Number|#)?[:\s]+(\d+)",
        r"Application\s*#?[:\s]+(\d+)",
        r"Case\s*#?[:\s]+(\d+)"
    ]

    for pattern in policy_patterns:
        match = re.search(pattern, combined_text, re.IGNORECASE)
        if match:
            result['policy_number'] = match.group(1)
            break

    # Determine status
    if 'approved' in lower_text or 'approval' in lower_text:
        result['new_status'] = 'APPROVED'
    elif 'underwriting' in lower_text:
        result['new_status'] = 'UNDERWRITING'
    elif 'pending' in lower_text:
        result['new_status'] = 'SUBMITTED'
    elif 'delivered' in lower_text or 'delivery' in lower_text:
        result['new_status'] = 'DELIVERED'
    elif 'declined' in lower_text or 'rejected' in lower_text:
        result['new_status'] = 'DECLINED'

    # Extract name
    name_patterns = [
        r"(?:Insured|Client|Applicant)[:\s]+([A-Za-z\s,]+?)(?:\n|,|$)",
        r"(?:for|regarding)[:\s]+([A-Za-z\s]+?)(?:\n|,|$)"
    ]

    for pattern in name_patterns:
        match = re.search(pattern, combined_text, re.IGNORECASE)
        if match:
            result['insured_name'] = match.group(1).strip().title()
            break

    return result if result['policy_number'] or result['new_status'] else None


def parse_calendly_email(subject, body):
    """
    Parse Calendly confirmation/notification emails.

    Example subject: "New Event: John Smith - Financial Education Session"
    """
    result = {
        'attendee_name': None,
        'attendee_email': None,
        'attendee_phone': None,
        'event_type': None,
        'event_date': None,
        'duration_minutes': None
    }

    clean_body = clean_html(body) if '<' in body else body
    combined_text = f"{subject}\n{clean_body}"

    # Extract attendee name from subject
    subject_patterns = [
        r"New Event[:\s]+(.+?)\s+-\s+(.+)",
        r"Booking Confirmed[:\s]+(.+?)\s+-\s+(.+)",
        r"Meeting with[:\s]+(.+?)(?:\n|$)"
    ]

    for pattern in subject_patterns:
        match = re.search(pattern, subject, re.IGNORECASE)
        if match:
            result['attendee_name'] = match.group(1).strip()
            if len(match.groups()) > 1:
                result['event_type'] = match.group(2).strip()
            break

    # Extract email
    email_patterns = [
        r"Email[:\s]+([\w\.-]+@[\w\.-]+\.\w+)",
        r"([\w\.-]+@[\w\.-]+\.\w+)"
    ]

    for pattern in email_patterns:
        match = re.search(pattern, combined_text)
        if match:
            email = match.group(1).lower()
            # Filter out Calendly system emails
            if 'calendly' not in email and 'noreply' not in email:
                result['attendee_email'] = email
                break

    # Extract phone number
    phone_patterns = [
        r"Phone[:\s]+([\d\-\(\)\s\+]+)",
        r"(?:^|\s)(\+?1?[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{4})(?:\s|$)"
    ]

    for pattern in phone_patterns:
        match = re.search(pattern, combined_text)
        if match:
            phone = re.sub(r'[^\d+]', '', match.group(1))
            if len(phone) >= 10:
                result['attendee_phone'] = phone
                break

    # Extract event type from body if not in subject
    if not result['event_type']:
        event_patterns = [
            r"Event Type[:\s]+(.+?)(?:\n|$)",
            r"Meeting Type[:\s]+(.+?)(?:\n|$)",
            r"(Financial Education|BPO|Intro Call|Presentation|Consultation)"
        ]

        for pattern in event_patterns:
            match = re.search(pattern, combined_text, re.IGNORECASE)
            if match:
                result['event_type'] = match.group(1).strip()
                break

    # Extract date/time
    date_patterns = [
        r"(\w+day,?\s+\w+\s+\d{1,2},?\s+\d{4})\s+(?:at\s+)?(\d{1,2}:\d{2}\s*(?:AM|PM)?)",
        r"Date[:\s]+(.+?)(?:\n|$)",
        r"When[:\s]+(.+?)(?:\n|$)"
    ]

    for pattern in date_patterns:
        match = re.search(pattern, combined_text, re.IGNORECASE)
        if match:
            try:
                date_str = match.group(1)
                if len(match.groups()) > 1:
                    date_str += ' ' + match.group(2)
                # Try to parse the date
                for fmt in ['%A, %B %d, %Y %I:%M %p', '%B %d, %Y %I:%M %p',
                           '%m/%d/%Y %I:%M %p', '%Y-%m-%d %H:%M']:
                    try:
                        result['event_date'] = datetime.strptime(date_str.strip(), fmt)
                        break
                    except:
                        continue
            except:
                pass
            break

    # Extract duration
    duration_patterns = [
        r"(\d+)\s*(?:min|minute)",
        r"Duration[:\s]+(\d+)",
        r"(\d+)\s*hour"
    ]

    for pattern in duration_patterns:
        match = re.search(pattern, combined_text, re.IGNORECASE)
        if match:
            duration = int(match.group(1))
            if 'hour' in pattern.lower():
                duration *= 60
            result['duration_minutes'] = duration
            break

    return result if result['attendee_name'] or result['attendee_email'] else None


def parse_calendar_event(event):
    """
    Parse a Google Calendar event.

    Args:
        event: Google Calendar API event object
    """
    result = {
        'event_id': event.get('id'),
        'summary': event.get('summary', ''),
        'start': None,
        'end': None,
        'duration_minutes': None,
        'attendees': [],
        'location': event.get('location', ''),
        'description': event.get('description', '')
    }

    # Parse start time
    start = event.get('start', {})
    if 'dateTime' in start:
        result['start'] = datetime.fromisoformat(start['dateTime'].replace('Z', '+00:00'))
    elif 'date' in start:
        result['start'] = datetime.strptime(start['date'], '%Y-%m-%d')

    # Parse end time
    end = event.get('end', {})
    if 'dateTime' in end:
        result['end'] = datetime.fromisoformat(end['dateTime'].replace('Z', '+00:00'))
    elif 'date' in end:
        result['end'] = datetime.strptime(end['date'], '%Y-%m-%d')

    # Calculate duration
    if result['start'] and result['end']:
        delta = result['end'] - result['start']
        result['duration_minutes'] = int(delta.total_seconds() / 60)

    # Extract attendees
    attendees = event.get('attendees', [])
    for attendee in attendees:
        email = attendee.get('email', '')
        # Filter out the organizer and resource calendars
        if email and '@' in email and 'resource' not in email.lower():
            result['attendees'].append({
                'email': email,
                'name': attendee.get('displayName', ''),
                'response': attendee.get('responseStatus', 'needsAction')
            })

    return result


def detect_meeting_type(summary, description=''):
    """
    Detect the type of meeting from its title/description.
    """
    combined = f"{summary} {description}".lower()

    meeting_types = {
        'Financial Education': ['financial education', 'fe session', 'education session'],
        'BPO': ['bpo', 'business presentation', 'business opportunity'],
        'Intro Call': ['intro', 'introduction', 'initial call', 'first call', 'discovery'],
        'Presentation': ['presentation', 'proposal', 'review meeting'],
        'Follow-up': ['follow up', 'follow-up', 'check in', 'check-in'],
        'Consultation': ['consultation', 'consult', 'advisory'],
        'Closing': ['closing', 'sign', 'paperwork', 'application review']
    }

    for meeting_type, keywords in meeting_types.items():
        for keyword in keywords:
            if keyword in combined:
                return meeting_type

    return 'Meeting'  # Default


def extract_name_from_email(email):
    """
    Try to extract a name from an email address.
    Example: john.smith@gmail.com -> John Smith
    """
    if not email:
        return None

    local_part = email.split('@')[0]

    # Common separators
    for sep in ['.', '_', '-']:
        if sep in local_part:
            parts = local_part.split(sep)
            if len(parts) >= 2:
                # Filter out common prefixes/suffixes
                filtered = [p for p in parts if p.lower() not in ['info', 'contact', 'admin', 'support']]
                if filtered:
                    return ' '.join(p.title() for p in filtered)

    # If no separator, try to split on number or just return as-is
    name = re.sub(r'\d+', '', local_part)
    if name:
        return name.title()

    return None


def normalize_phone(phone):
    """Normalize phone number to standard format."""
    if not phone:
        return None

    # Remove all non-digit characters except +
    digits = re.sub(r'[^\d+]', '', phone)

    # Handle US numbers
    if digits.startswith('+1'):
        digits = digits[2:]
    elif digits.startswith('1') and len(digits) == 11:
        digits = digits[1:]

    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"

    return phone  # Return original if can't normalize


def calculate_commission(face_amount, product_type=None):
    """
    Calculate estimated commission based on face amount.
    """
    if not face_amount:
        return Decimal('0')

    face = float(face_amount)

    # Estimate monthly premium based on face amount
    if face >= 100000:
        monthly = face * 0.0025
    elif face >= 50000:
        monthly = face * 0.003
    else:
        monthly = face * 0.0035

    annual_premium = monthly * 12
    commission = annual_premium * 0.45  # 45% first-year commission

    return Decimal(str(round(commission, 2)))
