"""
Premium Dashboard Generator - Glenn Windom Operations Dashboard
Uses user's exact premium design with live data from database.
"""

from datetime import datetime, timedelta, date
from decimal import Decimal

from database import (
    get_session, Person, Application, Meeting, TimelineEvent,
    DailyMetrics, MonthlyRevenue, PersonStatus, ApplicationStatus,
    STAGE_PROBABILITIES, calculate_daily_metrics
)


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
        # Get all people from database
        people = session.query(Person).order_by(Person.weighted_value.desc()).all()

        # Get all applications
        applications = session.query(Application).all()

        # Get all meetings
        meetings = session.query(Meeting).all()

        # Get monthly revenue data
        revenues = session.query(MonthlyRevenue).order_by(MonthlyRevenue.month).all()

        # Calculate metrics
        total_pipeline = sum(float(p.estimated_commission or 0) for p in people if p.status != PersonStatus.COLD)
        weighted_pipeline = sum(float(p.weighted_value or 0) for p in people if p.status != PersonStatus.COLD)
        total_hours = sum(float(p.total_hours or 0) for p in people)
        total_meetings = sum(p.total_meetings or 0 for p in people)
        revenue_per_hour = weighted_pipeline / total_hours if total_hours > 0 else 0

        # 12-month revenue
        twelve_months_ago = date.today() - timedelta(days=365)
        total_revenue_12m = sum(float(r.revenue or 0) for r in revenues if r.month and r.month >= twelve_months_ago)

        # Pending commission (approved apps)
        pending_commission = sum(
            float(app.estimated_commission or 0)
            for app in applications
            if app.status in [ApplicationStatus.APPROVED, ApplicationStatus.SIGNATURE_NEEDED]
        )

        # Count referral sources
        sources = set(p.source for p in people if p.source and p.source not in ['Unknown', 'Direct', None])
        team_members = len(sources)

        # Active people count
        active_count = len([p for p in people if p.status != PersonStatus.COLD])

        # Generate command center items
        command_items = generate_command_center(session, people, applications, meetings)

        # Generate people table rows
        people_rows = generate_people_rows(session, people)

        # Generate pipeline stages
        pipeline_stages = generate_pipeline_stages(people)

        # Generate heatmap
        heatmap = generate_heatmap(revenues)

        # Generate suggestions
        suggestions = generate_suggestions(session, people, applications, revenues)

        # Generate projections
        projections = generate_projections(people, weighted_pipeline)

        now = datetime.now()

        html = f'''<!DOCTYPE html>
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
            padding: 1rem;
            line-height: 1.6;
            overflow-x: hidden;
        }}

        @media (max-width: 640px) {{
            body {{
                padding: 0.5rem;
            }}
        }}

        @keyframes fadeInUp {{
            from {{ opacity: 0; transform: translateY(30px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}

        @keyframes slideInRight {{
            from {{ opacity: 0; transform: translateX(-50px); }}
            to {{ opacity: 1; transform: translateX(0); }}
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

        @media (max-width: 640px) {{
            .header {{
                padding: 1rem;
                margin-bottom: 1.5rem;
                border-radius: 12px;
            }}
        }}

        h1 {{
            font-family: 'Space Grotesk', sans-serif;
            font-size: 2.5rem;
            background: linear-gradient(135deg, #60a5fa 0%, #a78bfa 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.5rem;
            animation: slideInRight 0.8s ease-out;
        }}

        @media (max-width: 640px) {{
            h1 {{
                font-size: 1.5rem;
                margin-bottom: 0.35rem;
            }}
        }}

        .subtitle {{
            color: #94a3b8;
            font-size: 1rem;
            animation: fadeInUp 1s ease-out;
        }}

        @media (max-width: 640px) {{
            .subtitle {{
                font-size: 0.75rem;
            }}
        }}

        /* COMMAND CENTER */
        .command-center {{
            background: linear-gradient(135deg, rgba(239, 68, 68, 0.15) 0%, rgba(251, 191, 36, 0.15) 100%);
            border: 2px solid rgba(251, 191, 36, 0.5);
            border-radius: 20px;
            padding: 2rem;
            margin-bottom: 2rem;
            box-shadow: 0 8px 32px rgba(251, 191, 36, 0.2);
            animation: fadeInUp 0.6s ease-out 0.2s both;
        }}

        @media (max-width: 640px) {{
            .command-center {{
                padding: 1rem;
                margin-bottom: 1.5rem;
                border-radius: 12px;
            }}
        }}

        .command-title {{
            font-size: 1.4rem;
            font-weight: 800;
            color: #fbbf24;
            margin-bottom: 1.5rem;
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }}

        @media (max-width: 640px) {{
            .command-title {{
                font-size: 1.1rem;
                margin-bottom: 1rem;
            }}
        }}

        .command-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 1.25rem;
        }}

        @media (max-width: 640px) {{
            .command-grid {{
                grid-template-columns: 1fr;
                gap: 0.75rem;
            }}
        }}

        .command-item {{
            background: rgba(15, 23, 42, 0.6);
            padding: 1.25rem;
            border-radius: 12px;
            border-left: 4px solid;
            transition: all 0.3s ease;
        }}

        @media (max-width: 640px) {{
            .command-item {{
                padding: 1rem;
                border-radius: 8px;
            }}
        }}

        .command-item:hover {{
            transform: translateX(5px);
            background: rgba(15, 23, 42, 0.9);
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
            line-height: 1.5;
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

        @media (max-width: 768px) {{
            .metrics-grid {{
                grid-template-columns: repeat(2, 1fr);
                gap: 1rem;
            }}
        }}

        @media (max-width: 480px) {{
            .metrics-grid {{
                grid-template-columns: 1fr;
                gap: 0.75rem;
            }}
        }}

        .metric-card {{
            background: linear-gradient(135deg, rgba(30, 39, 73, 0.95) 0%, rgba(45, 53, 97, 0.95) 100%);
            backdrop-filter: blur(10px);
            padding: 1.5rem;
            border-radius: 15px;
            border: 1px solid rgba(255,255,255,0.1);
            position: relative;
            overflow: hidden;
            transition: all 0.3s ease;
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

        .section-title {{
            font-size: 1.3rem;
            font-weight: 700;
            margin-bottom: 1.5rem;
            color: #ffffff;
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
            font-size: 0.9rem;
            font-weight: 600;
            color: #cbd5e1;
        }}

        .stage-count {{
            font-size: 0.85rem;
            color: #94a3b8;
        }}

        .stage-bar {{
            height: 12px;
            background: rgba(15, 23, 42, 0.6);
            border-radius: 6px;
            overflow: hidden;
        }}

        .stage-fill {{
            height: 100%;
            border-radius: 6px;
            transition: width 1.5s ease-out;
        }}

        .stage-fill.green {{ background: linear-gradient(90deg, #34d399, #10b981); }}
        .stage-fill.gold {{ background: linear-gradient(90deg, #fbbf24, #f59e0b); }}
        .stage-fill.blue {{ background: linear-gradient(90deg, #60a5fa, #3b82f6); }}
        .stage-fill.purple {{ background: linear-gradient(90deg, #a78bfa, #8b5cf6); }}
        .stage-fill.red {{ background: linear-gradient(90deg, #f87171, #ef4444); }}
        .stage-fill.grey {{ background: linear-gradient(90deg, #6b7280, #4b5563); }}

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
            transform: scale(1.05);
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

        .heatmap-legend {{
            margin-top: 1rem;
            padding: 1rem;
            background: rgba(15, 23, 42, 0.6);
            border-radius: 8px;
            font-size: 0.85rem;
            color: #94a3b8;
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
            margin-bottom: 0.75rem;
        }}

        .suggestion-text {{
            color: #e2e8f0;
            font-size: 0.95rem;
            line-height: 1.6;
        }}

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
            gap: 1.5rem;
        }}

        .projection-card {{
            background: rgba(15, 23, 42, 0.6);
            padding: 1.5rem;
            border-radius: 12px;
            border: 1px solid rgba(255,255,255,0.1);
        }}

        .projection-label {{
            font-size: 0.8rem;
            color: #94a3b8;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 0.75rem;
        }}

        .projection-value {{
            font-size: 1.8rem;
            font-weight: 800;
            color: #34d399;
            margin-bottom: 0.5rem;
        }}

        .projection-sub {{
            font-size: 0.85rem;
            color: #cbd5e1;
        }}

        .projection-status {{
            display: inline-block;
            padding: 0.4rem 0.9rem;
            border-radius: 20px;
            font-size: 0.75rem;
            font-weight: 600;
            margin-top: 0.75rem;
        }}

        .status-ontrack {{
            background: rgba(52, 211, 153, 0.2);
            color: #34d399;
        }}

        .status-moderate {{
            background: rgba(96, 165, 250, 0.2);
            color: #60a5fa;
        }}

        .status-behind {{
            background: rgba(248, 113, 113, 0.2);
            color: #f87171;
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

        .table-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1rem;
            flex-wrap: wrap;
            gap: 1rem;
        }}

        .risk-legend {{
            font-size: 0.8rem;
            color: #94a3b8;
        }}

        .risk-legend span {{
            margin: 0 0.5rem;
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
            transition: all 0.3s ease;
            cursor: pointer;
        }}

        tr:hover {{
            background: rgba(96, 165, 250, 0.1);
        }}

        .risk-green {{ color: #34d399; font-weight: 700; }}
        .risk-gold {{ color: #fbbf24; font-weight: 700; }}
        .risk-blue {{ color: #60a5fa; font-weight: 700; }}
        .risk-red {{ color: #f87171; font-weight: 700; }}
        .risk-grey {{ color: #6b7280; font-weight: 700; }}

        .totals-row {{
            background: rgba(96, 165, 250, 0.1);
            font-weight: 700;
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- HEADER -->
        <div class="header">
            <h1>GLENN WINDOM - Operations Dashboard</h1>
            <p class="subtitle">Real-Time Intelligence &bull; Contract Rate: 45% &bull; Updated: {now.strftime('%B %d, %Y - %I:%M %p')}</p>
        </div>

        <!-- 24-HOUR COMMAND CENTER -->
        <div class="command-center">
            <h2 class="command-title">&#127919; NEXT 24 HOURS - TOP PRIORITIES</h2>
            <div class="command-grid">
                {command_items}
            </div>
        </div>

        <!-- PERFORMANCE METRICS -->
        <div class="metrics-grid">
            <div class="metric-card">
                <div class="metric-label">12-Month Revenue</div>
                <div class="metric-value">{format_currency(total_revenue_12m)}</div>
                <div class="metric-sub">Actual commissions received</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Current Pipeline</div>
                <div class="metric-value">{format_currency(total_pipeline)}</div>
                <div class="metric-sub">{active_count} people tracked</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Pending Commission</div>
                <div class="metric-value">{format_currency(pending_commission)}</div>
                <div class="metric-sub">Approved, awaiting delivery</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Total Hours</div>
                <div class="metric-value">{int(total_hours)}</div>
                <div class="metric-sub">{total_meetings} meetings tracked</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Revenue/Hour</div>
                <div class="metric-value">{format_currency(revenue_per_hour)}</div>
                <div class="metric-sub">Pipeline value basis</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Team Members</div>
                <div class="metric-value">{team_members}</div>
                <div class="metric-sub">Referral sources</div>
            </div>
        </div>

        <!-- PERFORMANCE PROJECTIONS -->
        <div class="projections">
            <h2 class="section-title">&#128200; Performance Projections</h2>
            <div class="projection-grid">
                {projections}
            </div>
        </div>

        <!-- REVENUE HEATMAP -->
        <div class="heatmap">
            <h2 class="section-title">&#128293; 12-Month Revenue Heatmap</h2>
            <div class="heatmap-grid">
                {heatmap}
            </div>
            <div class="heatmap-legend">
                <strong style="color: #ffffff;">Legend:</strong>
                <span style="color: #34d399;">&#9632; Green: $7K+</span> &bull;
                <span style="color: #60a5fa;">&#9632; Blue: $4-7K</span> &bull;
                <span style="color: #a78bfa;">&#9632; Purple: $2.5-4K</span> &bull;
                <span style="color: #f59e0b;">&#9632; Orange: $500-2.5K</span> &bull;
                <span style="color: #f87171;">&#9632; Red: $0-500</span> &bull;
                <span style="color: #6b7280;">&#9632; Grey: No data</span>
            </div>
        </div>

        <!-- PIPELINE STAGE VISUALIZER -->
        <div class="pipeline-viz">
            <h2 class="section-title">&#128202; Pipeline Stage Visualizer</h2>
            {pipeline_stages}
        </div>

        <!-- SUGGESTIONS -->
        <div class="suggestions">
            <h2 class="suggestions-title">&#128161; Intelligent Suggestions</h2>
            {suggestions}
        </div>

        <!-- COMPLETE PEOPLE TRACKER -->
        <div class="people-table">
            <div class="table-header">
                <h2 class="section-title">&#128101; Complete People & Meetings Tracker</h2>
                <div class="risk-legend">
                    <strong>Legend:</strong>
                    <span class="risk-green">&#9632; Guaranteed</span>
                    <span class="risk-gold">&#9632; High Conf</span>
                    <span class="risk-blue">&#9632; Medium</span>
                    <span class="risk-red">&#9632; At Risk</span>
                </div>
            </div>
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
                        {people_rows}
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
    </script>
</body>
</html>'''

        return html

    finally:
        if close_session:
            session.close()


