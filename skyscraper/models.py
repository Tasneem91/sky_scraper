"""
Database models for AMG Skyscraper Platform
Users, Websites, Scraping Jobs, Statistics
"""

from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()


class User(UserMixin, db.Model):
    """User model for authentication and user management"""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    websites = db.relationship('Website', backref='creator', lazy='dynamic', foreign_keys='Website.created_by')
    scraping_jobs = db.relationship('ScrapingJob', backref='user', lazy='dynamic')

    def set_password(self, password):
        """Hash and set password"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Check if provided password matches hash"""
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        """Convert user to dictionary"""
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'is_admin': self.is_admin,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat(),
        }

    def __repr__(self):
        return f'<User {self.username}>'


class Website(db.Model):
    """Website configuration model"""
    __tablename__ = 'websites'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, index=True)
    description = db.Column(db.String(500))
    url = db.Column(db.String(255), nullable=False)
    type = db.Column(db.String(50), nullable=False)  # 'cars', 'realestate', etc.
    scraper_class = db.Column(db.String(120), nullable=False)
    scraper_file = db.Column(db.String(255), nullable=False)
    google_sheet_id = db.Column(db.String(255))
    image_folder = db.Column(db.String(255))
    enabled = db.Column(db.Boolean, default=True)
    priority = db.Column(db.Integer, default=0)

    # Scheduling
    scheduling_enabled = db.Column(db.Boolean, default=False)
    scheduling_frequency = db.Column(db.String(50))  # 'weekly', 'daily', etc.
    scheduling_day = db.Column(db.String(20))  # 'Monday', 'Tuesday', etc.
    scheduling_time = db.Column(db.String(10))  # '09:00'

    # Statistics
    total_items = db.Column(db.Integer, default=0)
    last_run = db.Column(db.DateTime)
    last_run_count = db.Column(db.Integer, default=0)
    last_run_status = db.Column(db.String(50))  # 'success', 'failed', 'pending'

    # Metadata
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    scraping_jobs = db.relationship('ScrapingJob', backref='website', lazy='dynamic', cascade='all, delete-orphan')
    statistics = db.relationship('Statistic', backref='website', lazy='dynamic', cascade='all, delete-orphan')

    def to_dict(self):
        """Convert website to dictionary"""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'url': self.url,
            'type': self.type,
            'enabled': self.enabled,
            'total_items': self.total_items,
            'last_run': self.last_run.isoformat() if self.last_run else None,
            'last_run_count': self.last_run_count,
            'scraper_class': self.scraper_class,
            'scraper_file': self.scraper_file,
            'google_sheet_id': self.google_sheet_id,
        }

    def __repr__(self):
        return f'<Website {self.name}>'


class ScrapingJob(db.Model):
    """Record of scraping jobs"""
    __tablename__ = 'scraping_jobs'

    id = db.Column(db.Integer, primary_key=True)
    website_id = db.Column(db.Integer, db.ForeignKey('websites.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    duration_seconds = db.Column(db.Float)
    items_count = db.Column(db.Integer, default=0)
    items_new = db.Column(db.Integer, default=0)
    items_duplicate = db.Column(db.Integer, default=0)
    status = db.Column(db.String(50), default='pending')  # 'pending', 'running', 'success', 'failed'
    error_message = db.Column(db.Text)
    sheets_written = db.Column(db.Boolean, default=False)

    def to_dict(self):
        """Convert job to dictionary"""
        return {
            'id': self.id,
            'website_id': self.website_id,
            'started_at': self.started_at.isoformat(),
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'duration_seconds': self.duration_seconds,
            'items_count': self.items_count,
            'status': self.status,
        }

    def __repr__(self):
        return f'<ScrapingJob {self.id} for website {self.website_id}>'


class Statistic(db.Model):
    """Statistics for each website"""
    __tablename__ = 'statistics'

    id = db.Column(db.Integer, primary_key=True)
    website_id = db.Column(db.Integer, db.ForeignKey('websites.id'), nullable=False)
    stat_date = db.Column(db.DateTime, default=datetime.utcnow)

    # General stats
    total_items = db.Column(db.Integer, default=0)
    items_added = db.Column(db.Integer, default=0)

    # Category stats (JSON stored as string)
    category_data = db.Column(db.Text)  # JSON: {category: count}

    # Price stats (JSON)
    price_stats = db.Column(db.Text)  # JSON: {avg, min, max, by_brand}

    # Year/Model stats (JSON)
    year_range = db.Column(db.Text)  # JSON: {min_year, max_year, avg_year, distribution}

    # Other
    raw_statistics = db.Column(db.Text)  # Full statistics JSON

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        """Convert statistics to dictionary"""
        return {
            'id': self.id,
            'website_id': self.website_id,
            'stat_date': self.stat_date.isoformat(),
            'total_items': self.total_items,
            'items_added': self.items_added,
        }

    def __repr__(self):
        return f'<Statistic {self.id} for website {self.website_id}>'


class AuditLog(db.Model):
    """Audit log for admin actions"""
    __tablename__ = 'audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    action = db.Column(db.String(255), nullable=False)  # 'add_website', 'edit_website', 'delete_user', etc.
    resource_type = db.Column(db.String(50))  # 'website', 'user', 'scraper', etc.
    resource_id = db.Column(db.Integer)
    details = db.Column(db.Text)  # JSON with details
    ip_address = db.Column(db.String(50))
    user_agent = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<AuditLog {self.action}>'
