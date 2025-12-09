"""
HTML Dashboard Generator.
Creates a professional dark-themed dashboard from database data.
"""

import json
from datetime import datetime, timedelta
from decimal import Decimal

from database import (
    get_session, Person, Application, Meeting, TimelineEvent, DailyMetrics,
    PersonStatus, ApplicationStatus, STAGE_PROBABILITIES, calculate_daily_metrics
)


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


def get_risk_level(probability):
    """Determine risk level based on probability."""
    if probability >= 100:
        return ('Guaranteed', 'guaranteed')
    elif probability >= 70:
        return ('High', 'high')
    elif probability >= 20:
        return ('Medium', 'medium')
    else:
        return ('At Risk', 'at-risk')


def get_priority_actions(session):
    """Generate priority actions for the command center."""
    actions = []
    now = datetime.now()

    # Get people who need attention
    people = session.query(Person).filter(
        Person.status.notin_([PersonStatus.COLD, PersonStatus.APPROVED])
    ).all()

    for person in people:
        days_since = (now - person.last_contact).days if person.last_contact else 999

        # Upcoming meetings (check meetings in next 24 hours)
        upcoming = session.query(Meeting).filter(
            Meeting.person_id == person.id,
            Meeting.date >= now,
            Meeting.date <= now + timedelta(hours=24)
        ).first()

        if upcoming:
            actions.append({
                'priority': 1,
                'type': 'scheduled',
                'tag': 'PREP',
                'message': f"Meeting with {person.name} at {upcoming.date.strftime('%I:%M %p')}",
                'amount': format_currency(person.estimated_commission),
                'person_id': person.id
            })

        # Applications pending follow-up
        if person.status == PersonStatus.APPLICATION:
            app = session.query(Application).filter(
                Application.person_id == person.id,
                Application.status.in_([ApplicationStatus.SUBMITTED, ApplicationStatus.UNDERWRITING])
            ).first()

            if app and days_since > 3:
                actions.append({
                    'priority': 2,
                    'type': 'important',
                    'tag': 'MONITOR',
                    'message': f"Check status: {person.name}'s application ({app.carrier})",
                    'amount': format_currency(app.estimated_commission),
                    'person_id': person.id
                })

        # Cold leads that need revival
        if days_since > 14 and person.status in [PersonStatus.ACTIVE, PersonStatus.WARM]:
            actions.append({
                'priority': 3,
                'type': 'urgent',
                'tag': 'CALL',
                'message': f"{person.name} losing momentum - {days_since} days since contact",
                'amount': format_currency(person.weighted_value),
                'person_id': person.id
            })

        # New scheduled meetings need intro prep
        if person.status == PersonStatus.SCHEDULED:
            actions.append({
                'priority': 4,
                'type': 'scheduled',
                'tag': 'PREP',
                'message': f"Prepare for intro with {person.name}",
                'amount': format_currency(person.estimated_commission),
                'person_id': person.id
            })

    # Sort by priority and return top 6
    actions.sort(key=lambda x: x['priority'])
    return actions[:6]


def get_suggestions(session):
    """Generate AI-like suggestions based on data."""
    suggestions = []
    people = session.query(Person).all()

    if not people:
        return ["Start by adding prospects to your pipeline"]

    # Find momentum patterns
    for person in people:
        if person.status == PersonStatus.APPLICATION:
            days_since = (datetime.now() - person.last_contact).days if person.last_contact else 0
            if days_since < 7:
                suggestions.append(f"{person.name} is moving fast - capitalize on momentum")

        if person.status in [PersonStatus.ACTIVE, PersonStatus.WARM]:
            days_since = (datetime.now() - person.last_contact).days if person.last_contact else 999
            if days_since > 10:
                suggestions.append(f"{person.name} losing momentum - schedule presentation NOW")

    # Find highest value prospect
    active_people = [p for p in people if p.status not in [PersonStatus.COLD, PersonStatus.APPROVED]]
    if active_people:
        highest = max(active_people, key=lambda p: float(p.estimated_commission or 0))
        if highest.estimated_commission and float(highest.estimated_commission) > 0:
            suggestions.append(f"Highest potential: {highest.name} - {format_currency(highest.estimated_commission)}")

    # Source analysis
    sources = {}
    for p in people:
        src = p.source or 'Unknown'
        if src not in sources:
            sources[src] = 0
        sources[src] += float(p.weighted_value or 0)

    if sources:
        top_source = max(sources.items(), key=lambda x: x[1])
        if top_source[1] > 0:
            suggestions.append(f"Your pipeline depends on {top_source[0]} ({format_currency(top_source[1])} weighted value)")

    return suggestions[:4]


