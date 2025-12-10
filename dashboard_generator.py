"""
WISE Financial Partners - Premium Dashboard Generator
Uses user's exact premium design with glassmorphism, confetti, and live data.
"""

import pytz
from datetime import datetime, timedelta, date
from decimal import Decimal

from database import (
    get_session, Person, Application, Meeting, TimelineEvent,
    DailyMetrics, MonthlyRevenue, PersonStatus, ApplicationStatus,
    STAGE_PROBABILITIES, calculate_daily_metrics, SyncStatus
)

# Los Angeles timezone
LA_TZ = pytz.timezone('America/Los_Angeles')


def get_la_time(dt=None):
    """Convert datetime to Los Angeles timezone."""
    if dt is None:
        dt = datetime.utcnow()
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)
    return dt.astimezone(LA_TZ)


def format_la_time(dt, format_str='%B %d, %Y - %I:%M %p %Z'):
    """Format datetime in Los Angeles timezone."""
    if dt is None:
        return "Never"
    la_time = get_la_time(dt)
    return la_time.strftime(format_str)


def format_currency(amount):
    """Format a number as currency."""
    if amount is None:
        return "$0"
    return f"${float(amount):,.0f}"


def format_currency_short(amount):
    """Format currency in short form (e.g., $3.5K)."""
    if amount is None or amount == 0:
        return "$0"
    val = float(amount)
    if val >= 1000000:
        return f"${val/1000000:.1f}M"
    if val >= 1000:
        return f"${val/1000:.1f}K"
    return f"${val:.0f}"


