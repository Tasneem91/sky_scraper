"""
Authentication helper functions for AMG Skyscraper
"""

import logging
from functools import wraps
from flask import redirect, url_for, flash, request
from flask_login import current_user
from models import User

logger = logging.getLogger(__name__)


def login_required(f):
    """Decorator to require login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in first', 'warning')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """Decorator to require admin privileges"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in first', 'warning')
            return redirect(url_for('login', next=request.url))

        if not current_user.is_admin:
            flash('You do not have permission to access this page', 'danger')
            return redirect(url_for('index'))

        return f(*args, **kwargs)
    return decorated_function


def validate_username(username):
    """Validate username format"""
    if not username or len(username) < 3:
        return False, "Username must be at least 3 characters"

    if len(username) > 80:
        return False, "Username must be less than 80 characters"

    if not username.isalnum() and '-' not in username and '_' not in username:
        return False, "Username can only contain letters, numbers, - and _"

    existing_user = User.query.filter_by(username=username).first()
    if existing_user:
        return False, "Username already taken"

    return True, "Valid"


def validate_email(email):
    """Validate email format"""
    import re

    email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

    if not re.match(email_regex, email):
        return False, "Invalid email format"

    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        return False, "Email already registered"

    return True, "Valid"


def validate_password(password):
    """Validate password strength"""
    if not password or len(password) < 6:
        return False, "Password must be at least 6 characters"

    if len(password) > 255:
        return False, "Password is too long"

    return True, "Valid"


def validate_website_config(name, url, website_type, scraper_class, scraper_file):
    """Validate website configuration"""
    errors = []

    if not name or len(name) < 2:
        errors.append("Website name is required (min 2 characters)")

    if not url or not url.startswith('http'):
        errors.append("Valid URL is required (must start with http/https)")

    if website_type not in ['cars', 'realestate', 'other']:
        errors.append("Invalid website type")

    if not scraper_class or len(scraper_class) < 3:
        errors.append("Scraper class name is required")

    if not scraper_file or not scraper_file.endswith('.py'):
        errors.append("Scraper file must be a Python file (.py)")

    return len(errors) == 0, errors if errors else "Valid"
