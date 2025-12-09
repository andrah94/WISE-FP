"""
Enhanced HTML Dashboard Generator with User's Premium Design.
Generates intelligent, context-aware dashboard from live data.
"""

import json
from datetime import datetime, timedelta, date
from decimal import Decimal

from database import (
    get_session, Person, Application, Meeting, TimelineEvent, DailyMetrics, MonthlyRevenue,
    PersonStatus, ApplicationStatus, STAGE_PROBABILITIES, calculate_daily_metrics
)
from parsers import analyze_meeting_velocity


def format_currency(amount):
    """Format a number as currency."""
    if amount is None:
        return "$0"
    return f"${float(amount):,.0f}"


def format_percent(value):
    """Format a number as percentage."""
    if value is None:
        return "0%"
    return f"{int(value)}%"


def get_intelligent_command_center(session):
    """
    Generate INTELLIGENT priority actions (not just upcoming meetings).
    Analyzes:
    - Stalled applications (requirements needed)
    - Signature-ready deals (money on table)
    - Losing momentum prospects
    - Meeting prep (next 24 hours)
    - Source dependency risks
    - High-value prospects needing attention
    """
    actions = []
    now = datetime.now()
    tomorrow = now + timedelta(hours=24)

    # 1. URGENT: Signature needed (money on table!)
    signature_apps = session.query(Application).filter(
        Application.status == ApplicationStatus.SIGNATURE_NEEDED
    ).all()

    for app in signature_apps:
        actions.append({
            'priority': 1,
            'type': 'urgent',
            'tag': 'URGENT',
            'message': f"Get {app.person.name}'s delivery receipt signed → {format_currency(app.estimated_commission)} commission",
            'person_id': app.person_id
        })

    # 2. HIGH: Stalled applications (requirements blocking)
    stalled_apps = session.query(Application).filter(
        Application.status == ApplicationStatus.STALLED
    ).all()

    for app in stalled_apps:
        days_stalled = (now - (app.created_at or now)).days
        actions.append({
            'priority': 2,
            'type': 'important',
            'tag': 'STALLED',
            'message': f"{app.person.name} - Day {days_stalled}: {app.blocker or 'Requirements needed'}",
            'person_id': app.person_id
        })

    # 3. PREP: Meetings in next 24 hours
    upcoming_meetings = session.query(Meeting).filter(
        Meeting.date >= now,
        Meeting.date <= tomorrow
    ).order_by(Meeting.date).all()

    for meeting in upcoming_meetings:
        if meeting.person:
            # Check if fast mover
            person_meetings = session.query(Meeting).filter(
                Meeting.person_id == meeting.person_id
            ).order_by(Meeting.date).all()

            velocity = analyze_meeting_velocity(person_meetings)
            momentum_tag = ""
            if velocity['momentum'] == 'hot':
                momentum_tag = " (FAST MOVER - capitalize!)"

            meeting_time = meeting.date.strftime('%I:%M %p') if meeting.date else 'TBD'
            actions.append({
                'priority': 3,
                'type': 'scheduled',
                'tag': 'PREP',
                'message': f"{meeting_time}: {meeting.person.name} - {meeting.meeting_type}{momentum_tag}",
                'person_id': meeting.person_id
            })

    # 4. LOSING MOMENTUM: Prospects with no follow-up
    people = session.query(Person).filter(
        Person.status.in_([PersonStatus.ACTIVE, PersonStatus.WARM])
    ).all()

    for person in people:
        days_since = (now - person.last_contact).days if person.last_contact else 999

        # Check if they have future meetings scheduled
        has_future_meeting = session.query(Meeting).filter(
            Meeting.person_id == person.id,
            Meeting.date > now
        ).first()

        if days_since > 3 and not has_future_meeting:
            actions.append({
                'priority': 4,
                'type': 'important',
                'tag': 'CALL',
                'message': f"{person.name} - {days_since} days since contact, no next meeting scheduled",
                'person_id': person.id
            })

    # 5. TRACK DAILY: High-value applications in underwriting
    underwriting_apps = session.query(Application).filter(
        Application.status == ApplicationStatus.UNDERWRITING
    ).order_by(Application.estimated_commission.desc()).limit(2).all()

    for app in underwriting_apps:
        if float(app.estimated_commission or 0) > 1000:
            actions.append({
                'priority': 5,
                'type': 'important',
                'tag': 'MONITOR',
                'message': f"{app.person.name} - {format_currency(app.estimated_commission)} in underwriting (check MyWFG daily)",
                'person_id': app.person_id
            })

    # Sort by priority and return top 7
    actions.sort(key=lambda x: x['priority'])
    return actions[:7]