def generate_command_center(session, people, applications, meetings):
    """Generate priority action items for command center."""
    items = []
    now = datetime.now()
    tomorrow = now + timedelta(hours=24)

    # 1. URGENT: Signature needed (approved apps)
    for app in applications:
        if app.status in [ApplicationStatus.APPROVED, ApplicationStatus.SIGNATURE_NEEDED]:
            if app.person:
                items.append({
                    'type': 'urgent',
                    'label': 'URGENT - GET SIGNATURE',
                    'tag': 'CALL',
                    'text': f"Get {app.person.name}'s delivery receipt signed - {format_currency(app.estimated_commission)} commission"
                })

    # 2. PREP: Meetings in next 24 hours
    for meeting in meetings:
        if meeting.date and now <= meeting.date <= tomorrow:
            person_name = meeting.person.name if meeting.person else 'Unknown'
            meeting_time = meeting.date.strftime('%I:%M %p') if meeting.date else 'TBD'
            items.append({
                'type': 'scheduled',
                'label': f'TOMORROW {meeting_time}',
                'tag': 'PREP',
                'text': f"{person_name} - {meeting.meeting_type or 'Meeting'}"
            })

    # 3. STALLED: Applications needing action
    for app in applications:
        if app.status == ApplicationStatus.STALLED and app.person:
            items.append({
                'type': 'important',
                'label': 'STALLED',
                'tag': 'ACTION',
                'text': f"{app.person.name} - {app.blocker or 'Requirements needed'}"
            })

    # 4. LOSING MOMENTUM: People not contacted in 3+ days
    for person in people:
        if person.status in [PersonStatus.ACTIVE, PersonStatus.WARM]:
            days_since = (now - person.last_contact).days if person.last_contact else 999
            if days_since >= 3:
                # Check if they have future meetings
                has_future = any(
                    m.date and m.date > now
                    for m in meetings
                    if m.person_id == person.id
                )
                if not has_future:
                    items.append({
                        'type': 'important',
                        'label': 'LOSING MOMENTUM',
                        'tag': 'CALL',
                        'text': f"{person.name} - {days_since} days since contact, no meeting scheduled"
                    })

    # 5. Monitor underwriting
    for app in applications:
        if app.status == ApplicationStatus.UNDERWRITING and app.person:
            if float(app.estimated_commission or 0) > 1000:
                items.append({
                    'type': 'important',
                    'label': 'TRACK DAILY',
                    'tag': 'MONITOR',
                    'text': f"{app.person.name} - {format_currency(app.estimated_commission)} in underwriting"
                })

    # Generate HTML
    if not items:
        return '''<div class="command-item scheduled">
            <div class="command-label">ALL CLEAR</div>
            <div class="command-text">No urgent priorities - great job staying on top of things!</div>
        </div>'''

    html = ""
    for item in items[:7]:  # Max 7 items
        html += f'''<div class="command-item {item['type']}">
            <div class="command-label">{item['label']}</div>
            <div class="command-text">
                <span class="action-tag">[{item['tag']}]</span>
                {item['text']}
            </div>
        </div>
        '''

    return html