def generate_dashboard_html(session=None):
    """Generate the complete premium dashboard HTML with live data."""
    close_session = False
    if session is None:
        session = get_session()
        close_session = True

    try:
        # Get all data from database
        people = session.query(Person).order_by(Person.weighted_value.desc()).all()
        applications = session.query(Application).all()
        meetings = session.query(Meeting).all()

        # Get monthly revenue data
        monthly_revenues = session.query(MonthlyRevenue).order_by(MonthlyRevenue.month).all()

        # Get sync status
        sync_statuses = session.query(SyncStatus).all()
        last_sync = None
        for status in sync_statuses:
            if status.last_sync and (last_sync is None or status.last_sync > last_sync):
                last_sync = status.last_sync

        # Calculate metrics
        now_la = get_la_time()

        # Financial metrics
        total_ytd = sum(float(mr.revenue or 0) for mr in monthly_revenues)
        monthly_avg = total_ytd / 12 if monthly_revenues else 0
        best_month = max(monthly_revenues, key=lambda x: float(x.revenue or 0)) if monthly_revenues else None
        best_month_amount = float(best_month.revenue or 0) if best_month else 0

        # Pipeline metrics
        total_pipeline_face = sum(float(app.face_amount or 0) for app in applications
                                   if app.status not in [ApplicationStatus.DELIVERED, ApplicationStatus.DECLINED])

        pending_commission = sum(float(app.estimated_commission or 0) for app in applications
                                  if app.status in [ApplicationStatus.APPROVED, ApplicationStatus.SIGNATURE_NEEDED])

        approved_count = len([app for app in applications
                              if app.status in [ApplicationStatus.APPROVED, ApplicationStatus.SIGNATURE_NEEDED]])

        # Monthly goal tracking (December)
        monthly_goal = 30000
        current_month_revenue = 0
        current_month = now_la.month
        for mr in monthly_revenues:
            if mr.month and mr.month.month == current_month:
                current_month_revenue = float(mr.revenue or 0)
                break

        goal_percentage = (current_month_revenue / monthly_goal * 100) if monthly_goal > 0 else 0
        goal_remaining = monthly_goal - current_month_revenue

        # Get today's meetings
        today = now_la.date()
        tomorrow = today + timedelta(days=1)

        today_meetings = [m for m in meetings
                         if m.date and m.date.date() == today]
        today_meetings.sort(key=lambda x: x.date)

        # Generate cash flow chart data
        cash_flow_data = []
        for mr in monthly_revenues[-12:]:  # Last 12 months
            if mr.month:
                cash_flow_data.append({
                    'month': mr.month.strftime('%b'),
                    'year': mr.month.strftime('%y'),
                    'amount': float(mr.revenue or 0)
                })

        # Default cash flow data if empty
        if not cash_flow_data:
            cash_flow_data = [
                {'month': 'Dec', 'year': '24', 'amount': 3526.26},
                {'month': 'Jan', 'year': '25', 'amount': 588.64},
                {'month': 'Feb', 'year': '25', 'amount': 3213.59},
                {'month': 'Mar', 'year': '25', 'amount': 882.95},
                {'month': 'Apr', 'year': '25', 'amount': 5623.05},
                {'month': 'May', 'year': '25', 'amount': 2894.99},
                {'month': 'Jun', 'year': '25', 'amount': 298.32},
                {'month': 'Jul', 'year': '25', 'amount': -24.00},
                {'month': 'Aug', 'year': '25', 'amount': 3958.48},
                {'month': 'Sep', 'year': '25', 'amount': 7278.86},
                {'month': 'Oct', 'year': '25', 'amount': 6662.33},
                {'month': 'Nov', 'year': '25', 'amount': 4157.66}
            ]
            total_ytd = sum(d['amount'] for d in cash_flow_data)
            monthly_avg = total_ytd / 12
            best_month_amount = max(d['amount'] for d in cash_flow_data)

        # Generate command center items
        command_items = []

        # Check for signature needed (money on table!)
        signature_apps = [app for app in applications if app.status == ApplicationStatus.SIGNATURE_NEEDED]
        for app in signature_apps:
            person_name = app.person.name if app.person else "Unknown"
            command_items.append({
                'type': 'success',
                'icon': '🎉',
                'label': 'READY FOR DELIVERY!',
                'text': f'{person_name} policy approved! Schedule delivery for ${format_currency(app.estimated_commission)} commission!'
            })

        # Check for approved apps
        approved_apps = [app for app in applications if app.status == ApplicationStatus.APPROVED]
        for app in approved_apps:
            person_name = app.person.name if app.person else "Unknown"
            face_str = format_currency_short(app.face_amount) if app.face_amount else ""
            command_items.append({
                'type': 'success',
                'icon': '✅',
                'label': 'APPROVED!',
                'text': f'{person_name} {face_str} APPROVED! Schedule delivery appointment!'
            })

        # Check for stalled apps
        stalled_apps = [app for app in applications if app.status == ApplicationStatus.STALLED]
        for app in stalled_apps:
            person_name = app.person.name if app.person else "Unknown"
            blocker = app.blocker or "Requirements needed"
            command_items.append({
                'type': 'important',
                'icon': '⚠️',
                'label': 'REQUIREMENTS NEEDED',
                'text': f'{person_name}: {blocker}'
            })

        # Today's meetings
        for meeting in today_meetings[:3]:  # Show up to 3 meetings
            meeting_time = format_la_time(meeting.date, '%I:%M %p')
            person_name = meeting.person.name if meeting.person else "Unknown"
            meeting_type = meeting.meeting_type or "Meeting"
            command_items.append({
                'type': 'scheduled',
                'icon': '📅',
                'label': f'{meeting_time} PT',
                'text': f'{person_name} - {meeting_type}'
            })

        # Generate pipeline cards
        pipeline_cards = []
        for app in applications:
            if app.status == ApplicationStatus.DELIVERED:
                continue
            person_name = app.person.name if app.person else "Unknown"
            face_str = format_currency_short(app.face_amount) if app.face_amount else ""

            card_type = 'pending'
            status_text = '⏳ IN UW'
            action_text = 'Monitor progress'
            action_class = 'info'

            if app.status == ApplicationStatus.SIGNATURE_NEEDED:
                card_type = 'approved'
                status_text = '✅ READY'
                action_text = 'Schedule delivery!'
                action_class = 'success'
            elif app.status == ApplicationStatus.APPROVED:
                card_type = 'approved'
                status_text = '✅ APPROVED'
                action_text = 'Schedule delivery!'
                action_class = 'success'
            elif app.status == ApplicationStatus.STALLED:
                card_type = 'urgent'
                status_text = '⚠️ REQS NEEDED'
                action_text = app.blocker or 'Check requirements'
                action_class = 'warning'
            elif app.status == ApplicationStatus.UNDERWRITING:
                card_type = 'pending'
                status_text = '⏳ IN UW'
                action_text = 'Monitor progress'
                action_class = 'info'

            pipeline_cards.append({
                'type': card_type,
                'status': status_text,
                'name': person_name,
                'policy': app.policy_number or '',
                'face': face_str,
                'action_text': action_text,
                'action_class': action_class
            })

        # Generate contacts
        contacts = []
        for person in people[:8]:  # Show top 8 contacts
            status_class = 'info'
            status_text = person.status or 'Active'

            if person.status == PersonStatus.APPROVED:
                status_class = 'success'
                status_text = 'Schedule delivery!'
            elif person.status == PersonStatus.WARM:
                status_class = 'warning'
                status_text = 'Follow up!'
            elif person.status == PersonStatus.ACTIVE:
                status_class = 'info'
                status_text = 'In progress'
            elif person.status == PersonStatus.COLD:
                status_class = 'warning'
                status_text = 'Re-engage'

            contacts.append({
                'name': person.name,
                'email': person.email,
                'phone': person.phone,
                'status_class': status_class,
                'status_text': status_text,
                'commission': format_currency(person.estimated_commission) if person.estimated_commission else ''
            })

        # Generate meetings HTML
        meetings_html = ""
        for meeting in today_meetings:
            meeting_time = format_la_time(meeting.date, '%I:%M %p')
            person_name = meeting.person.name if meeting.person else "Unknown"
            meeting_type = meeting.meeting_type or "Meeting"
            source = meeting.source or ""

            source_badge = ""
            if source:
                source_badge = f'<span class="meeting-source">via {source}</span>'

            meetings_html += f'''
            <div class="meeting-card glass-dark">
              <div class="meeting-time">{meeting_time}</div>
              <div class="meeting-info">
                <h4>{person_name}</h4>
                <p class="meeting-type">{meeting_type}</p>
                {source_badge}
              </div>
            </div>'''

        if not meetings_html:
            meetings_html = '''
            <div class="meeting-card glass-dark">
              <div class="meeting-time">--</div>
              <div class="meeting-info">
                <h4>No meetings scheduled</h4>
                <p class="meeting-type">Check your calendar</p>
              </div>
            </div>'''

        # Generate command items HTML
        command_html = ""
        for item in command_items[:6]:  # Show up to 6 command items
            command_html += f'''
            <div class="command-item glass-dark {item['type']}">
              <span class="command-icon">{item['icon']}</span>
              <div class="command-content">
                <span class="command-label">{item['label']}</span>
                <p>{item['text']}</p>
              </div>
            </div>'''

        if not command_html:
            command_html = '''
            <div class="command-item glass-dark info">
              <span class="command-icon">📋</span>
              <div class="command-content">
                <span class="command-label">ALL CLEAR</span>
                <p>No urgent actions needed. Keep prospecting!</p>
              </div>
            </div>'''

        # Generate pipeline HTML
        pipeline_html = ""
        for card in pipeline_cards[:8]:  # Show up to 8 pipeline cards
            pipeline_html += f'''
            <div class="pipeline-card glass-dark {card['type']}">
              <div class="pipeline-status">{card['status']}</div>
              <h4>{card['name']}</h4>
              <div class="pipeline-details">
                <span>{card['policy']}</span>
                <span class="highlight">{card['face']}</span>
              </div>
              <p class="pipeline-action {card['action_class']}">{card['action_text']}</p>
            </div>'''

        if not pipeline_html:
            pipeline_html = '''
            <div class="pipeline-card glass-dark new-prospect">
              <div class="pipeline-status">🆕 START HERE</div>
              <h4>Build Your Pipeline</h4>
              <div class="pipeline-details">
                <span>No active applications</span>
              </div>
              <p class="pipeline-action info">Schedule more meetings!</p>
            </div>'''

        # Generate contacts HTML
        contacts_html = ""
        for contact in contacts:
            name_class = 'blue'
            if contact['status_class'] == 'success':
                name_class = 'green'
            elif contact['status_class'] == 'warning':
                name_class = 'gold'

            phone_link = f'<a href="tel:{contact["phone"]}" class="contact-link">📞 {contact["phone"]}</a>' if contact['phone'] else ''
            email_link = f'<a href="mailto:{contact["email"]}" class="contact-link">✉️ {contact["email"]}</a>' if contact['email'] else ''
            commission_badge = f'<span class="contact-status {contact["status_class"]}">{contact["commission"]}</span>' if contact['commission'] else f'<span class="contact-status {contact["status_class"]}">{contact["status_text"]}</span>'

            contacts_html += f'''
            <div class="contact-card glass-dark">
              <h4 class="{name_class}">{contact['name']}</h4>
              <div class="contact-row">{phone_link}</div>
              <div class="contact-row">{email_link}</div>
              {commission_badge}
            </div>'''

        if not contacts_html:
            contacts_html = '''
            <div class="contact-card glass-dark">
              <h4 class="blue">No contacts yet</h4>
              <div class="contact-row">Start adding prospects!</div>
            </div>'''

        # Generate cash flow JSON for JavaScript
        import json
        cash_flow_json = json.dumps(cash_flow_data)

        # Current date/time for display
        current_date = now_la.strftime('%A, %B %d, %Y')
        last_sync_str = format_la_time(last_sync) if last_sync else "Never"

        # Build the complete HTML
        html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="refresh" content="300">
    <title>WISE Financial Partners - Premium Dashboard</title>
    <style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=Space+Grotesk:wght@500;600;700&display=swap');

