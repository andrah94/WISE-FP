"""
Database models and queries for the financial dashboard.
Uses SQLAlchemy with PostgreSQL.
"""

import os
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy import create_engine, Column, Integer, String, Numeric, DateTime, Date, Text, ForeignKey, Boolean, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.sql import func

Base = declarative_base()

# Status constants
class PersonStatus:
    SCHEDULED = 'SCHEDULED'
    NEW = 'NEW'
    ACTIVE = 'ACTIVE'
    WARM = 'WARM'
    APPLICATION = 'APPLICATION'
    APPROVED = 'APPROVED'
    COLD = 'COLD'

class ApplicationStatus:
    SUBMITTED = 'SUBMITTED'
    UNDERWRITING = 'UNDERWRITING'
    APPROVED = 'APPROVED'
    DELIVERED = 'DELIVERED'

# Stage probabilities
STAGE_PROBABILITIES = {
    PersonStatus.SCHEDULED: 15,
    PersonStatus.NEW: 20,
    PersonStatus.ACTIVE: 30,
    PersonStatus.WARM: 40,
    PersonStatus.APPLICATION: 70,
    PersonStatus.APPROVED: 100,
    PersonStatus.COLD: 5
}


class Person(Base):
    """People (prospects/clients) in the pipeline."""
    __tablename__ = 'people'

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255))
    phone = Column(String(50))
    status = Column(String(50), default=PersonStatus.NEW)
    source = Column(String(100), default='Unknown')  # Adara referral, Direct, etc.
    probability = Column(Integer, default=20)
    estimated_commission = Column(Numeric(12, 2), default=0)
    weighted_value = Column(Numeric(12, 2), default=0)
    total_meetings = Column(Integer, default=0)
    total_hours = Column(Numeric(6, 2), default=0)
    created_at = Column(DateTime, default=func.now())
    last_contact = Column(DateTime, default=func.now())
    notes = Column(Text)

    # Relationships
    applications = relationship("Application", back_populates="person", cascade="all, delete-orphan")
    meetings = relationship("Meeting", back_populates="person", cascade="all, delete-orphan")
    timeline_events = relationship("TimelineEvent", back_populates="person", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_person_name', 'name'),
        Index('idx_person_email', 'email'),
        Index('idx_person_status', 'status'),
    )

    def update_weighted_value(self):
        """Calculate weighted value based on commission and probability."""
        if self.estimated_commission and self.probability:
            self.weighted_value = Decimal(str(self.estimated_commission)) * Decimal(str(self.probability)) / 100
        else:
            self.weighted_value = Decimal('0')

    def apply_probability_decay(self):
        """Reduce probability based on days since last contact."""
        if not self.last_contact:
            return

        days_since_contact = (datetime.now() - self.last_contact).days
        base_prob = STAGE_PROBABILITIES.get(self.status, 20)

        if days_since_contact > 30:
            self.probability = int(base_prob * 0.5)
        elif days_since_contact > 14:
            self.probability = int(base_prob * 0.8)
        elif days_since_contact > 7:
            self.probability = int(base_prob * 0.9)
        else:
            self.probability = base_prob

        self.update_weighted_value()


class Application(Base):
    """Insurance applications linked to people."""
    __tablename__ = 'applications'

    id = Column(Integer, primary_key=True)
    person_id = Column(Integer, ForeignKey('people.id'), nullable=False)
    policy_number = Column(String(50))
    carrier = Column(String(100))  # Transamerica, Nationwide, etc.
    product = Column(String(255))  # Financial Foundation IUL II 2025, etc.
    face_amount = Column(Numeric(12, 2))
    monthly_premium = Column(Numeric(10, 2))
    annual_premium = Column(Numeric(12, 2))
    estimated_commission = Column(Numeric(12, 2))
    status = Column(String(50), default=ApplicationStatus.SUBMITTED)
    submitted_date = Column(Date)
    approval_date = Column(Date)
    file_closure_date = Column(Date)
    created_at = Column(DateTime, default=func.now())
    email_source = Column(String(255))  # Which email account it came from

    person = relationship("Person", back_populates="applications")

    __table_args__ = (
        Index('idx_application_policy', 'policy_number'),
        Index('idx_application_status', 'status'),
    )

    def calculate_commission(self):
        """Calculate estimated commission based on face amount."""
        if not self.face_amount:
            return

        face = float(self.face_amount)

        # Estimate monthly premium based on face amount
        if face >= 100000:
            monthly = face * 0.0025
        elif face >= 50000:
            monthly = face * 0.003
        else:
            monthly = face * 0.0035

        self.monthly_premium = Decimal(str(round(monthly, 2)))
        self.annual_premium = self.monthly_premium * 12
        self.estimated_commission = self.annual_premium * Decimal('0.45')  # 45% first-year