def generate_people_rows(session, people):
    """Generate table rows for people."""
    rows = ""
    totals = {'count': 0, 'meetings': 0, 'hours': 0, 'commission': 0, 'weighted': 0}

    for person in people:
        if person.status == PersonStatus.COLD:
            continue

        totals['count'] += 1
        totals['meetings'] += person.total_meetings or 0
        totals['hours'] += float(person.total_hours or 0)
        totals['commission'] += float(person.estimated_commission or 0)
        totals['weighted'] += float(person.weighted_value or 0)

        # Determine risk level
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

        # Determine next action
        if person.status == PersonStatus.APPROVED:
            next_action = "Get signature"
        elif person.status == PersonStatus.APPLICATION:
            next_action = "Monitor underwriting"
        elif person.status == PersonStatus.WARM:
            next_action = "Schedule presentation"
        elif person.status == PersonStatus.ACTIVE:
            next_action = "Book next meeting"
        elif person.status == PersonStatus.SCHEDULED:
            next_action = "Prepare for meeting"
        else:
            next_action = "Initial outreach"

        # Source info
        source_info = ""
        if person.source and person.source not in ['Unknown', 'Direct']:
            source_info = f"<br><small style='color: #a78bfa;'>via {person.source}</small>"

        rows += f'''<tr>
            <td>
                <strong>{person.name}</strong>
                {source_info}
            </td>
            <td>{person.status or 'NEW'}</td>
            <td class="risk-{risk_class}">&#9632; {risk_label}</td>
            <td>{person.total_meetings or 0}</td>
            <td>{float(person.total_hours or 0):.1f}</td>
            <td class="risk-{risk_class}">{format_currency(person.estimated_commission)}</td>
            <td>{prob}%</td>
            <td class="risk-{risk_class}">{format_currency(person.weighted_value)}</td>
            <td>{next_action}</td>
        </tr>
        '''

    # Totals row
    rows += f'''<tr class="totals-row">
        <td><strong>TOTALS</strong></td>
        <td>{totals['count']} People</td>
        <td>-</td>
        <td>{totals['meetings']}</td>
        <td>{totals['hours']:.1f}</td>
        <td style="color: #34d399;">{format_currency(totals['commission'])}</td>
        <td>-</td>
        <td style="color: #34d399;">{format_currency(totals['weighted'])}</td>
        <td>-</td>
    </tr>'''

    return rows


