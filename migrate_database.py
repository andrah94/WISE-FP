"""
Database migration script to add missing columns.
Adds blocker, urgency, and delivered_date columns to applications table.
Ensures MonthlyRevenue table exists.
"""

import os
import logging
from sqlalchemy import create_engine, text, inspect
from database import Base, MonthlyRevenue

logger = logging.getLogger(__name__)

def run_migration():
    """Run database migration."""
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        logger.error("DATABASE_URL not set")
        return False

    # Fix SQLAlchemy 1.4+ compatibility
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)

    engine = create_engine(database_url)

    logger.info("="*60)
    logger.info("DATABASE MIGRATION - Adding missing columns")
    logger.info("="*60)

    try:
        with engine.connect() as conn:
            inspector = inspect(engine)

            # Check if applications table exists
            if 'applications' not in inspector.get_table_names():
                logger.error("applications table does not exist!")
                return False

            logger.info("✓ Applications table exists")

            # Get existing columns
            existing_columns = {col['name'] for col in inspector.get_columns('applications')}
            logger.info(f"✓ Found {len(existing_columns)} existing columns")

            # Columns to add
            columns_to_add = []

            if 'blocker' not in existing_columns:
                columns_to_add.append(('blocker', 'TEXT'))
                logger.info("  → Will add 'blocker' column")
            else:
                logger.info("  ✓ 'blocker' column already exists")

            if 'urgency' not in existing_columns:
                columns_to_add.append(('urgency', 'VARCHAR(20)'))
                logger.info("  → Will add 'urgency' column")
            else:
                logger.info("  ✓ 'urgency' column already exists")

            if 'delivered_date' not in existing_columns:
                columns_to_add.append(('delivered_date', 'DATE'))
                logger.info("  → Will add 'delivered_date' column")
            else:
                logger.info("  ✓ 'delivered_date' column already exists")

            # Add missing columns
            if columns_to_add:
                logger.info(f"📝 Adding {len(columns_to_add)} missing columns...")

                for col_name, col_type in columns_to_add:
                    sql = f"ALTER TABLE applications ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
                    logger.info(f"  → {sql}")
                    conn.execute(text(sql))
                    conn.commit()
                    logger.info(f"  ✓ Added '{col_name}' column")

                logger.info("✅ All application columns added successfully!")
            else:
                logger.info("✅ All application columns already exist!")

            # Ensure MonthlyRevenue table exists
            logger.info("="*60)
            logger.info("Checking MonthlyRevenue table...")
            logger.info("="*60)

            if 'monthly_revenue' not in inspector.get_table_names():
                logger.info("📝 Creating MonthlyRevenue table...")
                Base.metadata.tables['monthly_revenue'].create(engine)
                logger.info("✅ MonthlyRevenue table created!")
            else:
                logger.info("✓ MonthlyRevenue table already exists")

            logger.info("="*60)
            logger.info("✅ DATABASE MIGRATION COMPLETED SUCCESSFULLY!")
            logger.info("="*60)
            return True

    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

if __name__ == '__main__':
    # Configure logging when run standalone
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    success = run_migration()
    if success:
        logger.info("🚀 Database is ready! You can now run the application.")
    else:
        logger.error("❌ Migration failed. Please check the errors above.")
        exit(1)