def get_pipeline_stages(session):
    """Get pipeline broken down by stage."""
    stages = {
        'approved': {'label': 'Confirmed Pending', 'count': 0, 'value': 0},
        'application': {'label': 'Applications', 'count': 0, 'value': 0},
        'active': {'label': 'Active Prospects', 'count': 0, 'value': 0},
        'scheduled': {'label': 'Scheduled', 'count': 0, 'value': 0}
    }

    people = session.query(Person).all()

    for person in people:
        commission = float(person.estimated_commission or 0)

        if person.status == PersonStatus.APPROVED:
            stages['approved']['count'] += 1
            stages['approved']['value'] += commission
        elif person.status == PersonStatus.APPLICATION:
            stages['application']['count'] += 1
            stages['application']['value'] += commission
        elif person.status in [PersonStatus.ACTIVE, PersonStatus.WARM]:
            stages['active']['count'] += 1
            stages['active']['value'] += commission
        elif person.status in [PersonStatus.SCHEDULED, PersonStatus.NEW]:
            stages['scheduled']['count'] += 1
            stages['scheduled']['value'] += commission

    return stages


def generate_dashboard_html(session=None):
    """Generate the complete dashboard HTML."""
    close_session = False
    if session is None:
        session = get_session()
        close_session = True

    try:
        # Calculate metrics
        metrics = calculate_daily_metrics(session)

        # Get all people
        people = session.query(Person).order_by(Person.weighted_value.desc()).all()

        # Get priority actions
        priority_actions = get_priority_actions(session)

        # Get suggestions
        suggestions = get_suggestions(session)

        # Get pipeline stages
        pipeline_stages = get_pipeline_stages(session)

        # Calculate totals
        total_pipeline = sum(float(p.estimated_commission or 0) for p in people)
        weighted_pipeline = sum(float(p.weighted_value or 0) for p in people)
        total_hours = sum(float(p.total_hours or 0) for p in people)
        total_meetings = sum(p.total_meetings or 0 for p in people)

        # Revenue per hour
        revenue_per_hour = weighted_pipeline / total_hours if total_hours > 0 else 0

        # Count by status
        active_count = len([p for p in people if p.status not in [PersonStatus.COLD]])

        # Generate HTML
        html = generate_html_template(
            people=people,
            metrics={
                'total_pipeline': total_pipeline,
                'weighted_pipeline': weighted_pipeline,
                'total_hours': total_hours,
                'total_meetings': total_meetings,
                'revenue_per_hour': revenue_per_hour,
                'active_count': active_count
            },
            priority_actions=priority_actions,
            suggestions=suggestions,
            pipeline_stages=pipeline_stages,
            last_updated=datetime.now()
        )

        return html

    finally:
        if close_session:
            session.close()