def generate_pipeline_stages(people):
    """Generate pipeline stage visualizer."""
    stages = {
        'signature': {'name': '&#10004; Signature/Delivery (GUARANTEED)', 'color': 'green', 'count': 0, 'value': 0},
        'application': {'name': '&#128203; Application/Underwriting (HIGH CONF)', 'color': 'gold', 'count': 0, 'value': 0},
        'warm': {'name': '&#128293; Warm - Multiple Touchpoints (STRONG)', 'color': 'blue', 'count': 0, 'value': 0},
        'active': {'name': '&#128188; Active - Education Scheduled (MEDIUM)', 'color': 'blue', 'count': 0, 'value': 0},
        'new': {'name': '&#127793; New/Scheduled (DEVELOPING)', 'color': 'purple', 'count': 0, 'value': 0},
        'cold': {'name': '&#10052; Cold/Canceled (AT RISK)', 'color': 'red', 'count': 0, 'value': 0},
    }

    for person in people:
        commission = float(person.estimated_commission or 0)

        if person.status == PersonStatus.APPROVED or (person.probability and person.probability >= 100):
            stages['signature']['count'] += 1
            stages['signature']['value'] += commission
        elif person.status == PersonStatus.APPLICATION:
            stages['application']['count'] += 1
            stages['application']['value'] += commission
        elif person.status == PersonStatus.WARM:
            stages['warm']['count'] += 1
            stages['warm']['value'] += commission
        elif person.status == PersonStatus.ACTIVE:
            stages['active']['count'] += 1
            stages['active']['value'] += commission
        elif person.status == PersonStatus.COLD:
            stages['cold']['count'] += 1
            stages['cold']['value'] += commission
        else:  # NEW, SCHEDULED
            stages['new']['count'] += 1
            stages['new']['value'] += commission

    # Calculate max for percentage
    max_value = max((s['value'] for s in stages.values()), default=1)
    if max_value == 0:
        max_value = 1

    html = ""
    for key, stage in stages.items():
        width = int((stage['value'] / max_value) * 100) if max_value > 0 else 0
        html += f'''<div class="stage">
            <div class="stage-header">
                <div class="stage-name">{stage['name']}</div>
                <div class="stage-count">{stage['count']} person{'s' if stage['count'] != 1 else ''} &bull; {format_currency(stage['value'])}</div>
            </div>
            <div class="stage-bar">
                <div class="stage-fill {stage['color']}" style="width: {width}%;"></div>
            </div>
        </div>
        '''

    return html