class Meeting(Base):
    """Meetings tracked from Calendar and Calendly."""
    __tablename__ = 'meetings'

    id = Column(Integer, primary_key=True)
    person_id = Column(Integer, ForeignKey('people.id'))
    meeting_type = Column(String(100))  # Financial Education, BPO, Intro, Presentation
    date = Column(DateTime)
    duration_minutes = Column(Integer, default=60)
    source = Column(String(50))  # Calendar, Calendly
    attendees = Column(Text)  # JSON list of attendees
    calendar_event_id = Column(String(255))  # To prevent duplicates
    calendly_event_id = Column(String(255))  # To prevent duplicates
    notes = Column(Text)
    created_at = Column(DateTime, default=func.now())

    person = relationship("Person", back_populates="meetings")

    __table_args__ = (
        Index('idx_meeting_date', 'date'),
        Index('idx_meeting_calendar_id', 'calendar_event_id'),
        Index('idx_meeting_calendly_id', 'calendly_event_id'),
    )


class TimelineEvent(Base):
    """Timeline of events for each person."""
    __tablename__ = 'timeline_events'

    id = Column(Integer, primary_key=True)
    person_id = Column(Integer, ForeignKey('people.id'))
    event_type = Column(String(50))  # APPLICATION, MEETING, STATUS_CHANGE, EMAIL
    description = Column(Text)
    timestamp = Column(DateTime, default=func.now())
    extra_data = Column(Text)  # JSON for additional data

    person = relationship("Person", back_populates="timeline_events")

    __table_args__ = (
        Index('idx_timeline_person', 'person_id'),
        Index('idx_timeline_timestamp', 'timestamp'),
    )


class DailyMetrics(Base):
    """Daily aggregated metrics for reporting."""
    __tablename__ = 'daily_metrics'

    id = Column(Integer, primary_key=True)
    date = Column(Date, unique=True)
    total_pipeline = Column(Numeric(14, 2), default=0)
    weighted_pipeline = Column(Numeric(14, 2), default=0)
    active_prospects = Column(Integer, default=0)
    total_meetings = Column(Integer, default=0)
    total_hours = Column(Numeric(8, 2), default=0)
    revenue_per_hour = Column(Numeric(10, 2), default=0)
    new_applications = Column(Integer, default=0)
    approved_applications = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())


class ProcessedEmail(Base):
    """Track processed emails to avoid duplicates."""
    __tablename__ = 'processed_emails'

    id = Column(Integer, primary_key=True)
    message_id = Column(String(255), unique=True)
    email_account = Column(String(255))
    subject = Column(String(500))
    processed_at = Column(DateTime, default=func.now())

    __table_args__ = (
        Index('idx_processed_email_msg_id', 'message_id'),
    )


class SyncStatus(Base):
    """Track sync status for each data source."""
    __tablename__ = 'sync_status'

    id = Column(Integer, primary_key=True)
    source = Column(String(100), unique=True)  # gmail_gwindom2, calendar, calendly, etc.
    last_sync = Column(DateTime)
    last_success = Column(DateTime)
    error_message = Column(Text)
    items_processed = Column(Integer, default=0)


# Database connection management
_engine = None
_Session = None


def get_engine():
    """Get or create database engine."""
    global _engine
    if _engine is None:
        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            raise ValueError("DATABASE_URL environment variable not set")

        # Handle Railway's postgres:// vs postgresql://
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)

        _engine = create_engine(database_url, pool_pre_ping=True, pool_recycle=300)
    return _engine