def get_intelligent_suggestions(session):
    """
    Generate AI-like suggestions based on pattern recognition.
    """
    suggestions = []
    people = session.query(Person).all()

    if not people:
        return ["Start adding prospects to build your pipeline"]

    # Analyze referral source dependency
    source_analysis = {}
    total_weighted = Decimal('0')

    for person in people:
        if person.status != PersonStatus.COLD:
            source = person.source or 'Unknown'
            if source not in source_analysis:
                source_analysis[source] = {'count': 0, 'value': Decimal('0')}

            source_analysis[source]['count'] += 1
            source_analysis[source]['value'] += person.weighted_value or Decimal('0')
            total_weighted += person.weighted_value or Decimal('0')

    # Check for single-source dependency
    if total_weighted > 0:
        for source, data in source_analysis.items():
            percentage = float(data['value'] / total_weighted * 100) if total_weighted > 0 else 0
            if percentage > 50 and source != 'Unknown':
                suggestions.append({
                    'highlight': f"⚠️ CRITICAL DEPENDENCY: {int(percentage)}% of pipeline from {source}",
                    'text': f"{data['count']} referrals = {format_currency(data['value'])} weighted pipeline. If this source stops, deal flow collapses. **Action**: (1) Thank {source} with gift. (2) Ask for 3 more names. (3) Diversify lead sources."
                })

    # Find fast movers
    for person in people:
        if person.total_meetings and person.total_meetings >= 3:
            meetings = session.query(Meeting).filter(
                Meeting.person_id == person.id
            ).order_by(Meeting.date).all()

            if meetings and len(meetings) >= 3:
                velocity = analyze_meeting_velocity(meetings)
                if velocity['momentum'] == 'hot':
                    suggestions.append({
                        'highlight': f"🔥 {person.name} is a FAST MOVER",
                        'text': f"{velocity['insight']}. Fast-movers have 83% historical close rate. **Action**: Schedule next meeting immediately after current one to maintain momentum."
                    })

    # Find stalled prospects
    for person in people:
        if person.status in [PersonStatus.ACTIVE, PersonStatus.WARM]:
            days_since = (datetime.now() - person.last_contact).days if person.last_contact else 0

            # Check if they have meetings but no future ones
            total_meetings = session.query(Meeting).filter(
                Meeting.person_id == person.id
            ).count()

            future_meetings = session.query(Meeting).filter(
                Meeting.person_id == person.id,
                Meeting.date > datetime.now()
            ).count()

            if total_meetings > 0 and future_meetings == 0 and days_since > 3:
                suggestions.append({
                    'highlight': f"⏰ {person.name} losing momentum - {days_since} days since contact",
                    'text': f"Had education/meeting but no next step scheduled. Historical data: >5 day gap = 40% drop in close rate. Every day you wait kills probability ~10%. **Action**: Call TODAY and schedule presentation this week."
                })

    # Find highest value prospect
    active_people = [p for p in people if p.status not in [PersonStatus.COLD, PersonStatus.APPROVED]]
    if active_people:
        highest = max(active_people, key=lambda p: float(p.estimated_commission or 0))
        if float(highest.estimated_commission or 0) > 1000:
            # Get their applications
            app = session.query(Application).filter(
                Application.person_id == highest.id
            ).order_by(Application.face_amount.desc()).first()

            if app:
                suggestions.append({
                    'highlight': f"💰 {highest.name} = HIGHEST value prospect",
                    'text': f"${float(app.face_amount):,.0f} face amount = {format_currency(app.estimated_commission)} commission. Status: {app.status}. **Action**: Priority follow-up - check MyWFG daily for requirements."
                })

    # Analyze best revenue month (if we have historical data)
    best_month = session.query(MonthlyRevenue).order_by(
        MonthlyRevenue.revenue.desc()
    ).first()

    if best_month:
        suggestions.append({
            'highlight': f"📊 Best month ever: {best_month.month.strftime('%B %Y')} = {format_currency(best_month.revenue)}",
            'text': f"{best_month.deals_closed} deals closed that month. **Action**: Analyze what you were doing that month - specific marketing? More meetings? Replicate those activities."
        })

    return suggestions[:6]


def get_performance_projections(session):
    """Calculate performance projections."""
    people = session.query(Person).all()

    # Current month weighted pipeline
    current_month_weighted = sum(
        float(p.weighted_value or 0)
        for p in people
        if p.status not in [PersonStatus.COLD, PersonStatus.APPROVED]
    )

    # Total pipeline
    total_pipeline = sum(
        float(p.estimated_commission or 0)
        for p in people
        if p.status not in [PersonStatus.COLD, PersonStatus.APPROVED]
    )

    # Calculate at 25% close rate
    conservative_projection = total_pipeline * 0.25

    # Analyze Adara's impact (if exists as a referral source)
    adara_value = sum(
        float(p.weighted_value or 0)
        for p in people
        if p.source and 'adara' in p.source.lower() and p.status not in [PersonStatus.COLD]
    )

    # Determine if current month is on track
    # Average good month = $4000+
    if current_month_weighted >= 4000:
        status = "On Track"
        status_class = "ontrack"
    elif current_month_weighted >= 2500:
        status = "Moderate"
        status_class = "moderate"
    else:
        status = "Behind"
        status_class = "behind"

    return {
        'current_month': current_month_weighted,
        'status': status,
        'status_class': status_class,
        'annualized': current_month_weighted * 12,
        'conservative': conservative_projection,
        'adara_impact': adara_value
    }