def generate_heatmap(revenues):
    """Generate 12-month revenue heatmap."""
    # Build month lookup
    revenue_by_month = {}
    for r in revenues:
        if r.month:
            key = r.month.strftime('%Y-%m')
            revenue_by_month[key] = float(r.revenue or 0)

    html = ""
    today = date.today()

    for i in range(12):
        # Go back from current month
        month_offset = 11 - i
        month_date = today.replace(day=1) - timedelta(days=30 * month_offset)
        month_date = month_date.replace(day=1)

        key = month_date.strftime('%Y-%m')
        revenue = revenue_by_month.get(key, 0)

        # Determine level
        if revenue >= 7000:
            level = 5
        elif revenue >= 4000:
            level = 4
        elif revenue >= 2500:
            level = 3
        elif revenue >= 500:
            level = 2
        elif revenue > 0:
            level = 1
        else:
            level = 0

        month_label = month_date.strftime("%b '%y").upper()

        html += f'''<div class="heatmap-cell level-{level}">
            <div class="heatmap-month">{month_label}</div>
            <div class="heatmap-value">{format_currency_short(revenue)}</div>
        </div>
        '''

    return html


def generate_suggestions(session, people, applications, revenues):
    """Generate intelligent suggestions."""
    suggestions = []

    if not people:
        return '''<div class="suggestion-insight">
            <p class="suggestion-highlight">Start adding prospects to build your pipeline</p>
            <p class="suggestion-text">Email scanning will automatically detect applications and meetings from your Gmail and Calendar.</p>
        </div>'''

    # Analyze referral source dependency
    source_values = {}
    total_weighted = Decimal('0')

    for person in people:
        if person.status != PersonStatus.COLD:
            source = person.source or 'Unknown'
            if source not in source_values:
                source_values[source] = Decimal('0')
            source_values[source] += person.weighted_value or Decimal('0')
            total_weighted += person.weighted_value or Decimal('0')

    # Check for single-source dependency
    if total_weighted > 0:
        for source, value in source_values.items():
            if source not in ['Unknown', 'Direct']:
                percentage = float(value / total_weighted * 100)
                if percentage > 50:
                    suggestions.append({
                        'highlight': f"Your pipeline depends heavily on {source} ({int(percentage)}%)",
                        'text': f"{format_currency(value)} weighted pipeline from this source. Consider diversifying your lead sources to reduce risk."
                    })

    # Find people losing momentum
    now = datetime.now()
    for person in people:
        if person.status in [PersonStatus.ACTIVE, PersonStatus.WARM]:
            days_since = (now - person.last_contact).days if person.last_contact else 0
            if days_since > 5:
                suggestions.append({
                    'highlight': f"{person.name} losing momentum - {days_since} days since contact",
                    'text': "Every day you wait reduces close probability. Call TODAY and schedule the next meeting."
                })

    # Highest value prospect
    active = [p for p in people if p.status not in [PersonStatus.COLD, PersonStatus.APPROVED]]
    if active:
        highest = max(active, key=lambda p: float(p.estimated_commission or 0))
        if float(highest.estimated_commission or 0) > 1000:
            suggestions.append({
                'highlight': f"{highest.name} is your highest value prospect",
                'text': f"{format_currency(highest.estimated_commission)} potential commission. Prioritize this relationship."
            })

    # Best month analysis
    if revenues:
        best = max(revenues, key=lambda r: float(r.revenue or 0))
        if best.revenue and float(best.revenue) > 0:
            suggestions.append({
                'highlight': f"Best month: {best.month.strftime('%B %Y')} = {format_currency(best.revenue)}",
                'text': "Analyze what you did differently that month and replicate those activities."
            })

    if not suggestions:
        return '''<div class="suggestion-insight">
            <p class="suggestion-highlight">Keep building your pipeline!</p>
            <p class="suggestion-text">Add more prospects to get personalized suggestions based on your data patterns.</p>
        </div>'''

    html = ""
    for s in suggestions[:6]:
        html += f'''<div class="suggestion-insight">
            <p class="suggestion-highlight">{s['highlight']}</p>
            <p class="suggestion-text">{s['text']}</p>
        </div>
        '''

    return html