def get_session():
    """Get a new database session."""
    global _Session
    if _Session is None:
        _Session = sessionmaker(bind=get_engine())
    return _Session()


def init_db():
    """Initialize database tables."""
    engine = get_engine()
    Base.metadata.create_all(engine)
    print("Database tables created successfully")


def get_or_create_person(session, name, email=None):
    """Get existing person or create new one."""
    # Try to find by email first (more reliable)
    if email:
        person = session.query(Person).filter(
            func.lower(Person.email) == email.lower()
        ).first()
        if person:
            return person, False

    # Try to find by name (case-insensitive)
    if name:
        # Normalize name for comparison
        normalized_name = ' '.join(name.strip().split()).upper()
        person = session.query(Person).filter(
            func.upper(Person.name) == normalized_name
        ).first()
        if person:
            return person, False

    # Create new person
    person = Person(
        name=name.strip().title() if name else 'Unknown',
        email=email,
        status=PersonStatus.NEW,
        probability=STAGE_PROBABILITIES[PersonStatus.NEW]
    )
    session.add(person)
    return person, True


def update_person_stats(session, person_id):
    """Update person's total meetings and hours."""
    person = session.query(Person).get(person_id)
    if not person:
        return

    # Count meetings
    meeting_count = session.query(func.count(Meeting.id)).filter(
        Meeting.person_id == person_id
    ).scalar() or 0

    # Sum hours
    total_minutes = session.query(func.sum(Meeting.duration_minutes)).filter(
        Meeting.person_id == person_id
    ).scalar() or 0

    person.total_meetings = meeting_count
    person.total_hours = Decimal(str(total_minutes / 60))

    # Update commission from applications
    total_commission = session.query(func.sum(Application.estimated_commission)).filter(
        Application.person_id == person_id
    ).scalar() or Decimal('0')

    person.estimated_commission = total_commission
    person.update_weighted_value()


def calculate_daily_metrics(session):
    """Calculate and store daily metrics."""
    from datetime import date
    today = date.today()

    # Get or create today's metrics
    metrics = session.query(DailyMetrics).filter(DailyMetrics.date == today).first()
    if not metrics:
        metrics = DailyMetrics(date=today)
        session.add(metrics)

    # Calculate totals from people
    people = session.query(Person).filter(
        Person.status.notin_([PersonStatus.COLD])
    ).all()

    metrics.total_pipeline = sum(p.estimated_commission or 0 for p in people)
    metrics.weighted_pipeline = sum(p.weighted_value or 0 for p in people)
    metrics.active_prospects = len([p for p in people if p.status in [
        PersonStatus.ACTIVE, PersonStatus.WARM, PersonStatus.APPLICATION
    ]])

    # Meeting stats
    meetings = session.query(Meeting).filter(
        func.date(Meeting.date) >= today - timedelta(days=365)
    ).all()

    metrics.total_meetings = len(meetings)
    metrics.total_hours = Decimal(str(sum(m.duration_minutes or 0 for m in meetings) / 60))

    if metrics.total_hours > 0:
        metrics.revenue_per_hour = metrics.weighted_pipeline / metrics.total_hours

    session.commit()
    return metrics


def check_email_processed(session, message_id):
    """Check if an email has already been processed."""
    return session.query(ProcessedEmail).filter(
        ProcessedEmail.message_id == message_id
    ).first() is not None


def mark_email_processed(session, message_id, email_account, subject):
    """Mark an email as processed."""
    processed = ProcessedEmail(
        message_id=message_id,
        email_account=email_account,
        subject=subject[:500] if subject else None
    )
    session.add(processed)


def update_sync_status(session, source, success=True, error_message=None, items_processed=0):
    """Update sync status for a data source."""
    status = session.query(SyncStatus).filter(SyncStatus.source == source).first()
    if not status:
        status = SyncStatus(source=source)
        session.add(status)

    status.last_sync = datetime.now()
    if success:
        status.last_success = datetime.now()
        status.error_message = None
    else:
        status.error_message = error_message

    status.items_processed = items_processed
    session.commit()