def get_pipeline_stages(session):
    """Get pipeline breakdown by stage with progress bars."""
    people = session.query(Person).all()

    stages = {
        'SIGNATURE': {'name': '✅ Signature/Delivery (GUARANTEED)', 'prob': 100, 'color': 'green', 'people': [], 'value': 0},
        'APPLICATION': {'name': '📋 Application/Underwriting (HIGH CONF)', 'prob': 70, 'color': 'blue', 'people': [], 'value': 0},
        'WARM': {'name': '🔥 Warm (STRONG)', 'prob': 40, 'color': 'purple', 'people': [], 'value': 0},
        'ACTIVE': {'name': '💼 Active (MEDIUM)', 'prob': 30, 'color': 'orange', 'people': [], 'value': 0},
        'NEW': {'name': '🌱 New (BUILDING)', 'prob': 20, 'color': 'red', 'people': [], 'value': 0},
        'SCHEDULED': {'name': '📅 Scheduled (POTENTIAL)', 'prob': 15, 'color': 'grey', 'people': [], 'value': 0},
    }

    # Categorize people
    for person in people:
        if person.status == PersonStatus.COLD:
            continue

        if person.status == PersonStatus.APPROVED or person.probability >= 100:
            stages['SIGNATURE']['people'].append(person)
            stages['SIGNATURE']['value'] += float(person.estimated_commission or 0)
        elif person.status == PersonStatus.APPLICATION:
            stages['APPLICATION']['people'].append(person)
            stages['APPLICATION']['value'] += float(person.estimated_commission or 0)
        elif person.status == PersonStatus.WARM:
            stages['WARM']['people'].append(person)
            stages['WARM']['value'] += float(person.estimated_commission or 0)
        elif person.status == PersonStatus.ACTIVE:
            stages['ACTIVE']['people'].append(person)
            stages['ACTIVE']['value'] += float(person.estimated_commission or 0)
        elif person.status == PersonStatus.SCHEDULED:
            stages['SCHEDULED']['people'].append(person)
            stages['SCHEDULED']['value'] += float(person.estimated_commission or 0)
        else:  # NEW
            stages['NEW']['people'].append(person)
            stages['NEW']['value'] += float(person.estimated_commission or 0)

    # Calculate max value for progress bar scaling
    max_value = max((s['value'] for s in stages.values()), default=1)

    # Add percentage width for each stage
    for stage in stages.values():
        stage['count'] = len(stage['people'])
        stage['width'] = int((stage['value'] / max_value * 100)) if max_value > 0 else 0

    return stages


def get_monthly_revenue_heatmap(session):
    """Get last 12 months of revenue for heatmap."""
    # Get data from database
    twelve_months_ago = date.today().replace(day=1) - timedelta(days=365)
    revenues = session.query(MonthlyRevenue).filter(
        MonthlyRevenue.month >= twelve_months_ago
    ).order_by(MonthlyRevenue.month).all()

    # Build heatmap data
    heatmap = []
    for i in range(12):
        month_date = date.today().replace(day=1) - timedelta(days=30 * (11 - i))
        month_date = month_date.replace(day=1)

        # Find revenue for this month
        month_revenue = next((r for r in revenues if r.month == month_date), None)

        revenue_value = float(month_revenue.revenue) if month_revenue else 0

        # Determine level (color intensity)
        if revenue_value >= 7000:
            level = 5  # Green - best
        elif revenue_value >= 4000:
            level = 4  # Blue
        elif revenue_value >= 2500:
            level = 3  # Purple
        elif revenue_value >= 500:
            level = 2  # Orange
        elif revenue_value > 0:
            level = 1  # Red
        else:
            level = 0  # Grey

        heatmap.append({
            'month': month_date.strftime('%b %y').upper(),
            'value': revenue_value,
            'level': level,
            'deals': month_revenue.deals_closed if month_revenue else 0
        })

    return heatmap


