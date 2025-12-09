"""
Main Flask application with scheduled data syncing.
Entry point for the financial dashboard.
"""

import os
import logging
from datetime import datetime

from flask import Flask, Response, jsonify, request
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from database import init_db, get_session, calculate_daily_metrics, SyncStatus, Person
from email_scanner import scan_all_accounts
from calendar_scanner import scan_calendar
from calendly_scanner import scan_calendly
from dashboard_generator import generate_dashboard_html

# Import migration function
from migrate_database import run_migration

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Global variable to store last generated dashboard
_cached_dashboard = None
_last_update = None


def run_full_sync():
    """Run a full sync of all data sources."""
    global _cached_dashboard, _last_update

    logger.info("="*60)
    logger.info("Starting full data sync...")
    logger.info("="*60)

    start_time = datetime.now()

    try:
        # Scan Gmail accounts
        try:
            scan_all_accounts(days_back=7)
        except Exception as e:
            logger.error(f"Gmail scan error: {e}")

        # Scan Google Calendar
        try:
            scan_calendar(days_back=30, days_forward=30)
        except Exception as e:
            logger.error(f"Calendar scan error: {e}")

        # Scan Calendly
        try:
            scan_calendly(days_back=30, days_forward=30)
        except Exception as e:
            logger.error(f"Calendly scan error: {e}")

        # Update metrics
        session = get_session()
        try:
            calculate_daily_metrics(session)
            session.commit()
        finally:
            session.close()

        # Regenerate dashboard
        _cached_dashboard = generate_dashboard_html()
        _last_update = datetime.now()

        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(f"Full sync completed in {elapsed:.1f} seconds")

    except Exception as e:
        logger.error(f"Error during full sync: {e}")
        raise


def initialize_scheduler():
    """Initialize the background scheduler for periodic syncs."""
    scheduler = BackgroundScheduler()

    # Get update interval from environment (default 15 minutes)
    interval_minutes = int(os.getenv('UPDATE_INTERVAL_MINUTES', 15))

    scheduler.add_job(
        func=run_full_sync,
        trigger=IntervalTrigger(minutes=interval_minutes),
        id='full_sync',
        name='Full data sync',
        replace_existing=True,
        max_instances=1
    )

    scheduler.start()
    logger.info(f"Scheduler started - syncing every {interval_minutes} minutes")

    return scheduler


# Flask Routes

@app.route('/')
def dashboard():
    """Serve the main dashboard."""
    global _cached_dashboard, _last_update

    # Generate dashboard if not cached
    if _cached_dashboard is None:
        try:
            _cached_dashboard = generate_dashboard_html()
            _last_update = datetime.now()
        except Exception as e:
            logger.error(f"Error generating dashboard: {e}")
            return f"<h1>Error generating dashboard</h1><p>{str(e)}</p>", 500

    return Response(_cached_dashboard, mimetype='text/html')


@app.route('/api/refresh', methods=['POST'])
def refresh_dashboard():
    """Manually trigger a data refresh."""
    try:
        run_full_sync()
        return jsonify({
            'status': 'success',
            'message': 'Dashboard refreshed',
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error refreshing: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/status')
def sync_status():
    """Get sync status for all data sources."""
    session = get_session()
    try:
        statuses = session.query(SyncStatus).all()
        result = {
            'last_dashboard_update': _last_update.isoformat() if _last_update else None,
            'sources': {}
        }

        for status in statuses:
            result['sources'][status.source] = {
                'last_sync': status.last_sync.isoformat() if status.last_sync else None,
                'last_success': status.last_success.isoformat() if status.last_success else None,
                'error': status.error_message,
                'items_processed': status.items_processed
            }

        return jsonify(result)
    finally:
        session.close()


@app.route('/api/people')
def get_people():
    """Get all people in the pipeline."""
    session = get_session()
    try:
        people = session.query(Person).order_by(Person.weighted_value.desc()).all()
        result = []

        for person in people:
            result.append({
                'id': person.id,
                'name': person.name,
                'email': person.email,
                'phone': person.phone,
                'status': person.status,
                'probability': person.probability,
                'estimated_commission': float(person.estimated_commission or 0),
                'weighted_value': float(person.weighted_value or 0),
                'total_meetings': person.total_meetings,
                'total_hours': float(person.total_hours or 0),
                'last_contact': person.last_contact.isoformat() if person.last_contact else None
            })

        return jsonify(result)
    finally:
        session.close()


@app.route('/api/person/<int:person_id>')
def get_person_details(person_id):
    """Get detailed information about a person."""
    session = get_session()
    try:
        person = session.query(Person).get(person_id)
        if not person:
            return jsonify({'error': 'Person not found'}), 404

        # Get applications
        applications = [{
            'id': app.id,
            'policy_number': app.policy_number,
            'carrier': app.carrier,
            'product': app.product,
            'face_amount': float(app.face_amount or 0),
            'status': app.status,
            'submitted_date': app.submitted_date.isoformat() if app.submitted_date else None
        } for app in person.applications]

        # Get meetings
        meetings = [{
            'id': m.id,
            'type': m.meeting_type,
            'date': m.date.isoformat() if m.date else None,
            'duration': m.duration_minutes,
            'source': m.source
        } for m in person.meetings]

        # Get timeline
        timeline = [{
            'id': t.id,
            'type': t.event_type,
            'description': t.description,
            'timestamp': t.timestamp.isoformat() if t.timestamp else None
        } for t in person.timeline_events]

        return jsonify({
            'id': person.id,
            'name': person.name,
            'email': person.email,
            'phone': person.phone,
            'status': person.status,
            'source': person.source,
            'probability': person.probability,
            'estimated_commission': float(person.estimated_commission or 0),
            'weighted_value': float(person.weighted_value or 0),
            'total_meetings': person.total_meetings,
            'total_hours': float(person.total_hours or 0),
            'created_at': person.created_at.isoformat() if person.created_at else None,
            'last_contact': person.last_contact.isoformat() if person.last_contact else None,
            'applications': applications,
            'meetings': meetings,
            'timeline': timeline
        })
    finally:
        session.close()


@app.route('/health')
def health_check():
    """Health check endpoint for Railway."""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat()
    })


# Initialize on startup
scheduler = None


def create_app():
    """Create and configure the Flask application."""
    global scheduler

    # Initialize database
    try:
        init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.error(f"Database initialization error: {e}")

    # Run database migration
    try:
        logger.info("Running database migration...")
        if run_migration():
            logger.info("Database migration completed successfully")
        else:
            logger.warning("Database migration had issues (see logs above)")
    except Exception as e:
        logger.error(f"Database migration error: {e}")

    # Run initial sync
    try:
        logger.info("Running initial data sync...")
        run_full_sync()
    except Exception as e:
        logger.error(f"Initial sync error: {e}")

    # Start scheduler
    scheduler = initialize_scheduler()

    return app


# For gunicorn
app = create_app()


if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