:root {{
  --bg-dark: #0a0e1a;
  --bg-gradient-1: #0f172a;
  --bg-gradient-2: #1e1b4b;
  --glass-bg: rgba(255, 255, 255, 0.05);
  --glass-border: rgba(255, 255, 255, 0.1);
  --glass-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
  --green: #10b981;
  --green-soft: rgba(16, 185, 129, 0.2);
  --blue: #3b82f6;
  --blue-soft: rgba(59, 130, 246, 0.2);
  --gold: #f59e0b;
  --gold-soft: rgba(245, 158, 11, 0.2);
  --red: #ef4444;
  --red-soft: rgba(239, 68, 68, 0.2);
  --purple: #8b5cf6;
  --purple-soft: rgba(139, 92, 246, 0.2);
  --text-white: #ffffff;
  --text-gray: #94a3b8;
  --text-muted: #64748b;
  --radius-lg: 20px;
  --radius-md: 14px;
  --radius-sm: 10px;
}}

* {{ margin: 0; padding: 0; box-sizing: border-box; }}
html {{ scroll-behavior: smooth; }}
body {{
  font-family: 'Inter', -apple-system, sans-serif;
  background: var(--bg-dark);
  color: var(--text-white);
  min-height: 100vh;
  overflow-x: hidden;
  line-height: 1.5;
}}

.parallax-bg {{
  position: fixed;
  top: 0; left: 0;
  width: 100%; height: 100%;
  z-index: -1;
  background:
    radial-gradient(ellipse at 20% 20%, rgba(59, 130, 246, 0.15) 0%, transparent 50%),
    radial-gradient(ellipse at 80% 80%, rgba(139, 92, 246, 0.15) 0%, transparent 50%),
    radial-gradient(ellipse at 50% 50%, rgba(16, 185, 129, 0.1) 0%, transparent 60%),
    linear-gradient(180deg, var(--bg-gradient-1) 0%, var(--bg-dark) 50%, var(--bg-gradient-2) 100%);
  animation: gradientShift 15s ease infinite;
  background-size: 200% 200%;
}}

@keyframes gradientShift {{
  0%, 100% {{ background-position: 0% 0%; }}
  25% {{ background-position: 100% 0%; }}
  50% {{ background-position: 100% 100%; }}
  75% {{ background-position: 0% 100%; }}
}}

#confetti-container {{
  position: fixed;
  top: 0; left: 0;
  width: 100%; height: 100%;
  pointer-events: none;
  z-index: 9999;
  overflow: hidden;
}}

.confetti {{
  position: absolute;
  width: 10px; height: 10px;
  opacity: 0;
  animation: confetti-fall 3s ease-out forwards;
}}

@keyframes confetti-fall {{
  0% {{ opacity: 1; transform: translateY(0) rotate(0deg) scale(1); }}
  100% {{ opacity: 0; transform: translateY(100vh) rotate(720deg) scale(0.5); }}
}}

.container {{
  max-width: 1400px;
  margin: 0 auto;
  padding: 1rem;
  position: relative;
  z-index: 1;
}}

.glass {{
  background: var(--glass-bg);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--glass-shadow);
}}

.glass-dark {{
  background: rgba(15, 23, 42, 0.6);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: var(--radius-md);
}}

.header {{
  padding: 1.5rem;
  margin-bottom: 1rem;
  position: relative;
  overflow: hidden;
}}

.header::before {{
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 3px;
  background: linear-gradient(90deg, var(--blue), var(--purple), var(--green), var(--gold));
  background-size: 300% 100%;
  animation: headerGradient 4s ease infinite;
}}

@keyframes headerGradient {{
  0%, 100% {{ background-position: 0% 50%; }}
  50% {{ background-position: 100% 50%; }}
}}

.header-content {{
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 1rem;
}}

.header-left h1 {{
  font-family: 'Space Grotesk', sans-serif;
  font-size: clamp(1.5rem, 5vw, 2.25rem);
  font-weight: 700;
  margin-bottom: 0.25rem;
}}

