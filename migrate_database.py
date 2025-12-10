"""
Database migration script to add missing columns.
Adds blocker, urgency, and delivered_date columns to applications table.
Ensures MonthlyRevenue table exists.
"""

import os
import logging
from sqlalchemy import create_engine, text, inspect

logger = logging.getLogger(__name__)


def run_migration():
    """Run database migration."""
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        logger.warning("DATABASE_URL not set - skipping migration")
        return True  # Return True so app continues

    # Fix SQLAlchemy 1.4+ compatibility
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)

    engine = create_engine(database_url)

    logger.info("=" * 60)
    logger.info("DATABASE MIGRATION")
    logger.info("=" * 60)

    try:
        with engine.connect() as conn:
            inspector = inspect(engine)

            # Check if applications table exists
            if 'applications' not in inspector.get_table_names():
                logger.warning("Applications table does not exist - will be created by init_db()")
                return True

            logger.info("Applications table exists")

            # Get existing columns
            existing_columns = {col['name'] for col in inspector.get_columns('applications')}
            logger.info(f"Found {len(existing_columns)} existing columns")

            # Columns to add
            columns_to_add = []

            if 'blocker' not in existing_columns:
                columns_to_add.append(('blocker', 'TEXT'))
                logger.info("  -> Will add 'blocker' column")
            else:
                logger.info("  -> 'blocker' column already exists")

            if 'urgency' not in existing_columns:
                columns_to_add.append(('urgency', 'VARCHAR(20)'))
                logger.info("  -> Will add 'urgency' column")
            else:
                logger.info("  -> 'urgency' column already exists")

            if 'delivered_date' not in existing_columns:
                columns_to_add.append(('delivered_date', 'DATE'))
                logger.info("  -> Will add 'delivered_date' column")
            else:
                logger.info("  -> 'delivered_date' column already exists")

            # Add missing columns
            if columns_to_add:
                for col_name, col_type in columns_to_add:
                    try:
                        sql = text(f"ALTER TABLE applications ADD COLUMN IF NOT EXISTS {col_name} {col_type}")
                        conn.execute(sql)
                        conn.commit()
                        logger.info(f"  -> Added '{col_name}' column")
                    except Exception as e:
                        logger.warning(f"  -> Could not add '{col_name}': {e}")
            else:
                logger.info("No columns to add - schema is up to date")

            # Create monthly_revenue table if not exists
            if 'monthly_revenue' not in inspector.get_table_names():
                logger.info("Creating monthly_revenue table...")
                create_table_sql = text("""
                    CREATE TABLE IF NOT EXISTS monthly_revenue (
                        id SERIAL PRIMARY KEY,
                        month DATE UNIQUE,
                        revenue NUMERIC(12, 2) DEFAULT 0,
                        deals_closed INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.execute(create_table_sql)
                conn.commit()
                logger.info("  -> monthly_revenue table created")

                # Seed with default data
                seed_data = [
                    ('2024-12-01', 3526.26, 2),
                    ('2025-01-01', 588.64, 1),
                    ('2025-02-01', 3213.59, 2),
                    ('2025-03-01', 882.95, 1),
                    ('2025-04-01', 5623.05, 3),
                    ('2025-05-01', 2894.99, 2),
                    ('2025-06-01', 298.32, 1),
                    ('2025-07-01', -24.00, 0),
                    ('2025-08-01', 3958.48, 2),
                    ('2025-09-01', 7278.86, 4),
                    ('2025-10-01', 6662.33, 3),
                    ('2025-11-01', 4157.66, 2),
                ]
                for month, revenue, deals in seed_data:
                    insert_sql = text("""
                        INSERT INTO monthly_revenue (month, revenue, deals_closed)
                        VALUES (:month, :revenue, :deals)
                        ON CONFLICT (month) DO NOTHING
                    """)
                    conn.execute(insert_sql, {'month': month, 'revenue': revenue, 'deals': deals})
                conn.commit()
                logger.info("  -> monthly_revenue seeded with historical data")
            else:
                logger.info("monthly_revenue table already exists")

        logger.info("=" * 60)
        logger.info("MIGRATION COMPLETED SUCCESSFULLY")
        logger.info("=" * 60)
        return True

    except Exception as e:
        logger.error(f"Migration error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    success = run_migration()
    if success:
        logger.info("Database is ready!")
    else:
        logger.error("Migration failed!")
        exit(1)