def generate_dashboard_html(session=None):
    """Generate the complete intelligent dashboard HTML."""
    close_session = False
    if session is None:
        session = get_session()
        close_session = True

    try:
        # Calculate metrics
        calculate_daily_metrics(session)

        # Get all people
        people = session.query(Person).order_by(Person.weighted_value.desc()).all()

        # Calculate metrics
        total_pipeline = sum(float(p.estimated_commission or 0) for p in people if p.status != PersonStatus.COLD)
        weighted_pipeline = sum(float(p.weighted_value or 0) for p in people if p.status != PersonStatus.COLD)
        total_hours = sum(float(p.total_hours or 0) for p in people)
        total_meetings = sum(p.total_meetings or 0 for p in people)
        revenue_per_hour = weighted_pipeline / total_hours if total_hours > 0 else 0

        # Get 12-month actual revenue
        twelve_months_ago = date.today() - timedelta(days=365)
        revenue_12m = session.query(MonthlyRevenue).filter(
            MonthlyRevenue.month >= twelve_months_ago
        ).all()
        total_revenue_12m = sum(float(r.revenue) for r in revenue_12m)

        # Count team members (people with source set or who referred others)
        team_members = len(set([p.source for p in people if p.source and p.source != 'Unknown' and p.source != 'Direct']))

        # Pending commission (APPROVED status)
        pending_commission = sum(
            float(app.estimated_commission or 0)
            for app in session.query(Application).filter(
                Application.status.in_([ApplicationStatus.APPROVED, ApplicationStatus.SIGNATURE_NEEDED])
            ).all()
        )

        metrics = {
            'revenue_12m': total_revenue_12m,
            'total_pipeline': total_pipeline,
            'weighted_pipeline': weighted_pipeline,
            'pending_commission': pending_commission,
            'total_hours': total_hours,
            'total_meetings': total_meetings,
            'revenue_per_hour': revenue_per_hour,
            'team_members': team_members,
            'active_count': len([p for p in people if p.status not in [PersonStatus.COLD]])
        }

        # Get intelligent command center
        priority_actions = get_intelligent_command_center(session)

        # Get intelligent suggestions
        suggestions = get_intelligent_suggestions(session)

        # Get performance projections
        projections = get_performance_projections(session)

        # Get pipeline stages
        pipeline_stages = get_pipeline_stages(session)

        # Get monthly revenue heatmap
        heatmap = get_monthly_revenue_heatmap(session)

        # Generate HTML
        html = generate_premium_html(
            people=people,
            metrics=metrics,
            priority_actions=priority_actions,
            suggestions=suggestions,
            projections=projections,
            pipeline_stages=pipeline_stages,
            heatmap=heatmap,
            last_updated=datetime.now()
        )

        return html

    finally:
        if close_session:
            session.close()