.gradient-text {{
  background: linear-gradient(135deg, #60a5fa 0%, #a78bfa 50%, #34d399 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}}

.greeting {{ font-size: 1.1rem; color: var(--text-gray); margin-bottom: 0.25rem; }}
.subtitle {{ font-size: 0.8rem; color: var(--text-muted); }}

.header-right {{
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 0.5rem;
}}

.live-badge {{
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  background: var(--green-soft);
  color: var(--green);
  padding: 0.3rem 0.75rem;
  border-radius: 999px;
  font-size: 0.7rem;
  font-weight: 700;
}}

.live-dot {{
  width: 8px; height: 8px;
  background: var(--green);
  border-radius: 50%;
  animation: pulse 2s infinite;
}}

@keyframes pulse {{
  0%, 100% {{ opacity: 1; transform: scale(1); }}
  50% {{ opacity: 0.5; transform: scale(1.3); }}
}}

.clock {{
  font-size: 1.5rem;
  font-weight: 700;
  font-family: 'Space Grotesk', sans-serif;
  color: var(--blue);
}}

.goal-section {{
  display: flex;
  align-items: center;
  gap: 1.5rem;
  margin: 1.5rem 0;
  padding: 1rem;
  background: rgba(245, 158, 11, 0.1);
  border-radius: var(--radius-md);
  border: 1px solid rgba(245, 158, 11, 0.3);
}}

.goal-ring-container {{
  position: relative;
  width: 100px; height: 100px;
  flex-shrink: 0;
}}

.goal-ring {{
  width: 100%; height: 100%;
  transform: rotate(-90deg);
}}

.goal-ring-bg {{
  fill: none;
  stroke: rgba(255, 255, 255, 0.1);
  stroke-width: 8;
}}

.goal-ring-progress {{
  fill: none;
  stroke: var(--gold);
  stroke-width: 8;
  stroke-linecap: round;
  stroke-dasharray: 327;
  stroke-dashoffset: 327;
  transition: stroke-dashoffset 1.5s ease-out;
  filter: drop-shadow(0 0 6px var(--gold));
}}

.goal-ring-text {{
  position: absolute;
  top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  text-align: center;
}}

.goal-amount {{ display: block; font-size: 1.1rem; font-weight: 800; color: var(--gold); }}
.goal-label {{ display: block; font-size: 0.65rem; color: var(--text-muted); }}

.goal-info h3 {{ font-size: 1rem; margin-bottom: 0.25rem; color: var(--gold); }}
.goal-percent {{ font-size: 0.9rem; font-weight: 600; color: var(--text-white); }}
.goal-remaining {{ font-size: 0.8rem; color: var(--text-muted); }}

.top-nav {{
  display: flex;
  gap: 0.5rem;
  overflow-x: auto;
  padding: 0.5rem 0;
  margin-top: 1rem;
  scrollbar-width: none;
}}
.top-nav::-webkit-scrollbar {{ display: none; }}

.top-nav a {{
  text-decoration: none;
  font-size: 0.75rem;
  color: var(--text-gray);
  padding: 0.5rem 1rem;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  white-space: nowrap;
  transition: all 0.3s ease;
}}

.top-nav a:hover {{
  background: var(--blue-soft);
  color: var(--blue);
  border-color: var(--blue);
  transform: translateY(-2px);
}}

section {{ margin-bottom: 1rem; }}
.section-shell {{ padding: 1.25rem; }}

.section-title {{
  font-size: 1rem;
  font-weight: 700;
  margin-bottom: 1rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}}

.section-title .emoji {{ font-size: 1.2rem; }}
.section-title.gold {{ color: var(--gold); }}
.section-title.green {{ color: var(--green); }}
.section-title.blue {{ color: var(--blue); }}
.section-title.purple {{ color: var(--purple); }}

.wins-section .section-shell {{ cursor: pointer; transition: all 0.3s ease; }}
.wins-section .section-shell:hover {{ transform: scale(1.02); }}

.wins-section .celebrate {{
  background: linear-gradient(135deg, var(--green-soft) 0%, var(--gold-soft) 100%);
  border: 2px solid var(--green);
  display: flex;
  align-items: center;
  gap: 1rem;
}}

.win-icon {{ font-size: 3rem; animation: bounce 1s infinite; }}

@keyframes bounce {{
  0%, 100% {{ transform: translateY(0); }}
  50% {{ transform: translateY(-10px); }}
}}

.win-content h3 {{ color: var(--green); font-size: 1.1rem; margin-bottom: 0.5rem; }}
.win-items {{ display: flex; flex-wrap: wrap; gap: 0.5rem; }}

.win-badge {{
  background: var(--green-soft);
  color: var(--green);
  padding: 0.3rem 0.6rem;
  border-radius: 6px;
  font-size: 0.75rem;
  font-weight: 600;
}}

.win-hint {{ font-size: 0.7rem; color: var(--text-muted); margin-top: 0.5rem; }}

.financial-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 0.75rem;
}}

.stat-card {{
  padding: 1rem;
  text-align: center;
  transition: transform 0.3s ease;
}}

.stat-card:hover {{ transform: translateY(-4px); }}

.stat-label {{
  display: block;
  font-size: 0.65rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 0.3rem;
}}

.stat-value {{
  display: block;
  font-size: 1.5rem;
  font-weight: 800;
  font-family: 'Space Grotesk', sans-serif;
}}

.stat-value.green {{ color: var(--green); }}
.stat-value.blue {{ color: var(--blue); }}
.stat-value.gold {{ color: var(--gold); }}
.stat-value.red {{ color: var(--red); }}

.stat-sub {{ display: block; font-size: 0.65rem; color: var(--text-muted); margin-top: 0.2rem; }}

.chart-container {{ padding: 1rem 0; }}

.chart-bars {{
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  height: 200px;
  gap: 4px;
  padding: 0 0.5rem;
}}

.chart-bar {{
  flex: 1;
  min-width: 20px;
  max-width: 60px;
  border-radius: 6px 6px 0 0;
  position: relative;
  cursor: pointer;
  transition: all 0.3s ease;
  animation: barGrow 1s ease-out forwards;
  transform-origin: bottom;
}}

@keyframes barGrow {{
  from {{ transform: scaleY(0); }}
  to {{ transform: scaleY(1); }}
}}

.chart-bar:hover {{
  filter: brightness(1.2);
  transform: scaleY(1.05);
}}

.chart-bar.positive {{ background: linear-gradient(180deg, var(--green), rgba(16, 185, 129, 0.6)); }}
.chart-bar.negative {{ background: linear-gradient(180deg, var(--red), rgba(239, 68, 68, 0.6)); }}
.chart-bar.best {{
  background: linear-gradient(180deg, var(--gold), rgba(245, 158, 11, 0.6));
  box-shadow: 0 0 20px var(--gold-soft);
}}

.chart-bar-tooltip {{
  position: absolute;
  bottom: 100%;
  left: 50%;
  transform: translateX(-50%);
  background: var(--bg-dark);
  color: var(--text-white);
  padding: 0.4rem 0.6rem;
  border-radius: 6px;
  font-size: 0.7rem;
  font-weight: 600;
  white-space: nowrap;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.2s;
  z-index: 10;
}}

.chart-bar:hover .chart-bar-tooltip {{ opacity: 1; }}

.chart-labels {{
  display: flex;
  justify-content: space-between;
  padding: 0.5rem 0.5rem 0;
  gap: 4px;
}}

.chart-label {{
  flex: 1;
  text-align: center;
  font-size: 0.6rem;
  color: var(--text-muted);
  min-width: 20px;
  max-width: 60px;
}}

.chart-legend {{
  display: flex;
  justify-content: center;
  gap: 1.5rem;
  margin-top: 1rem;
}}

.legend-item {{
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.7rem;
  color: var(--text-gray);
}}

.legend-dot {{ width: 10px; height: 10px; border-radius: 3px; }}
.legend-dot.green {{ background: var(--green); }}
.legend-dot.red {{ background: var(--red); }}
.legend-dot.gold {{ background: var(--gold); }}

.chart-total {{
  text-align: center;
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
  font-size: 0.85rem;
  color: var(--text-gray);
}}

.chart-total strong {{ color: var(--green); }}

.alert-glow {{
  border: 1px solid var(--gold);
  box-shadow: 0 0 30px var(--gold-soft);
}}

.command-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 0.75rem;
}}

