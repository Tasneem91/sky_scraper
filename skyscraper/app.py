"""
AMG Skyscraper - Professional Enterprise-Grade Data Collection Platform
Multi-Website Scraper with User Authentication & Admin Management
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, current_user
import json
import logging
from datetime import datetime
from pathlib import Path
import importlib
import sys
import os

# Import Phase 1 components
from models import db, User
from database import init_db, get_enabled_websites
from auth import login_required, admin_required

try:
    from sheets_integration import GoogleSheetsManager
    SHEETS_AVAILABLE = True
except ImportError:
    SHEETS_AVAILABLE = False
    logging.warning("Google Sheets integration not available - install google-auth libraries")

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create instance directory first (before any database operations)
instance_path = Path('instance')
instance_path.mkdir(exist_ok=True)

# Initialize Flask app
app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False
app.config['SECRET_KEY'] = 'amg-skyscraper-secret-key-change-in-production'  # Change in production!

# Database URI with absolute path (Windows-compatible)
db_path = os.path.abspath(os.path.join('instance', 'amg_skyscraper.db'))
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False  # Suppress deprecation warning

# Initialize database
db.init_app(app)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page'

@login_manager.user_loader
def load_user(user_id):
    """Load user from database by ID"""
    return User.query.get(int(user_id))

# Load configuration
CONFIG_FILE = 'websites_config.json'

def load_config():
    """Load websites configuration from JSON"""
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"Config file {CONFIG_FILE} not found!")
        return None

def save_config(config):
    """Save updated configuration to JSON"""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Error saving config: {e}")
        return False

def get_scraper_instance(website_config):
    """
    Dynamically load and instantiate a scraper class

    Args:
        website_config: Website configuration dictionary

    Returns:
        Scraper instance or None if error
    """
    try:
        scraper_file = website_config.get('scraper_file')
        scraper_class_name = website_config.get('scraper_class')

        if not scraper_file or not scraper_class_name:
            logger.error(f"Missing scraper_file or scraper_class for {website_config.get('id')}")
            return None

        # Import module dynamically
        module_name = scraper_file.replace('/', '.').replace('.py', '')
        try:
            module = importlib.import_module(module_name)
        except ImportError as e:
            logger.warning(f"Cannot import {module_name}: {e}")
            logger.warning(f"Using base scraper instead for {website_config.get('id')}")
            # Return base scraper as fallback
            from scrapers.base_scraper import CarsScraper, RealEstateScraper
            if website_config.get('type') == 'cars':
                return CarsScraper(website_config)
            else:
                return RealEstateScraper(website_config)

        # Get class from module
        scraper_class = getattr(module, scraper_class_name)

        # Instantiate and return
        return scraper_class(website_config)

    except Exception as e:
        logger.error(f"Error loading scraper for {website_config.get('id')}: {e}")
        return None


def write_to_google_sheets(items, website_config):
    """
    Write scraped items to Google Sheets

    Args:
        items: List of item dictionaries
        website_config: Website configuration with google_sheet_id

    Returns:
        True if successful, False otherwise
    """
    if not SHEETS_AVAILABLE:
        logger.warning("Google Sheets not available - skipping write")
        return False

    try:
        sheet_id = website_config.get('google_sheet_id')
        if not sheet_id or sheet_id == 'YOUR-SHEET-ID-HERE':
            logger.warning(f"No valid Google Sheet ID configured for {website_config.get('id')}")
            return False

        logger.info(f"Writing {len(items)} items to Google Sheet: {sheet_id}")

        # Initialize Google Sheets manager
        sheets_manager = GoogleSheetsManager()
        sheets_manager.set_spreadsheet_id(sheet_id)

        if not items:
            logger.warning("No items to write to Google Sheets")
            return False

        # Convert items to rows format for Google Sheets
        # First row is headers
        headers = list(items[0].keys())
        rows = [headers]

        # Add data rows
        for item in items:
            row = [str(item.get(header, '')) for header in headers]
            rows.append(row)

        # Clear existing data (optional - comment out to append instead)
        # sheets_manager.clear_range('Sheet1')

        # Write headers (update first row)
        sheets_manager.update_rows([headers], 'Sheet1!A1')

        # Append data starting from row 2
        if len(rows) > 1:
            sheets_manager.append_rows(rows[1:], 'Sheet1!A2')

        # Format header row
        sheets_manager.format_header('Sheet1!A1:Z1')

        logger.info(f"Successfully wrote {len(items)} items to Google Sheet")
        return True

    except Exception as e:
        logger.error(f"Error writing to Google Sheets: {e}", exc_info=True)
        return False


# ============================================================================
# AUTHENTICATION ROUTES (Phase 1)
# ============================================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login page and handler"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = request.form.get('remember') is not None
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user, remember=remember)
            next_page = request.args.get('next')
            return redirect(next_page if next_page else url_for('index'))
        
        flash('Invalid username or password', 'danger')
    
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    """User registration page and handler"""
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        password_confirm = request.form.get('password_confirm')
        
        # Validate passwords match
        if password != password_confirm:
            flash('Passwords do not match', 'danger')
            return redirect(url_for('register'))
        
        # Check if user exists
        if User.query.filter_by(username=username).first():
            flash('Username already taken', 'danger')
            return redirect(url_for('register'))
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'danger')
            return redirect(url_for('register'))
        
        # Create user
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        flash('Account created! Please log in', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')


@app.route('/logout')
@login_required
def logout():
    """User logout"""
    logout_user()
    flash('You have been logged out', 'info')
    return redirect(url_for('login'))


# ============================================================================
# APPLICATION ROUTES (Protected with @login_required)
# ============================================================================

@app.route('/')
@login_required
def index():
    """Dashboard - home page with website selector"""
    config = load_config()
    if not config:
        return "Error loading configuration", 500

    websites = config.get('websites', [])

    # Group by type
    cars_websites = [w for w in websites if w.get('type') == 'cars']
    realestate_websites = [w for w in websites if w.get('type') == 'realestate']

    return render_template('index.html',
                         cars_websites=cars_websites,
                         realestate_websites=realestate_websites,
                         app_name=config.get('app_name', 'AMG Skyscraper'))


@app.route('/website/<website_id>')
@login_required
def website_detail(website_id):
    """Website detail page - scraper control and statistics"""
    config = load_config()
    website = next((w for w in config['websites'] if w['id'] == website_id), None)

    if not website:
        return "Website not found", 404

    return render_template('website.html', website=website)


@app.route('/statistics/<website_id>')
@login_required
def statistics(website_id):
    """Statistics dashboard for a website"""
    config = load_config()
    website = next((w for w in config['websites'] if w['id'] == website_id), None)

    if not website:
        return "Website not found", 404

    return render_template('statistics.html', website=website)


# ============================================================================
# API ROUTES
# ============================================================================

@app.route('/api/websites')
@login_required
def api_websites():
    """Get all websites"""
    config = load_config()
    return jsonify(config.get('websites', []))


@app.route('/api/website/<website_id>')
@login_required
def api_website_detail(website_id):
    """Get specific website configuration"""
    config = load_config()
    website = next((w for w in config['websites'] if w['id'] == website_id), None)

    if not website:
        return jsonify({'error': 'Website not found'}), 404

    return jsonify(website)


@app.route('/api/run-scraper', methods=['POST'])
@login_required
def api_run_scraper():
    """Execute scraper for a website"""
    data = request.get_json()
    website_id = data.get('website_id')
    listing_type = data.get('listing_type', 'sell')  # NEW: For Damazzle SELL/RENT

    config = load_config()
    website = next((w for w in config['websites'] if w['id'] == website_id), None)

    if not website:
        return jsonify({'error': 'Website not found'}), 404

    if not website.get('enabled'):
        return jsonify({'error': 'Website is disabled'}), 400

    try:
        logger.info(f"Starting scraper for {website_id} (listing_type: {listing_type}) by user {current_user.username}")

        # Get scraper instance (NEW: Handle Damazzle with listing_type)
        if 'damazzle' in website_id.lower():
            try:
                from scrapers.damazzle_scraper import DamazzleScraper
                scraper = DamazzleScraper(website, listing_type=listing_type)
            except ImportError:
                scraper = get_scraper_instance(website)
        else:
            scraper = get_scraper_instance(website)

        if not scraper:
            return jsonify({'error': 'Could not initialize scraper'}), 500

        # Run scraper
        start_time = datetime.now()
        items = scraper.scrape()
        end_time = datetime.now()

        duration = (end_time - start_time).total_seconds()

        # Get statistics
        stats = scraper.get_statistics(items)

        # Write to Google Sheets
        sheets_success = False
        sheets_message = ""
        if items:
            sheets_success = write_to_google_sheets(items, website)
            if sheets_success:
                sheets_message = f"Data successfully written to Google Sheet ID: {website.get('google_sheet_id')}"
            else:
                sheets_message = "Warning: Could not write to Google Sheets (check configuration)"
            logger.info(sheets_message)

        # Update config with run info
        website['last_run'] = end_time.isoformat()
        website['total_items'] = len(items)
        website['last_run_count'] = len(items)

        save_config(config)

        return jsonify({
            'status': 'success',
            'website_id': website_id,
            'listing_type': listing_type,  # NEW: Return selected type
            'items_scraped': len(items),
            'duration_seconds': duration,
            'statistics': stats,
            'sheets_written': sheets_success,
            'sheets_message': sheets_message,
            'message': f'Successfully scraped {len(items)} items in {duration:.1f} seconds'
        })

    except Exception as e:
        logger.error(f"Error running scraper for {website_id}: {e}", exc_info=True)
        return jsonify({
            'status': 'error',
            'error': str(e),
            'message': f'Error scraping {website_id}: {str(e)}'
        }), 500


@app.route('/api/statistics/<website_id>')
@login_required
def api_statistics(website_id):
    """Get statistics for a website"""
    config = load_config()
    website = next((w for w in config['websites'] if w['id'] == website_id), None)

    if not website:
        return jsonify({'error': 'Website not found'}), 404

    stats = {
        'website_id': website_id,
        'total_items': website.get('total_items', 0),
        'last_run': website.get('last_run'),
        'last_run_count': website.get('last_run_count', 0),
        'enabled': website.get('enabled', False),
        'type': website.get('type'),
    }

    return jsonify(stats)


@app.route('/api/enable-website', methods=['POST'])
@login_required
@admin_required
def api_enable_website():
    """Enable a website (admin only)"""
    data = request.get_json()
    website_id = data.get('website_id')
    enabled = data.get('enabled', True)

    config = load_config()
    website = next((w for w in config['websites'] if w['id'] == website_id), None)

    if not website:
        return jsonify({'error': 'Website not found'}), 404

    website['enabled'] = enabled
    if save_config(config):
        return jsonify({
            'status': 'success',
            'website_id': website_id,
            'enabled': enabled,
            'message': f'Website {website_id} is now {"enabled" if enabled else "disabled"}'
        })
    else:
        return jsonify({'error': 'Failed to save configuration'}), 500


@app.route('/api/update-sheet-id', methods=['POST'])
@login_required
@admin_required
def api_update_sheet_id():
    """Update Google Sheet ID for a website (admin only)"""
    data = request.get_json()
    website_id = data.get('website_id')
    sheet_id = data.get('sheet_id')

    if not sheet_id:
        return jsonify({'error': 'sheet_id is required'}), 400

    config = load_config()
    website = next((w for w in config['websites'] if w['id'] == website_id), None)

    if not website:
        return jsonify({'error': 'Website not found'}), 404

    website['google_sheet_id'] = sheet_id
    if save_config(config):
        return jsonify({
            'status': 'success',
            'website_id': website_id,
            'sheet_id': sheet_id,
            'message': f'Google Sheet ID updated for {website_id}'
        })
    else:
        return jsonify({'error': 'Failed to save configuration'}), 500


@app.route('/api/health')
def api_health():
    """Health check endpoint (no auth required)"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'version': '3.0',
        'authenticated': current_user.is_authenticated if current_user else False
    })


# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({'error': 'Not found'}), 404


@app.errorhandler(500)
def server_error(error):
    """Handle 500 errors"""
    logger.error(f"Server error: {error}")
    return jsonify({'error': 'Internal server error'}), 500


if __name__ == '__main__':
    # Create necessary directories
    Path('instance').mkdir(exist_ok=True)
    Path('logs').mkdir(exist_ok=True)
    Path('images').mkdir(exist_ok=True)
    Path('data').mkdir(exist_ok=True)
    Path('templates').mkdir(exist_ok=True)
    Path('static').mkdir(exist_ok=True)

    # Verify config exists
    if not Path(CONFIG_FILE).exists():
        logger.error(f"Configuration file {CONFIG_FILE} not found!")
        logger.error("Please create websites_config.json first")
        sys.exit(1)

    logger.info("Starting AMG Skyscraper Platform")
    
    # Initialize database with app context
    with app.app_context():
        init_db(app)
        logger.info("Database initialized successfully")
    
    logger.info("Visit http://localhost:5000 in your browser")

    # Run Flask app
    app.run(
        debug=True,
        host='0.0.0.0',
        port=5000,
        use_reloader=True
    )