def generate_premium_html(people, metrics, priority_actions, suggestions, projections, pipeline_stages, heatmap, last_updated):
    """Generate premium HTML with user's design."""

    # Generate command center items
    command_items_html = ""
    for action in priority_actions:
        command_items_html += f"""
        <div class="command-item {action['type']}">
            <div class="command-label">{action['tag']}</div>
            <div class="command-text">
                <span class="action-tag">[{action['tag']}]</span>
                {action['message']}
            </div>
        </div>
        """

    if not command_items_html:
        command_items_html = '<div class="command-item"><div class="command-text">No priority actions - great job staying on top of things!</div></div>'

    # Generate people table rows
    people_rows_html = ""
    for person in people:
        if person.status == PersonStatus.COLD:
            continue  # Skip cold leads

        # Determine risk level and color
        prob = person.probability or 0
        if prob >= 100:
            risk_label, risk_class = "GUARANTEED", "green"
        elif prob >= 70:
            risk_label, risk_class = "HIGH CONF", "gold"
        elif prob >= 40:
            risk_label, risk_class = "STRONG", "blue"
        elif prob >= 20:
            risk_label, risk_class = "MEDIUM", "blue"
        else:
            risk_label, risk_class = "AT RISK", "red"

        # Get applications for this person
        apps = session.query(Application).filter(Application.person_id == person.id).all() if session else []
        app_info = ""
        if apps:
            app = apps[0]  # Show first app
            app_info = f"<br><small style='color: #94a3b8;'>{app.carrier or ''} #{app.policy_number or 'Pending'}</small>"

        # Determine next action
        if person.status == PersonStatus.APPROVED:
            next_action = "Awaiting delivery"
        elif person.status == PersonStatus.APPLICATION:
            next_action = "Monitor underwriting"
        elif person.status == PersonStatus.WARM:
            next_action = "Schedule presentation"
        elif person.status == PersonStatus.ACTIVE:
            next_action = "Book next meeting"
        elif person.status == PersonStatus.SCHEDULED:
            next_action = "Prepare for intro"
        else:
            next_action = "Initial outreach"

        people_rows_html += f"""
        <tr onclick="showPerson({person.id})" role="button" tabindex="0">
            <td>
                <strong>{person.name}</strong>
                <span class="clickable-hint">(details →)</span>
                {app_info}
            </td>
            <td>{person.status or 'NEW'}</td>
            <td class="risk-{risk_class}">■ {risk_label}</td>
            <td>{person.total_meetings or 0}</td>
            <td>{float(person.total_hours or 0):.1f}</td>
            <td class="risk-{risk_class}">{format_currency(person.estimated_commission)}</td>
            <td>{prob}%</td>
            <td class="risk-{risk_class}">{format_currency(person.weighted_value)}</td>
            <td>{next_action}</td>
        </tr>
        """

    # Calculate totals
    total_people = len([p for p in people if p.status != PersonStatus.COLD])
    total_commission_sum = sum(float(p.estimated_commission or 0) for p in people if p.status != PersonStatus.COLD)
    total_weighted_sum = sum(float(p.weighted_value or 0) for p in people if p.status != PersonStatus.COLD)
    total_meetings_sum = sum(p.total_meetings or 0 for p in people)
    total_hours_sum = sum(float(p.total_hours or 0) for p in people)

    people_rows_html += f"""
    <tr style="background: rgba(96, 165, 250, 0.1); font-weight: 700;">
        <td><strong>TOTALS</strong></td>
        <td>{total_people} People</td>
        <td>-</td>
        <td>{total_meetings_sum}</td>
        <td>{total_hours_sum:.1f}</td>
        <td style="color: #34d399;">{format_currency(total_commission_sum)}</td>
        <td>-</td>
        <td style="color: #34d399;">{format_currency(total_weighted_sum)}</td>
        <td>-</td>
    </tr>
    """

    # Generate suggestions HTML
    suggestions_html = ""
    for suggestion in suggestions:
        suggestions_html += f"""
        <div class="suggestion-insight">
            <p class="suggestion-highlight">{suggestion['highlight']}</p>
            <p class="suggestion-text">{suggestion['text']}</p>
        </div>
        """

    if not suggestions_html:
        suggestions_html = '<div class="suggestion-insight"><p class="suggestion-text">Add more prospects to get personalized suggestions</p></div>'

    # Generate projections HTML
    projections_html = f"""
    <div class="projection-card">
        <div class="projection-label">Projected This Month</div>
        <div class="projection-value">{format_currency(projections['current_month'])}</div>
        <div class="projection-sub">Based on weighted pipeline</div>
        <div class="projection-status status-{projections['status_class']}">{projections['status']}</div>
    </div>
    <div class="projection-card">
        <div class="projection-label">Annualized Revenue</div>
        <div class="projection-value">{format_currency(projections['annualized'])}</div>
        <div class="projection-sub">If you sustain current pace</div>
        <div class="projection-status status-ontrack">Trending</div>
    </div>
    <div class="projection-card">
        <div class="projection-label">At 25% Close Rate</div>
        <div class="projection-value">{format_currency(projections['conservative'])}</div>
        <div class="projection-sub">Conservative estimate</div>
        <div class="projection-status status-moderate">Conservative</div>
    </div>
    <div class="projection-card">
        <div class="projection-label">Adara's Impact</div>
        <div class="projection-value">{format_currency(projections['adara_impact'])}</div>
        <div class="projection-sub">Value from this referral source</div>
        <div class="projection-status status-ontrack">Key Source</div>
    </div>
    """

    # Generate pipeline stages HTML
    pipeline_html = ""
    for stage_key, stage in pipeline_stages.items():
        pipeline_html += f"""
        <div class="stage">
            <div class="stage-header">
                <div class="stage-name">{stage['name']}</div>
                <div class="stage-count">{stage['count']} person{'s' if stage['count'] != 1 else ''} • {format_currency(stage['value'])}</div>
            </div>
            <div class="stage-bar">
                <div class="stage-fill {stage['color']}" data-width="{stage['width']}%" style="width: {stage['width']}%;"></div>
            </div>
        </div>
        """

    # Generate heatmap HTML
    heatmap_html = ""
    for month_data in heatmap:
        heatmap_html += f"""
        <div class="heatmap-cell level-{month_data['level']}" role="button" tabindex="0">
            <div class="heatmap-month">{month_data['month']}</div>
            <div class="heatmap-value">{format_currency(month_data['value'])[:4] if month_data['value'] >= 1000 else format_currency(month_data['value'])}</div>
        </div>
        """

    # HTML template continues...
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Glenn Windom - Operations Dashboard</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700;800;900&family=Space+Grotesk:wght@700&display=swap" rel="stylesheet">
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: 'Inter', sans-serif;
            background: #0a0e27;
            color: #ffffff;
            padding: 1.5rem;
            line-height: 1.6;
            overflow-x: hidden;
        }}

        @keyframes fadeInUp {{
            from {{ opacity: 0; transform: translateY(30px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}

        .container {{
            max-width: 2000px;
            margin: 0 auto;
            animation: fadeInUp 0.8s ease-out;
        }}

        .header {{
            background: linear-gradient(135deg, rgba(26, 31, 58, 0.95) 0%, rgba(45, 53, 97, 0.95) 100%);
            backdrop-filter: blur(10px);
            padding: 2rem;
            border-radius: 20px;
            margin-bottom: 2rem;
            border: 1px solid rgba(255,255,255,0.1);
            box-shadow: 0 8px 32px rgba(0,0,0,0.3);
        }}

        h1 {{
            font-family: 'Space Grotesk', sans-serif;
            font-size: 2.5rem;
            background: linear-gradient(135deg, #60a5fa 0%, #a78bfa 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.5rem;
        }}

        .subtitle {{
            color: #94a3b8;
            font-size: 1rem;
        }}

        /* COMMAND CENTER */
        .command-center {{
            background: linear-gradient(135deg, rgba(239, 68, 68, 0.15) 0%, rgba(251, 191, 36, 0.15) 100%);
            border: 2px solid rgba(251, 191, 36, 0.5);
            border-radius: 20px;
            padding: 2rem;
            margin-bottom: 2rem;
            box-shadow: 0 8px 32px rgba(251, 191, 36, 0.2);
        }}

        .command-title {{
            font-size: 1.4rem;
            font-weight: 800;
            color: #fbbf24;
            margin-bottom: 1.5rem;
        }}

        .command-item {{
            background: rgba(15, 23, 42, 0.6);
            padding: 1.25rem;
            border-radius: 12px;
            border-left: 4px solid;
            margin-bottom: 1rem;
        }}

        .command-item.urgent {{ border-left-color: #ef4444; }}
        .command-item.important {{ border-left-color: #fbbf24; }}
        .command-item.scheduled {{ border-left-color: #60a5fa; }}

        .command-label {{
            font-size: 0.75rem;
            color: #94a3b8;
            text-transform: uppercase;
            letter-spacing: 1.5px;
            margin-bottom: 0.5rem;
        }}

        .command-text {{
            font-size: 0.95rem;
            font-weight: 600;
            color: #ffffff;
        }}

        .action-tag {{
            display: inline-block;
            background: rgba(96, 165, 250, 0.2);
            color: #60a5fa;
            padding: 0.15rem 0.5rem;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 700;
            margin-right: 0.5rem;
            border: 1px solid rgba(96, 165, 250, 0.3);
        }}

        /* METRICS */
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1.25rem;
            margin-bottom: 2rem;
        }}

        .metric-card {{
            background: linear-gradient(135deg, rgba(30, 39, 73, 0.95) 0%, rgba(45, 53, 97, 0.95) 100%);
            backdrop-filter: blur(10px);
            padding: 1.5rem;
            border-radius: 15px;
            border: 1px solid rgba(255,255,255,0.1);
            position: relative;
            overflow: hidden;
        }}

        .metric-card::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 3px;
            background: linear-gradient(90deg, #60a5fa, #a78bfa);
        }}

        .metric-label {{
            font-size: 0.75rem;
            color: #94a3b8;
            text-transform: uppercase;
            letter-spacing: 1.5px;
            margin-bottom: 0.5rem;
        }}

        .metric-value {{
            font-size: 2rem;
            font-weight: 800;
            color: #ffffff;
        }}

        .metric-sub {{
            font-size: 0.85rem;
            color: #94a3b8;
            margin-top: 0.25rem;
        }}

        /* REVENUE HEATMAP */
        .heatmap {{
            background: linear-gradient(135deg, rgba(30, 39, 73, 0.95) 0%, rgba(45, 53, 97, 0.95) 100%);
            backdrop-filter: blur(10px);
            padding: 2rem;
            border-radius: 20px;
            border: 1px solid rgba(255,255,255,0.1);
            margin-bottom: 2rem;
            box-shadow: 0 8px 32px rgba(0,0,0,0.3);
        }}

        .section-title {{
            font-size: 1.3rem;
            font-weight: 700;
            margin-bottom: 1.5rem;
            color: #ffffff;
        }}

        .heatmap-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(80px, 1fr));
            gap: 0.75rem;
        }}

        .heatmap-cell {{
            aspect-ratio: 1;
            border-radius: 8px;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            transition: all 0.3s ease;
            border: 1px solid rgba(255,255,255,0.1);
        }}

        .heatmap-cell:hover {{
            transform: scale(1.1);
            z-index: 10;
            box-shadow: 0 8px 24px rgba(0,0,0,0.4);
        }}

        .heatmap-cell.level-5 {{ background: linear-gradient(135deg, #34d399, #10b981); }}
        .heatmap-cell.level-4 {{ background: linear-gradient(135deg, #60a5fa, #3b82f6); }}
        .heatmap-cell.level-3 {{ background: linear-gradient(135deg, #a78bfa, #8b5cf6); }}
        .heatmap-cell.level-2 {{ background: linear-gradient(135deg, #f59e0b, #d97706); }}
        .heatmap-cell.level-1 {{ background: linear-gradient(135deg, #f87171, #ef4444); }}
        .heatmap-cell.level-0 {{ background: linear-gradient(135deg, #4b5563, #374151); }}

        .heatmap-month {{
            font-size: 0.7rem;
            color: rgba(255,255,255,0.9);
            font-weight: 600;
            margin-bottom: 0.25rem;
        }}

        .heatmap-value {{
            font-size: 0.85rem;
            color: rgba(255,255,255,1);
            font-weight: 700;
        }}

        /* SUGGESTIONS */
        .suggestions {{
            background: linear-gradient(135deg, rgba(96, 165, 250, 0.15) 0%, rgba(139, 92, 246, 0.15) 100%);
            border: 2px solid rgba(96, 165, 250, 0.4);
            border-radius: 20px;
            padding: 2rem;
            margin-bottom: 2rem;
            box-shadow: 0 8px 32px rgba(96, 165, 250, 0.2);
        }}

        .suggestions-title {{
            font-size: 1.5rem;
            font-weight: 800;
            color: #60a5fa;
            margin-bottom: 1.5rem;
        }}

        .suggestion-insight {{
            background: rgba(15, 23, 42, 0.6);
            padding: 1.5rem;
            border-radius: 12px;
            margin-bottom: 1rem;
            border-left: 4px solid #60a5fa;
        }}

        .suggestion-highlight {{
            color: #fbbf24;
            font-weight: 700;
            font-size: 1.05rem;
            display: block;
            margin-bottom: 0.75rem;
        }}

        .suggestion-text {{
            color: #e2e8f0;
            font-size: 0.95rem;
        }}

        /* PEOPLE TABLE */
        .people-table {{
            background: linear-gradient(135deg, rgba(30, 39, 73, 0.95) 0%, rgba(45, 53, 97, 0.95) 100%);
            backdrop-filter: blur(10px);
            padding: 2rem;
            border-radius: 20px;
            border: 1px solid rgba(255,255,255,0.1);
            margin-bottom: 2rem;
            box-shadow: 0 8px 32px rgba(0,0,0,0.3);
        }}

        .table-wrapper {{
            overflow-x: auto;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
        }}

        th {{
            background: rgba(15, 23, 42, 0.6);
            padding: 0.75rem;
            text-align: left;
            font-size: 0.8rem;
            color: #94a3b8;
            text-transform: uppercase;
            letter-spacing: 1px;
            border-bottom: 2px solid #60a5fa;
        }}

        td {{
            padding: 0.75rem;
            border-bottom: 1px solid rgba(255,255,255,0.05);
            font-size: 0.9rem;
        }}

        tr {{
            cursor: pointer;
        }}

        tr:hover {{
            background: rgba(96, 165, 250, 0.1);
        }}

        .clickable-hint {{
            color: #64748b;
            font-size: 0.75rem;
            margin-left: 0.25rem;
        }}

        .risk-green {{ color: #34d399; font-weight: 700; }}
        .risk-gold {{ color: #fbbf24; font-weight: 700; }}
        .risk-blue {{ color: #60a5fa; font-weight: 700; }}
        .risk-red {{ color: #f87171; font-weight: 700; }}

        /* PROJECTIONS */
        .projections {{
            background: linear-gradient(135deg, rgba(30, 39, 73, 0.95) 0%, rgba(45, 53, 97, 0.95) 100%);
            backdrop-filter: blur(10px);
            padding: 2rem;
            border-radius: 20px;
            border: 1px solid rgba(255,255,255,0.1);
            margin-bottom: 2rem;
            box-shadow: 0 8px 32px rgba(0,0,0,0.3);
        }}

        .projection-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1.25rem;
        }}

        .projection-card {{
            background: rgba(15, 23, 42, 0.8);
            padding: 1.5rem;
            border-radius: 12px;
            border: 1px solid rgba(96, 165, 250, 0.3);
            position: relative;
            overflow: hidden;
        }}

        .projection-card::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 3px;
            background: linear-gradient(90deg, #60a5fa, #a78bfa);
        }}

        .projection-label {{
            font-size: 0.75rem;
            color: #94a3b8;
            text-transform: uppercase;
            letter-spacing: 1.5px;
            margin-bottom: 0.5rem;
        }}

        .projection-value {{
            font-size: 1.8rem;
            font-weight: 800;
            color: #ffffff;
            margin-bottom: 0.5rem;
        }}

        .projection-sub {{
            font-size: 0.8rem;
            color: #94a3b8;
            margin-bottom: 0.75rem;
        }}

        .projection-status {{
            display: inline-block;
            padding: 0.25rem 0.75rem;
            border-radius: 6px;
            font-size: 0.75rem;
            font-weight: 700;
            text-transform: uppercase;
        }}

        .projection-status.status-ontrack {{
            background: rgba(34, 197, 94, 0.2);
            color: #34d399;
            border: 1px solid rgba(34, 197, 94, 0.5);
        }}

        .projection-status.status-moderate {{
            background: rgba(96, 165, 250, 0.2);
            color: #60a5fa;
            border: 1px solid rgba(96, 165, 250, 0.5);
        }}

        .projection-status.status-behind {{
            background: rgba(239, 68, 68, 0.2);
            color: #f87171;
            border: 1px solid rgba(239, 68, 68, 0.5);
        }}

        /* PIPELINE VISUALIZER */
        .pipeline-viz {{
            background: linear-gradient(135deg, rgba(30, 39, 73, 0.95) 0%, rgba(45, 53, 97, 0.95) 100%);
            backdrop-filter: blur(10px);
            padding: 2rem;
            border-radius: 20px;
            border: 1px solid rgba(255,255,255,0.1);
            margin-bottom: 2rem;
            box-shadow: 0 8px 32px rgba(0,0,0,0.3);
        }}

        .stage {{
            margin-bottom: 1.5rem;
        }}

        .stage-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 0.5rem;
        }}

        .stage-name {{
            font-size: 0.95rem;
            font-weight: 700;
            color: #ffffff;
        }}

        .stage-count {{
            font-size: 0.85rem;
            color: #94a3b8;
        }}

        .stage-bar {{
            background: rgba(15, 23, 42, 0.6);
            height: 32px;
            border-radius: 8px;
            overflow: hidden;
            position: relative;
            border: 1px solid rgba(255,255,255,0.1);
        }}

        .stage-fill {{
            height: 100%;
            transition: width 1s ease;
            position: relative;
            overflow: hidden;
        }}

        .stage-fill::after {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: linear-gradient(90deg, rgba(255,255,255,0), rgba(255,255,255,0.1), rgba(255,255,255,0));
            animation: shimmer 2s infinite;
        }}

        @keyframes shimmer {{
            0% {{ transform: translateX(-100%); }}
            100% {{ transform: translateX(100%); }}
        }}

        .stage-fill.green {{ background: linear-gradient(90deg, #34d399, #10b981); }}
        .stage-fill.blue {{ background: linear-gradient(90deg, #60a5fa, #3b82f6); }}
        .stage-fill.purple {{ background: linear-gradient(90deg, #a78bfa, #8b5cf6); }}
        .stage-fill.orange {{ background: linear-gradient(90deg, #f59e0b, #d97706); }}
        .stage-fill.red {{ background: linear-gradient(90deg, #f87171, #ef4444); }}
        .stage-fill.grey {{ background: linear-gradient(90deg, #6b7280, #4b5563); }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>GLENN WINDOM - Operations Dashboard</h1>
            <p class="subtitle">Real-Time Intelligence • Contract Rate: 45% • Updated: {last_updated.strftime('%B %d, %Y - %I:%M %p')}</p>
        </div>

        <!-- COMMAND CENTER -->
        <div class="command-center">
            <h2 class="command-title">🎯 NEXT 24 HOURS - TOP PRIORITIES</h2>
            {command_items_html}
        </div>

        <!-- METRICS -->
        <div class="metrics-grid">
            <div class="metric-card">
                <div class="metric-label">12-Month Revenue</div>
                <div class="metric-value">{format_currency(metrics['revenue_12m'])}</div>
                <div class="metric-sub">Actual commissions received</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Current Pipeline</div>
                <div class="metric-value">{format_currency(metrics['total_pipeline'])}</div>
                <div class="metric-sub">{metrics['active_count']} people tracked</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Pending Commission</div>
                <div class="metric-value">{format_currency(metrics['pending_commission'])}</div>
                <div class="metric-sub">Approved, awaiting delivery</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Total Hours</div>
                <div class="metric-value">{int(metrics['total_hours'])}</div>
                <div class="metric-sub">{metrics['total_meetings']} meetings tracked</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Revenue/Hour</div>
                <div class="metric-value">{format_currency(metrics['revenue_per_hour'])}</div>
                <div class="metric-sub">Pipeline value basis</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Team Members</div>
                <div class="metric-value">{metrics['team_members']}</div>
                <div class="metric-sub">Referral sources</div>
            </div>
        </div>

        <!-- PERFORMANCE PROJECTIONS -->
        <div class="projections">
            <h2 class="section-title">📈 Performance Projections</h2>
            <div class="projection-grid">
                {projections_html}
            </div>
        </div>

        <!-- REVENUE HEATMAP -->
        <div class="heatmap">
            <h2 class="section-title">🔥 12-Month Revenue Heatmap</h2>
            <div class="heatmap-grid">
                {heatmap_html}
            </div>
            <div style="margin-top: 1rem; padding: 1rem; background: rgba(15, 23, 42, 0.6); border-radius: 8px; font-size: 0.85rem; color: #94a3b8;">
                <strong style="color: #ffffff;">Legend:</strong>
                <span style="color: #34d399;">■ Green: $7K+</span> •
                <span style="color: #60a5fa;">■ Blue: $4-7K</span> •
                <span style="color: #a78bfa;">■ Purple: $2.5-4K</span> •
                <span style="color: #f59e0b;">■ Orange: $500-2.5K</span> •
                <span style="color: #f87171;">■ Red: $0-500</span> •
                <span style="color: #6b7280;">■ Grey: No data</span>
            </div>
        </div>

        <!-- PIPELINE STAGE VISUALIZER -->
        <div class="pipeline-viz">
            <h2 class="section-title">📊 Pipeline Stage Visualizer</h2>
            {pipeline_html}
        </div>

        <!-- SUGGESTIONS -->
        <div class="suggestions">
            <h2 class="suggestions-title">💡 Intelligent Suggestions</h2>
            {suggestions_html}
        </div>

        <!-- PEOPLE TABLE -->
        <div class="people-table">
            <h2 class="section-title">👥 Complete People & Meetings Tracker</h2>
            <div class="table-wrapper">
                <table>
                    <thead>
                        <tr>
                            <th>Name</th>
                            <th>Status</th>
                            <th>Risk</th>
                            <th>Mtgs</th>
                            <th>Hours</th>
                            <th>Commission (45%)</th>
                            <th>Prob</th>
                            <th>Weighted</th>
                            <th>Next Action</th>
                        </tr>
                    </thead>
                    <tbody>
                        {people_rows_html}
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <script>
        // Auto-refresh every 5 minutes
        setTimeout(function() {{
            location.reload();
        }}, 300000);

        function showPerson(personId) {{
            // TODO: Implement modal with person details
            console.log('Show person:', personId);
            window.location.href = '/api/person/' + personId;
        }}
    </script>
</body>
</html>"""

    return html


# Global session for template function
session = None


if __name__ == '__main__':
    # Test generation
    html = generate_dashboard_html()
    print("Dashboard generated successfully!")
    print(f"Length: {len(html)} characters")