.command-item {{
  display: flex;
  gap: 0.75rem;
  padding: 1rem;
  transition: transform 0.3s ease;
}}

.command-item:hover {{ transform: translateX(4px); }}

.command-icon {{ font-size: 1.5rem; flex-shrink: 0; }}
.command-content {{ flex: 1; }}

.command-label {{
  display: block;
  font-size: 0.65rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 0.3rem;
}}

.command-item.success .command-label {{ color: var(--green); }}
.command-item.scheduled .command-label {{ color: var(--blue); }}
.command-item.important .command-label {{ color: var(--gold); }}
.command-item.urgent .command-label {{ color: var(--red); }}
.command-item.info .command-label {{ color: var(--purple); }}

.command-item.success {{ border-left: 3px solid var(--green); }}
.command-item.scheduled {{ border-left: 3px solid var(--blue); }}
.command-item.important {{ border-left: 3px solid var(--gold); }}
.command-item.urgent {{ border-left: 3px solid var(--red); }}
.command-item.info {{ border-left: 3px solid var(--purple); }}

.command-content p {{ font-size: 0.85rem; color: var(--text-gray); line-height: 1.4; }}

.meetings-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 0.75rem;
}}

.meeting-card {{
  padding: 1rem;
  display: flex;
  gap: 1rem;
  transition: transform 0.3s ease;
}}

.meeting-card:hover {{ transform: translateY(-4px); }}

.meeting-card.highlight-card {{
  border: 2px solid var(--gold);
  background: linear-gradient(135deg, var(--gold-soft) 0%, transparent 100%);
}}

.meeting-time {{
  font-size: 0.9rem;
  font-weight: 700;
  color: var(--blue);
  min-width: 70px;
}}

.meeting-time.gold {{ color: var(--gold); }}
.meeting-time.purple {{ color: var(--purple); }}

.meeting-info h4 {{ font-size: 0.95rem; margin-bottom: 0.3rem; }}
.meeting-info p {{ font-size: 0.75rem; color: var(--text-gray); margin-bottom: 0.2rem; }}
.meeting-type {{ font-size: 0.7rem; color: var(--text-muted); }}
.meeting-type.gold {{ color: var(--gold); }}
.meeting-source {{ font-size: 0.65rem; color: var(--text-muted); font-style: italic; }}

.zoom-btn {{
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  margin-top: 0.5rem;
  padding: 0.5rem 1rem;
  background: linear-gradient(135deg, #2563eb, #3b82f6);
  color: white;
  text-decoration: none;
  border-radius: 8px;
  font-size: 0.75rem;
  font-weight: 600;
  transition: all 0.3s ease;
}}

.zoom-btn:hover {{
  transform: scale(1.05);
  box-shadow: 0 4px 15px rgba(59, 130, 246, 0.4);
}}

.zoom-icon {{ font-size: 1rem; }}

.pipeline-cards {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 0.75rem;
}}

.pipeline-card {{
  padding: 1rem;
  transition: transform 0.3s ease;
}}

.pipeline-card:hover {{ transform: translateY(-4px); }}

.pipeline-status {{
  font-size: 0.65rem;
  font-weight: 700;
  text-transform: uppercase;
  margin-bottom: 0.5rem;
}}

.pipeline-card.approved .pipeline-status {{ color: var(--green); }}
.pipeline-card.pending .pipeline-status {{ color: var(--blue); }}
.pipeline-card.urgent .pipeline-status {{ color: var(--gold); }}
.pipeline-card.new-prospect .pipeline-status {{ color: var(--purple); }}
.pipeline-card.warning-card .pipeline-status {{ color: var(--red); }}