def generate_html_template(people, metrics, priority_actions, suggestions, pipeline_stages, last_updated):
    """Generate the HTML template with all data."""

    # Generate people rows
    people_rows = ""
    for person in people:
        risk_label, risk_class = get_risk_level(person.probability or 0)
        status_class = (person.status or 'new').lower()

        # Get next action based on status
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

        people_rows += f"""
        <tr class="person-row" data-person-id="{person.id}">
            <td class="name-cell">{person.name}</td>
            <td><span class="status-badge status-{status_class}">{person.status or 'NEW'}</span></td>
            <td><span class="risk-badge risk-{risk_class}">{risk_label}</span></td>
            <td class="center">{person.total_meetings or 0}</td>
            <td class="center">{float(person.total_hours or 0):.1f}</td>
            <td class="currency">{format_currency(person.estimated_commission)}</td>
            <td class="center">{format_percent(person.probability)}</td>
            <td class="currency weighted">{format_currency(person.weighted_value)}</td>
            <td class="action-cell">{next_action}</td>
        </tr>
        """

    # Generate priority action items
    action_items = ""
    for action in priority_actions:
        action_items += f"""
        <div class="action-item action-{action['type']}">
            <span class="action-tag">[{action['tag']}]</span>
            <span class="action-message">{action['message']}</span>
            <span class="action-amount">{action['amount']}</span>
        </div>
        """

    if not action_items:
        action_items = '<div class="action-item">No priority actions - great job!</div>'

    # Generate suggestions
    suggestion_items = ""
    for suggestion in suggestions:
        suggestion_items += f'<li>{suggestion}</li>'

    if not suggestion_items:
        suggestion_items = '<li>Add more prospects to get personalized suggestions</li>'

    # Generate pipeline stages
    stage_cards = ""
    for key, stage in pipeline_stages.items():
        stage_cards += f"""
        <div class="stage-card">
            <div class="stage-label">{stage['label']}</div>
            <div class="stage-value">{format_currency(stage['value'])}</div>
            <div class="stage-count">{stage['count']} people</div>
        </div>
        """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Glenn Windom - Operations Dashboard</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #e0e0e0;
            min-height: 100vh;
            padding: 20px;
        }}

        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}

        /* Header */
        .header {{
            text-align: center;
            margin-bottom: 30px;
            padding: 20px;
            background: rgba(255,255,255,0.05);
            border-radius: 15px;
            border: 1px solid rgba(255,255,255,0.1);
        }}

        .header h1 {{
            font-size: 2.5rem;
            color: #4fc3f7;
            margin-bottom: 5px;
        }}

        .header .subtitle {{
            color: #90a4ae;
            font-size: 1rem;
        }}

        .header .last-updated {{
            color: #78909c;
            font-size: 0.85rem;
            margin-top: 10px;
        }}

        /* Command Center */
        .command-center {{
            background: rgba(255,255,255,0.05);
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 25px;
            border: 1px solid rgba(255,255,255,0.1);
        }}

        .command-center h2 {{
            color: #4fc3f7;
            margin-bottom: 15px;
            font-size: 1.3rem;
        }}

        .action-item {{
            display: flex;
            align-items: center;
            padding: 12px 15px;
            margin-bottom: 10px;
            border-radius: 8px;
            background: rgba(0,0,0,0.2);
        }}

        .action-item:last-child {{
            margin-bottom: 0;
        }}

        .action-urgent {{
            border-left: 4px solid #ef5350;
        }}

        .action-scheduled {{
            border-left: 4px solid #4fc3f7;
        }}

        .action-important {{
            border-left: 4px solid #ffb74d;
        }}

        .action-tag {{
            font-weight: bold;
            margin-right: 10px;
            min-width: 80px;
        }}

        .action-urgent .action-tag {{
            color: #ef5350;
        }}

        .action-scheduled .action-tag {{
            color: #4fc3f7;
        }}

        .action-important .action-tag {{
            color: #ffb74d;
        }}

        .action-message {{
            flex: 1;
        }}

        .action-amount {{
            font-weight: bold;
            color: #81c784;
        }}

        /* Metrics Grid */
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 25px;
        }}

        .metric-card {{
            background: rgba(255,255,255,0.05);
            border-radius: 15px;
            padding: 20px;
            text-align: center;
            border: 1px solid rgba(255,255,255,0.1);
        }}

        .metric-value {{
            font-size: 2rem;
            font-weight: bold;
            color: #4fc3f7;
            margin-bottom: 5px;
        }}

        .metric-label {{
            color: #90a4ae;
            font-size: 0.9rem;
        }}

        .metric-sub {{
            color: #78909c;
            font-size: 0.8rem;
            margin-top: 5px;
        }}

        /* Pipeline Stages */
        .pipeline-stages {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin-bottom: 25px;
        }}

        .stage-card {{
            background: rgba(255,255,255,0.05);
            border-radius: 10px;
            padding: 15px;
            text-align: center;
            border: 1px solid rgba(255,255,255,0.1);
        }}

        .stage-label {{
            color: #90a4ae;
            font-size: 0.85rem;
            margin-bottom: 5px;
        }}

        .stage-value {{
            font-size: 1.5rem;
            font-weight: bold;
            color: #81c784;
        }}

        .stage-count {{
            color: #78909c;
            font-size: 0.8rem;
        }}

        /* People Table */
        .table-container {{
            background: rgba(255,255,255,0.05);
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 25px;
            overflow-x: auto;
            border: 1px solid rgba(255,255,255,0.1);
        }}

        .table-container h2 {{
            color: #4fc3f7;
            margin-bottom: 15px;
            font-size: 1.3rem;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
        }}

        th {{
            background: rgba(0,0,0,0.3);
            padding: 12px 10px;
            text-align: left;
            font-weight: 600;
            color: #90a4ae;
            font-size: 0.85rem;
            text-transform: uppercase;
        }}

        td {{
            padding: 12px 10px;
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }}

        tr:hover {{
            background: rgba(255,255,255,0.03);
        }}

        .person-row {{
            cursor: pointer;
        }}

        .name-cell {{
            font-weight: 500;
            color: #e0e0e0;
        }}

        .center {{
            text-align: center;
        }}

        .currency {{
            text-align: right;
            font-family: 'Monaco', 'Consolas', monospace;
        }}

        .weighted {{
            color: #81c784;
            font-weight: bold;
        }}

        /* Status Badges */
        .status-badge {{
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
        }}

        .status-approved {{
            background: rgba(129, 199, 132, 0.2);
            color: #81c784;
        }}

        .status-application {{
            background: rgba(255, 183, 77, 0.2);
            color: #ffb74d;
        }}

        .status-warm, .status-active {{
            background: rgba(79, 195, 247, 0.2);
            color: #4fc3f7;
        }}

        .status-scheduled, .status-new {{
            background: rgba(144, 164, 174, 0.2);
            color: #90a4ae;
        }}

        .status-cold {{
            background: rgba(239, 83, 80, 0.2);
            color: #ef5350;
        }}

        /* Risk Badges */
        .risk-badge {{
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 0.75rem;
            font-weight: 600;
        }}

        .risk-guaranteed {{
            background: rgba(129, 199, 132, 0.3);
            color: #81c784;
        }}

        .risk-high {{
            background: rgba(255, 215, 64, 0.3);
            color: #ffd740;
        }}

        .risk-medium {{
            background: rgba(79, 195, 247, 0.3);
            color: #4fc3f7;
        }}

        .risk-at-risk {{
            background: rgba(239, 83, 80, 0.3);
            color: #ef5350;
        }}

        .action-cell {{
            color: #90a4ae;
            font-size: 0.85rem;
        }}

        /* Suggestions */
        .suggestions {{
            background: rgba(255,255,255,0.05);
            border-radius: 15px;
            padding: 20px;
            border: 1px solid rgba(255,255,255,0.1);
        }}

        .suggestions h2 {{
            color: #4fc3f7;
            margin-bottom: 15px;
            font-size: 1.3rem;
        }}

        .suggestions ul {{
            list-style: none;
        }}

        .suggestions li {{
            padding: 10px 0;
            border-bottom: 1px solid rgba(255,255,255,0.05);
            color: #b0bec5;
        }}

        .suggestions li:last-child {{
            border-bottom: none;
        }}

        .suggestions li::before {{
            content: "💡 ";
        }}

        /* Responsive */
        @media (max-width: 768px) {{
            .header h1 {{
                font-size: 1.8rem;
            }}

            .metrics-grid {{
                grid-template-columns: repeat(2, 1fr);
            }}

            .metric-value {{
                font-size: 1.5rem;
            }}

            table {{
                font-size: 0.85rem;
            }}

            th, td {{
                padding: 8px 6px;
            }}
        }}

        /* Empty state */
        .empty-state {{
            text-align: center;
            padding: 40px;
            color: #78909c;
        }}

        .empty-state h3 {{
            margin-bottom: 10px;
            color: #90a4ae;
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <div class="header">
            <h1>Glenn Windom - Operations Dashboard</h1>
            <div class="subtitle">Real-time Pipeline Tracking</div>
            <div class="last-updated">Last updated: {last_updated.strftime('%B %d, %Y at %I:%M %p')}</div>
        </div>

        <!-- 24-Hour Command Center -->
        <div class="command-center">
            <h2>⚡ 24-Hour Command Center</h2>
            {action_items}
        </div>

        <!-- Metrics Grid -->
        <div class="metrics-grid">
            <div class="metric-card">
                <div class="metric-value">{format_currency(metrics['weighted_pipeline'])}</div>
                <div class="metric-label">Weighted Pipeline</div>
                <div class="metric-sub">{metrics['active_count']} active prospects</div>
            </div>
            <div class="metric-card">
                <div class="metric-value">{format_currency(metrics['total_pipeline'])}</div>
                <div class="metric-label">Total Pipeline</div>
                <div class="metric-sub">If all close</div>
            </div>
            <div class="metric-card">
                <div class="metric-value">{metrics['total_meetings']}</div>
                <div class="metric-label">Total Meetings</div>
                <div class="metric-sub">{metrics['total_hours']:.1f} hours</div>
            </div>
            <div class="metric-card">
                <div class="metric-value">{format_currency(metrics['revenue_per_hour'])}</div>
                <div class="metric-label">Revenue/Hour</div>
                <div class="metric-sub">Weighted value</div>
            </div>
        </div>

        <!-- Pipeline Stages -->
        <div class="pipeline-stages">
            {stage_cards}
        </div>

        <!-- People Tracker -->
        <div class="table-container">
            <h2>👥 People Tracker</h2>
            {"<table><thead><tr><th>Name</th><th>Status</th><th>Risk</th><th>Meetings</th><th>Hours</th><th>Commission</th><th>Prob</th><th>Weighted</th><th>Next Action</th></tr></thead><tbody>" + people_rows + "</tbody></table>" if people else '<div class="empty-state"><h3>No prospects yet</h3><p>Data will appear here once emails are synced</p></div>'}
        </div>

        <!-- Suggestions -->
        <div class="suggestions">
            <h2>💡 Smart Suggestions</h2>
            <ul>
                {suggestion_items}
            </ul>
        </div>
    </div>

    <script>
        // Auto-refresh every 5 minutes
        setTimeout(function() {{
            location.reload();
        }}, 300000);

        // Click handler for person rows (future: open modal)
        document.querySelectorAll('.person-row').forEach(function(row) {{
            row.addEventListener('click', function() {{
                var personId = this.getAttribute('data-person-id');
                console.log('Clicked person:', personId);
                // TODO: Open modal with person details
            }});
        }});
    </script>
</body>
</html>"""

    return html


if __name__ == '__main__':
    # Generate dashboard and save to file
    html = generate_dashboard_html()
    with open('dashboard.html', 'w') as f:
        f.write(html)
    print("Dashboard generated: dashboard.html")