def generate_projections(people, weighted_pipeline):
    """Generate performance projections."""
    total_pipeline = sum(float(p.estimated_commission or 0) for p in people if p.status != PersonStatus.COLD)

    # Annualized
    annualized = weighted_pipeline * 12

    # Conservative (25% close rate)
    conservative = total_pipeline * 0.25

    # Determine status
    if weighted_pipeline >= 4000:
        status = "On Track"
        status_class = "ontrack"
    elif weighted_pipeline >= 2500:
        status = "Moderate"
        status_class = "moderate"
    else:
        status = "Behind"
        status_class = "behind"

    return f'''<div class="projection-card">
        <div class="projection-label">Projected This Month</div>
        <div class="projection-value">{format_currency(weighted_pipeline)}</div>
        <div class="projection-sub">Based on weighted pipeline</div>
        <div class="projection-status status-{status_class}">{status}</div>
    </div>
    <div class="projection-card">
        <div class="projection-label">Annualized Revenue</div>
        <div class="projection-value">{format_currency(annualized)}</div>
        <div class="projection-sub">If you sustain current pace</div>
        <div class="projection-status status-ontrack">Trending</div>
    </div>
    <div class="projection-card">
        <div class="projection-label">At 25% Close Rate</div>
        <div class="projection-value">{format_currency(conservative)}</div>
        <div class="projection-sub">Conservative estimate</div>
        <div class="projection-status status-moderate">Conservative</div>
    </div>
    <div class="projection-card">
        <div class="projection-label">Total Pipeline</div>
        <div class="projection-value">{format_currency(total_pipeline)}</div>
        <div class="projection-sub">If all deals close</div>
        <div class="projection-status status-ontrack">Maximum</div>
    </div>'''


if __name__ == '__main__':
    html = generate_dashboard_html()
    with open('dashboard.html', 'w') as f:
        f.write(html)
    print("Dashboard generated: dashboard.html")