.pipeline-card.approved {{ border-left: 3px solid var(--green); }}
.pipeline-card.pending {{ border-left: 3px solid var(--blue); }}
.pipeline-card.urgent {{ border-left: 3px solid var(--gold); }}
.pipeline-card.new-prospect {{ border-left: 3px solid var(--purple); }}
.pipeline-card.warning-card {{ border-left: 3px solid var(--red); }}

.pipeline-card h4 {{ font-size: 1rem; margin-bottom: 0.5rem; }}

.pipeline-details {{
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  font-size: 0.75rem;
  color: var(--text-gray);
  margin-bottom: 0.5rem;
}}

.pipeline-details .highlight {{ color: var(--gold); font-weight: 600; }}

.pipeline-action {{
  font-size: 0.75rem;
  font-weight: 600;
  padding: 0.3rem 0.5rem;
  border-radius: 4px;
  display: inline-block;
}}

.pipeline-action.success {{ background: var(--green-soft); color: var(--green); }}
.pipeline-action.warning {{ background: var(--gold-soft); color: var(--gold); }}
.pipeline-action.info {{ background: var(--blue-soft); color: var(--blue); }}

.contacts-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 0.75rem;
}}

.contact-card {{
  padding: 1rem;
  transition: transform 0.3s ease;
}}

.contact-card:hover {{ transform: translateY(-4px); }}

.contact-card h4 {{ font-size: 0.95rem; margin-bottom: 0.75rem; }}
.contact-card h4.green {{ color: var(--green); }}
.contact-card h4.blue {{ color: var(--blue); }}
.contact-card h4.gold {{ color: var(--gold); }}
.contact-card h4.purple {{ color: var(--purple); }}

.contact-row {{ margin-bottom: 0.4rem; }}

.contact-link {{
  color: var(--text-gray);
  text-decoration: none;
  font-size: 0.8rem;
  transition: color 0.2s;
  display: block;
  padding: 0.3rem 0;
}}

.contact-link:hover {{ color: var(--blue); }}

.contact-status {{
  display: inline-block;
  margin-top: 0.5rem;
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  font-size: 0.65rem;
  font-weight: 700;
  text-transform: uppercase;
}}

.contact-status.success {{ background: var(--green-soft); color: var(--green); }}
.contact-status.warning {{ background: var(--gold-soft); color: var(--gold); }}
.contact-status.scheduled {{ background: var(--gold-soft); color: var(--gold); }}
.contact-status.info {{ background: var(--blue-soft); color: var(--blue); }}
.contact-status.partner {{ background: var(--purple-soft); color: var(--purple); }}

.footer {{
  text-align: center;
  padding: 1.5rem;
  margin-top: 1rem;
}}

.footer p {{
  font-size: 0.75rem;
  color: var(--text-muted);
  margin: 0.2rem 0;
}}

.green {{ color: var(--green) !important; }}
.blue {{ color: var(--blue) !important; }}
.gold {{ color: var(--gold) !important; }}
.red {{ color: var(--red) !important; }}
.purple {{ color: var(--purple) !important; }}
.highlight {{ color: var(--gold); font-weight: 600; }}

@media (max-width: 640px) {{
  .container {{ padding: 0.75rem; }}
  .header {{ padding: 1rem; }}
  .goal-section {{ flex-direction: column; text-align: center; }}
  .chart-bars {{ height: 150px; }}
  .chart-label {{ font-size: 0.5rem; }}
  .command-grid, .meetings-grid, .pipeline-cards, .contacts-grid {{ grid-template-columns: 1fr; }}
  .wins-section .celebrate {{ flex-direction: column; text-align: center; }}
  .meeting-card {{ flex-direction: column; gap: 0.5rem; }}
}}

@media (min-width: 1024px) {{
  .container {{ padding: 1.5rem; }}
  .financial-grid {{ grid-template-columns: repeat(6, 1fr); }}
  .command-grid {{ grid-template-columns: repeat(3, 1fr); }}
}}
    </style>
</head>
<body>
<div class="parallax-bg"></div>
<div id="confetti-container"></div>

