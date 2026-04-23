"""
Database initialization and management for AMG Skyscraper
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from models import db, User, Website, ScrapingJob, Statistic, AuditLog

logger = logging.getLogger(__name__)


def init_db(app):
    """Initialize database with Flask app context"""
    with app.app_context():
        # Create all tables
        db.create_all()
        logger.info("Database tables created")

        # Create default admin user if not exists
        create_default_admin()

        # Migrate existing websites from JSON config if needed
        migrate_websites_from_json(app)


def create_default_admin():
    """Create default admin user if database is empty"""
    if User.query.filter_by(is_admin=True).first():
        logger.info("Admin user already exists")
        return

    try:
        admin = User(
            username='admin',
            email='admin@amgskyscraper.local',
            is_admin=True,
            is_active=True
        )
        admin.set_password('admin')  # Default password - CHANGE THIS!

        db.session.add(admin)
        db.session.commit()
        logger.info("Default admin user created (username: admin, password: admin)")
        logger.warning("SECURITY: Change default admin password immediately!")

    except Exception as e:
        logger.error(f"Error creating default admin: {e}")
        db.session.rollback()


def migrate_websites_from_json(app):
    """Migrate existing websites from websites_config.json to database"""
    config_file = Path(app.root_path) / 'websites_config.json'

    if not config_file.exists():
        logger.info("No websites_config.json found - skipping migration")
        return

    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)

        websites = config.get('websites', [])

        for website_data in websites:
            # Check if website already exists
            existing = Website.query.filter_by(name=website_data.get('name')).first()
            if existing:
                logger.debug(f"Website {website_data['name']} already in database")
                continue

            # Create new website
            website = Website(
                name=website_data.get('name'),
                description=website_data.get('description', ''),
                url=website_data.get('url'),
                type=website_data.get('type'),
                scraper_class=website_data.get('scraper_class'),
                scraper_file=website_data.get('scraper_file'),
                google_sheet_id=website_data.get('google_sheet_id'),
                image_folder=website_data.get('image_folder'),
                enabled=website_data.get('enabled', False),
                priority=website_data.get('priority', 0),
                total_items=website_data.get('total_items', 0),
                created_by=1,  # Admin user
            )

            # Add scheduling info if available
            scheduling = website_data.get('scheduling', {})
            if scheduling:
                website.scheduling_enabled = scheduling.get('enabled', False)
                website.scheduling_frequency = scheduling.get('frequency')
                website.scheduling_day = scheduling.get('day')
                website.scheduling_time = scheduling.get('time')

            db.session.add(website)
            logger.info(f"Migrated website: {website.name}")

        db.session.commit()
        logger.info(f"Migrated {len(websites)} websites from JSON config")

    except Exception as e:
        logger.error(f"Error migrating websites: {e}")
        db.session.rollback()


def add_website(name, description, url, website_type, scraper_class, scraper_file,
                google_sheet_id=None, image_folder=None, created_by_id=None):
    """Add a new website to the database"""
    try:
        # Check if website already exists
        existing = Website.query.filter_by(name=name).first()
        if existing:
            logger.warning(f"Website {name} already exists")
            return None

        website = Website(
            name=name,
            description=description,
            url=url,
            type=website_type,
            scraper_class=scraper_class,
            scraper_file=scraper_file,
            google_sheet_id=google_sheet_id,
            image_folder=image_folder or f'images/{name.lower()}',
            created_by=created_by_id or 1,
        )

        db.session.add(website)
        db.session.commit()
        logger.info(f"Website added: {name}")
        return website

    except Exception as e:
        logger.error(f"Error adding website: {e}")
        db.session.rollback()
        return None


def update_website(website_id, **kwargs):
    """Update website configuration"""
    try:
        website = Website.query.get(website_id)
        if not website:
            logger.warning(f"Website {website_id} not found")
            return None

        # Update fields
        for key, value in kwargs.items():
            if hasattr(website, key):
                setattr(website, key, value)

        website.updated_at = datetime.utcnow()
        db.session.commit()
        logger.info(f"Website updated: {website.name}")
        return website

    except Exception as e:
        logger.error(f"Error updating website: {e}")
        db.session.rollback()
        return None


def delete_website(website_id):
    """Delete a website from database"""
    try:
        website = Website.query.get(website_id)
        if not website:
            logger.warning(f"Website {website_id} not found")
            return False

        website_name = website.name
        db.session.delete(website)
        db.session.commit()
        logger.info(f"Website deleted: {website_name}")
        return True

    except Exception as e:
        logger.error(f"Error deleting website: {e}")
        db.session.rollback()
        return False


def add_user(username, email, password, is_admin=False):
    """Add a new user to the database"""
    try:
        # Check if user already exists
        existing = User.query.filter_by(username=username).first()
        if existing:
            logger.warning(f"User {username} already exists")
            return None

        user = User(
            username=username,
            email=email,
            is_admin=is_admin,
            is_active=True,
        )
        user.set_password(password)

        db.session.add(user)
        db.session.commit()
        logger.info(f"User added: {username}")
        return user

    except Exception as e:
        logger.error(f"Error adding user: {e}")
        db.session.rollback()
        return None


def get_user(username):
    """Get user by username"""
    return User.query.filter_by(username=username).first()


def get_user_by_id(user_id):
    """Get user by ID"""
    return User.query.get(user_id)


def get_all_users():
    """Get all users"""
    return User.query.all()


def get_all_websites():
    """Get all websites"""
    return Website.query.order_by(Website.priority, Website.name).all()


def get_enabled_websites():
    """Get only enabled websites"""
    return Website.query.filter_by(enabled=True).order_by(Website.priority, Website.name).all()


def record_scraping_job(website_id, user_id=None, status='pending', items_count=0,
                       duration_seconds=0, error_message=None, sheets_written=False):
    """Record a scraping job"""
    try:
        job = ScrapingJob(
            website_id=website_id,
            user_id=user_id,
            status=status,
            items_count=items_count,
            duration_seconds=duration_seconds,
            error_message=error_message,
            sheets_written=sheets_written,
        )

        db.session.add(job)
        db.session.commit()
        logger.info(f"Scraping job recorded: {job.id}")
        return job

    except Exception as e:
        logger.error(f"Error recording scraping job: {e}")
        db.session.rollback()
        return None


def save_statistics(website_id, total_items, items_added, stats_data):
    """Save statistics for a website"""
    try:
        statistic = Statistic(
            website_id=website_id,
            total_items=total_items,
            items_added=items_added,
            raw_statistics=json.dumps(stats_data, ensure_ascii=False),
        )

        db.session.add(statistic)
        db.session.commit()
        logger.info(f"Statistics saved for website {website_id}")
        return statistic

    except Exception as e:
        logger.error(f"Error saving statistics: {e}")
        db.session.rollback()
        return None


def log_audit(user_id, action, resource_type, resource_id=None, details=None,
             ip_address=None, user_agent=None):
    """Log an audit event"""
    try:
        audit = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=json.dumps(details) if details else None,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        db.session.add(audit)
        db.session.commit()
        logger.debug(f"Audit log: {action}")
        return audit

    except Exception as e:
        logger.error(f"Error logging audit event: {e}")
        db.session.rollback()
        return None