<div class="container">
  <!-- HEADER -->
  <header class="header glass">
    <div class="header-content">
      <div class="header-left">
        <h1 class="gradient-text">WISE Financial Partners</h1>
        <p class="greeting" id="greeting">Good morning, Glenn!</p>
        <p class="subtitle">SA 99MCG | <span id="current-date">{current_date}</span></p>
        <p class="subtitle" style="margin-top: 0.25rem;">Last Sync: {last_sync_str}</p>
      </div>
      <div class="header-right">
        <div class="live-badge">
          <span class="live-dot"></span>
          LIVE
        </div>
        <div class="clock" id="clock">12:00 PM</div>
      </div>
    </div>

    <!-- Goal Progress Ring -->
    <div class="goal-section">
      <div class="goal-ring-container">
        <svg class="goal-ring" viewBox="0 0 120 120">
          <circle class="goal-ring-bg" cx="60" cy="60" r="52"/>
          <circle class="goal-ring-progress" cx="60" cy="60" r="52" id="goal-progress"/>
        </svg>
        <div class="goal-ring-text">
          <span class="goal-amount" id="goal-amount">${current_month_revenue:,.0f}</span>
          <span class="goal-label">of ${monthly_goal:,}</span>
        </div>
      </div>
      <div class="goal-info">
        <h3>December Goal</h3>
        <p class="goal-percent" id="goal-percent">{goal_percentage:.1f}% achieved</p>
        <p class="goal-remaining">${goal_remaining:,.0f} to go</p>
      </div>
    </div>

    <!-- Navigation -->
    <nav class="top-nav">
      <a href="#financial">💰 Financial</a>
      <a href="#cashflow">📊 Cash Flow</a>
      <a href="#command">🎯 Command</a>
      <a href="#pipeline">📋 Pipeline</a>
      <a href="#meetings">📅 Meetings</a>
      <a href="#contacts">📇 Contacts</a>
    </nav>
  </header>

  <!-- WINS CELEBRATION -->
  <section id="wins" class="wins-section">
    <div class="section-shell glass celebrate" onclick="triggerConfetti()">
      <div class="win-icon">🎉</div>
      <div class="win-content">
        <h3>CELEBRATE YOUR WINS!</h3>
        <div class="win-items">
          <span class="win-badge">✅ {approved_count} Approved Applications!</span>
          <span class="win-badge">💰 {format_currency(pending_commission)} Pending</span>
          <span class="win-badge">📋 {format_currency_short(total_pipeline_face)} Pipeline</span>
        </div>
        <p class="win-hint">Tap to celebrate! 🎊</p>
      </div>
    </div>
  </section>

  <!-- FINANCIAL OVERVIEW -->
  <section id="financial">
    <div class="section-shell glass">
      <h2 class="section-title"><span class="emoji">💰</span> Financial Overview</h2>
      <div class="financial-grid">
        <div class="stat-card glass-dark">
          <span class="stat-label">YTD Cash Flow</span>
          <span class="stat-value green">{format_currency(total_ytd)}</span>
          <span class="stat-sub">Dec '24 - Nov '25</span>
        </div>
        <div class="stat-card glass-dark">
          <span class="stat-label">Monthly Avg</span>
          <span class="stat-value">{format_currency(monthly_avg)}</span>
          <span class="stat-sub">12 months</span>
        </div>
        <div class="stat-card glass-dark">
          <span class="stat-label">Best Month</span>
          <span class="stat-value green">{format_currency(best_month_amount)}</span>
          <span class="stat-sub">Sep 2025 🏆</span>
        </div>
        <div class="stat-card glass-dark">
          <span class="stat-label">Pending</span>
          <span class="stat-value gold">{format_currency(pending_commission)}</span>
          <span class="stat-sub">Ready for delivery</span>
        </div>
        <div class="stat-card glass-dark">
          <span class="stat-label">Pipeline</span>
          <span class="stat-value blue">{format_currency_short(total_pipeline_face)}</span>
          <span class="stat-sub">Total face value</span>
        </div>
        <div class="stat-card glass-dark">
          <span class="stat-label">Approved</span>
          <span class="stat-value green">{approved_count}</span>
          <span class="stat-sub">Ready for delivery</span>
        </div>
      </div>
    </div>
  </section>

  <!-- CASH FLOW CHART -->
  <section id="cashflow">
    <div class="section-shell glass">
      <h2 class="section-title"><span class="emoji">📊</span> Cash Flow - Monthly Breakdown</h2>
      <div class="chart-container">
        <div class="chart-bars" id="chart-bars"></div>
        <div class="chart-labels" id="chart-labels"></div>
      </div>
      <div class="chart-legend">
        <span class="legend-item"><span class="legend-dot green"></span> Positive</span>
        <span class="legend-item"><span class="legend-dot red"></span> Negative</span>
        <span class="legend-item"><span class="legend-dot gold"></span> Best Month</span>
      </div>
      <div class="chart-total">
        Total: <strong>{format_currency(total_ytd)}</strong> | Avg: <strong>{format_currency(monthly_avg)}/mo</strong>
      </div>
    </div>
  </section>

  <!-- COMMAND CENTER -->
  <section id="command">
    <div class="section-shell glass alert-glow">
      <h2 class="section-title gold"><span class="emoji">🎯</span> Today's Command Center</h2>
      <div class="command-grid">
        {command_html}
      </div>
    </div>
  </section>

  <!-- TODAY'S MEETINGS -->
  <section id="meetings">
    <div class="section-shell glass">
      <h2 class="section-title purple"><span class="emoji">📅</span> Today's Meetings</h2>
      <div class="meetings-grid">
        {meetings_html}
      </div>
    </div>
  </section>

  <!-- PIPELINE -->
  <section id="pipeline">
    <div class="section-shell glass">
      <h2 class="section-title"><span class="emoji">📋</span> Pipeline</h2>
      <div class="pipeline-cards">
        {pipeline_html}
      </div>
    </div>
  </section>

  <!-- CONTACTS -->
  <section id="contacts">
    <div class="section-shell glass">
      <h2 class="section-title"><span class="emoji">📇</span> Quick Contacts</h2>
      <div class="contacts-grid">
        {contacts_html}
      </div>
    </div>
  </section>

  <!-- FOOTER -->
  <footer class="footer glass">
    <p>WISE Financial Partners | Glenn E. Windom II</p>
    <p>Last Sync: {last_sync_str}</p>
  </footer>
</div>

<script>
const cashFlowData = {cash_flow_json};

document.addEventListener('DOMContentLoaded', () => {{
  updateClock();
  updateGreeting();
  initCashFlowChart();
  initGoalRing();
  setInterval(updateClock, 1000);
  setInterval(updateGreeting, 60000);
  setTimeout(() => {{ triggerConfetti(); }}, 1500);
}});

function updateClock() {{
  const now = new Date();
  const options = {{ hour: 'numeric', minute: '2-digit', hour12: true }};
  const timeString = now.toLocaleTimeString('en-US', options);
  const clockEl = document.getElementById('clock');
  if (clockEl) clockEl.textContent = timeString;

  const dateOptions = {{ weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' }};
  const dateString = now.toLocaleDateString('en-US', dateOptions);
  const dateEl = document.getElementById('current-date');
  if (dateEl) dateEl.textContent = dateString;
}}

function updateGreeting() {{
  const hour = new Date().getHours();
  let greeting = '', emoji = '';
  if (hour >= 5 && hour < 12) {{ greeting = 'Good morning'; emoji = '☀️'; }}
  else if (hour >= 12 && hour < 17) {{ greeting = 'Good afternoon'; emoji = '🌤️'; }}
  else if (hour >= 17 && hour < 21) {{ greeting = 'Good evening'; emoji = '🌅'; }}
  else {{ greeting = 'Working late'; emoji = '🌙'; }}
  const greetingEl = document.getElementById('greeting');
  if (greetingEl) greetingEl.textContent = `${{greeting}}, Glenn! ${{emoji}}`;
}}

function initCashFlowChart() {{
  const barsContainer = document.getElementById('chart-bars');
  const labelsContainer = document.getElementById('chart-labels');
  if (!barsContainer || !labelsContainer) return;

  const maxAmount = Math.max(...cashFlowData.map(d => Math.abs(d.amount)));
  const bestMonth = Math.max(...cashFlowData.map(d => d.amount));

  barsContainer.innerHTML = '';
  labelsContainer.innerHTML = '';

  cashFlowData.forEach((data, index) => {{
    const bar = document.createElement('div');
    bar.className = 'chart-bar';
    if (data.amount === bestMonth) bar.classList.add('best');
    else if (data.amount < 0) bar.classList.add('negative');
    else bar.classList.add('positive');

    const heightPercent = Math.max(5, (Math.abs(data.amount) / maxAmount) * 100);
    bar.style.height = `${{heightPercent}}%`;
    bar.style.animationDelay = `${{index * 0.08}}s`;

    const tooltip = document.createElement('div');
    tooltip.className = 'chart-bar-tooltip';
    const sign = data.amount < 0 ? '-' : '';
    tooltip.textContent = `${{data.month}} '${{data.year}}: ${{sign}}$${{Math.abs(data.amount).toLocaleString()}}`;
    bar.appendChild(tooltip);
    barsContainer.appendChild(bar);

    const label = document.createElement('div');
    label.className = 'chart-label';
    label.textContent = data.month;
    labelsContainer.appendChild(label);
  }});
}}

function initGoalRing() {{
  const currentAmount = {current_month_revenue};
  const monthlyGoal = {monthly_goal};
  const percentage = (currentAmount / monthlyGoal) * 100;
  const progressRing = document.getElementById('goal-progress');
  if (progressRing) {{
    const circumference = 327;
    const offset = circumference - (percentage / 100) * circumference;
    setTimeout(() => {{ progressRing.style.strokeDashoffset = offset; }}, 500);
  }}
}}

function triggerConfetti() {{
  const container = document.getElementById('confetti-container');
  if (!container) return;
  const colors = ['#10b981', '#f59e0b', '#3b82f6', '#8b5cf6', '#ef4444', '#ec4899', '#14b8a6', '#ffffff'];
  const shapes = ['square', 'circle', 'triangle'];

  for (let i = 0; i < 150; i++) {{
    const confetti = document.createElement('div');
    confetti.className = 'confetti';
    const color = colors[Math.floor(Math.random() * colors.length)];
    const shape = shapes[Math.floor(Math.random() * shapes.length)];
    const size = Math.random() * 10 + 5;
    const left = Math.random() * 100;
    const delay = Math.random() * 0.5;
    const duration = Math.random() * 2 + 2;

    confetti.style.width = `${{size}}px`;
    confetti.style.height = `${{size}}px`;
    confetti.style.backgroundColor = color;
    confetti.style.left = `${{left}}%`;
    confetti.style.top = '-20px';
    confetti.style.animationDelay = `${{delay}}s`;
    confetti.style.animationDuration = `${{duration}}s`;

    if (shape === 'circle') confetti.style.borderRadius = '50%';
    else if (shape === 'triangle') {{
      confetti.style.width = '0';
      confetti.style.height = '0';
      confetti.style.backgroundColor = 'transparent';
      confetti.style.borderLeft = `${{size/2}}px solid transparent`;
      confetti.style.borderRight = `${{size/2}}px solid transparent`;
      confetti.style.borderBottom = `${{size}}px solid ${{color}}`;
    }}

    container.appendChild(confetti);
    setTimeout(() => {{ confetti.remove(); }}, (delay + duration) * 1000);
  }}
}}

let ticking = false;
window.addEventListener('scroll', () => {{
  if (!ticking) {{
    requestAnimationFrame(() => {{
      const scrolled = window.pageYOffset;
      const parallaxBg = document.querySelector('.parallax-bg');
      if (parallaxBg) parallaxBg.style.transform = `translateY(${{scrolled * 0.3}}px)`;
      ticking = false;
    }});
    ticking = true;
  }}
}});

document.querySelectorAll('.top-nav a').forEach(anchor => {{
  anchor.addEventListener('click', function(e) {{
    e.preventDefault();
    const targetId = this.getAttribute('href');
    const targetEl = document.querySelector(targetId);
    if (targetEl) {{
      const headerOffset = 100;
      const elementPosition = targetEl.getBoundingClientRect().top;
      const offsetPosition = elementPosition + window.pageYOffset - headerOffset;
      window.scrollTo({{ top: offsetPosition, behavior: 'smooth' }});
    }}
  }});
}});

const observerOptions = {{ threshold: 0.1, rootMargin: '0px 0px -50px 0px' }};
const observer = new IntersectionObserver((entries) => {{
  entries.forEach(entry => {{
    if (entry.isIntersecting) {{
      entry.target.style.opacity = '1';
      entry.target.style.transform = 'translateY(0)';
    }}
  }});
}}, observerOptions);

document.querySelectorAll('section').forEach(section => {{
  section.style.opacity = '0';
  section.style.transform = 'translateY(20px)';
  section.style.transition = 'all 0.6s ease-out';
  observer.observe(section);
}});

const winsSection = document.getElementById('wins');
if (winsSection) {{
  winsSection.style.opacity = '1';
  winsSection.style.transform = 'translateY(0)';
}}

console.log('%c WISE Financial Partners ', 'background: linear-gradient(135deg, #3b82f6, #8b5cf6); color: white; font-size: 20px; padding: 10px 20px; border-radius: 8px; font-weight: bold;');
console.log('%c Dashboard Loaded Successfully ✨', 'color: #10b981; font-size: 14px;');
</script>
</body>
</html>'''

        return html

    except Exception as e:
        print(f"Error generating dashboard: {e}")
        import traceback
        traceback.print_exc()
        return f"<html><body><h1>Error generating dashboard</h1><pre>{e}</pre></body></html>"

    finally:
        if close_session:
            session.close()
