from flask import (
    Flask, render_template, request, redirect, url_for, 
    session, flash, jsonify, send_file, send_from_directory,
    make_response, render_template_string
)
from flask_session import Session
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from xhtml2pdf import pisa
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from dotenv import load_dotenv
from datetime import datetime, timedelta, date, timezone
from calendar import monthcalendar
from sqlalchemy import text
import calendar
import csv
import re
import random
import string
import secrets
import os
import json
import io
from io import BytesIO
import base64
import logging

# =====================================================
# SECURITY & LOGGING IMPORTS (NEW)
# =====================================================
from logger_config import setup_logging, get_audit_logger, get_security_logger
from security import (
    create_secure_session, login_required, member_only, admin_only,
    rate_limit, validate_member_id, log_api_access, log_failed_access
)

# =====================================================
# INITIALIZE FLASK APP WITH SECURITY CONFIGURATION
# =====================================================

app = Flask(__name__)

# Load environment variables
load_dotenv()

# =====================================================
# TIER 1: SESSION SECURITY
# =====================================================
app.secret_key = os.getenv("SECRET_KEY", "dev-key-change-in-production")
app.config['SESSION_TYPE'] = 'filesystem'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)  # 30-minute timeout
app.config['SESSION_COOKIE_SECURE'] = True  # HTTPS only
app.config['SESSION_COOKIE_HTTPONLY'] = True  # No JavaScript access
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # CSRF protection
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
    "DATABASE_URL", 
    'sqlite:///room120.db'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configure session
Session(app)
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# =====================================================
# TIER 1: HTTPS ENFORCEMENT (Production)
# =====================================================
if not app.debug and os.getenv("FLASK_ENV") == "production":
    try:
        from flask_talisman import Talisman
        Talisman(
            app,
            force_https=True,
            strict_transport_security=True,
            strict_transport_security_max_age=31536000,
            content_security_policy={
                'default-src': "'self'",
                'script-src': "'self' 'unsafe-inline'",
                'style-src': "'self' 'unsafe-inline'",
                'img-src': "'self' data:",
            }
        )
        logging.info("Flask-Talisman HTTPS enforcement enabled")
    except ImportError:
        logging.warning("Flask-Talisman not installed. Run: pip install flask-talisman")

# =====================================================
# SETUP LOGGING (TIER 2)
# =====================================================
setup_logging()
logger = logging.getLogger(__name__)






UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads', 'invoices')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024  # 32 MB — covers PDFs and CSVs

@app.errorhandler(413)
def request_entity_too_large(e):
    flash('File is too large. Maximum upload size is 32 MB.', 'danger')
    return redirect(request.referrer or url_for('home'))



# ----------------------
# Models
# ----------------------

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(10), nullable=False)
    first_name = db.Column(db.String(100))
    last_name = db.Column(db.String(100))
    email = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    member_number = db.Column(db.String(100))
    active = db.Column(db.Boolean, default=True)
    membership_type = db.Column(db.String(20), default='single')
    staff_role_id = db.Column(db.Integer, db.ForeignKey('staff_role.id'), nullable=True)
    staff_role    = db.relationship('StaffRole', back_populates='users', foreign_keys=[staff_role_id])

    created_at         = db.Column(db.DateTime, default=datetime.utcnow)
    favorite_drink     = db.Column(db.String(200))
    seating_preference = db.Column(db.String(200))
    allergies          = db.Column(db.String(500))
    preferences_notes  = db.Column(db.Text)

    amount_spent = db.Column(db.Float, default=0.0)
    amount_owed = db.Column(db.Float, default=0.0)
    tax_owed = db.Column(db.Float, default=0.0)
    tax_paid = db.Column(db.Float, default=0.0)
    gratuity_owed = db.Column(db.Float, default=0.0)
    gratuity_paid = db.Column(db.Float, default=0.0)
    minimum_adjustment = db.Column(db.Float, default=0.0)


    invoices = db.relationship('Invoice', back_populates='member', cascade='all, delete-orphan')
    reservations = db.relationship('Reservation', back_populates='user', cascade='all, delete-orphan')
    notes_received = db.relationship('Note', foreign_keys='Note.member_id', back_populates='member', cascade='all, delete-orphan')
    notes_written = db.relationship('Note', foreign_keys='Note.author_id', back_populates='author', cascade='all, delete-orphan')
    orders = db.relationship('Order', back_populates='user', cascade='all, delete-orphan')



    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)


class MembershipType(db.Model):
    __tablename__ = 'membership_type'
    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(50), unique=True, nullable=False)   # slug stored on User
    display_name  = db.Column(db.String(100), nullable=False)
    min_spend     = db.Column(db.Float, default=0.0)
    monthly_dues  = db.Column(db.Float, default=0.0)
    description   = db.Column(db.String(500))
    is_active     = db.Column(db.Boolean, default=True)
    sort_order    = db.Column(db.Integer, default=0)


class StaffRole(db.Model):
    __tablename__ = 'staff_role'
    id           = db.Column(db.Integer, primary_key=True)
    name         = db.Column(db.String(50), unique=True, nullable=False)
    display_name = db.Column(db.String(100), nullable=False)
    color        = db.Column(db.String(20), default='secondary')  # Bootstrap colour name
    permissions  = db.Column(db.Text, default='[]')               # JSON array of perm slugs
    users        = db.relationship('User', back_populates='staff_role')


class ClubSetting(db.Model):
    __tablename__ = 'club_setting'
    key   = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.Text, default='')


class SavedReport(db.Model):
    __tablename__ = 'saved_report'
    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(500))
    config      = db.Column(db.Text, nullable=False)   # JSON blob
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
    last_run_at = db.Column(db.DateTime)


class Reservation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    date = db.Column(db.Date)
    time = db.Column(db.Time)
    guests = db.Column(db.Integer)  # <-- Add this line
    notes = db.Column(db.Text)

    user = db.relationship('User', back_populates='reservations')


class Note(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    member_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    member = db.relationship('User', foreign_keys=[member_id], back_populates='notes_received')
    author = db.relationship('User', foreign_keys=[author_id], back_populates='notes_written')


class Invoice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False)
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    
    member_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    member = db.relationship('User', back_populates='invoices')

    # New fields for invoice creation
    date_created = db.Column(db.DateTime, default=datetime.utcnow)
    total_amount = db.Column(db.Float)
    tax_amount = db.Column(db.Float)
    gratuity_amount = db.Column(db.Float)
    notes = db.Column(db.Text)
    is_paid = db.Column(db.Boolean, default=False)
    # Links back to source order(s) for generated invoices
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=True)
    order_ids_json = db.Column(db.Text, nullable=True)

    line_items = db.relationship('InvoiceLineItem', back_populates='invoice', cascade="all, delete-orphan")

class InvoiceLineItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoice.id'))
    description = db.Column(db.String(200))
    amount = db.Column(db.Float)

    invoice = db.relationship('Invoice', back_populates='line_items')



class BlockedDate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(20), unique=True, nullable=False)

class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    date = db.Column(db.String(20), nullable=False)
    time = db.Column(db.String(20), nullable=False)
    description = db.Column(db.Text, nullable=False)


class PrivateEventRequest(db.Model):
    __tablename__ = 'private_event_request'
    id               = db.Column(db.Integer, primary_key=True)
    member_id        = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    event_name       = db.Column(db.String(200), nullable=False)
    event_type       = db.Column(db.String(20), default='buyout')   # 'buyout' | 'hosted_night'
    event_date       = db.Column(db.Date, nullable=False)
    start_time       = db.Column(db.String(10))
    end_time         = db.Column(db.String(10))
    estimated_guests = db.Column(db.Integer)
    description      = db.Column(db.Text)
    special_requests = db.Column(db.Text)
    status           = db.Column(db.String(20), default='pending')  # pending|approved|denied
    admin_notes      = db.Column(db.Text)
    actual_guests    = db.Column(db.Integer)
    submitted_at     = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_at      = db.Column(db.DateTime)
    reviewed_by_id   = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    member      = db.relationship('User', foreign_keys=[member_id], backref='private_event_requests')
    reviewed_by = db.relationship('User', foreign_keys=[reviewed_by_id])



class Application(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    membership_type = db.Column(db.String(50))  # 'individual' or 'corporate'
    first_name = db.Column(db.String(100))
    last_name = db.Column(db.String(100))
    dob = db.Column(db.String(20))
    email = db.Column(db.String(150))
    phone = db.Column(db.String(50))
    company_name = db.Column(db.String(200))
    referred_by = db.Column(db.String(150))
    promo_opt_in = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(20), default='pending')
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.Time, nullable=True)
    subtotal = db.Column(db.Float, nullable=False)
    tax = db.Column(db.Float, nullable=False)
    gratuity = db.Column(db.Float, nullable=False)
    total = db.Column(db.Float, nullable=False)
    paid_by_credit = db.Column(db.Boolean, default=False)
    paid = db.Column(db.Boolean, default=False)  # ✅ Add this line
    notes = db.Column(db.Text, nullable=True)

    user = db.relationship('User', back_populates='orders')
    items = db.relationship('OrderItem', back_populates='order', cascade='all, delete-orphan')


class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'))
    item_name = db.Column(db.String(100))
    price = db.Column(db.Float)

    order = db.relationship('Order', back_populates='items')

class AdminActionLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    action = db.Column(db.String(255), nullable=False)
    details = db.Column(db.Text, nullable=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    admin = db.relationship("User", backref="admin_logs")


class AuditLog(db.Model):
    __tablename__ = 'audit_log'
    id         = db.Column(db.Integer, primary_key=True)
    timestamp  = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    user_id    = db.Column(db.Integer, nullable=True)
    username   = db.Column(db.String(100))
    role       = db.Column(db.String(20))
    category   = db.Column(db.String(50), index=True)   # auth | page_visit | member | order | invoice | reservation | event | report | settings | system
    action     = db.Column(db.String(300))
    details    = db.Column(db.Text)
    ip_address = db.Column(db.String(50))
    path       = db.Column(db.String(300))
    method     = db.Column(db.String(10))




class Table(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50))           # “Booth 3” or “A1”
    capacity = db.Column(db.Integer, default=4)
    
    # Position on seating map
    x = db.Column(db.Integer)                 # pixel or % coordinate
    y = db.Column(db.Integer)
    width = db.Column(db.Integer, default=80)
    height = db.Column(db.Integer, default=80)

    active = db.Column(db.Boolean, default=True)






class LayoutItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(20))  # square, circle, rect, wall-straight, wall-curve
    x = db.Column(db.Integer)
    y = db.Column(db.Integer)
    width = db.Column(db.Integer)
    height = db.Column(db.Integer)

class SeatingItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(50))
    label = db.Column(db.String(200))
    x = db.Column(db.Integer)
    y = db.Column(db.Integer)
    width = db.Column(db.Integer)
    height = db.Column(db.Integer)
    rotation = db.Column(db.Integer)
    extra = db.Column(db.String)

    # CASCADE DELETE
    reservations = db.relationship(
        "SeatingReservation",
        backref="table",
        cascade="all, delete-orphan",
        passive_deletes=True
    )





class SeatingReservation(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    seating_item_id = db.Column(db.Integer, db.ForeignKey("seating_item.id"))
    event_id = db.Column(
        db.Integer,
        db.ForeignKey("event.id", ondelete="CASCADE"),
        nullable=False
    )

    member_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    guest_name = db.Column(db.String(200))
    num_guests = db.Column(db.Integer)
    timeslots = db.Column(db.String)
    notes = db.Column(db.String)
    seats_occupied = db.Column(db.Integer, default=1)


# =====================================================
# TOAST API MODELS (READ-ONLY - for storing synced data)
# =====================================================

class ToastTransaction(db.Model):
    """
    Stores transaction data synced from Toast API.
    READ-ONLY: This data comes from Toast and is never modified here.
    """
    __tablename__ = 'toast_transactions'
    
    id = db.Column(db.Integer, primary_key=True)
    toast_transaction_id = db.Column(db.String(255), unique=True, nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Transaction details from Toast
    transaction_date = db.Column(db.DateTime, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    tax_amount = db.Column(db.Float, default=0.0)
    gratuity_amount = db.Column(db.Float, default=0.0)
    subtotal = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(100))  # e.g., "Credit Card", "Cash"
    
    # Local sync metadata
    synced_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    member = db.relationship('User', backref='toast_transactions')
    items = db.relationship('ToastTransactionItem', back_populates='transaction', cascade='all, delete-orphan')


class ToastTransactionItem(db.Model):
    """Items purchased in a Toast transaction."""
    __tablename__ = 'toast_transaction_items'
    
    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey('toast_transactions.id'), nullable=False)
    toast_item_id = db.Column(db.String(255))
    item_name = db.Column(db.String(255), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    unit_price = db.Column(db.Float, nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    
    transaction = db.relationship('ToastTransaction', back_populates='items')


class ToastMemberSpending(db.Model):
    """
    Aggregated spending data for members.
    Synced from Toast transactions for analytics and display.
    """
    __tablename__ = 'toast_member_spending'
    
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True, nullable=False)
    
    # Spending totals
    total_spent = db.Column(db.Float, default=0.0)
    total_tax_paid = db.Column(db.Float, default=0.0)
    total_gratuity_paid = db.Column(db.Float, default=0.0)
    transaction_count = db.Column(db.Integer, default=0)
    
    # Time-based metrics
    last_transaction_date = db.Column(db.DateTime)
    first_transaction_date = db.Column(db.DateTime)
    
    # Metadata
    last_synced = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    member = db.relationship('User', backref='toast_spending_stats')


class ToastSyncLog(db.Model):
    """
    Tracks when data was synced from Toast.
    Helps prevent duplicate syncs and troubleshoot issues.
    """
    __tablename__ = 'toast_sync_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    sync_type = db.Column(db.String(100), nullable=False)  # e.g., "transactions", "all_members"
    status = db.Column(db.String(20), nullable=False)  # "success", "failed", "partial"
    records_synced = db.Column(db.Integer, default=0)
    error_message = db.Column(db.Text)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    
    
class SetupToken(db.Model):
    __tablename__ = 'setup_token'
    id         = db.Column(db.Integer, primary_key=True)
    token      = db.Column(db.String(64), unique=True, nullable=False, index=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used       = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user       = db.relationship('User', backref='setup_tokens')


class WeeklySalesReport(db.Model):
    """Stores parsed data from weekly Toast Sales Summary PDF uploads."""
    __tablename__ = 'weekly_sales_report'
    id                = db.Column(db.Integer, primary_key=True)
    week_start        = db.Column(db.Date, nullable=False, index=True)
    week_end          = db.Column(db.Date, nullable=False)
    period_label      = db.Column(db.String(150))   # user-defined label, e.g. "July 2026"
    period_type       = db.Column(db.String(20), default='weekly')  # daily/weekly/monthly/quarterly/custom
    location          = db.Column(db.String(200))
    uploaded_at       = db.Column(db.DateTime, default=datetime.utcnow)
    original_filename = db.Column(db.String(255))

    # Revenue Summary
    net_sales      = db.Column(db.Float, default=0.0)
    gratuity       = db.Column(db.Float, default=0.0)
    tax_amount     = db.Column(db.Float, default=0.0)
    tips           = db.Column(db.Float, default=0.0)
    paid_in_total  = db.Column(db.Float, default=0.0)
    total_amount   = db.Column(db.Float, default=0.0)

    # Net Sales Summary
    gross_sales     = db.Column(db.Float, default=0.0)
    sales_discounts = db.Column(db.Float, default=0.0)
    sales_refunds   = db.Column(db.Float, default=0.0)

    # Tip Summary
    tips_collected         = db.Column(db.Float, default=0.0)
    tips_refunded          = db.Column(db.Float, default=0.0)
    tips_withheld          = db.Column(db.Float, default=0.0)
    tips_after_withholding = db.Column(db.Float, default=0.0)

    # Cash Summary
    expected_closeout_cash = db.Column(db.Float, default=0.0)
    actual_closeout_cash   = db.Column(db.Float, default=0.0)
    cash_overage           = db.Column(db.Float, default=0.0)
    total_cash_payments    = db.Column(db.Float, default=0.0)

    # Service Mode Summary
    quick_service_net = db.Column(db.Float, default=0.0)
    table_service_net = db.Column(db.Float, default=0.0)
    total_guests      = db.Column(db.Integer, default=0)
    avg_per_guest     = db.Column(db.Float, default=0.0)
    total_orders      = db.Column(db.Integer, default=0)
    avg_per_order     = db.Column(db.Float, default=0.0)

    # Void Summary
    void_amount      = db.Column(db.Float, default=0.0)
    void_order_count = db.Column(db.Integer, default=0)
    void_item_count  = db.Column(db.Integer, default=0)

    # Discounts & Service Charges
    total_discounts_amount = db.Column(db.Float, default=0.0)
    total_discount_count   = db.Column(db.Integer, default=0)
    total_service_charges  = db.Column(db.Float, default=0.0)
    service_charge_count   = db.Column(db.Integer, default=0)

    # Tax
    taxable_amount = db.Column(db.Float, default=0.0)

    # JSON-encoded breakdowns (variable-length tables)
    payments_json        = db.Column(db.Text, default='[]')
    categories_json      = db.Column(db.Text, default='[]')
    revenue_centers_json = db.Column(db.Text, default='[]')
    dining_options_json  = db.Column(db.Text, default='[]')
    discounts_json       = db.Column(db.Text, default='[]')


class LaborReport(db.Model):
    """Stores parsed Toast labor / employee shift data for a period."""
    __tablename__ = 'labor_report'
    id                = db.Column(db.Integer, primary_key=True)
    week_start        = db.Column(db.Date, nullable=False, index=True)
    week_end          = db.Column(db.Date, nullable=False)
    period_label      = db.Column(db.String(150))
    period_type       = db.Column(db.String(20), default='weekly')
    uploaded_at       = db.Column(db.DateTime, default=datetime.utcnow)
    original_filename = db.Column(db.String(255))

    # Hour totals
    total_hours    = db.Column(db.Float, default=0.0)
    regular_hours  = db.Column(db.Float, default=0.0)
    overtime_hours = db.Column(db.Float, default=0.0)
    shift_count    = db.Column(db.Integer, default=0)
    employee_count = db.Column(db.Integer, default=0)

    # Cost totals
    total_cost    = db.Column(db.Float, default=0.0)
    regular_cost  = db.Column(db.Float, default=0.0)
    overtime_cost = db.Column(db.Float, default=0.0)

    # JSON breakdowns
    employees_json   = db.Column(db.Text, default='[]')  # [{name, job, hours, regular_pay, ot_pay, total_pay}]
    jobs_json        = db.Column(db.Text, default='[]')  # [{job, hours, cost}]


BACKUP_ADMIN_USERNAME = "backupadmin"
BACKUP_ADMIN_PASSWORD = "room120secure"




# ----------------------
# Routes
# ----------------------
@app.before_request
def enable_foreign_keys():
    db.session.execute(text('PRAGMA foreign_keys = ON'))


@app.route('/toast/sales')
def toast_sales():
    data = toast_api_get("sales")  # Replace with real endpoint later
    return render_template("toast_sales.html", sales_data=data)


# =====================================================
# CONTEXT PROCESSOR - Make user available in templates
# =====================================================
app.jinja_env.globals['enumerate'] = enumerate
app.jinja_env.filters['fromjson'] = json.loads


@app.context_processor
def inject_globals():
    """Inject current user and membership types into every template."""
    user = None
    if session.get('user_id'):
        user = User.query.get(session.get('user_id'))
    try:
        all_types = MembershipType.query.order_by(MembershipType.sort_order, MembershipType.display_name).all()
    except Exception:
        all_types = []
    type_map = {t.name: t for t in all_types}
    active_types = [t for t in all_types if t.is_active]
    return dict(
        current_user=user,
        membership_types=active_types,
        all_membership_types=all_types,
        membership_type_map=type_map,
    )


def log_audit(category, action, details=None):
    """Write one audit entry. Safe to call anywhere — never raises."""
    try:
        uid = session.get('user_id')
        entry = AuditLog(
            user_id   = uid if isinstance(uid, int) else None,
            username  = session.get('username', 'system'),
            role      = session.get('role', ''),
            category  = category,
            action    = action,
            details   = details,
            ip_address= request.remote_addr,
            path      = request.path,
            method    = request.method,
        )
        db.session.add(entry)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        app.logger.error(f"Audit log write failed: {exc}")


@app.route('/favicon.ico')
def favicon():
    resp = send_from_directory(
        os.path.join(app.root_path, 'static', 'assets'),
        'room120_logo.png',
        mimetype='image/png',
    )
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp


# Capture every authenticated GET (page visit) automatically
_SKIP_AUDIT_PATHS = {'/static', '/favicon.ico'}
_SKIP_AUDIT_ENDPOINTS = {'static'}

@app.after_request
def auto_audit_page_visit(response):
    try:
        if (request.method == 'GET'
                and session.get('user_id')
                and not request.path.startswith('/static/')
                and request.endpoint not in _SKIP_AUDIT_ENDPOINTS):
            uid = session.get('user_id')
            entry = AuditLog(
                user_id   = uid if isinstance(uid, int) else None,
                username  = session.get('username', ''),
                role      = session.get('role', ''),
                category  = 'page_visit',
                action    = f'Visited {request.path}',
                details   = f'Status {response.status_code} · endpoint={request.endpoint}',
                ip_address= request.remote_addr,
                path      = request.path,
                method    = 'GET',
            )
            db.session.add(entry)
            db.session.commit()
    except Exception as exc:
        db.session.rollback()
        app.logger.error(f"Auto audit failed: {exc}")
    return response


def get_setting(key, default=''):
    s = ClubSetting.query.get(key)
    return s.value if s else default

def set_setting(key, value):
    s = ClubSetting.query.get(key)
    if s:
        s.value = str(value)
    else:
        db.session.add(ClubSetting(key=key, value=str(value)))


def authorized(*perms):
    """True if the current session user may perform all of the listed actions.
    Admins always pass. Staff pass only if their role includes every perm.
    Members and unauthenticated users always fail."""
    role = session.get('role')
    if role == 'admin':
        return True
    if role == 'staff':
        user_perms = set(session.get('permissions', []))
        return all(p in user_perms for p in perms)
    return False


# Register after definition so the function exists at assignment time
app.jinja_env.globals['authorized'] = authorized


PERMISSIONS = {
    'Members': {
        'view_members':         'View members list & search',
        'view_member_profile':  'View individual member profiles',
        'add_member':           'Add new members',
        'edit_member':          'Edit member details',
        'delete_member':        'Delete a member',
        'bulk_delete_members':  'Bulk delete members',
        'toggle_member_active': 'Activate / deactivate members',
        'import_members':       'Import members via CSV',
        'export_members':       'Export members to CSV',
        'manage_admins':        'Manage admin & staff accounts',
    },
    'Orders': {
        'view_orders':       'View member orders',
        'add_order':         'Add orders',
        'edit_order':        'Edit orders',
        'delete_order':      'Delete orders',
        'toggle_order_paid': 'Mark orders paid / unpaid',
    },
    'Invoices': {
        'view_invoices':       'View invoices',
        'add_invoice':         'Create invoices manually',
        'edit_invoice':        'Edit invoices',
        'delete_invoice':      'Delete invoices',
        'toggle_invoice_paid': 'Mark invoices paid / unpaid',
        'generate_invoice':    'Generate invoice from orders',
        'upload_invoice':      'Upload invoice PDF files',
    },
    'Reservations': {
        'view_reservations':  'View all reservations',
        'add_reservation':    'Create reservations for members',
        'edit_reservation':   'Edit reservations',
        'delete_reservation': 'Delete reservations',
        'block_dates':        'Block / unblock reservation dates',
    },
    'Events': {
        'view_events':           'View events list',
        'add_event':             'Add events',
        'edit_event':            'Edit events',
        'delete_event':          'Delete events',
        'view_private_events':   'View private event requests',
        'approve_private_event': 'Approve private event requests',
        'deny_private_event':    'Deny / reject private event requests',
        'edit_private_event':    'Edit private event details (guest count, notes)',
        'delete_private_event':  'Delete private event requests',
        'manage_private_events': 'Approve / deny private events (legacy — use above)',
    },
    'Applications': {
        'view_applications':   'View member applications',
        'approve_application': 'Approve applications',
        'deny_application':    'Deny / reject applications',
        'delete_application':  'Delete applications',
    },
    'Notes': {
        'view_notes':  'View member notes',
        'add_note':    'Add notes to members',
        'edit_note':   'Edit notes',
        'delete_note': 'Delete notes',
    },
    'Reports & Analytics': {
        'view_analytics':      'View analytics dashboard',
        'view_sales_report':   'View sales report',
        'view_reports':        'View saved reports',
        'create_report':       'Create / save new reports',
        'edit_report':         'Edit saved reports',
        'delete_report':       'Delete saved reports',
        'export_report':       'Export reports to CSV',
        'view_sales_dashboard':  'View weekly Toast Sales Dashboard',
        'upload_sales_report':   'Upload weekly Toast Sales PDF',
        'delete_sales_report':   'Delete uploaded weekly sales reports',
        'view_labor_dashboard':  'View Labor & Payroll Dashboard',
        'upload_labor_report':   'Upload Toast Labor ZIP',
        'delete_labor_report':   'Delete uploaded labor reports',
    },
    'Seating': {
        'view_seating':   'View seating map',
        'edit_seating':   'Edit seating layout & assignments',
        'delete_seating': 'Remove seating assignments',
    },
    'Shift Planner': {
        'view_shift_planner': 'View & use the shift planner',
        'edit_shift_planner': 'Edit shift plans & download PDFs',
    },
    'Settings & System': {
        'view_settings':           'View settings page',
        'edit_settings':           'Edit club settings',
        'manage_membership_types': 'Add / edit / delete membership types',
        'manage_roles':            'Manage staff roles & permissions',
        'view_audit':              'View audit log',
        'clear_audit':             'Clear audit log entries',
        'export_backup':           'Export full database backup',
        'import_backup':           'Restore database from backup',
    },
}
app.jinja_env.globals['PERMISSIONS'] = PERMISSIONS


SETTING_DEFAULTS = {
    # Club Info
    'club_name':                  'Room 120',
    'club_tagline':               '',
    'club_address':               '',
    'club_phone':                 '',
    'club_email':                 '',
    # Fiscal Year
    'fiscal_year_start_month':    '1',
    # Reservations
    'max_guests_per_reservation': '20',
    'max_advance_booking_days':   '90',
    'min_advance_booking_hours':  '24',
    'max_reservations_per_month': '0',
    # Billing
    'minimum_spend_period':       'annual',
    'late_fee_percentage':        '0',
    'grace_period_days':          '0',
    # Applications
    'applications_open':          'true',
    # Notifications
    'notify_on_new_application':  'false',
    'notify_on_invoice_created':  'false',
    'notify_email':               '',
}


def seed_membership_types():
    """Create default membership types if the table is empty."""
    if MembershipType.query.count() == 0:
        defaults = [
            MembershipType(name='single',    display_name='Single',    min_spend=3000.0, monthly_dues=0.0, sort_order=0),
            MembershipType(name='corporate', display_name='Corporate', min_spend=5000.0, monthly_dues=0.0, sort_order=1),
        ]
        db.session.add_all(defaults)
        db.session.commit()


def seed_club_settings():
    """Insert missing setting keys with their defaults."""
    for key, default in SETTING_DEFAULTS.items():
        if not ClubSetting.query.get(key):
            db.session.add(ClubSetting(key=key, value=default))
    db.session.commit()

@app.route('/admin/send-setup-link/<int:user_id>', methods=['POST'])
def send_setup_link(user_id):
    if not authorized('edit_member'):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    member = User.query.get_or_404(user_id)
    if not member.email:
        return jsonify({'success': False, 'error': 'This member has no email address on file.'})

    # Invalidate any previous unused tokens for this user
    SetupToken.query.filter_by(user_id=user_id, used=False).delete()

    token      = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(hours=48)
    db.session.add(SetupToken(token=token, user_id=user_id, expires_at=expires_at))
    db.session.commit()

    setup_url = url_for('setup_account', token=token, _external=True)

    log_audit('member', f'Setup link generated for {member.first_name} {member.last_name}',
              f'token_expires={expires_at.isoformat()}')

    return jsonify({
        'success':     True,
        'setup_url':   setup_url,
        'member_name': f'{member.first_name} {member.last_name}',
    })


@app.route('/setup/<token>', methods=['GET', 'POST'])
def setup_account(token):
    st = SetupToken.query.filter_by(token=token, used=False).first()

    if not st:
        return render_template('setup_account.html',
                               error='This setup link is invalid or has already been used.')
    if st.expires_at < datetime.utcnow():
        return render_template('setup_account.html',
                               error='This setup link has expired. Contact the club for a new one.')

    member = st.user
    errors = []

    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm  = request.form.get('confirm_password', '')
        phone    = request.form.get('phone', '').strip()

        if len(password) < 8:
            errors.append('Password must be at least 8 characters.')
        if password != confirm:
            errors.append('Passwords do not match.')

        if not errors:
            member.set_password(password)
            if phone:
                member.phone = phone
            st.used = True
            db.session.commit()

            session.clear()
            session['user_id']  = member.id
            session['role']     = member.role
            session['username'] = member.username
            if member.role == 'staff' and member.staff_role:
                session['permissions'] = json.loads(member.staff_role.permissions or '[]')

            log_audit('auth', f'Account setup completed: {member.first_name} {member.last_name}', '')
            flash(f'Welcome to Room 120, {member.first_name}! Your account is ready.', 'success')
            return redirect(url_for('home'))

    return render_template('setup_account.html', member=member, errors=errors)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # Backup Admin Login
        if username == BACKUP_ADMIN_USERNAME and password == BACKUP_ADMIN_PASSWORD:
            session['user_id'] = 'backup_admin'
            session['username'] = BACKUP_ADMIN_USERNAME
            session['role'] = 'admin'
            log_audit('auth', 'Logged in (backup admin)', f'IP: {request.remote_addr}')
            flash('Logged in as Backup Admin.', 'success')
            return redirect(url_for('home'))

        # Normal User Login
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            if not user.active:
                log_audit('auth', f'Login blocked — account inactive: {username}', f'IP: {request.remote_addr}')
                flash('Your account is deactivated. Please contact an administrator.', 'danger')
                return redirect(url_for('login'))

            session['user_id'] = user.id
            session['username'] = user.username
            if user.role == 'admin':
                session['role'] = 'admin'
                session['permissions'] = []
            elif user.role == 'staff':
                session['role'] = 'staff'
                sr = user.staff_role
                session['permissions'] = json.loads(sr.permissions or '[]') if sr else []
                session['staff_role_id'] = user.staff_role_id
            else:
                session['role'] = 'member'
                session['permissions'] = []
            log_audit('auth', f'Logged in', f'Role: {session["role"]} · IP: {request.remote_addr}')
            flash('Logged in successfully.', 'success')
            return redirect(url_for('home'))
        else:
            log_audit('auth', f'Failed login attempt: {username}', f'IP: {request.remote_addr}')
            flash('Invalid credentials.', 'danger')
    return render_template('login.html')


@app.route('/logout')
def logout():
    log_audit('auth', 'Logged out')
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
def public_home():
    return render_template('public_home.html')


@app.route('/home')
def home():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    
    user = User.query.get(session.get('user_id'))

    # Set default view_as_member if not set
    if 'view_as_member' not in session:
        session['view_as_member'] = False

    return render_template(
        'home.html',
        current_user=user,
        view_as_member=session['view_as_member']
    )


@app.route('/toggle_view')
def toggle_view():
    if session.get('role') == 'admin':
        session['view_as_member'] = not session.get('view_as_member', False)
    return redirect(url_for('home'))



@app.route('/dashboard')
def dashboard():
    if not authorized('view_analytics'):
        return redirect(url_for('home'))
    # Get filters
    filter_status = request.args.get('status', '')
    filter_type = request.args.get('type', '')

    members_query = User.query.filter_by(role='member')

    # Apply active/inactive filter
    if filter_status == 'active':
        members_query = members_query.filter_by(active=True)
    elif filter_status == 'inactive':
        members_query = members_query.filter_by(active=False)

    # Apply membership type filter
    if filter_type:
        members_query = members_query.filter_by(membership_type=filter_type)

    members = members_query.all()

    # Serialize members data
    members_data = [
        {
            'id': m.id,
            'username': m.username,
            'first_name': m.first_name,
            'last_name': m.last_name,
            'email': m.email,
            'phone': m.phone,
            'membership_type': m.membership_type,
            'active': m.active,
            'amount_spent': m.amount_spent,
            'amount_owed': m.amount_owed
        }
        for m in members
    ]

    # Counts for all members
    total_members = User.query.filter_by(role='member').count()
    active_members = User.query.filter_by(role='member', active=True).count()
    inactive_members = User.query.filter_by(role='member', active=False).count()
    # Dynamic counts per membership type
    all_types = MembershipType.query.order_by(MembershipType.sort_order, MembershipType.display_name).all()
    type_counts = [
        {'name': t.name, 'display_name': t.display_name,
         'count': User.query.filter_by(role='member', membership_type=t.name).count()}
        for t in all_types
    ]
    # Keep legacy vars so existing template references don't break during transition
    corporate_count = next((x['count'] for x in type_counts if x['name'] == 'corporate'), 0)
    single_count    = next((x['count'] for x in type_counts if x['name'] == 'single'), 0)

    # Financial summaries
    total_outstanding = sum((m.amount_owed or 0) for m in members)
    total_spent = sum((m.amount_spent or 0) for m in members)

    # Member Balance Chart Data
    member_labels = []
    member_balances = []

    for m in members:
        label = " ".join(filter(None, [m.first_name, m.last_name])) or f"Member {m.id}"
        balance = (m.amount_owed or 0) + (m.amount_spent or 0)
        member_labels.append(label)
        member_balances.append(round(balance, 2))

    # Total Reservations
    total_reservations = Reservation.query.count()

    # Recent Reservations
    recent_reservations = Reservation.query.order_by(Reservation.date.desc(), Reservation.time.desc()).limit(5).all()

    # Serialize reservations data
    reservations_data = [
        {
            'id': r.id,
            'date': r.date.strftime('%Y-%m-%d'),
            'time': r.time.strftime('%H:%M') if r.time else None,
            'user': {
                'first_name': r.user.first_name if r.user else None,
                'last_name': r.user.last_name if r.user else None
            } if r.user else None,
            'guests': r.guests,
            'notes': r.notes
        }
        for r in recent_reservations
    ]

    return render_template('dashboard.html',
        total_members=total_members,
        active_members=active_members,
        inactive_members=inactive_members,
        corporate_count=corporate_count,
        single_count=single_count,
        type_counts=type_counts,
        total_reservations=total_reservations,
        total_outstanding=round(total_outstanding, 2),
        total_spent=round(total_spent, 2),
        member_labels=member_labels,
        member_balances=member_balances,
        filter_status=filter_status,
        filter_type=filter_type,
        members=members_data,
        reservations=reservations_data
    )

@app.route('/reservations', methods=['GET', 'POST'])
def reservations():
    if not session.get('user_id'):
        return redirect(url_for('login'))

    current_user = User.query.get(session['user_id'])
    is_staff     = current_user.role in ('admin', 'staff')
    blocked_dates = [b.date for b in BlockedDate.query.all()]
    error = None

    # Pre-filled values from RSVP links
    prefill_date = request.args.get('date')
    prefill_time = request.args.get('time')
    prefill_note = request.args.get('note')

    # For admins/staff: list of members to book on behalf of
    all_members = (
        User.query.filter_by(role='member', active=True)
            .order_by(User.last_name, User.first_name).all()
        if is_staff else []
    )

    if request.method == 'POST':
        date_str   = request.form['date']
        time_str   = request.form['time']
        guests_str = request.form['guests']
        notes      = request.form.get('notes', '')

        # Determine whose reservation this is
        if is_staff:
            for_member_id = request.form.get('for_member_id', '').strip()
            if for_member_id:
                target_user = User.query.get(int(for_member_id))
                if not target_user:
                    error = "Selected member not found."
                    return render_template('reservations.html',
                                           reservations=[], blocked_dates=blocked_dates,
                                           error=error, all_members=all_members,
                                           is_staff=is_staff)
            else:
                target_user = current_user
        else:
            target_user = current_user

        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            error = "Invalid date format."
            return render_template('reservations.html', reservations=[], blocked_dates=blocked_dates,
                                   error=error, all_members=all_members, is_staff=is_staff)

        try:
            time_obj = datetime.strptime(time_str, '%H:%M').time()
        except ValueError:
            error = "Invalid time format."
            return render_template('reservations.html', reservations=[], blocked_dates=blocked_dates,
                                   error=error, all_members=all_members, is_staff=is_staff)

        try:
            guests_int = int(guests_str)
        except ValueError:
            error = "Guests must be a number."
            return render_template('reservations.html', reservations=[], blocked_dates=blocked_dates,
                                   error=error, all_members=all_members, is_staff=is_staff)

        if date_str in blocked_dates:
            error = "Sorry, this date is blocked for reservations."
        else:
            new_reservation = Reservation(
                user_id=target_user.id,
                date=date_obj,
                time=time_obj,
                guests=guests_int,
                notes=notes
            )
            db.session.add(new_reservation)
            db.session.commit()
            log_audit('reservation', f'Reservation created for {target_user.first_name} {target_user.last_name}',
                      f'By: {current_user.username} · Date: {date_str} · Time: {time_str} · Guests: {guests_int}')
            flash(f'Reservation booked for {target_user.first_name} {target_user.last_name}.', 'success')
            return redirect(url_for('reservations'))

    my_reservations = Reservation.query.filter_by(user_id=current_user.id).all()

    return render_template(
        'reservations.html',
        reservations=my_reservations,
        blocked_dates=blocked_dates,
        error=error,
        prefill_date=prefill_date,
        prefill_time=prefill_time,
        prefill_note=prefill_note,
        all_members=all_members,
        is_staff=is_staff,
        current_user=current_user,
    )


@app.route('/admin/reservations')
def admin_reservations():
    if not authorized('view_reservations'):
        return redirect(url_for('home'))

    all_reservations = Reservation.query.all()
    raw_blocked = BlockedDate.query.all()

    # Parse string dates into date objects for template display
    for b in raw_blocked:
        try:
            b.parsed = datetime.strptime(b.date, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            b.parsed = None

    blocked_dates = raw_blocked

    # Convert reservation times to datetime.time if stored as strings
    for res in all_reservations:
        if isinstance(res.time, str):
            try:
                res.time = datetime.strptime(res.time, '%H:%M:%S').time()
            except ValueError:
                try:
                    res.time = datetime.strptime(res.time, '%H:%M').time()
                except ValueError:
                    pass  # Leave it unchanged if invalid

    return render_template(
        'admin_reservations.html',
        reservations=all_reservations,
        blocked_dates=blocked_dates
    )
BLOCKED_DATES = []

@app.route('/admin/block-date', methods=['POST'])
def block_date():
    if not authorized('block_dates'):
        return redirect(url_for('home'))

    date = request.form['blocked_date']
    existing = BlockedDate.query.filter_by(date=date).first()

    if not existing:
        db.session.add(BlockedDate(date=date))
        db.session.commit()
        log_audit('reservation', f'Date blocked: {date}')

    return redirect(url_for('admin_reservations'))

@app.route('/admin/unblock-date/<int:id>', methods=['POST'])
def unblock_date(id):
    if not authorized('block_dates'):
        return redirect(url_for('home'))

    blocked = BlockedDate.query.get_or_404(id)
    log_audit('reservation', f'Date unblocked: {blocked.date}')
    db.session.delete(blocked)
    db.session.commit()

    return redirect(url_for('admin_reservations'))


@app.route('/reservations/edit/<int:reservation_id>', methods=['GET', 'POST'])
def edit_reservation(reservation_id):
    reservation = Reservation.query.get_or_404(reservation_id)

    if request.method == 'POST':
        try:
            # Get form values
            date_str = request.form['date']
            time_str = request.form['time']
            guests_str = request.form['guests']
            notes = request.form['notes']

            # Convert date string to date object
            reservation.date = datetime.strptime(date_str, '%Y-%m-%d').date()

            # Convert time string to time object
            reservation.time = datetime.strptime(time_str, '%H:%M').time()

            # Convert guests to int
            reservation.guests = int(guests_str)

            # Notes
            reservation.notes = notes

            db.session.commit()
            log_audit('reservation', f'Reservation updated', f'ID: {reservation_id} · Date: {date_str} · Guests: {guests_str}')
            return redirect(url_for('view_member', user_id=reservation.user_id))
        
        except ValueError:
            flash('Invalid input. Please check your date, time, and number of guests.', 'danger')
            return render_template('edit_reservation.html', reservation=reservation)

    return render_template('edit_reservation.html', reservation=reservation)




@app.route('/reservations/delete/<int:reservation_id>', methods=['POST'])
def delete_reservation(reservation_id):
    reservation = Reservation.query.get_or_404(reservation_id)

    # Restrict access: Only authorized staff/admin or the reservation owner can delete
    if not authorized('delete_reservation') and session.get('user_id') != reservation.user_id:
        return redirect(url_for('home'))

    owner_id = reservation.user_id
    log_audit('reservation', f'Reservation deleted', f'ID: {reservation_id} · Date: {reservation.date} · Guests: {reservation.guests}')
    db.session.delete(reservation)
    db.session.commit()
    return redirect(url_for('view_member', user_id=owner_id))


@app.route("/seating_map")
def seating_map():
    event_id = request.args.get("event_id")

    events = Event.query.all()
    items = SeatingItem.query.all()
    members = User.query.filter_by(role="member").all()

    selected_event = Event.query.get(event_id) if event_id else None

    reservation_map = {}
    member_rsvp_map = {}
    event_rsvps = []

    if selected_event:
        for r in SeatingReservation.query.filter_by(event_id=selected_event.id).all():
            reservation_map[r.seating_item_id] = r

        try:
            event_date = datetime.strptime(selected_event.date, '%Y-%m-%d').date()
            for r in Reservation.query.filter_by(date=event_date).all():
                if r.user:
                    info = {
                        'id': r.user_id,
                        'name': " ".join(filter(None, [r.user.first_name, r.user.last_name])) or f"Member {r.user_id}",
                        'guests': r.guests or 1,
                        'time': r.time.strftime('%I:%M %p') if r.time else '',
                        'notes': r.notes or ''
                    }
                    member_rsvp_map[r.user_id] = info
                    event_rsvps.append(info)
        except Exception:
            pass

    return render_template(
        "seating_map.html",
        events=events,
        items=items,
        selected_event=selected_event,
        members=members,
        reservation_map=reservation_map,
        member_rsvp_map=member_rsvp_map,
        event_rsvps=event_rsvps
    )

@app.route("/download_seating_pdf", methods=["POST"])
def download_seating_pdf():
    # Expect JSON: { "image": "data:image/png;base64,...." }
    data = request.get_json(silent=True) or {}
    img_data = data.get("image")

    if not img_data or "," not in img_data:
        return jsonify({"error": "Invalid or missing image data"}), 400

    # Strip header "data:image/png;base64,..."
    try:
        header, encoded = img_data.split(",", 1)
    except ValueError:
        return jsonify({"error": "Malformed image data"}), 400

    try:
        image_bytes = base64.b64decode(encoded)
    except Exception:
        return jsonify({"error": "Failed to decode image data"}), 400

    # Wrap image bytes in a stream
    image_stream = io.BytesIO(image_bytes)
    image_stream.seek(0)

    # Create PDF in memory
    pdf_buffer = io.BytesIO()
    c = canvas.Canvas(pdf_buffer, pagesize=letter)
    page_width, page_height = letter

    # Wrap the image stream with ImageReader (IMPORTANT – this fixes corrupt PDFs)
    img = ImageReader(image_stream)
    img_width, img_height = img.getSize()

    # Fit the image nicely on the page with margins
    max_w = page_width - 60  # 30pt margin each side
    max_h = page_height - 120  # some top/bottom margin

    scale = min(max_w / img_width, max_h / img_height)
    draw_w = img_width * scale
    draw_h = img_height * scale

    x = (page_width - draw_w) / 2
    y = (page_height - draw_h) / 2

    # Draw image on PDF
    c.drawImage(img, x, y, width=draw_w, height=draw_h)
    c.showPage()
    c.save()

    pdf_buffer.seek(0)

    return send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name="seating_map.pdf"
    )


@app.route("/seating-map/members")
def seating_members():
    members = User.query.filter_by(role="member").all()

    output = []
    for m in members:
        output.append({
            "id": m.id,
            "name": " ".join(filter(None, [m.first_name, m.last_name])) or f"Member {m.id}",
            "email": m.email
        })

    return jsonify(output)


@app.route("/seating-map/reservations/<int:event_id>")
def get_reservations(event_id):

    reservations = SeatingReservation.query.filter_by(event_id=event_id).all()

    result = []
    for r in reservations:
        result.append({
            "id": r.id,
            "seating_item_id": r.seating_item_id,
            "member_id": r.member_id,
            "guest_name": r.guest_name,
            "num_guests": r.num_guests,
            "timeslots": json.loads(r.timeslots) if r.timeslots else [],
            "notes": r.notes
        })

    return jsonify(result)

@app.route("/load-event-reservations/<int:event_id>")
def load_event_reservations(event_id):
    reservations = SeatingReservation.query.filter_by(event_id=event_id).all()

    result = []
    for r in reservations:
        result.append({
            "id": r.id,
            "table_id": r.seating_item_id,
            "member_id": r.member_id,
            "guest_name": r.guest_name,
            "num_guests": r.num_guests,
            "timeslots": r.timeslots.split(",") if r.timeslots else [],
            "notes": r.notes
        })

    return jsonify(result)


@app.route("/seating/assign", methods=["POST"])
def seating_assign():
    data = request.json

    res = SeatingReservation(
        table_id=data["table_id"],
        member_id=data["member_id"],
        date=datetime.strptime(data["date"], "%Y-%m-%d").date(),
        time=data["time"],
        guest_count=data["guest_count"],
        notes=data.get("notes", "")
    )

    db.session.add(res)
    db.session.commit()

    return {"status": "ok"}


@app.route("/seating/reservations")
def seating_reservations_for_date():
    date_str = request.args.get("date")
    date = datetime.strptime(date_str, "%Y-%m-%d").date()

    reservations = SeatingReservation.query.filter_by(date=date).all()

    data = [{
        "id": r.id,
        "table_id": r.table_id,
        "member": r.member.first_name + " " + r.member.last_name,
        "time": r.time,
        "guest_count": r.guest_count,
        "status": r.status
    } for r in reservations]

    return jsonify(data)


@app.route("/seating-layout")
def seating_layout():
    items = SeatingItem.query.all()
    return render_template("seating_layout.html", items=items)



@app.route("/seating/layout/save", methods=["POST"])
def seating_layout_save():
    data = request.json

    for t in data:
        table = Table.query.get(t["id"])
        table.x = t["x"]
        table.y = t["y"]
        table.width = t["width"]
        table.height = t["height"]

    db.session.commit()

    return {"status": "ok"}

@app.route("/seating/layout/create", methods=["POST"])
def seating_create_table():
    data = request.json

    new_table = Table(
        name=data["name"],
        capacity=data["capacity"],
        x=100,
        y=100,
        width=80,
        height=80,
        active=True
    )

    db.session.add(new_table)
    db.session.commit()

    return {
        "status": "ok",
        "id": new_table.id,
        "name": new_table.name,
        "capacity": new_table.capacity
    }

@app.route("/add-seating-item", methods=["POST"])
def add_seating_item():
    item = SeatingItem(
        kind=request.form["kind"],
        x=int(request.form["x"]),
        y=int(request.form["y"]),
        width=int(request.form["width"]),
        height=int(request.form["height"])
    )
    db.session.add(item)
    db.session.commit()
    return redirect(url_for("seating_layout"))

@app.route("/update-seating-item/<int:item_id>", methods=["POST"])
def update_seating_item(item_id):
    item = SeatingItem.query.get(item_id)
    item.x = int(request.form["x"])
    item.y = int(request.form["y"])
    item.width = int(request.form["width"])
    item.height = int(request.form["height"])
    db.session.commit()
    return redirect(url_for("seating_layout"))

@app.route("/delete-seating-item/<int:item_id>")
def delete_seating_item(item_id):
    item = SeatingItem.query.get(item_id)
    db.session.delete(item)
    db.session.commit()
    return redirect(url_for("seating_layout"))

@app.route('/save_layout', methods=['POST'])
def save_layout():
    if not authorized('edit_seating'):
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"status": "error", "message": "No data received"}), 400

    try:
        # Delete reservations first to avoid FK conflicts, then items
        SeatingReservation.query.delete(synchronize_session=False)
        SeatingItem.query.delete(synchronize_session=False)
        db.session.flush()

        for item in data:
            db_item = SeatingItem(
                kind=item.get("kind"),
                label=item.get("label"),
                x=int(item.get("x") or 0),
                y=int(item.get("y") or 0),
                width=int(item.get("width") or 80),
                height=int(item.get("height") or 80),
                rotation=int(item.get("rotation") or 0),
                extra=item.get("extra")
            )
            db.session.add(db_item)

        db.session.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/save_seating_layout", methods=["POST"])
def save_seating_layout():
    data = request.json.get("items", [])

    for item in data:
        if item.get("id"):
            obj = SeatingItem.query.get(item["id"])
            if obj:
                obj.x = item["x"]
                obj.y = item["y"]
                obj.width = item["width"]
                obj.height = item["height"]
                obj.label = item["label"]
        else:
            obj = SeatingItem(
                kind=item["kind"],
                x=item["x"],
                y=item["y"],
                width=item["width"],
                height=item["height"],
                label=item["label"],
            )
            db.session.add(obj)

    db.session.commit()
    return jsonify({"status": "saved"})


@app.post("/save-table-reservation")
def save_table_reservation():
    data = request.json

    item_id = data["item_id"]
    event_id = data["event_id"]
    member_id = data.get("member_id")
    guest_name = data.get("guest_name", "")
    num_guests = data.get("num_guests", 1)
    timeslots = ",".join(data.get("timeslots", []))
    notes = data.get("notes", "")

    # Check if reservation exists
    res = SeatingReservation.query.filter_by(
        seating_item_id=item_id,
        event_id=event_id
    ).first()

    if not res:
        res = SeatingReservation(seating_item_id=item_id, event_id=event_id)

    res.member_id = member_id
    res.guest_name = guest_name
    res.num_guests = num_guests
    res.timeslots = timeslots
    res.notes = notes

    db.session.add(res)
    db.session.commit()

    return {"status": "success"}

@app.route("/save_all_reservations", methods=["POST"])
def save_all_reservations():
    all_data = request.json

    # Just loop and save everything
    for entry in all_data:
        r = SeatingReservation(
            seating_item_id=entry["seating_item_id"],
            event_id=entry["event_id"],
            member_id=entry.get("member_id"),
            guest_name=entry.get("guest_name"),
            num_guests=entry.get("num_guests"),
            timeslots=",".join(entry.get("timeslots", [])),
            notes=entry.get("notes")
        )
        db.session.add(r)

    db.session.commit()

    return {"status": "saved"}



@app.route("/save_single_reservation", methods=["POST"])
def save_single_reservation():
    data = request.get_json()

    seating_item_id = data.get("seating_item_id")
    event_id = data.get("event_id")

    if not seating_item_id or not event_id:
        return jsonify({"status": "error", "message": "Missing table or event"}), 400

    # Get or create reservation for this table + event
    reservation = SeatingReservation.query.filter_by(
        seating_item_id=seating_item_id,
        event_id=event_id
    ).first()

    if not reservation:
        reservation = SeatingReservation(
            seating_item_id=seating_item_id,
            event_id=event_id
        )
        db.session.add(reservation)

    # Update reservation fields
    member_id  = data.get("member_id")  or None
    guest_name = data.get("guest_name") or None

    # Clearing: delete the record rather than leave an empty row
    if not member_id and not guest_name:
        if reservation.id:  # already persisted
            db.session.delete(reservation)
            db.session.commit()
        return jsonify({"status": "ok", "display_label": "", "seats_occupied": 1})

    # If member exists, ALWAYS override guest name
    if member_id:
        reservation.member_id  = member_id
        reservation.guest_name = None
    else:
        reservation.member_id  = None
        reservation.guest_name = guest_name

    reservation.num_guests     = data.get("num_guests")  or None
    reservation.timeslots      = data.get("timeslots")   or None
    reservation.notes          = data.get("notes")       or None
    seats = int(data.get("seats_occupied") or 1)
    reservation.seats_occupied = max(1, seats)

    db.session.commit()

    # Compute display label for the front-end
    if reservation.member_id:
        member = User.query.get(reservation.member_id)
        label = " ".join(filter(None, [member.first_name, member.last_name])) or "Member"
    else:
        label = reservation.guest_name

    if reservation.seats_occupied and reservation.seats_occupied > 1:
        label += f" ×{reservation.seats_occupied}"

    return jsonify({
        "status": "ok",
        "display_label": label,
        "seats_occupied": reservation.seats_occupied
    })



@app.route("/reset_event_seating/<int:event_id>", methods=["POST"])
def reset_event_seating(event_id):
    try:
        SeatingReservation.query.filter_by(event_id=event_id).delete(synchronize_session=False)
        db.session.commit()
        return jsonify({"status": "ok"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/get_members_json")
def get_members_json():
    members = User.query.filter_by(role="member").all()
    data = []

    for m in members:
        data.append({
            "id": m.id,
            "name": " ".join(filter(None, [m.first_name, m.last_name])) or f"Member {m.id}",
            "email": m.email,
            "phone": m.phone
        })

    return jsonify(data)



@app.route("/load_event", methods=["POST"])
def load_event():
    event_id = request.form.get("event_id")

    items = SeatingItem.query.all()
    reservations = SeatingReservation.query.filter_by(event_id=event_id).all()

    return render_template("partials/map_tables.html",
                           items=items,
                           reservations=reservations)

@app.route('/register_admin', methods=['GET', 'POST'])
def register_admin():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        first_name = request.form['first_name']
        last_name = request.form['last_name']

        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            Flask('Username already exists.')
            return redirect(url_for('register_admin'))

        new_admin = User(
            username=username,
            first_name=first_name,
            last_name=last_name,
            role='admin',
            active=True
        )
        new_admin.set_password(password)

        db.session.add(new_admin)
        db.session.commit()
        log_audit('member', f'Admin account created: {first_name} {last_name}', f'Username: {username}')
        Flask('Admin registered successfully. You can now log in.')
        return redirect(url_for('login'))

    return render_template('register_admin.html')

@app.route('/toggle-admin/<int:user_id>', methods=['POST'])
def toggle_admin(user_id):
    if not authorized('manage_admins'):
        return redirect(url_for('home'))

    admin = User.query.get(user_id)
    if admin and admin.role == 'admin':
        admin.active = not admin.active
        db.session.commit()
        status = 'activated' if admin.active else 'deactivated'
        log_audit('member', f'Admin {status}: {admin.first_name} {admin.last_name}', f'Username: {admin.username}')
    return redirect(url_for('manage_admins'))

@app.route('/manage-admins')
def manage_admins():
    if not authorized('manage_admins'):
        return redirect(url_for('home'))
    admins      = User.query.filter_by(role='admin').all()
    staff_users = User.query.filter_by(role='staff').order_by(User.first_name, User.last_name).all()
    staff_roles = StaffRole.query.order_by(StaffRole.display_name).all()
    return render_template('manage_admins.html', admins=admins,
                           staff_users=staff_users, staff_roles=staff_roles)


@app.route('/edit-admin/<int:user_id>', methods=['GET', 'POST'])
def edit_admin(user_id):
    if not authorized('manage_admins'):
        return redirect(url_for('home'))
    admin = User.query.get_or_404(user_id)
    if request.method == 'POST':
        admin.first_name = request.form['first_name'].strip()
        admin.last_name  = request.form.get('last_name', '').strip()
        admin.username   = request.form['username'].strip()
        admin.email      = request.form.get('email', '').strip() or None
        new_password = request.form.get('password', '').strip()
        if new_password:
            admin.password = generate_password_hash(new_password)
        db.session.commit()
        log_audit('member', f'User updated: {admin.first_name} {admin.last_name}',
                  f'Role: {admin.role} · Username: {admin.username}')
        flash(f'{admin.first_name} {admin.last_name} updated successfully.', 'success')
        return redirect(url_for('manage_admins'))
    return render_template('edit_admin.html', admin=admin)

@app.route('/delete-admin/<int:user_id>', methods=['POST'])
def delete_admin(user_id):
    if session.get('role') != 'admin':  # delete admin is superadmin-only
        return redirect(url_for('home'))
    admin = User.query.get(user_id)
    if admin:
        log_audit('member', f'Admin deleted: {admin.first_name} {admin.last_name}', f'Username: {admin.username}')
        db.session.delete(admin)
        db.session.commit()
    return redirect(url_for('manage_admins'))

@app.route('/manage-members')
def manage_members():
    if not authorized('view_members'):
        return redirect(url_for('home'))

    search_term = request.args.get('search', '').strip()

    if search_term:
        members = User.query.filter(
            User.role == 'member',
            (User.first_name.ilike(f'%{search_term}%')) |
            (User.last_name.ilike(f'%{search_term}%')) |
            (User.username.ilike(f'%{search_term}%'))
        ).order_by(User.first_name, User.last_name).all()
    else:
        members = User.query.filter_by(role='member').order_by(User.first_name, User.last_name).all()

    return render_template('manage_members.html', members=members, search_term=search_term)

@app.route('/admin/sales-report', methods=['GET'])
def admin_sales_report():
    """Display sales report with Toast POS data only."""
    if 'user_id' not in session:
        return redirect('/login')
    
    user = User.query.get(session.get('user_id'))
    if not user or not authorized('view_sales_report'):
        return redirect('/dashboard')
    
    # Initialize Toast data
    toast_data = {
        'total_revenue': 0,
        'today_revenue': 0,
        'total_transactions': 0,
        'recent_transactions': [],
        'error': None,
        'timestamp': None
    }
    
    # Try to pull Toast data
    try:
        from datetime import datetime, date
        from toast_api import get_draft_room_orders
        
        orders = get_draft_room_orders()
        
        if orders:
            toast_data['total_transactions'] = len(orders)
            total_revenue = 0
            today_revenue = 0
            recent = []
            
            today = date.today()
            
            for order in orders:
                try:
                    amount = float(order.get('total', 0))
                    total_revenue += amount
                    
                    # Check if today's order
                    order_date_str = order.get('createdDate', '')
                    if order_date_str:
                        try:
                            order_dt = datetime.fromisoformat(order_date_str.replace('Z', '+00:00'))
                            if order_dt.date() == today:
                                today_revenue += amount
                        except:
                            pass
                    
                    # Add to recent
                    if len(recent) < 20:
                        recent.append({
                            'id': order.get('id', 'N/A')[:12],
                            'amount': amount,
                            'customer': order.get('customerName', 'Walk-in'),
                            'date': order.get('createdDate', 'N/A')[:10] if order.get('createdDate') else 'N/A',
                            'time': order.get('createdDate', 'N/A')[11:19] if order.get('createdDate') else 'N/A'
                        })
                except Exception as e:
                    app.logger.debug(f"Error processing order: {e}")
                    continue
            
            toast_data['total_revenue'] = total_revenue
            toast_data['today_revenue'] = today_revenue
            toast_data['recent_transactions'] = recent
            toast_data['timestamp'] = datetime.now().strftime('%I:%M %p')
        else:
            toast_data['error'] = 'No transactions returned from Toast - Check API credentials'
    
    except Exception as e:
        app.logger.error(f"Toast API Error: {str(e)}")
        toast_data['error'] = f"Toast API Error: {str(e)}"
    
    return render_template('admin_sales_report.html', toast_data=toast_data)

@app.route('/toggle-member/<int:user_id>', methods=['POST'])
def toggle_member(user_id):
    if not authorized('toggle_member_active'):
        return redirect(url_for('home'))
    
    member = User.query.get(user_id)
    if member and member.role == 'member':
        member.active = not bool(member.active)
        db.session.commit()
        status = 'activated' if member.active else 'deactivated'
        log_audit('member', f'Member {status}: {member.first_name} {member.last_name}', f'Username: {member.username}')
        flash(f'{member.first_name} {member.last_name} has been {status}.', 'success')
    return redirect(url_for('view_member', user_id=user_id))

def _delete_members_by_ids(member_ids):
    """
    Hard-delete member users and every dependent record, bypassing FK constraints
    that SQLAlchemy cascade doesn't cover (Toast tables, seating, setup tokens, etc.).
    Returns the number of users actually deleted.
    """
    if not member_ids:
        return 0

    ids_str = ','.join(str(int(i)) for i in member_ids)

    with db.engine.connect() as conn:
        conn.execute(text("PRAGMA foreign_keys = OFF"))

        # Dependent records that need manual cleanup
        conn.execute(text(f"DELETE FROM setup_token WHERE user_id IN ({ids_str})"))
        conn.execute(text(f"""
            DELETE FROM toast_transaction_items
            WHERE transaction_id IN (
                SELECT id FROM toast_transactions WHERE member_id IN ({ids_str})
            )
        """))
        conn.execute(text(f"DELETE FROM toast_transactions WHERE member_id IN ({ids_str})"))
        conn.execute(text(f"DELETE FROM toast_member_spending WHERE member_id IN ({ids_str})"))
        conn.execute(text(f"UPDATE seating_reservation SET member_id = NULL WHERE member_id IN ({ids_str})"))
        conn.execute(text(f"UPDATE admin_action_log SET admin_id = NULL WHERE admin_id IN ({ids_str})"))
        conn.execute(text(f"UPDATE private_event_request SET reviewed_by_id = NULL WHERE reviewed_by_id IN ({ids_str})"))
        conn.execute(text(f"DELETE FROM private_event_request WHERE member_id IN ({ids_str})"))
        conn.execute(text(f"""
            DELETE FROM order_item
            WHERE order_id IN (SELECT id FROM "order" WHERE user_id IN ({ids_str}))
        """))
        conn.execute(text(f'DELETE FROM "order" WHERE user_id IN ({ids_str})'))
        conn.execute(text(f"""
            DELETE FROM invoice_line_item
            WHERE invoice_id IN (SELECT id FROM invoice WHERE member_id IN ({ids_str}))
        """))
        conn.execute(text(f"DELETE FROM invoice WHERE member_id IN ({ids_str})"))
        conn.execute(text(f"DELETE FROM note WHERE member_id IN ({ids_str}) OR author_id IN ({ids_str})"))
        conn.execute(text(f"DELETE FROM reservation WHERE user_id IN ({ids_str})"))
        conn.execute(text(f'DELETE FROM "user" WHERE id IN ({ids_str}) AND role = \'member\''))

        conn.execute(text("PRAGMA foreign_keys = ON"))
        conn.commit()

    # Keep SQLAlchemy's identity map in sync
    db.session.expire_all()
    return len(member_ids)


@app.route('/bulk_delete_members', methods=['POST'])
def bulk_delete_members():
    if not authorized('bulk_delete_members'):
        return redirect(url_for('home'))

    selected_ids = request.form.getlist('selected_members')
    if not selected_ids:
        flash('No members selected.', 'warning')
        return redirect(url_for('manage_members'))

    try:
        id_ints = [int(i) for i in selected_ids]
        members = User.query.filter(User.id.in_(id_ints), User.role == 'member').all()
        if not members:
            flash('No eligible member accounts found in selection.', 'warning')
            return redirect(url_for('manage_members'))

        names = [f'{m.first_name} {m.last_name}' for m in members]
        count = _delete_members_by_ids([m.id for m in members])
        log_audit('member', f'Bulk deleted {count} member(s)', ', '.join(names))
        flash(f'{count} member(s) deleted successfully.', 'success')
    except Exception as e:
        logger.error(f'Bulk delete error: {e}')
        flash(f'Error deleting members: {e}', 'danger')

    return redirect(url_for('manage_members'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    """Member self-registration page."""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        password_confirm = request.form.get('password_confirm', '').strip()
        
        # Validation
        if not name or not email or not password:
            flash('All fields are required', 'error')
            return redirect('/register')
        
        if password != password_confirm:
            flash('Passwords do not match', 'error')
            return redirect('/register')
        
        if len(password) < 6:
            flash('Password must be at least 6 characters', 'error')
            return redirect('/register')
        
        # Check if user exists
        existing = User.query.filter_by(email=email).first()
        if existing:
            flash('Email already registered', 'error')
            return redirect('/register')
        
        # Create new member
        try:
            user = User(
                name=name,
                email=email,
                role='Member',
                is_active=True
            )
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            
            flash('Registration successful! Please log in.', 'success')
            return redirect('/login')
        except Exception as e:
            db.session.rollback()
            flash(f'Registration failed: {str(e)}', 'error')
            return redirect('/register')
    
    return render_template('register.html')

# =====================================================
# MEMBER CSV IMPORT (ADMIN ONLY)
# =====================================================

@app.route('/admin/export-backup')
def export_backup():
    if not authorized('export_backup'):
        return redirect(url_for('home'))

    def _sv(v):
        if v is None:
            return None
        t = type(v).__name__
        if t in ('datetime', 'date'):
            return v.isoformat()
        if t == 'time':
            return v.strftime('%H:%M:%S')
        return v

    def _dump(model_cls):
        return [
            {col.name: _sv(getattr(obj, col.name)) for col in model_cls.__table__.columns}
            for obj in model_cls.query.all()
        ]

    # Export order follows FK dependencies (parents before children)
    backup = {
        '_meta': {
            'version': 1,
            'exported_at': datetime.utcnow().isoformat(),
            'app': 'room120',
        },
        MembershipType.__tablename__:          _dump(MembershipType),
        StaffRole.__tablename__:               _dump(StaffRole),
        ClubSetting.__tablename__:             _dump(ClubSetting),
        SavedReport.__tablename__:             _dump(SavedReport),
        BlockedDate.__tablename__:             _dump(BlockedDate),
        Event.__tablename__:                   _dump(Event),
        User.__tablename__:                    _dump(User),
        Application.__tablename__:             _dump(Application),
        PrivateEventRequest.__tablename__:     _dump(PrivateEventRequest),
        Note.__tablename__:                    _dump(Note),
        Reservation.__tablename__:             _dump(Reservation),
        AdminActionLog.__tablename__:          _dump(AdminActionLog),
        AuditLog.__tablename__:                _dump(AuditLog),
        Order.__tablename__:                   _dump(Order),
        OrderItem.__tablename__:               _dump(OrderItem),
        Invoice.__tablename__:                 _dump(Invoice),
        InvoiceLineItem.__tablename__:         _dump(InvoiceLineItem),
        Table.__tablename__:                   _dump(Table),
        LayoutItem.__tablename__:              _dump(LayoutItem),
        SeatingItem.__tablename__:             _dump(SeatingItem),
        SeatingReservation.__tablename__:      _dump(SeatingReservation),
        ToastTransaction.__tablename__:        _dump(ToastTransaction),
        ToastTransactionItem.__tablename__:    _dump(ToastTransactionItem),
        ToastMemberSpending.__tablename__:     _dump(ToastMemberSpending),
        ToastSyncLog.__tablename__:            _dump(ToastSyncLog),
        SetupToken.__tablename__:              _dump(SetupToken),
    }

    fname = f'room120_backup_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.json'
    resp = make_response(json.dumps(backup, indent=2, default=str))
    resp.headers['Content-Type'] = 'application/json'
    resp.headers['Content-Disposition'] = f'attachment; filename="{fname}"'
    log_audit('system', 'Full database backup exported', fname)
    return resp


@app.route('/admin/import-backup', methods=['POST'])
def import_backup():
    if not authorized('import_backup'):
        return redirect(url_for('home'))

    f = request.files.get('backup_file')
    if not f or not f.filename.lower().endswith('.json'):
        flash('Please upload a valid .json backup file.', 'danger')
        return redirect(url_for('import_members'))

    try:
        data = json.loads(f.read().decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        flash(f'Could not parse backup file: {exc}', 'danger')
        return redirect(url_for('import_members'))

    meta = data.get('_meta', {})
    if meta.get('app') != 'room120' or meta.get('version') != 1:
        flash('This does not look like a valid Room 120 backup file.', 'danger')
        return redirect(url_for('import_members'))

    # Dependency-ordered list: insert in this order, delete in reverse
    INSERT_ORDER = [
        MembershipType, StaffRole, ClubSetting, SavedReport,
        BlockedDate, Event,
        User, Application, PrivateEventRequest,
        Note, Reservation, AdminActionLog, AuditLog,
        Order, OrderItem, Invoice, InvoiceLineItem,
        Table, LayoutItem, SeatingItem, SeatingReservation,
        ToastTransaction, ToastTransactionItem, ToastMemberSpending, ToastSyncLog,
        SetupToken,
    ]

    try:
        with db.engine.connect() as conn:
            conn.execute(db.text('PRAGMA foreign_keys = OFF'))

            # Wipe all tables in reverse order to avoid FK constraint errors
            for model_cls in reversed(INSERT_ORDER):
                tbl = model_cls.__tablename__
                conn.execute(db.text(f'DELETE FROM "{tbl}"'))

            # Re-insert everything in dependency order
            for model_cls in INSERT_ORDER:
                tbl = model_cls.__tablename__
                rows = data.get(tbl, [])
                for row in rows:
                    if not row:
                        continue
                    cols = ', '.join(f'"{k}"' for k in row)
                    params = {f'p{i}': v for i, v in enumerate(row.values())}
                    placeholders = ', '.join(f':p{i}' for i in range(len(row)))
                    conn.execute(
                        db.text(f'INSERT INTO "{tbl}" ({cols}) VALUES ({placeholders})'),
                        params,
                    )

            conn.execute(db.text('PRAGMA foreign_keys = ON'))
            conn.commit()

        log_audit('system', 'Full database restored from backup',
                  f'Backup dated {meta.get("exported_at", "unknown")}')
        flash('Database fully restored from backup. All data has been replaced.', 'success')
    except Exception as exc:
        flash(f'Restore failed: {exc}', 'danger')

    return redirect(url_for('import_members'))


@app.route('/import_members', methods=['GET', 'POST'])
def import_members():
    if not authorized('import_members'):
        return redirect(url_for('home'))

    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file selected', 'danger')
            return redirect('/import_members')

        file = request.files['file']
        if not file or file.filename == '':
            flash('No file selected', 'danger')
            return redirect('/import_members')

        if not file.filename.endswith('.csv'):
            flash('Please upload a CSV file', 'danger')
            return redirect('/import_members')

        try:
            from io import StringIO

            csv_content = file.read().decode('utf-8-sig')  # handle Excel BOM
            reader = csv.DictReader(StringIO(csv_content))

            # Wipe all existing members before importing the fresh list
            existing_member_ids = [u.id for u in User.query.filter_by(role='member').all()]
            wiped = _delete_members_by_ids(existing_member_ids)
            logger.info(f'Import: wiped {wiped} existing member records before re-import')

            import_date     = date.today()
            import_date_str = import_date.strftime('%B %d, %Y')
            bal_item_name   = f'Outstanding balance as of {import_date_str}'

            created, updated, skipped = 0, 0, 0
            errors = []
            affected_users = []

            def parse_balance(val):
                cleaned = re.sub(r'[^\d.\-]', '', str(val or ''))
                try:
                    return round(float(cleaned), 2) if cleaned else 0.0
                except ValueError:
                    return 0.0

            def safe_username(first, last):
                base  = re.sub(r'[^a-z0-9]', '', (first + last).lower()) or 'member'
                uname = base
                i     = 2
                while User.query.filter_by(username=uname).first():
                    uname = f'{base}{i}'
                    i    += 1
                return uname

            for row_num, row in enumerate(reader, start=2):
                name_raw = (row.get('Name') or '').strip()
                if not name_raw:
                    skipped += 1
                    continue

                parts      = name_raw.split()
                first_name = parts[0]
                last_name  = ' '.join(parts[1:]) if len(parts) > 1 else ''
                email      = (row.get('Email') or '').strip() or None
                phone      = (row.get('Phone') or '').strip() or None
                member_num = (row.get('Customer Number') or '').strip() or None
                balance    = parse_balance(row.get('Outstanding Balance', ''))

                # Derive membership type from member number prefix
                prefix = (member_num or '').lower()[:1]
                if prefix == 'c':
                    membership_type = 'corporate'
                elif prefix == 's':
                    membership_type = 'single'
                else:
                    membership_type = 'single'

                try:
                    sp = db.session.begin_nested()

                    user = User(
                        username        = safe_username(first_name, last_name),
                        first_name      = first_name,
                        last_name       = last_name,
                        email           = email,
                        phone           = phone,
                        member_number   = member_num,
                        membership_type = membership_type,
                        role            = 'member',
                        active          = True,
                    )
                    user.set_password(secrets.token_urlsafe(12))
                    db.session.add(user)
                    created += 1

                    db.session.flush()

                    if balance != 0.0:
                        order = Order(
                            user_id        = user.id,
                            date           = import_date,
                            time           = None,
                            subtotal       = balance,
                            tax            = 0.0,
                            gratuity       = 0.0,
                            total          = balance,
                            paid_by_credit = False,
                            paid           = False,
                            notes          = 'Imported outstanding balance',
                        )
                        db.session.add(order)
                        db.session.flush()
                        db.session.add(OrderItem(
                            order_id  = order.id,
                            item_name = bal_item_name,
                            price     = balance,
                        ))

                    sp.commit()
                    affected_users.append(user)

                except Exception as row_err:
                    sp.rollback()
                    errors.append(f'Row {row_num} ({name_raw}): {row_err}')
                    continue

            # Recalculate balances for all affected members
            db.session.flush()
            for u in affected_users:
                recalculate_balances(u)

            db.session.commit()
            log_audit('member',
                      f'CSV import: {created} created, {updated} updated',
                      f'File: {file.filename} · Skipped: {skipped} · Errors: {len(errors)}')

            flash(f'✓ Replaced all members — {created} imported from CSV', 'success')
            if skipped:
                flash(f'{skipped} blank-name rows skipped', 'info')
            for msg in errors[:5]:
                flash(f'⚠ {msg}', 'warning')
            if len(errors) > 5:
                flash(f'… and {len(errors) - 5} more errors (check server logs)', 'warning')
            return redirect(url_for('manage_members'))

        except Exception as e:
            db.session.rollback()
            logger.error(f'Import error: {e}')
            flash(f'Error importing file: {e}', 'danger')
            return redirect('/import_members')

    return render_template('admin_import_members.html')


@app.route('/test-toast', methods=['GET'])
def test_toast():
    """Debug route to test Toast credentials"""
    from toast_api import get_oauth_token
    import os
    
    logger.info("=== TESTING TOAST CREDENTIALS ===")
    
    client_id = os.getenv('TOAST_CLIENT_ID')
    client_secret = os.getenv('TOAST_CLIENT_SECRET')
    restaurant_id = os.getenv('TOAST_RESTAURANT_ID')
    
    logger.info(f"CLIENT_ID: {client_id[:20]}..." if client_id else "CLIENT_ID: NOT SET")
    logger.info(f"CLIENT_SECRET: {client_secret[:20]}..." if client_secret else "CLIENT_SECRET: NOT SET")
    logger.info(f"RESTAURANT_ID: {restaurant_id}")
    
    token = get_oauth_token()
    logger.info(f"Token obtained: {token[:50]}..." if token else "Token: FAILED")
    
    if token:
        return f"✓ Token obtained successfully: {token[:50]}..."
    else:
        return "✗ Failed to get token - check .env file and Flask logs"

@app.route('/apply', methods=['GET', 'POST'])
def apply_step_1():
    if request.method == 'POST':
        membership_type = request.form.get('membership_type')
        if membership_type in ['individual', 'corporate']:
            session['application_type'] = membership_type
            return redirect(url_for('apply_step_2'))
        else:
            flash('Please select a valid membership type.', 'danger')
    return render_template('apply_step_1.html')





@app.route('/apply/step-2', methods=['GET', 'POST'])
def apply_step_2():
    membership_type = session.get('application_type')
    if not membership_type:
        return redirect(url_for('apply_step_1'))

    if request.method == 'POST':
        session['first_name'] = request.form['first_name']
        session['last_name'] = request.form['last_name']
        session['dob'] = request.form['dob']
        session['email'] = request.form['email']
        session['phone'] = request.form['phone']
        session['referred_by'] = request.form['referred_by']
        if membership_type == 'corporate':
            session['company_name'] = request.form['company_name']
        return redirect(url_for('apply_step_3'))

    return render_template('apply_step_2.html', membership_type=membership_type)


@app.route('/apply/step-3', methods=['GET', 'POST'])
def apply_step_3():
    membership_type = session.get('application_type')
    if not membership_type:
        return redirect(url_for('apply_step_1'))

    if request.method == 'POST':
        promo_opt_in = 'promo_opt_in' in request.form

        application = Application(
            membership_type=membership_type,
            first_name=session.get('first_name'),
            last_name=session.get('last_name'),
            dob=session.get('dob'),
            email=session.get('email'),
            phone=session.get('phone'),
            referred_by=session.get('referred_by'),
            company_name=session.get('company_name') if membership_type == 'corporate' else '',
            promo_opt_in=promo_opt_in,
        )

        db.session.add(application)
        db.session.commit()

        # Clear session
        for key in ['application_type', 'first_name', 'last_name', 'dob', 'email', 'phone', 'referred_by', 'company_name']:
            session.pop(key, None)

        return redirect(url_for('apply_complete'))

    return render_template('apply_step_3.html', membership_type=membership_type)





@app.route('/apply/complete')
def apply_complete():
    return render_template('apply_complete.html')

@app.route('/admin/applications')
def admin_applications():
    if not authorized('view_applications'):
        return redirect(url_for('home'))
    applications = Application.query.order_by(Application.submitted_at.desc()).all()
    return render_template('admin_applications.html', applications=applications)


@app.route('/admin/application/<int:app_id>')
def view_application(app_id):
    if not authorized('view_applications'):
        return redirect(url_for('home'))
    application = Application.query.get_or_404(app_id)
    return render_template('admin_application_detail.html', application=application)


@app.route('/admin/approve_application/<int:app_id>', methods=['POST'])
def approve_application(app_id):
    if not authorized('approve_application'):
        return redirect(url_for('home'))

    application = Application.query.get_or_404(app_id)

    full_username = (application.first_name + application.last_name).lower()
    auto_password = full_username + "room120"

    if User.query.filter_by(username=full_username).first():
        flash('Username already exists. Please handle manually.', 'danger')
        return redirect(url_for('admin_applications'))

    new_user = User(
        username=full_username,
        role='member',
        first_name=application.first_name,
        last_name=application.last_name,
        email=application.email,
        phone=application.phone,
        membership_type=application.membership_type
    )
    new_user.set_password(auto_password)

    application.status = 'approved'
    db.session.add(new_user)
    db.session.commit()

    log_audit('member', f'Application approved: {new_user.first_name} {new_user.last_name}', f'Username: {full_username} · Type: {application.membership_type}')
    flash(f'Member {new_user.first_name} {new_user.last_name} created.', 'success')
    return redirect(url_for('admin_applications'))


@app.route('/admin/application/<int:app_id>/deny', methods=['POST'])
def deny_application(app_id):
    if not authorized('deny_application'):
        return redirect(url_for('home'))
    application = Application.query.get_or_404(app_id)
    application.status = 'denied'
    db.session.commit()
    log_audit('member', f'Application denied: {application.first_name} {application.last_name}', f'Email: {application.email}')
    flash('Application denied.', 'warning')
    return redirect(url_for('admin_applications'))


@app.route('/admin/application/<int:app_id>/delete', methods=['POST'])
def delete_application(app_id):
    if not authorized('delete_application'):
        return redirect(url_for('home'))
    application = Application.query.get_or_404(app_id)
    log_audit('member', f'Application deleted: {application.first_name} {application.last_name}', f'Email: {application.email} · Status: {application.status}')
    db.session.delete(application)
    db.session.commit()
    flash('Application deleted.', 'info')
    return redirect(url_for('admin_applications'))




@app.route('/admin/application/<int:app_id>/download')
def download_application_pdf(app_id):
    if not authorized('view_applications'):
        return redirect(url_for('home'))
    application = Application.query.get_or_404(app_id)
    rendered_html = render_template('application_pdf.html', application=application)
    result = BytesIO()
    pdf = pisa.CreatePDF(BytesIO(rendered_html.encode("utf-8")), dest=result)
    if pdf.err:
        return "PDF error", 500
    response = make_response(result.getvalue())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'inline; filename=application_{application.id}.pdf'
    return response




@app.route('/register_member', methods=['POST'])
def register_member():
    username = request.form.get('username')
    password = request.form.get('password')
    first_name = request.form.get('first_name')
    last_name = request.form.get('last_name')
    email = request.form.get('email')
    phone = request.form.get('phone')
    member_number = request.form.get('member_number')

    if User.query.filter_by(username=username).first():
        flash('Username already exists.', 'danger')
    else:
        member = User(
            username=username,
            role='member',
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            member_number=member_number,
            active=True
        )
        member.set_password(password)
        db.session.add(member)
        db.session.commit()
        name = ' '.join(filter(None, [first_name, last_name]))
        log_audit('member', f'Member created: {name}', f'Username: {username} · Type: {membership_type}')
        flash('Member added successfully.', 'success')

    return redirect(url_for('manage_members'))


@app.route('/import_members', methods=['POST'])
def import_members_old():
    """Legacy route - redirect to new import endpoint."""
    return redirect(url_for('import_members'))






@app.route('/export-members')
def export_members():
    if not authorized('export_members'):
        return redirect(url_for('home'))

    members = User.query.filter_by(role='member').all()

    csv_data = "username,first_name,last_name,email,member_number,active\n"
    for m in members:
        csv_data += f"{m.username},{m.first_name},{m.last_name},{m.email or ''},{m.phone},{m.member_number or ''},{'Active' if m.active else 'Inactive'}\n"

    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=members.csv"}
    )

@app.route('/add-member', methods=['GET', 'POST'])
def add_member_page():
    if not authorized('add_member'):
        return redirect(url_for('home'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        member_number = request.form.get('member_number')
        membership_type = request.form.get('membership_type', 'single')

        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'danger')
        else:
            member = User(
                username=username,
                role='member',
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone=phone,
                member_number=member_number,
                membership_type=membership_type,
                active=True
            )
            member.set_password(password)
            db.session.add(member)
            db.session.commit()
            flash('Member added successfully.', 'success')
            return redirect(url_for('manage_members'))

    return render_template('add_member.html',
        member_types=MembershipType.query.filter_by(is_active=True).order_by(MembershipType.sort_order).all()
    )

@app.route('/upload-invoice/<int:user_id>', methods=['POST'])
def upload_invoice(user_id):
    if not authorized('upload_invoice'):
        return redirect(url_for('home'))

    member = User.query.get_or_404(user_id)
    file = request.files.get('invoice')

    if file and file.filename.endswith('.pdf'):
        original_filename = secure_filename(file.filename)
        stored_filename = f"{datetime.utcnow().timestamp()}_{original_filename}"
        save_path = os.path.join(app.config['UPLOAD_FOLDER'], stored_filename)
        
        file.save(save_path)

        invoice = Invoice(
            original_filename=original_filename,
            stored_filename=stored_filename,
            member_id=member.id
        )
        db.session.add(invoice)
        db.session.commit()
        flash('Invoice uploaded successfully.', 'success')
    else:
        flash('Invalid file. Please upload a PDF.', 'danger')

    return redirect(url_for('view_member', user_id=member.id))

@app.route('/download_invoice/<int:invoice_id>')
def download_invoice(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)

    # If it's a manually created invoice (with totals & line items)
    if invoice.total_amount is not None:
        rendered = render_template('invoice_pdf.html', invoice=invoice)
        pdf = BytesIO()
        pisa.CreatePDF(rendered, dest=pdf)
        pdf.seek(0)

        return send_file(
            pdf,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"invoice_{invoice.id}.pdf"
        )

    # Else it's an uploaded file-based invoice (use stored file)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], invoice.stored_filename)
    if not os.path.exists(filepath):
        return "File not found", 404

    return send_from_directory(
        directory=app.config['UPLOAD_FOLDER'],
        path=invoice.stored_filename,
        as_attachment=True,
        download_name=invoice.original_filename
    )

@app.route('/create_invoice', methods=['GET', 'POST'])
def create_invoice():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    
    members = User.query.filter_by(role='member').all()

    if request.method == 'POST':
        member_id = request.form.get('member_id')
        notes = request.form.get('notes')
        tax = float(request.form.get('tax', 0))
        line_items = request.form.getlist('line_items[]')
        amounts = request.form.getlist('amounts[]')

        no_tax = 'no_tax' in request.form
        no_gratuity = 'no_gratuity' in request.form

        subtotal = sum(float(amount) for amount in amounts)
        tax_amount = 0 if no_tax else round(subtotal * 0.0875, 2)
        gratuity_amount = 0 if no_gratuity else round(subtotal * 0.2, 2)
        total = round(subtotal + tax_amount + gratuity_amount, 2)

        invoice = Invoice(
            member_id=member_id,
            total_amount=total,
            tax_amount=tax_amount,
            notes=notes,
            original_filename="Manual Entry",
            stored_filename="manual_entry"
        )

        for description, amount in zip(line_items, amounts):
            item = InvoiceLineItem(description=description, amount=float(amount))
            invoice.line_items.append(item)

        member = User.query.get(member_id)
        db.session.add(invoice)
        db.session.flush()
        recalculate_balances(member)
        db.session.commit()
        mname = ' '.join(filter(None, [member.first_name, member.last_name]))
        log_audit('invoice', f'Invoice created for {mname}', f'Total: ${total:.2f}')
        flash('Invoice created successfully.', 'success')
        return redirect(url_for('view_member', user_id=member_id))

    return render_template('create_invoice.html', members=members)

@app.route('/load_member_info/<int:member_id>')
def load_member_info(member_id):
    member = User.query.get_or_404(member_id)
    return jsonify({
        'first_name': member.first_name,
        'last_name': member.last_name,
        'email': member.email,
        'phone': member.phone,
        'member_number': member.member_number,
        'membership_type': member.membership_type
    })



@app.route('/submit_invoice', methods=['POST'])
def submit_invoice():
    member_id = request.form.get('member_id')
    notes = request.form.get('notes')
    tax = float(request.form.get('tax', 0))
    line_items = request.form.getlist('line_items[]')
    amounts = request.form.getlist('amounts[]')

    total = sum(float(amount) for amount in amounts)
    grand_total = total + tax

    invoice = Invoice(
        member_id=member_id,
        total_amount=grand_total,
        tax_amount=tax,
        notes=notes,
        original_filename="Manual Entry",
        stored_filename="manual_entry"
    )

    for description, amount in zip(line_items, amounts):
        item = InvoiceLineItem(description=description, amount=float(amount))
        invoice.line_items.append(item)

    # ✅ Update member balances
    member = User.query.get(member_id)
    member.amount_owed += total
    member.tax_owed += tax

    db.session.add(invoice)
    db.session.commit()

    return redirect(url_for('view_member', user_id=member_id))





@app.route('/delete_invoice/<int:invoice_id>', methods=['POST'])
def delete_invoice(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    member = invoice.member
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], invoice.stored_filename)

    if os.path.exists(filepath):
        os.remove(filepath)

    mname = ' '.join(filter(None, [member.first_name, member.last_name]))
    total_was = invoice.total_amount or 0
    db.session.delete(invoice)
    db.session.flush()
    recalculate_balances(member)
    db.session.commit()
    log_audit('invoice', f'Invoice deleted for {mname}', f'Invoice #{invoice_id} · Total was ${total_was:.2f}')
    flash('Invoice deleted.', 'success')
    return redirect(url_for('view_member', user_id=member.id))


@app.route('/toggle_invoice_paid/<int:invoice_id>', methods=['POST'])
def toggle_invoice_paid(invoice_id):
    if not authorized('toggle_invoice_paid'):
        return redirect(url_for('login'))
    invoice = Invoice.query.get_or_404(invoice_id)
    member = invoice.member

    if invoice.original_filename == 'Generated from Order' and invoice.order_id:
        # Sync directly to the source order's paid_by_credit
        order = Order.query.get(invoice.order_id)
        if order:
            order.paid_by_credit = not order.paid_by_credit
            invoice.is_paid = order.paid_by_credit
    elif invoice.original_filename == 'Generated from Orders' and invoice.order_ids_json:
        # Sync to all source orders
        ids = json.loads(invoice.order_ids_json)
        orders = Order.query.filter(Order.id.in_(ids)).all()
        new_state = not invoice.is_paid
        for o in orders:
            o.paid_by_credit = new_state
        invoice.is_paid = new_state
    else:
        # Manual Entry or uploaded PDF — just toggle the invoice flag
        invoice.is_paid = not invoice.is_paid

    db.session.flush()
    recalculate_balances(member)
    db.session.commit()
    status = 'paid' if invoice.is_paid else 'unpaid'
    mname = ' '.join(filter(None, [member.first_name, member.last_name]))
    log_audit('invoice', f'Invoice marked {status} for {mname}', f'Invoice #{invoice_id} · ${invoice.total_amount or 0:.2f}')
    flash(f'Invoice marked as {status}.', 'success')
    return redirect(url_for('view_member', user_id=member.id))


@app.route('/edit_invoice/<int:invoice_id>', methods=['GET', 'POST'])
def edit_invoice(invoice_id):
    if not authorized('edit_invoice'):
        return redirect(url_for('login'))
    invoice = Invoice.query.get_or_404(invoice_id)
    member = invoice.member

    if request.method == 'POST':
        invoice.notes = request.form.get('notes', '').strip()
        invoice.is_paid = 'is_paid' in request.form

        if invoice.original_filename in ('Manual Entry', 'Generated from Order', 'Generated from Orders'):
            # Rebuild line items
            for item in list(invoice.line_items):
                db.session.delete(item)
            descriptions = request.form.getlist('description[]')
            amounts = request.form.getlist('amount[]')
            for desc, amt in zip(descriptions, amounts):
                desc = desc.strip()
                if desc:
                    invoice.line_items.append(InvoiceLineItem(
                        description=desc,
                        amount=round(float(amt or 0), 2)
                    ))
            sub = round(sum(i.amount for i in invoice.line_items), 2)
            tax = round(float(request.form.get('tax_amount') or 0), 2)
            grat = round(float(request.form.get('gratuity_amount') or 0), 2)
            invoice.tax_amount = tax
            invoice.gratuity_amount = grat
            invoice.total_amount = round(sub + tax + grat, 2)
        else:
            # Uploaded PDF — update amounts directly
            invoice.total_amount = round(float(request.form.get('total_amount') or 0), 2)
            invoice.tax_amount = round(float(request.form.get('tax_amount') or 0), 2)
            invoice.gratuity_amount = round(float(request.form.get('gratuity_amount') or 0), 2)

        db.session.flush()
        recalculate_balances(member)
        db.session.commit()
        mname = ' '.join(filter(None, [member.first_name, member.last_name]))
        log_audit('invoice', f'Invoice updated for {mname}', f'Invoice #{invoice_id} · Total: ${invoice.total_amount:.2f}')
        flash('Invoice updated.', 'success')
        return redirect(url_for('view_member', user_id=member.id))

    return render_template('edit_invoice.html', invoice=invoice, member=member)


@app.route('/member/<int:user_id>/update_balance', methods=['POST'])
def update_balance(user_id):
    if not authorized('edit_member'):
        return redirect(url_for('login'))

    user = User.query.get_or_404(user_id)

    try:
        user.amount_spent = float(request.form.get('amount_spent', 0))
        user.amount_owed = float(request.form.get('amount_owed', 0))
        user.tax_owed = float(request.form.get('tax_owed', 0))
        user.tax_paid = float(request.form.get('tax_paid', 0))
        user.gratuity_owed = float(request.form.get('gratuity_owed', 0))
        user.gratuity_paid = float(request.form.get('gratuity_paid', 0))
        user.minimum_adjustment = float(request.form.get('minimum_adjustment', 0))  # <-- Add this

        db.session.commit()
        log_audit('member', f'Balance manually updated: {user.first_name} {user.last_name}',
                  f'Spent: ${user.amount_spent} · Owed: ${user.amount_owed}')
        flash('Balance updated successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating balance: {str(e)}', 'danger')

    return redirect(url_for('view_member', user_id=user.id))










def recalculate_balances(user):
    orders = Order.query.filter_by(user_id=user.id).all()

    # amount_spent = ALL orders (paid + owed) — this is what drives minimum spend progress
    user.amount_spent  = round(sum(o.total    for o in orders), 2)
    user.tax_paid      = round(sum(o.tax      for o in orders if o.paid_by_credit), 2)
    user.gratuity_paid = round(sum(o.gratuity for o in orders if o.paid_by_credit), 2)
    user.amount_owed   = round(sum(o.subtotal for o in orders if not o.paid_by_credit), 2)
    user.tax_owed      = round(sum(o.tax      for o in orders if not o.paid_by_credit), 2)
    user.gratuity_owed = round(sum(o.gratuity for o in orders if not o.paid_by_credit), 2)

    # Manual invoices (not generated from orders) also count toward balance + minimum spend
    manual_invoices = Invoice.query.filter_by(
        member_id=user.id, original_filename='Manual Entry'
    ).all()
    for inv in manual_invoices:
        sub = round(sum(item.amount for item in inv.line_items), 2)
        tax = inv.tax_amount or 0
        if inv.gratuity_amount is not None:
            grat = inv.gratuity_amount
        else:
            grat = round(max(0, (inv.total_amount or 0) - tax - sub), 2)
        user.amount_spent = round(user.amount_spent + sub, 2)
        if inv.is_paid:
            user.tax_paid      = round(user.tax_paid      + tax,  2)
            user.gratuity_paid = round(user.gratuity_paid + grat, 2)
        else:
            user.amount_owed   = round(user.amount_owed   + sub,  2)
            user.tax_owed      = round(user.tax_owed      + tax,  2)
            user.gratuity_owed = round(user.gratuity_owed + grat, 2)


@app.route('/add_order/<int:user_id>', methods=['GET', 'POST'])
def add_order(user_id):
    if not authorized('add_order'):
        return redirect(url_for('login'))

    user = User.query.get_or_404(user_id)

    if request.method == 'POST':
        date_str = request.form.get('date')
        time_str = request.form.get('time')
        notes = request.form.get('notes')
        paid_by_credit = request.form.get('paid_by_credit') == 'yes'

        try:
            order_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            order_time = datetime.strptime(time_str, "%H:%M").time() if time_str else None
        except ValueError:
            flash("Invalid date or time format.", "danger")
            return redirect(request.url)

        items = []
        subtotal = 0.0

        item_names = request.form.getlist('item_name[]')
        item_prices = request.form.getlist('item_price[]')

        for name, price in zip(item_names, item_prices):
            try:
                price_val = float(price)
            except ValueError:
                continue
            items.append(OrderItem(item_name=name, price=price_val))
            subtotal += price_val

        no_tax = 'no_tax' in request.form
        no_gratuity = 'no_gratuity' in request.form

        tax = 0 if no_tax else round(subtotal * 0.0875, 2)
        gratuity = 0 if no_gratuity else round(subtotal * 0.2, 2)
        total = round(subtotal + tax + gratuity, 2)

        new_order = Order(
            user_id=user.id,
            date=order_date,
            time=order_time,
            subtotal=subtotal,
            tax=tax,
            gratuity=gratuity,
            total=total,
            paid_by_credit=paid_by_credit,
            notes=notes,
            items=items
        )

        db.session.add(new_order)
        db.session.flush()
        recalculate_balances(user)
        db.session.commit()
        mname = ' '.join(filter(None, [user.first_name, user.last_name]))
        log_audit('order', f'Order created for {mname}', f'Total: ${total:.2f} · Date: {order_date}')
        flash("Order successfully added.", "success")
        return redirect(url_for('view_member', user_id=user.id))

    return render_template('add_order.html', user=user)







@app.route('/order/edit/<int:order_id>', methods=['GET', 'POST'])
def edit_order(order_id):
    order = Order.query.get_or_404(order_id)
    user = order.user

    if request.method == 'POST':
        order.date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
        order.time = datetime.strptime(request.form['time'], '%H:%M').time()
        order.paid_by_credit = 'paid_by_credit' in request.form
        order.notes = request.form.get('notes')

        OrderItem.query.filter_by(order_id=order.id).delete()

        items = []
        subtotal = 0.0
        for name, price in zip(request.form.getlist('item_name'), request.form.getlist('item_price')):
            price = float(price)
            items.append(OrderItem(item_name=name, price=price))
            subtotal += price

        order.items = items
        order.subtotal = subtotal

        no_tax = 'no_tax' in request.form
        no_gratuity = 'no_gratuity' in request.form

        order.tax = 0 if no_tax else round(order.subtotal * 0.0875, 2)
        order.gratuity = 0 if no_gratuity else round(order.subtotal * 0.2, 2)
        order.total = round(order.subtotal + order.tax + order.gratuity, 2)

        db.session.flush()
        recalculate_balances(user)
        db.session.commit()
        mname = ' '.join(filter(None, [user.first_name, user.last_name]))
        log_audit('order', f'Order updated for {mname}', f'Order #{order.id} · Total: ${order.total:.2f}')
        flash('Order updated successfully.', 'success')
        return redirect(url_for('view_member', user_id=user.id))

    return render_template('edit_order.html', order=order, user=user)


# =====================================================
# TOAST API INTEGRATION - REGISTER SECURE ROUTES
# =====================================================
try:
    # from toast_routes import register_toast_routes
    # register_toast_routes(app)
    logger.info("Toast API routes registered successfully")
except ImportError as e:
    logger.warning(f"Could not import toast_routes: {e}")
except Exception as e:
    logger.error(f"Error registering Toast API routes: {e}")


@app.route('/delete_order/<int:order_id>', methods=['POST'])
def delete_order(order_id):
    if not authorized('delete_order'):
        return redirect(url_for('login'))

    order = Order.query.get_or_404(order_id)
    user = order.user

    mname = ' '.join(filter(None, [user.first_name, user.last_name]))
    for item in order.items:
        db.session.delete(item)
    db.session.delete(order)
    db.session.flush()
    recalculate_balances(user)
    db.session.commit()
    log_audit('order', f'Order deleted for {mname}', f'Order #{order_id} · Total was ${order.total:.2f}')
    flash('Order deleted and balances updated.', 'success')
    return redirect(url_for('view_member', user_id=user.id))




@app.route('/toggle_order_paid/<int:order_id>')
def toggle_order_paid(order_id):
    if not authorized('toggle_order_paid'):
        return redirect(url_for('home'))

    order = Order.query.get_or_404(order_id)
    user = order.user

    order.paid_by_credit = not order.paid_by_credit
    linked = Invoice.query.filter_by(order_id=order.id).first()
    if linked:
        linked.is_paid = order.paid_by_credit
    db.session.flush()
    recalculate_balances(user)
    db.session.commit()
    mname = ' '.join(filter(None, [user.first_name, user.last_name]))
    status = 'paid' if order.paid_by_credit else 'unpaid'
    log_audit('order', f'Order marked {status} for {mname}', f'Order #{order.id} · ${order.total:.2f}')
    return redirect(url_for('view_member', user_id=user.id))











@app.route('/edit_member/<int:user_id>', methods=['GET', 'POST'])
def edit_member(user_id):
    if not authorized('edit_member'):
        return redirect(url_for('home'))
    user = User.query.get_or_404(user_id)

    if request.method == 'POST':
        user.first_name    = request.form['first_name']
        user.last_name     = request.form['last_name']
        user.username      = request.form['username']
        user.email         = request.form.get('email', '').strip() or None
        user.phone         = request.form.get('phone', '').strip() or None
        user.member_number = request.form.get('member_number', '').strip() or None
        user.membership_type = request.form['membership_type']
        user.active        = 'active' in request.form

        new_password = request.form.get('password', '').strip()
        pwd_changed = bool(new_password)
        if new_password:
            user.password = generate_password_hash(new_password)

        db.session.commit()
        mname = f'{user.first_name} {user.last_name}'
        log_audit('member', f'Member updated: {mname}',
                  f'Type: {user.membership_type} · Active: {user.active}'
                  + (' · Password changed' if pwd_changed else ''))
        flash('Member updated successfully.', 'success')
        return redirect(url_for('view_member', user_id=user.id))

    return render_template('edit_member.html', member=user,
        member_types=MembershipType.query.order_by(MembershipType.sort_order).all()
    )





@app.route('/save_preferences/<int:user_id>', methods=['POST'])
def save_preferences(user_id):
    member = User.query.get_or_404(user_id)
    is_self = session.get('user_id') == user_id
    if not is_self and not authorized('edit_member'):
        return redirect(url_for('home'))

    fields = ['favorite_drink', 'seating_preference', 'allergies', 'preferences_notes']
    changed = []
    for f in fields:
        new_val = request.form.get(f, '').strip()
        old_val = getattr(member, f) or ''
        if new_val != old_val:
            changed.append(f'{f}: {old_val!r} → {new_val!r}')
        setattr(member, f, new_val or None)

    db.session.commit()
    if changed:
        mname = f'{member.first_name} {member.last_name}'
        log_audit('member', f'Preferences updated: {mname}', ' | '.join(changed))
    flash('Preferences saved.', 'success')
    return redirect(url_for('view_member', user_id=user_id))


@app.route('/delete_member/<int:user_id>', methods=['POST'])
def delete_member(user_id):
    if not authorized('delete_member'):
        return redirect(url_for('login'))

    user = User.query.get_or_404(user_id)
    mname = ' '.join(filter(None, [user.first_name, user.last_name]))
    db.session.delete(user)
    db.session.commit()
    log_audit('member', f'Member deleted: {mname}', f'Username: {user.username}')
    flash("Member deleted successfully.", "success")
    return redirect(url_for('manage_members'))



@app.route('/member/<int:user_id>')
def view_member(user_id):
    if not session.get('user_id'):
        return redirect(url_for('login'))

    member = User.query.get_or_404(user_id)

    # Only allow access if authorized staff/admin or the user themself
    if not authorized('view_member_profile') and session.get('user_id') != member.id:
        return redirect(url_for('home'))

    reservations = Reservation.query.filter_by(user_id=member.id).all()
    orders = Order.query.filter_by(user_id=member.id).order_by(Order.date.desc()).all()
    invoices = Invoice.query.filter_by(member_id=member.id).order_by(Invoice.date_created.desc()).all()

    is_admin = session.get('role') == 'admin'
    can_edit   = authorized('edit_member')
    can_toggle = authorized('toggle_member_active')
    can_delete = authorized('delete_member')

    return render_template(
        'member_profile.html',
        member=member,
        user=member,
        reservations=reservations,
        orders=orders,
        invoices=invoices,
        is_admin=is_admin,
        can_edit=can_edit,
        can_toggle=can_toggle,
        can_delete=can_delete,
    )






@app.route('/add-note/<int:user_id>', methods=['POST'])
def add_note(user_id):
    if not authorized('add_note'):
        return redirect(url_for('home'))

    content = request.form['note']
    note = Note(content=content, member_id=user_id, author_id=session['user_id'])
    db.session.add(note)
    db.session.commit()
    member = User.query.get(user_id)
    mname = f'{member.first_name} {member.last_name}' if member else f'#{user_id}'
    log_audit('member', f'Note added for {mname}', content[:120])
    return redirect(url_for('view_member', user_id=user_id))

@app.route('/edit_note/<int:note_id>', methods=['GET', 'POST'])
def edit_note(note_id):
    if not authorized('edit_note'):
        return redirect(url_for('home'))

    note = Note.query.get_or_404(note_id)

    if request.method == 'POST':
        note.content = request.form['content']
        db.session.commit()
        member = User.query.get(note.member_id)
        mname = f'{member.first_name} {member.last_name}' if member else f'#{note.member_id}'
        log_audit('member', f'Note updated for {mname}', note.content[:120])
        flash('Note updated.')
        return redirect(url_for('view_member', user_id=note.member_id))

    return render_template('edit_note.html', note=note)


@app.route('/delete_note/<int:note_id>', methods=['POST'])
def delete_note(note_id):
    if not authorized('delete_note'):
        return redirect(url_for('home'))

    note = Note.query.get_or_404(note_id)
    member_id = note.member_id
    member = User.query.get(member_id)
    mname = f'{member.first_name} {member.last_name}' if member else f'#{member_id}'
    log_audit('member', f'Note deleted for {mname}', note.content[:120])
    db.session.delete(note)
    db.session.commit()
    flash('Note deleted.')
    return redirect(url_for('view_member', user_id=member_id))



@app.route('/events')
def events():
    if not session.get('user_id'):
        return redirect(url_for('login'))

    view_mode = request.args.get('view', 'list')
    events = Event.query.order_by(Event.date.asc()).all()

    for event in events:
        db.session.expunge(event)
        if isinstance(event.date, str):
            try:
                event.date = datetime.strptime(event.date, '%Y-%m-%d').date()
            except Exception:
                pass
        if isinstance(event.time, str):
            try:
                event.time = datetime.strptime(event.time, '%H:%M:%S').time()
            except ValueError:
                try:
                    event.time = datetime.strptime(event.time, '%H:%M').time()
                except Exception:
                    pass

    return render_template(
        'events.html',
        events=events,
        view_mode=view_mode,
        is_admin=(session.get('role') == 'admin')
    )

@app.route('/events')
def events_page():
    events = Event.query.order_by(Event.date, Event.time).all()
    return render_template('events.html', events=events)



@app.route('/admin/events/add', methods=['GET', 'POST'])
def add_event():
    if not authorized('add_event'):
        return redirect(url_for('events'))

    if request.method == 'POST':
        name = request.form['name']
        date = request.form['date']
        time = request.form['time']
        description = request.form['description']
        

        event = Event(name=name, date=date, time=time, description=description)
        db.session.add(event)
        db.session.commit()
        log_audit('event', f'Event created: {name}', f'Date: {date} · Time: {time}')
        return redirect(url_for('events'))

    return render_template('add_event.html')

@app.route('/admin/events', methods=['GET', 'POST'])
def admin_events():
    if not authorized('view_events'):
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        name = request.form['name']
        date = request.form['date']
        time = request.form['time']
        description = request.form['description']
        event = Event(name=name, date=date, time=time, description=description)
        db.session.add(event)
        db.session.commit()
        return redirect(url_for('admin_events'))

    events = Event.query.all()

    for event in events:
        db.session.expunge(event)
        if isinstance(event.date, str):
            try:
                event.date = datetime.strptime(event.date, '%Y-%m-%d').date()
            except Exception:
                pass
        if isinstance(event.time, str):
            try:
                event.time = datetime.strptime(event.time, '%H:%M:%S').time()
            except ValueError:
                try:
                    event.time = datetime.strptime(event.time, '%H:%M').time()
                except Exception:
                    pass

    return render_template('admin_events.html', events=events)

@app.route('/admin/events/edit/<int:event_id>', methods=['GET', 'POST'])
def edit_event(event_id):
    if not authorized('edit_event'):
        return redirect(url_for('home'))
    
    event = Event.query.get_or_404(event_id)
    
    if request.method == 'POST':
        event.name = request.form['name']
        event.date = request.form['date']
        event.time = request.form['time']
        event.description = request.form['description']
        db.session.commit()
        log_audit('event', f'Event updated: {event.name}', f'Date: {event.date}')
        return redirect(url_for('admin_events'))

    return render_template('edit_event.html', event=event)

@app.route("/delete_event/<int:event_id>", methods=["POST"])
def delete_event(event_id):
    event = Event.query.get_or_404(event_id)

    # Delete all reservations FIRST
    SeatingReservation.query.filter_by(event_id=event_id).delete()
    ename = event.name
    db.session.delete(event)
    db.session.commit()
    log_audit('event', f'Event deleted: {ename}', f'Event #{event_id}')
    return redirect(url_for("events_page"))


# ─────────────────────────────────────────────────────────────────
# Private Event Requests
# ─────────────────────────────────────────────────────────────────

@app.route('/private-event/request', methods=['GET', 'POST'])
def private_event_request():
    if not session.get('user_id'):
        return redirect(url_for('login'))

    if request.method == 'POST':
        event_date_str = request.form.get('event_date', '').strip()
        try:
            event_date_val = datetime.strptime(event_date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid date.', 'danger')
            return redirect(url_for('private_event_request'))

        req = PrivateEventRequest(
            member_id        = session['user_id'],
            event_name       = request.form.get('event_name', '').strip(),
            event_type       = request.form.get('event_type', 'buyout'),
            event_date       = event_date_val,
            start_time       = request.form.get('start_time', '').strip(),
            end_time         = request.form.get('end_time', '').strip(),
            estimated_guests = request.form.get('estimated_guests', type=int),
            description      = request.form.get('description', '').strip() or None,
            special_requests = request.form.get('special_requests', '').strip() or None,
        )
        db.session.add(req)
        db.session.commit()
        mname = f'{req.member.first_name} {req.member.last_name}'
        log_audit('event', f'Private event request submitted: {req.event_name}',
                  f'By: {mname} · Date: {event_date_str} · Type: {req.event_type}')
        flash('Your private event request has been submitted and is pending review.', 'success')
        return redirect(url_for('my_private_events'))

    return render_template('private_event_request.html', now=date.today())


@app.route('/private-events/mine')
def my_private_events():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    requests_list = PrivateEventRequest.query.filter_by(
        member_id=session['user_id']
    ).order_by(PrivateEventRequest.submitted_at.desc()).all()
    return render_template('my_private_events.html', requests=requests_list)


@app.route('/admin/private-events')
def admin_private_events():
    if not authorized('view_private_events'):
        return redirect(url_for('home'))
    status_filter = request.args.get('status', '')
    q = PrivateEventRequest.query
    if status_filter:
        q = q.filter_by(status=status_filter)
    reqs = q.order_by(PrivateEventRequest.event_date.asc(),
                      PrivateEventRequest.submitted_at.desc()).all()
    return render_template('admin_private_events.html', requests=reqs,
                           status_filter=status_filter)


@app.route('/admin/private-event/<int:req_id>/review', methods=['POST'])
def review_private_event(req_id):
    pe     = PrivateEventRequest.query.get_or_404(req_id)
    action = request.form.get('action')   # 'approve' or 'deny'

    if action == 'approve' and not authorized('approve_private_event', 'manage_private_events'):
        return redirect(url_for('home'))
    if action == 'deny' and not authorized('deny_private_event', 'manage_private_events'):
        return redirect(url_for('home'))

    admin_notes = request.form.get('admin_notes', '').strip() or None

    if action not in ('approve', 'deny'):
        flash('Invalid action.', 'danger')
        return redirect(url_for('admin_private_events'))

    pe.status        = 'approved' if action == 'approve' else 'denied'
    pe.admin_notes   = admin_notes
    pe.reviewed_at   = datetime.utcnow()
    pe.reviewed_by_id = session.get('user_id')

    if action == 'approve':
        date_str = pe.event_date.strftime('%Y-%m-%d')
        if not BlockedDate.query.filter_by(date=date_str).first():
            db.session.add(BlockedDate(date=date_str))

    db.session.commit()
    mname = f'{pe.member.first_name} {pe.member.last_name}'
    log_audit('event', f'Private event {pe.status}: {pe.event_name}',
              f'Member: {mname} · Date: {pe.event_date}')
    flash(f'Request {pe.status}.', 'success')
    return redirect(url_for('admin_private_events'))


@app.route('/admin/private-event/<int:req_id>/guests', methods=['POST'])
def update_private_event_guests(req_id):
    if not authorized('edit_private_event', 'manage_private_events'):
        return redirect(url_for('home'))
    pe = PrivateEventRequest.query.get_or_404(req_id)
    pe.actual_guests = request.form.get('actual_guests', type=int)
    db.session.commit()
    log_audit('event', f'Private event guest count updated: {pe.event_name}',
              f'Actual guests: {pe.actual_guests}')
    flash('Guest count updated.', 'success')
    return redirect(url_for('admin_private_events'))


@app.route('/generate_invoice/<int:order_id>', methods=['POST'])
def generate_invoice(order_id):
    if not authorized('generate_invoice'):
        return redirect(url_for('home'))

    order = Order.query.get_or_404(order_id)
    member = order.user

    invoice = Invoice(
        member_id=member.id,
        original_filename="Generated from Order",
        stored_filename="generated_order_invoice",
        date_created=datetime.now(timezone.utc),
        total_amount=order.total,
        tax_amount=order.tax,
        gratuity_amount=order.gratuity,
        notes=order.notes or f"Order from {order.date.strftime('%B %d, %Y')}",
        is_paid=order.paid_by_credit,
        order_id=order.id
    )

    for item in order.items:
        invoice.line_items.append(InvoiceLineItem(
            description=item.item_name,
            amount=item.price
        ))

    db.session.add(invoice)
    db.session.commit()
    log_audit('invoice', f'Invoice generated from order for {member.first_name} {member.last_name}',
              f'Order #{order_id} · Total: ${order.total:.2f}')

    flash('Invoice generated successfully.', 'success')
    return redirect(url_for('view_member', user_id=member.id))


@app.route('/generate_invoice_multi', methods=['POST'])
def generate_invoice_multi():
    if not authorized('generate_invoice'):
        return redirect(url_for('home'))

    order_ids = request.form.getlist('order_ids[]')
    if not order_ids:
        flash('No orders selected.', 'warning')
        return redirect(request.referrer or url_for('home'))

    orders = Order.query.filter(Order.id.in_([int(i) for i in order_ids])).order_by(Order.date).all()
    if not orders:
        flash('Orders not found.', 'danger')
        return redirect(request.referrer or url_for('home'))

    member = orders[0].user
    if any(o.user_id != member.id for o in orders):
        flash('All selected orders must belong to the same member.', 'danger')
        return redirect(request.referrer or url_for('home'))

    total_tax   = round(sum(o.tax      for o in orders), 2)
    total_grat  = round(sum(o.gratuity for o in orders), 2)
    total_total = round(sum(o.total    for o in orders), 2)
    all_paid    = all(o.paid_by_credit for o in orders)

    date_range = f"{orders[0].date.strftime('%b %d')} – {orders[-1].date.strftime('%b %d, %Y')}" \
        if len(orders) > 1 else orders[0].date.strftime('%B %d, %Y')

    invoice = Invoice(
        member_id=member.id,
        original_filename="Generated from Orders",
        stored_filename="generated_order_invoice",
        date_created=datetime.now(timezone.utc),
        total_amount=total_total,
        tax_amount=total_tax,
        gratuity_amount=total_grat,
        notes=f"Combined invoice for {len(orders)} order(s): {date_range}",
        is_paid=all_paid,
        order_ids_json=json.dumps([o.id for o in orders])
    )

    for order in orders:
        for item in order.items:
            invoice.line_items.append(InvoiceLineItem(
                description=f"{order.date.strftime('%b %d')} — {item.item_name}",
                amount=item.price
            ))
        if not order.items:
            invoice.line_items.append(InvoiceLineItem(
                description=f"Order — {order.date.strftime('%b %d, %Y')}",
                amount=order.subtotal
            ))

    db.session.add(invoice)
    db.session.commit()
    log_audit('invoice', f'Combined invoice generated for {member.first_name} {member.last_name}',
              f'{len(orders)} orders · Total: ${total_total:.2f}')

    flash(f'Combined invoice generated for {len(orders)} order(s).', 'success')
    return redirect(url_for('view_member', user_id=member.id))


@app.route('/members_table')
def members_table():
    if not authorized('view_members'):
        return redirect(url_for('home'))

    members = User.query.filter(User.role.in_(['member', 'staff', 'admin'])).order_by(User.last_name, User.first_name).all()
    all_membership_types = MembershipType.query.order_by(MembershipType.sort_order).all()
    return render_template('members_table.html', members=members, all_membership_types=all_membership_types)


# ...existing code...

_FLOAT_FIELDS = frozenset({
    'amount_spent', 'amount_owed', 'tax_owed', 'tax_paid',
    'gratuity_owed', 'gratuity_paid', 'minimum_adjustment',
})

@app.route('/update_member/<int:member_id>', methods=['POST'])
def update_member(member_id):
    if not authorized('edit_member'):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    member = User.query.get_or_404(member_id)
    data = request.json

    try:
        audit_parts = []
        for field, value in data.items():
            if not hasattr(member, field):
                continue
            if field == 'id':
                continue
            if field == 'password':
                if value:
                    member.set_password(value)
                    audit_parts.append('password=<changed>')
            elif field == 'active':
                setattr(member, field, str(value).strip().lower() in ('true', '1', 'yes'))
                audit_parts.append(f'active={member.active}')
            elif field == 'role':
                if session.get('role') == 'admin' and value in ('member', 'staff', 'admin'):
                    setattr(member, field, value)
                    audit_parts.append(f'role={value}')
            elif field in _FLOAT_FIELDS:
                try:
                    clean = str(value).replace('$', '').replace(',', '').strip()
                    setattr(member, field, float(clean) if clean else 0.0)
                    audit_parts.append(f'{field}={value}')
                except (ValueError, TypeError):
                    pass
            else:
                setattr(member, field, value)
                audit_parts.append(f'{field}={value}')
        db.session.commit()
        log_audit('member', f'Member updated: {member.first_name} {member.last_name}',
                  ', '.join(audit_parts))
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/update_members', methods=['POST'])
def update_members():
    if not authorized('edit_member'):
        return redirect(url_for('home'))

    updates = request.form.to_dict(flat=False)
    try:
        for member_id, fields in updates.items():
            member = User.query.get(member_id)
            for field, value in fields.items():
                if hasattr(member, field):
                    setattr(member, field, value if field != 'active' else value == 'True')
        db.session.commit()
        # No flash message here
    except Exception as e:
        db.session.rollback()
        flash(f'Error saving changes: {str(e)}', 'danger')

    return redirect(url_for('members_table'))

@app.route('/upload_invoices', methods=['GET', 'POST'])
def upload_invoices():
    if not authorized('upload_invoice'):
        return redirect(url_for('home'))

    if request.method == 'POST':
        file = request.files.get('csv_file')
        if not file or not file.filename.endswith('.csv'):
            flash('Please upload a valid CSV file.', 'danger')
            return redirect(url_for('upload_invoices'))

        try:
            import csv
            stream = file.stream.read().decode("UTF8").splitlines()
            csv_reader = csv.DictReader(stream)

            for row in csv_reader:
                # Match member by email or member number
                email = row.get('customer_email', '').strip()
                member_number = row.get('customer_guid', '').strip()
                member = None

                if email:
                    member = User.query.filter_by(email=email).first()
                if not member and member_number:
                    member = User.query.filter_by(member_number=member_number).first()

                if not member:
                    # Skip if no matching member is found
                    continue

                # Create the invoice
                total_amount = float(row.get('total', 0))
                tax_amount = float(row.get('tax', 0))
                notes = row.get('message', 'No notes provided.')

                invoice = Invoice(
                    member_id=member.id,
                    original_filename=row.get('invoice_number', 'Unknown Invoice'),
                    stored_filename="uploaded_invoice",
                    total_amount=total_amount,
                    tax_amount=tax_amount,
                    notes=notes
                )

                # Add line items if available
                line_item_description = row.get('order', 'General Invoice')
                line_item_amount = float(row.get('subtotal', 0))
                if line_item_description and line_item_amount:
                    line_item = InvoiceLineItem(
                        description=line_item_description,
                        amount=line_item_amount
                    )
                    invoice.line_items.append(line_item)

                # Update member balances
                member.amount_owed += total_amount
                member.tax_owed += tax_amount

                db.session.add(invoice)

            db.session.commit()
            flash('Invoices uploaded and processed successfully.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error processing invoices: {str(e)}', 'danger')

        return redirect(url_for('manage_members'))

    return render_template('upload_invoices.html')

@app.route('/admin-actions-log/')
def admin_actions_log():
    admin_logs = AdminActionLog.query.order_by(AdminActionLog.date.desc()).all()
    return render_template('admin_actions_log.html', admin_logs=admin_logs)

def log_admin_action(admin_id, action, details=None):
    """Log an admin action."""
    log_entry = AdminActionLog(admin_id=admin_id, action=action, details=details)
    db.session.add(log_entry)
    db.session.commit()

@app.route('/sync_toast_data', methods=['POST'])
def sync_toast_data():
    if not authorized('edit_settings'):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    # Fetch API credentials from environment
    api_key = os.getenv('TOAST_API_KEY')
    client_id = os.getenv('TOAST_CLIENT_ID')
    client_secret = os.getenv('TOAST_CLIENT_SECRET')
    secret_key = os.getenv('TOAST_SECRET_KEY')

    if not api_key or not client_id or not client_secret or not secret_key:
        flash('API credentials are not configured.', 'danger')
        return redirect(url_for('manage_members'))

    try:
        # Fetch data from Toast API
        app.logger.info("Fetching data from Toast API...")
        toast_data = toast_api_get(
            "restaurants/admin/invoices/customers",  # Updated endpoint
            api_key=api_key,
            client_id=client_id,
            client_secret=client_secret,
            secret_key=secret_key
        )

        # Log the API response for debugging
        app.logger.info("Toast API Response: %s", toast_data)

        if not toast_data or 'customers' not in toast_data:
            flash('No customer data received from Toast.', 'warning')
            return redirect(url_for('manage_members'))

        # Process each customer
        for customer in toast_data.get('customers', []):
            app.logger.info("Processing customer: %s", customer)
            email = customer.get('email')
            if not email:
                app.logger.warning("Customer missing email: %s", customer)
                continue

            member = User.query.filter_by(email=email).first()

            if not member:
                # Create new member
                app.logger.info("Creating new member: %s", email)
                member = User(
                    username=customer.get('username', email.split('@')[0]),
                    first_name=customer.get('first_name'),
                    last_name=customer.get('last_name'),
                    email=email,
                    phone=customer.get('phone'),
                    role='member',
                    active=True
                )
                member.set_password('default_password')  # Set a default password
                db.session.add(member)
            else:
                app.logger.info("Member already exists: %s", email)

        db.session.commit()
        flash('Members synced successfully from Toast.', 'success')
    except Exception as e:
        app.logger.error("Error syncing data from Toast: %s", str(e))
        db.session.rollback()
        flash(f'Error syncing data from Toast: {str(e)}', 'danger')

    return redirect(url_for('manage_members'))

# ----------------------
# Reports engine
# ----------------------

REPORT_SOURCES = {
    'members': {
        'label': 'Members',
        'has_dates': False,
        'columns': [
            {'key': 'full_name',          'label': 'Full Name',        'type': 'str'},
            {'key': 'first_name',         'label': 'First Name',       'type': 'str'},
            {'key': 'last_name',          'label': 'Last Name',        'type': 'str'},
            {'key': 'username',           'label': 'Username',         'type': 'str'},
            {'key': 'email',              'label': 'Email',            'type': 'str'},
            {'key': 'phone',              'label': 'Phone',            'type': 'str'},
            {'key': 'member_number',      'label': 'Member #',         'type': 'str'},
            {'key': 'membership_type',    'label': 'Membership Type',  'type': 'str'},
            {'key': 'active',             'label': 'Active',           'type': 'bool'},
            {'key': 'amount_spent',       'label': 'Total Spent',      'type': 'currency'},
            {'key': 'amount_owed',        'label': 'Amount Owed',      'type': 'currency'},
            {'key': 'tax_owed',           'label': 'Tax Owed',         'type': 'currency'},
            {'key': 'gratuity_owed',      'label': 'Gratuity Owed',    'type': 'currency'},
            {'key': 'minimum_adjustment', 'label': 'Min. Adjustment',  'type': 'currency'},
        ],
        'filterable': [
            {'key': 'membership_type', 'label': 'Membership Type', 'type': 'select'},
            {'key': 'active',          'label': 'Active',           'type': 'bool'},
            {'key': 'amount_spent',    'label': 'Total Spent',      'type': 'number'},
            {'key': 'amount_owed',     'label': 'Amount Owed',      'type': 'number'},
            {'key': 'tax_owed',        'label': 'Tax Owed',         'type': 'number'},
            {'key': 'gratuity_owed',   'label': 'Gratuity Owed',   'type': 'number'},
        ],
        'sortable': [
            {'key': 'first_name',   'label': 'First Name'},
            {'key': 'last_name',    'label': 'Last Name'},
            {'key': 'amount_spent', 'label': 'Total Spent'},
            {'key': 'amount_owed',  'label': 'Amount Owed'},
            {'key': 'membership_type', 'label': 'Membership Type'},
        ],
    },
    'orders': {
        'label': 'Orders',
        'has_dates': True,
        'columns': [
            {'key': 'member_name', 'label': 'Member',    'type': 'str'},
            {'key': 'date',        'label': 'Date',      'type': 'date'},
            {'key': 'time',        'label': 'Time',      'type': 'str'},
            {'key': 'subtotal',    'label': 'Subtotal',  'type': 'currency'},
            {'key': 'tax',         'label': 'Tax',       'type': 'currency'},
            {'key': 'gratuity',    'label': 'Gratuity',  'type': 'currency'},
            {'key': 'total',       'label': 'Total',     'type': 'currency'},
            {'key': 'paid',        'label': 'Paid',      'type': 'bool'},
            {'key': 'notes',       'label': 'Notes',     'type': 'str'},
        ],
        'filterable': [
            {'key': 'paid',     'label': 'Paid',     'type': 'bool'},
            {'key': 'total',    'label': 'Total',    'type': 'number'},
            {'key': 'subtotal', 'label': 'Subtotal', 'type': 'number'},
        ],
        'sortable': [
            {'key': 'date',  'label': 'Date'},
            {'key': 'total', 'label': 'Total'},
        ],
    },
    'invoices': {
        'label': 'Invoices',
        'has_dates': True,
        'columns': [
            {'key': 'member_name',     'label': 'Member',   'type': 'str'},
            {'key': 'date_created',    'label': 'Date',     'type': 'date'},
            {'key': 'total_amount',    'label': 'Total',    'type': 'currency'},
            {'key': 'tax_amount',      'label': 'Tax',      'type': 'currency'},
            {'key': 'gratuity_amount', 'label': 'Gratuity', 'type': 'currency'},
            {'key': 'is_paid',         'label': 'Paid',     'type': 'bool'},
            {'key': 'notes',           'label': 'Notes',    'type': 'str'},
        ],
        'filterable': [
            {'key': 'is_paid',      'label': 'Paid',    'type': 'bool'},
            {'key': 'total_amount', 'label': 'Total',   'type': 'number'},
        ],
        'sortable': [
            {'key': 'date_created', 'label': 'Date'},
            {'key': 'total_amount', 'label': 'Total'},
        ],
    },
    'reservations': {
        'label': 'Reservations',
        'has_dates': True,
        'columns': [
            {'key': 'member_name', 'label': 'Member', 'type': 'str'},
            {'key': 'date',        'label': 'Date',   'type': 'date'},
            {'key': 'time',        'label': 'Time',   'type': 'str'},
            {'key': 'guests',      'label': 'Guests', 'type': 'number'},
            {'key': 'notes',       'label': 'Notes',  'type': 'str'},
        ],
        'filterable': [
            {'key': 'guests', 'label': 'Guests', 'type': 'number'},
        ],
        'sortable': [
            {'key': 'date',   'label': 'Date'},
            {'key': 'guests', 'label': 'Guests'},
        ],
    },
}


def _apply_num_filter(q, field, op, val):
    try:
        fval = float(val)
    except (ValueError, TypeError):
        return q
    ops = {'eq': field == fval, 'gt': field > fval, 'gte': field >= fval,
           'lt': field < fval,  'lte': field <= fval}
    expr = ops.get(op)
    return q.filter(expr) if expr is not None else q


def _apply_date_filter(q, field, op, val):
    try:
        d = datetime.strptime(val, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return q
    ops = {'eq': field == d, 'gt': field > d, 'gte': field >= d,
           'lt': field < d,  'lte': field <= d}
    expr = ops.get(op)
    return q.filter(expr) if expr is not None else q


def execute_report(config):
    source   = config.get('source', 'members')
    sel_cols = config.get('columns', [])
    filters  = config.get('filters', [])
    sort_by  = config.get('sort_by', '')
    sort_dir = config.get('sort_dir', 'asc')
    date_from = config.get('date_from', '')
    date_to   = config.get('date_to', '')

    src_def  = REPORT_SOURCES.get(source, {})
    col_defs = {c['key']: c for c in src_def.get('columns', [])}
    headers  = [col_defs[k]['label'] for k in sel_cols if k in col_defs]
    col_types = [col_defs[k]['type']  for k in sel_cols if k in col_defs]
    rows = []

    if source == 'members':
        q = User.query.filter_by(role='member')
        for f in filters:
            fk, op, val = f.get('field'), f.get('op'), f.get('value', '')
            if fk == 'active':
                q = q.filter(User.active == (val == 'true'))
            elif fk == 'membership_type':
                q = q.filter(User.membership_type == val)
            elif fk in ('amount_spent', 'amount_owed', 'tax_owed', 'gratuity_owed'):
                q = _apply_num_filter(q, getattr(User, fk), op, val)
        sort_map = {'first_name': User.first_name, 'last_name': User.last_name,
                    'amount_spent': User.amount_spent, 'amount_owed': User.amount_owed,
                    'membership_type': User.membership_type}
        col = sort_map.get(sort_by)
        if col is not None:
            q = q.order_by(col.desc() if sort_dir == 'desc' else col)
        else:
            q = q.order_by(User.first_name, User.last_name)
        for m in q.all():
            name = ' '.join(filter(None, [m.first_name, m.last_name]))
            def _mv(k):
                return {
                    'full_name': name, 'first_name': m.first_name or '',
                    'last_name': m.last_name or '', 'username': m.username or '',
                    'email': m.email or '', 'phone': m.phone or '',
                    'member_number': m.member_number or '',
                    'membership_type': m.membership_type or '',
                    'active': 'Yes' if m.active else 'No',
                    'amount_spent': m.amount_spent or 0,
                    'amount_owed': m.amount_owed or 0,
                    'tax_owed': m.tax_owed or 0,
                    'gratuity_owed': m.gratuity_owed or 0,
                    'minimum_adjustment': m.minimum_adjustment or 0,
                }.get(k, '')
            rows.append([_mv(k) for k in sel_cols if k in col_defs])

    elif source == 'orders':
        q = Order.query.join(User, Order.user_id == User.id)
        for f in filters:
            fk, op, val = f.get('field'), f.get('op'), f.get('value', '')
            if fk == 'paid':
                q = q.filter(Order.paid == (val == 'true'))
            elif fk == 'total':
                q = _apply_num_filter(q, Order.total, op, val)
            elif fk == 'subtotal':
                q = _apply_num_filter(q, Order.subtotal, op, val)
        if date_from:
            try: q = q.filter(Order.date >= datetime.strptime(date_from, '%Y-%m-%d').date())
            except ValueError: pass
        if date_to:
            try: q = q.filter(Order.date <= datetime.strptime(date_to, '%Y-%m-%d').date())
            except ValueError: pass
        sort_map = {'date': Order.date, 'total': Order.total}
        col = sort_map.get(sort_by, Order.date)
        q = q.order_by(col.desc() if sort_dir == 'desc' else col)
        for o in q.all():
            mname = ' '.join(filter(None, [o.user.first_name, o.user.last_name])) if o.user else ''
            def _ov(k):
                return {
                    'member_name': mname,
                    'date': o.date.strftime('%Y-%m-%d') if o.date else '',
                    'time': o.time.strftime('%H:%M') if o.time else '',
                    'subtotal': o.subtotal or 0, 'tax': o.tax or 0,
                    'gratuity': o.gratuity or 0, 'total': o.total or 0,
                    'paid': 'Yes' if o.paid else 'No', 'notes': o.notes or '',
                }.get(k, '')
            rows.append([_ov(k) for k in sel_cols if k in col_defs])

    elif source == 'invoices':
        q = Invoice.query.join(User, Invoice.member_id == User.id)
        for f in filters:
            fk, op, val = f.get('field'), f.get('op'), f.get('value', '')
            if fk == 'is_paid':
                q = q.filter(Invoice.is_paid == (val == 'true'))
            elif fk == 'total_amount':
                q = _apply_num_filter(q, Invoice.total_amount, op, val)
        if date_from:
            try: q = q.filter(Invoice.date_created >= datetime.strptime(date_from, '%Y-%m-%d'))
            except ValueError: pass
        if date_to:
            try: q = q.filter(Invoice.date_created <= datetime.strptime(date_to, '%Y-%m-%d'))
            except ValueError: pass
        sort_map = {'date_created': Invoice.date_created, 'total_amount': Invoice.total_amount}
        col = sort_map.get(sort_by, Invoice.date_created)
        q = q.order_by(col.desc() if sort_dir == 'desc' else col)
        for inv in q.all():
            mname = ' '.join(filter(None, [inv.member.first_name, inv.member.last_name])) if inv.member else ''
            def _iv(k):
                return {
                    'member_name': mname,
                    'date_created': inv.date_created.strftime('%Y-%m-%d') if inv.date_created else '',
                    'total_amount': inv.total_amount or 0, 'tax_amount': inv.tax_amount or 0,
                    'gratuity_amount': inv.gratuity_amount or 0,
                    'is_paid': 'Yes' if inv.is_paid else 'No', 'notes': inv.notes or '',
                }.get(k, '')
            rows.append([_iv(k) for k in sel_cols if k in col_defs])

    elif source == 'reservations':
        q = Reservation.query.join(User, Reservation.user_id == User.id)
        for f in filters:
            fk, op, val = f.get('field'), f.get('op'), f.get('value', '')
            if fk == 'guests':
                q = _apply_num_filter(q, Reservation.guests, op, val)
        if date_from:
            try: q = q.filter(Reservation.date >= datetime.strptime(date_from, '%Y-%m-%d').date())
            except ValueError: pass
        if date_to:
            try: q = q.filter(Reservation.date <= datetime.strptime(date_to, '%Y-%m-%d').date())
            except ValueError: pass
        sort_map = {'date': Reservation.date, 'guests': Reservation.guests}
        col = sort_map.get(sort_by, Reservation.date)
        q = q.order_by(col.desc() if sort_dir == 'desc' else col)
        for r in q.all():
            mname = ' '.join(filter(None, [r.user.first_name, r.user.last_name])) if r.user else ''
            def _rv(k):
                return {
                    'member_name': mname,
                    'date': r.date.strftime('%Y-%m-%d') if r.date else '',
                    'time': r.time.strftime('%H:%M') if r.time else '',
                    'guests': r.guests or 0, 'notes': r.notes or '',
                }.get(k, '')
            rows.append([_rv(k) for k in sel_cols if k in col_defs])

    # Compute column totals for currency/number columns
    totals = []
    for i, ct in enumerate(col_types):
        if ct in ('currency', 'number'):
            try:
                totals.append(sum(float(r[i]) for r in rows if isinstance(r[i], (int, float))))
            except Exception:
                totals.append(None)
        else:
            totals.append(None)

    # Format currency values for display
    fmt_rows = []
    for row in rows:
        fmt_row = []
        for i, (val, ct) in enumerate(zip(row, col_types)):
            if ct == 'currency' and isinstance(val, (int, float)):
                fmt_row.append(f'${val:,.2f}')
            else:
                fmt_row.append(val)
        fmt_rows.append(fmt_row)

    fmt_totals = []
    for val, ct in zip(totals, col_types):
        if ct == 'currency' and val is not None:
            fmt_totals.append(f'${val:,.2f}')
        elif ct == 'number' and val is not None:
            fmt_totals.append(str(val))
        else:
            fmt_totals.append('')

    return {
        'headers': headers,
        'col_types': col_types,
        'header_keys': [k for k in sel_cols if k in col_defs],
        'rows': fmt_rows,
        'raw_rows': rows,
        'totals': fmt_totals,
        'count': len(rows),
        'source_label': src_def.get('label', source),
    }


@app.route('/admin/analytics')
def admin_analytics():
    if not authorized('view_analytics'):
        return redirect(url_for('home'))

    today = date.today()

    # Build list of (year, month) for the last 12 months, oldest first
    months = []
    y, m = today.year, today.month
    for _ in range(12):
        months.insert(0, (y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1

    month_labels = [f"{date(yr, mo, 1).strftime('%b %Y')}" for yr, mo in months]

    def ym_key(yr, mo):
        return f'{yr:04d}-{mo:02d}'

    # ── Monthly revenue (from Orders) ─────────────────────────────
    rev_rows = db.session.query(
        db.func.strftime('%Y-%m', Order.date).label('ym'),
        db.func.sum(Order.total).label('rev')
    ).group_by('ym').all()
    rev_map = {r.ym: round(float(r.rev or 0), 2) for r in rev_rows}
    monthly_revenue = [rev_map.get(ym_key(yr, mo), 0) for yr, mo in months]

    # ── Monthly reservation counts ────────────────────────────────
    rsv_rows = db.session.query(
        db.func.strftime('%Y-%m', Reservation.date).label('ym'),
        db.func.count(Reservation.id).label('cnt')
    ).group_by('ym').all()
    rsv_map = {r.ym: r.cnt for r in rsv_rows}
    monthly_reservations = [rsv_map.get(ym_key(yr, mo), 0) for yr, mo in months]

    # ── New members per month (by created_at) ─────────────────────
    new_mem_rows = db.session.query(
        db.func.strftime('%Y-%m', User.created_at).label('ym'),
        db.func.count(User.id).label('cnt')
    ).filter(User.role == 'member', User.created_at.isnot(None)).group_by('ym').all()
    new_mem_map = {r.ym: r.cnt for r in new_mem_rows}
    monthly_new_members = [new_mem_map.get(ym_key(yr, mo), 0) for yr, mo in months]

    # ── KPI scalars ───────────────────────────────────────────────
    total_members    = User.query.filter_by(role='member').count()
    active_members   = User.query.filter_by(role='member', active=True).count()
    inactive_members = User.query.filter_by(role='member', active=False).count()

    churn_rate = round((inactive_members / total_members * 100) if total_members else 0, 1)

    total_revenue = db.session.query(db.func.sum(Order.total)).scalar() or 0
    avg_revenue_per_member = round(float(total_revenue) / active_members, 2) if active_members else 0

    # Avg monthly visit frequency: reservations in last 90 days / 3 / active members
    cutoff_90 = today - timedelta(days=90)
    recent_rsv = Reservation.query.filter(Reservation.date >= cutoff_90).count()
    avg_monthly_visits = round((recent_rsv / 3) / active_members, 2) if active_members else 0

    # Revenue per member per month (for trend line)
    monthly_rpm = [
        round(monthly_revenue[i] / active_members, 2) if active_members else 0
        for i in range(12)
    ]

    # Membership type breakdown (pie)
    types = MembershipType.query.order_by(MembershipType.sort_order).all()
    type_labels = [t.display_name for t in types]
    type_counts_list = [
        User.query.filter_by(role='member', membership_type=t.name).count()
        for t in types
    ]
    # Catch members whose type isn't in MembershipType table
    known_types = {t.name for t in types}
    other_count = User.query.filter(
        User.role == 'member',
        ~User.membership_type.in_(known_types)
    ).count() if known_types else User.query.filter_by(role='member').count()
    if other_count:
        type_labels.append('Other')
        type_counts_list.append(other_count)

    return render_template('admin_analytics.html',
        month_labels=month_labels,
        monthly_revenue=monthly_revenue,
        monthly_reservations=monthly_reservations,
        monthly_new_members=monthly_new_members,
        monthly_rpm=monthly_rpm,
        total_members=total_members,
        active_members=active_members,
        inactive_members=inactive_members,
        churn_rate=churn_rate,
        avg_revenue_per_member=avg_revenue_per_member,
        avg_monthly_visits=avg_monthly_visits,
        total_revenue=round(float(total_revenue), 2),
        type_labels=type_labels,
        type_counts_list=type_counts_list,
    )


@app.route('/admin/calendar')
def admin_calendar():
    can_view = (authorized('view_reservations') or
                authorized('view_events') or
                authorized('view_private_events'))
    if not can_view:
        return redirect(url_for('home'))
    return render_template('admin_calendar.html')


@app.route('/admin/calendar/events')
def admin_calendar_events():
    can_view = (authorized('view_reservations') or
                authorized('view_events') or
                authorized('view_private_events'))
    if not can_view:
        return jsonify([])

    start_str = request.args.get('start', '')
    end_str   = request.args.get('end', '')
    try:
        start_date = datetime.fromisoformat(start_str[:10]).date() if start_str else date.today() - timedelta(days=60)
        end_date   = datetime.fromisoformat(end_str[:10]).date()   if end_str   else date.today() + timedelta(days=60)
    except ValueError:
        start_date = date.today() - timedelta(days=60)
        end_date   = date.today() + timedelta(days=60)

    events = []

    # ── Reservations ──────────────────────────────────────────────────────────
    if authorized('view_reservations'):
        for r in Reservation.query.filter(
            Reservation.date >= start_date,
            Reservation.date <= end_date
        ).all():
            member_name = f'{r.user.first_name} {r.user.last_name}' if r.user else 'Unknown'
            g = r.guests or 1
            time_str = r.time.strftime('%H:%M:%S') if r.time else '19:00:00'
            events.append({
                'id':    f'rsv-{r.id}',
                'title': f'{member_name} · {g} guest{"s" if g != 1 else ""}',
                'start': f'{r.date.isoformat()}T{time_str}',
                'color': '#5c9bf5',
                'extendedProps': {
                    'type':   'reservation',
                    'member': member_name,
                    'guests': g,
                    'notes':  r.notes or '',
                    'member_id': r.user_id,
                },
            })

    # ── Club Events ───────────────────────────────────────────────────────────
    if authorized('view_events'):
        for e in Event.query.filter(
            Event.date >= start_date.isoformat(),
            Event.date <= end_date.isoformat()
        ).all():
            time_part = e.time if e.time else '19:00'
            events.append({
                'id':    f'evt-{e.id}',
                'title': e.name,
                'start': f'{e.date}T{time_part}',
                'color': '#f5b45c',
                'extendedProps': {
                    'type':        'event',
                    'description': e.description or '',
                },
            })

    # ── Private Events ────────────────────────────────────────────────────────
    if authorized('view_private_events'):
        for pe in PrivateEventRequest.query.filter(
            PrivateEventRequest.event_date >= start_date,
            PrivateEventRequest.event_date <= end_date,
            PrivateEventRequest.status != 'denied'
        ).all():
            color  = '#22c55e' if pe.status == 'approved' else '#f59e0b'
            prefix = '' if pe.status == 'approved' else 'PENDING: '
            member_name = f'{pe.member.first_name} {pe.member.last_name}'
            type_label  = 'Full Buyout' if pe.event_type == 'buyout' else 'Hosted Night'
            start_iso   = pe.event_date.isoformat()
            if pe.start_time:
                start_iso += f'T{pe.start_time}'
            ev = {
                'id':    f'pe-{pe.id}',
                'title': f'{prefix}{pe.event_name} ({type_label})',
                'start': start_iso,
                'color': color,
                'extendedProps': {
                    'type':              'private_event',
                    'status':            pe.status,
                    'member':            member_name,
                    'member_id':         pe.member_id,
                    'event_type':        type_label,
                    'estimated_guests':  pe.estimated_guests,
                    'special_requests':  pe.special_requests or '',
                    'description':       pe.description or '',
                },
            }
            if pe.end_time:
                ev['end'] = f'{pe.event_date.isoformat()}T{pe.end_time}'
            events.append(ev)

    # ── Blocked Dates ─────────────────────────────────────────────────────────
    if authorized('view_reservations'):
        for b in BlockedDate.query.filter(
            BlockedDate.date >= start_date.isoformat(),
            BlockedDate.date <= end_date.isoformat()
        ).all():
            events.append({
                'id':    f'blk-{b.id}',
                'title': 'Blocked',
                'start': b.date,
                'allDay': True,
                'color': '#ef4444',
                'extendedProps': {'type': 'blocked'},
            })

    return jsonify(events)


@app.route('/admin/reports')
def admin_reports():
    if not authorized('view_reports'):
        return redirect(url_for('home'))
    reports = SavedReport.query.order_by(SavedReport.name).all()
    membership_type_options = [{'value': t.name, 'label': t.display_name}
                               for t in MembershipType.query.order_by(MembershipType.sort_order).all()]
    return render_template(
        'admin_reports.html',
        reports=reports,
        sources_json=json.dumps(REPORT_SOURCES),
        membership_type_options_json=json.dumps(membership_type_options),
    )


@app.route('/admin/reports/save', methods=['POST'])
def save_report():
    if not authorized('create_report'):
        return redirect(url_for('home'))
    name        = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    config_raw  = request.form.get('config', '{}')
    if not name:
        flash('Report name is required.', 'danger')
        return redirect(url_for('admin_reports'))
    try:
        json.loads(config_raw)
    except ValueError:
        flash('Invalid report configuration.', 'danger')
        return redirect(url_for('admin_reports'))
    rpt = SavedReport(name=name, description=description, config=config_raw)
    db.session.add(rpt)
    db.session.commit()
    log_audit('report', f'Report created: {name}', f'Source: {json.loads(config_raw).get("source", "?")}')
    flash(f'Report "{name}" saved.', 'success')
    return redirect(url_for('run_report', report_id=rpt.id))


@app.route('/admin/reports/<int:report_id>/update', methods=['POST'])
def update_report(report_id):
    if not authorized('edit_report'):
        return redirect(url_for('home'))
    rpt = SavedReport.query.get_or_404(report_id)
    rpt.name        = request.form.get('name', rpt.name).strip()
    rpt.description = request.form.get('description', rpt.description or '').strip()
    config_raw      = request.form.get('config', rpt.config)
    try:
        json.loads(config_raw)
        rpt.config = config_raw
    except ValueError:
        flash('Invalid report configuration.', 'danger')
        return redirect(url_for('admin_reports'))
    db.session.commit()
    log_audit('report', f'Report updated: {rpt.name}', f'Source: {json.loads(rpt.config).get("source", "?")}')
    flash(f'Report "{rpt.name}" updated.', 'success')
    return redirect(url_for('run_report', report_id=rpt.id))


@app.route('/admin/reports/<int:report_id>/delete', methods=['POST'])
def delete_report(report_id):
    if not authorized('delete_report'):
        return redirect(url_for('home'))
    rpt = SavedReport.query.get_or_404(report_id)
    name = rpt.name
    db.session.delete(rpt)
    db.session.commit()
    log_audit('report', f'Report deleted: {name}')
    flash(f'Report "{name}" deleted.', 'success')
    return redirect(url_for('admin_reports'))


@app.route('/admin/reports/<int:report_id>/run')
def run_report(report_id):
    if not authorized('view_reports'):
        return redirect(url_for('home'))
    rpt = SavedReport.query.get_or_404(report_id)
    config = json.loads(rpt.config)
    results = execute_report(config)
    rpt.last_run_at = datetime.utcnow()
    db.session.commit()
    return render_template('admin_report_run.html', report=rpt, config=config, results=results)


@app.route('/admin/reports/<int:report_id>/export')
def export_report(report_id):
    if not authorized('export_report'):
        return redirect(url_for('home'))
    rpt = SavedReport.query.get_or_404(report_id)
    config = json.loads(rpt.config)
    results = execute_report(config)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(results['headers'])
    for row in results['rows']:
        writer.writerow(row)
    if any(results['totals']):
        writer.writerow(['TOTAL' if i == 0 else (t or '') for i, t in enumerate(results['totals'])])
    output.seek(0)
    filename = rpt.name.lower().replace(' ', '_') + '.csv'
    return make_response(
        output.getvalue(),
        200,
        {'Content-Type': 'text/csv',
         'Content-Disposition': f'attachment; filename="{filename}"'}
    )


# ----------------------
# Audit route
# ----------------------

@app.route('/admin/audit')
def admin_audit():
    if not authorized('view_audit'):
        return redirect(url_for('home'))

    page            = request.args.get('page', 1, type=int)
    category        = request.args.get('category', '')
    change_type     = request.args.get('change_type', '')
    username        = request.args.get('username', '').strip()
    date_from       = request.args.get('date_from', '')
    date_to         = request.args.get('date_to', '')
    search          = request.args.get('search', '').strip()
    per_page        = 100

    q = AuditLog.query
    if category:
        q = q.filter(AuditLog.category == category)
    if change_type == 'changes':
        q = q.filter(AuditLog.category != 'page_visit')
    elif change_type == 'visits':
        q = q.filter(AuditLog.category == 'page_visit')
    if username:
        q = q.filter(AuditLog.username.ilike(f'%{username}%'))
    if date_from:
        try:
            q = q.filter(AuditLog.timestamp >= datetime.strptime(date_from, '%Y-%m-%d'))
        except ValueError:
            pass
    if date_to:
        try:
            q = q.filter(AuditLog.timestamp <= datetime.strptime(date_to, '%Y-%m-%d').replace(hour=23, minute=59, second=59))
        except ValueError:
            pass
    if search:
        q = q.filter(
            AuditLog.action.ilike(f'%{search}%') |
            AuditLog.details.ilike(f'%{search}%') |
            AuditLog.path.ilike(f'%{search}%')
        )

    q = q.order_by(AuditLog.timestamp.desc())
    total  = q.count()
    logs   = q.offset((page - 1) * per_page).limit(per_page).all()
    pages  = (total + per_page - 1) // per_page

    categories = [r[0] for r in db.session.query(AuditLog.category).distinct().order_by(AuditLog.category).all()]

    return render_template('admin_audit.html',
        logs=logs, page=page, pages=pages, total=total,
        categories=categories,
        filter_category=category, filter_change_type=change_type,
        filter_username=username, filter_date_from=date_from,
        filter_date_to=date_to, filter_search=search,
    )


@app.route('/admin/audit/clear', methods=['POST'])
def clear_audit_log():
    if not authorized('clear_audit'):
        return redirect(url_for('home'))
    days = request.form.get('days', 30, type=int)
    cutoff = datetime.utcnow() - timedelta(days=days)
    deleted = AuditLog.query.filter(AuditLog.timestamp < cutoff).delete()
    db.session.commit()
    log_audit('system', f'Audit log cleared', f'Deleted {deleted} entries older than {days} days')
    flash(f'Cleared {deleted} audit entries older than {days} days.', 'success')
    return redirect(url_for('admin_audit'))


# ----------------------
# Settings routes
# ----------------------

@app.route('/admin/settings', methods=['GET', 'POST'])
def admin_settings():
    if not authorized('view_settings'):
        return redirect(url_for('home'))

    if request.method == 'POST':
        changed = []
        for key in SETTING_DEFAULTS:
            # checkboxes come through only when checked
            if key in ('applications_open', 'notify_on_new_application', 'notify_on_invoice_created'):
                new_val = 'true' if request.form.get(key) else 'false'
            else:
                new_val = request.form.get(key, '').strip()
            old_val = get_setting(key)
            if new_val != old_val:
                changed.append(f'{key}: {old_val!r} → {new_val!r}')
            set_setting(key, new_val)
        db.session.commit()
        if changed:
            log_audit('settings', 'Club settings updated', ' | '.join(changed))
        flash('Settings saved.', 'success')
        return redirect(url_for('admin_settings'))

    types = MembershipType.query.order_by(MembershipType.sort_order, MembershipType.display_name).all()
    type_counts = {}
    for t in types:
        type_counts[t.id] = User.query.filter_by(role='member', membership_type=t.name).count()
    settings = {k: get_setting(k, v) for k, v in SETTING_DEFAULTS.items()}
    staff_roles = StaffRole.query.order_by(StaffRole.display_name).all()
    return render_template('admin_settings.html',
        types=types, type_counts=type_counts, settings=settings,
        staff_roles=staff_roles, permissions=PERMISSIONS)


@app.route('/admin/settings/membership-type/add', methods=['POST'])
def add_membership_type():
    if not authorized('manage_membership_types'):
        return redirect(url_for('home'))
    name         = request.form.get('name', '').strip().lower().replace(' ', '_')
    display_name = request.form.get('display_name', '').strip()
    min_spend    = float(request.form.get('min_spend', 0) or 0)
    monthly_dues = float(request.form.get('monthly_dues', 0) or 0)
    description  = request.form.get('description', '').strip()
    sort_order   = int(request.form.get('sort_order', 0) or 0)
    if not name or not display_name:
        flash('Name and display name are required.', 'danger')
        return redirect(url_for('admin_settings'))
    if MembershipType.query.filter_by(name=name).first():
        flash(f'A membership type with slug "{name}" already exists.', 'danger')
        return redirect(url_for('admin_settings'))
    mt = MembershipType(
        name=name, display_name=display_name,
        min_spend=min_spend, monthly_dues=monthly_dues,
        description=description, sort_order=sort_order, is_active=True
    )
    db.session.add(mt)
    db.session.commit()
    log_audit('settings', f'Membership type created: {display_name}', f'Slug: {name} · Min spend: ${min_spend:.2f}')
    flash(f'Membership type "{display_name}" added.', 'success')
    return redirect(url_for('admin_settings'))


@app.route('/admin/settings/membership-type/<int:type_id>/edit', methods=['POST'])
def edit_membership_type(type_id):
    if not authorized('manage_membership_types'):
        return redirect(url_for('home'))
    mt = MembershipType.query.get_or_404(type_id)
    mt.display_name  = request.form.get('display_name', mt.display_name).strip()
    mt.min_spend     = float(request.form.get('min_spend', mt.min_spend) or 0)
    mt.monthly_dues  = float(request.form.get('monthly_dues', mt.monthly_dues) or 0)
    mt.description   = request.form.get('description', mt.description or '').strip()
    mt.sort_order    = int(request.form.get('sort_order', mt.sort_order) or 0)
    mt.is_active     = request.form.get('is_active') == 'on'
    db.session.commit()
    log_audit('settings', f'Membership type updated: {mt.display_name}', f'Slug: {mt.name} · Min spend: ${mt.min_spend:.2f} · Active: {mt.is_active}')
    flash(f'Membership type "{mt.display_name}" updated.', 'success')
    return redirect(url_for('admin_settings'))


@app.route('/admin/settings/membership-type/<int:type_id>/delete', methods=['POST'])
def delete_membership_type(type_id):
    if not authorized('manage_membership_types'):
        return redirect(url_for('home'))
    mt = MembershipType.query.get_or_404(type_id)
    count = User.query.filter_by(role='member', membership_type=mt.name).count()
    if count > 0:
        flash(f'Cannot delete "{mt.display_name}" — {count} member(s) are assigned to it. Reassign them first.', 'danger')
        return redirect(url_for('admin_settings'))
    dname = mt.display_name
    db.session.delete(mt)
    db.session.commit()
    log_audit('settings', f'Membership type deleted: {dname}')
    flash(f'Membership type "{dname}" deleted.', 'success')
    return redirect(url_for('admin_settings'))


# ----------------------
# Staff Role CRUD
# ----------------------

@app.route('/admin/settings/staff-role/add', methods=['POST'])
def add_staff_role():
    if not authorized('manage_roles'):
        return redirect(url_for('home'))
    name         = request.form.get('name', '').strip().lower().replace(' ', '_')
    display_name = request.form.get('display_name', '').strip()
    color        = request.form.get('color', 'secondary').strip()
    perms        = request.form.getlist('permissions')
    if not name or not display_name:
        flash('Name and display name are required.', 'danger')
        return redirect(url_for('admin_settings'))
    if StaffRole.query.filter_by(name=name).first():
        flash(f'A role with slug "{name}" already exists.', 'danger')
        return redirect(url_for('admin_settings'))
    role = StaffRole(name=name, display_name=display_name, color=color, permissions=json.dumps(perms))
    db.session.add(role)
    db.session.commit()
    log_audit('settings', f'Staff role created: {display_name}', f'Slug: {name} · Permissions: {len(perms)}')
    flash(f'Role "{display_name}" created.', 'success')
    return redirect(url_for('admin_settings'))


@app.route('/admin/settings/staff-role/<int:role_id>/edit', methods=['POST'])
def edit_staff_role(role_id):
    if not authorized('manage_roles'):
        return redirect(url_for('home'))
    sr = StaffRole.query.get_or_404(role_id)
    sr.display_name = request.form.get('display_name', sr.display_name).strip()
    sr.color        = request.form.get('color', sr.color).strip()
    perms           = request.form.getlist('permissions')
    sr.permissions  = json.dumps(perms)
    db.session.commit()
    # Invalidate sessions of staff users in this role (they'll get updated perms on next login)
    log_audit('settings', f'Staff role updated: {sr.display_name}', f'Slug: {sr.name} · Permissions: {len(perms)}')
    flash(f'Role "{sr.display_name}" updated.', 'success')
    return redirect(url_for('admin_settings'))


@app.route('/admin/settings/staff-role/<int:role_id>/delete', methods=['POST'])
def delete_staff_role(role_id):
    if not authorized('manage_roles'):
        return redirect(url_for('home'))
    sr = StaffRole.query.get_or_404(role_id)
    if sr.users:
        flash(f'Cannot delete "{sr.display_name}" — {len(sr.users)} user(s) are assigned to it.', 'danger')
        return redirect(url_for('admin_settings'))
    name = sr.display_name
    db.session.delete(sr)
    db.session.commit()
    log_audit('settings', f'Staff role deleted: {name}')
    flash(f'Role "{name}" deleted.', 'success')
    return redirect(url_for('admin_settings'))


@app.route('/register-staff', methods=['POST'])
def register_staff():
    if not authorized('manage_admins'):
        return redirect(url_for('home'))
    username     = request.form.get('username', '').strip()
    password     = request.form.get('password', '').strip()
    first_name   = request.form.get('first_name', '').strip()
    last_name    = request.form.get('last_name', '').strip()
    email        = request.form.get('email', '').strip()
    staff_role_id = request.form.get('staff_role_id', type=int)
    if not username or not password or not first_name:
        flash('Username, password, and first name are required.', 'danger')
        return redirect(url_for('manage_admins'))
    if User.query.filter_by(username=username).first():
        flash('Username already exists.', 'danger')
        return redirect(url_for('manage_admins'))
    u = User(username=username, first_name=first_name, last_name=last_name,
             email=email, role='staff', active=True,
             staff_role_id=staff_role_id or None)
    u.set_password(password)
    db.session.add(u)
    db.session.commit()
    log_audit('member', f'Staff user created: {first_name} {last_name}', f'Username: {username}')
    flash(f'Staff user "{username}" created.', 'success')
    return redirect(url_for('manage_admins'))


@app.route('/assign-staff-role/<int:user_id>', methods=['POST'])
def assign_staff_role(user_id):
    if not authorized('manage_admins'):
        return redirect(url_for('home'))
    user = User.query.get_or_404(user_id)
    new_role_id = request.form.get('staff_role_id', type=int)
    user.staff_role_id = new_role_id or None
    db.session.commit()
    role_name = user.staff_role.display_name if user.staff_role else 'None'
    log_audit('member', f'Staff role assigned to {user.first_name} {user.last_name}', f'Role: {role_name}')
    flash('Role updated.', 'success')
    return redirect(url_for('manage_admins'))


# ----------------------
# Run it
# ----------------------
def run_migrations():
    """Add columns that were introduced after the initial db.create_all()."""
    with db.engine.connect() as conn:
        cols = {row[1] for row in conn.execute(db.text("PRAGMA table_info('user')"))}
        if 'staff_role_id' not in cols:
            conn.execute(db.text("ALTER TABLE user ADD COLUMN staff_role_id INTEGER REFERENCES staff_role(id)"))
        if 'created_at' not in cols:
            conn.execute(db.text("ALTER TABLE user ADD COLUMN created_at DATETIME"))
        if 'favorite_drink' not in cols:
            conn.execute(db.text("ALTER TABLE user ADD COLUMN favorite_drink VARCHAR(200)"))
        if 'seating_preference' not in cols:
            conn.execute(db.text("ALTER TABLE user ADD COLUMN seating_preference VARCHAR(200)"))
        if 'allergies' not in cols:
            conn.execute(db.text("ALTER TABLE user ADD COLUMN allergies VARCHAR(500)"))
        if 'preferences_notes' not in cols:
            conn.execute(db.text("ALTER TABLE user ADD COLUMN preferences_notes TEXT"))
        conn.commit()


with app.app_context():
    db.create_all()
    run_migrations()
    seed_membership_types()
    seed_club_settings()

# =====================================================
# SHIFT PLANNER
# =====================================================

def _parse_roster_csv(csv_bytes):
    """Parse a CSV roster export. Returns {position: [{name, location, shift}]}.
    Accepts any CSV that has columns containing 'name' and 'position' (case-insensitive).
    Optional columns: shift/time, location."""
    import csv as _csv
    from io import StringIO

    text = csv_bytes.decode('utf-8-sig')
    reader = _csv.DictReader(StringIO(text))

    # Normalise header names to lowercase for flexible matching
    headers = [h.lower().strip() for h in (reader.fieldnames or [])]

    def _col(row, *candidates):
        for c in candidates:
            for h in headers:
                if c in h:
                    return row.get(next((k for k in row if k.lower().strip() == h), ''), '').strip()
        return ''

    employees = {}
    for row in reader:
        name     = _col(row, 'name', 'employee')
        position = _col(row, 'position', 'role', 'job', 'title')
        shift    = _col(row, 'shift', 'time', 'schedule', 'hours')
        location = _col(row, 'location', 'venue', 'site')

        if not name or not position:
            continue
        employees.setdefault(position, [])
        employees[position].append({'name': name, 'location': location, 'shift': shift})

    return employees


def _parse_roster_pdf(pdf_bytes):
    """Parse a roster-export PDF. Returns {position: [{name, location, shift}]}."""
    import pdfplumber

    known_positions = {
        'Bartender', 'Cook', 'Host', 'Runner', 'Server',
        'Room 120 Bartender', 'Manager', 'Barback', 'Supervisor', 'Security',
    }
    skip_prefixes = ('EMPLOYEES', 'STATUS', 'LOCATIONS', 'POSITIONS', 'TAGS', 'SHIFT TIME')
    employees = {}
    current_pos = None

    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            for line in (page.extract_text() or '').split('\n'):
                line = line.strip()
                if not line or any(line.startswith(p) for p in skip_prefixes):
                    continue
                if line in known_positions:
                    current_pos = line
                    employees.setdefault(current_pos, [])
                    continue
                if current_pos is None:
                    continue

                time_m = re.search(r'(\d+:\d+\s*(?:AM|PM)\s*-\s*\d+:\d+\s*(?:AM|PM))', line)
                shift  = time_m.group(1).strip() if time_m else ''
                chunk  = (line[:time_m.start()] if time_m else line).rstrip('- ').strip()

                location = ''
                for loc_str, loc_name in [
                    ('The Draft Room (79 Perry Street)', 'The Draft Room'),
                    ('The Draft Room', 'The Draft Room'),
                    ('Room 120', 'Room 120'),
                ]:
                    if loc_str in chunk:
                        location = loc_name
                        chunk = chunk.replace(loc_str, '').strip()
                        break

                name = chunk.replace(current_pos, '').strip('- ').strip()
                if name and len(name) > 1:
                    employees[current_pos].append({'name': name, 'location': location, 'shift': shift})

    return employees


def _shift_end_hour(shift_str):
    """Return the shift end time as a 24-hour integer, or 0 if unparseable."""
    m = re.search(r'-\s*(\d+):(\d+)\s*(AM|PM)', shift_str)
    if not m:
        return 0
    h, mi, period = int(m.group(1)), int(m.group(2)), m.group(3)
    if period == 'PM' and h != 12:
        h += 12
    elif period == 'AM' and h == 12:
        h = 0
    return h


def _generate_break_rotation(names, start_hour=19, start_min=0):
    """Round-robin 30-min break slots starting at start_hour:start_min (24h)."""
    rows = []
    h, m = start_hour, start_min
    i = 0
    while i < len(names):
        def fmt(hh, mm):
            label = 'AM' if hh < 12 else 'PM'
            hh12 = hh % 12 or 12
            return f'{hh12}:{mm:02d} {label}'

        eh, em = h, m + 30
        if em >= 60:
            eh += 1
            em -= 60

        on_break = [names[i]]
        if i + 1 < len(names) and len(names) > 3:
            on_break.append(names[i + 1])
            i += 2
        else:
            i += 1

        on_floor = [n for n in names if n not in on_break]
        rows.append({
            'time': f'{fmt(h, m)} – {fmt(eh, em)}',
            'on_break': ' & '.join(on_break),
            'on_floor': ', '.join(on_floor),
        })
        h, m = eh, em
    return rows


SHIFT_HISTORY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shift_history')
os.makedirs(SHIFT_HISTORY_DIR, exist_ok=True)


def _save_shift_history(plan):
    """Persist a finalized plan to shift_history/. Keeps 50 most recent."""
    ts    = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    slug  = re.sub(r'[^\w]', '_', plan.get('date', 'unknown'))[:20]
    fname = f'{ts}_{slug}.json'
    path  = os.path.join(SHIFT_HISTORY_DIR, fname)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'saved_at': datetime.utcnow().isoformat(), 'plan': plan}, f, indent=2)
    files = sorted(os.listdir(SHIFT_HISTORY_DIR))
    for old in files[:-50]:
        try:
            os.remove(os.path.join(SHIFT_HISTORY_DIR, old))
        except OSError:
            pass
    return fname


def _load_shift_history():
    """Return list of {filename, saved_at, event_name, date} newest-first."""
    entries = []
    for fname in sorted(os.listdir(SHIFT_HISTORY_DIR), reverse=True):
        if not fname.endswith('.json'):
            continue
        try:
            with open(os.path.join(SHIFT_HISTORY_DIR, fname), encoding='utf-8') as f:
                data = json.load(f)
            plan = data.get('plan', {})
            entries.append({
                'filename':   fname,
                'saved_at':   data.get('saved_at', ''),
                'event_name': plan.get('event_name', ''),
                'venue':      plan.get('venue', ''),
                'date':       plan.get('date', ''),
            })
        except Exception:
            pass
    return entries


@app.route('/admin/shift-planner', methods=['GET'])
def shift_planner():
    if not authorized('view_shift_planner'):
        return redirect(url_for('home'))
    history = _load_shift_history()
    return render_template('admin_shift_planner.html', history=history)


@app.route('/admin/shift-planner/upload', methods=['POST'])
def shift_planner_upload():
    if not authorized('edit_shift_planner'):
        return redirect(url_for('home'))

    file = request.files.get('roster_pdf')
    fname = (file.filename or '').lower()
    if not file or not (fname.endswith('.pdf') or fname.endswith('.csv')):
        flash('Please upload a PDF or CSV roster file.', 'danger')
        return redirect(url_for('shift_planner'))

    try:
        raw = file.read()
        employees = _parse_roster_csv(raw) if fname.endswith('.csv') else _parse_roster_pdf(raw)

        location_title = request.form.get('location_title', 'The Draft Room').strip()
        event_name     = request.form.get('event_name', '').strip()
        venue          = request.form.get('venue', '').strip()
        plan_date      = request.form.get('plan_date', '').strip()

        # Auto-assign bartenders: early-shift → Main Bar, late-shift → Lower Bar
        bartenders = employees.get('Bartender', [])
        late  = [e['name'] for e in bartenders if _shift_end_hour(e['shift']) >= 22]
        early = [e['name'] for e in bartenders if _shift_end_hour(e['shift']) < 22]
        if not early or not late:
            mid = len(bartenders) // 2
            early = [e['name'] for e in bartenders[:mid]]
            late  = [e['name'] for e in bartenders[mid:]]

        # Auto-generate break rotations for roles with 2+ late-shift people
        break_sections = []
        for pos, label in [('Bartender', 'Bartender'), ('Cook', 'Cook'), ('Server', 'Server')]:
            late_staff = [e['name'] for e in employees.get(pos, []) if _shift_end_hour(e['shift']) >= 22]
            if len(late_staff) >= 2:
                break_sections.append({
                    'name': f'{label} Break Rotation',
                    'break_after': '7:00 PM',
                    'rows': _generate_break_rotation(late_staff),
                })

        session['shift_plan'] = {
            'location_title': location_title,
            'event_name':     event_name,
            'venue':          venue,
            'date':           plan_date,
            'bar': {
                'main_label':  'Main Bar',
                'lower_label': 'Lower Bar',
                'main':  early,
                'lower': late,
            },
            'break_sections': break_sections,
            'all_employees': {pos: [e['name'] for e in lst] for pos, lst in employees.items()},
        }
        session['shift_plan_file'] = None  # new upload — no existing history file

        return redirect(url_for('shift_planner_edit'))

    except Exception as e:
        logger.error(f'Shift planner parse error: {e}')
        flash(f'Error parsing PDF: {e}', 'danger')
        return redirect(url_for('shift_planner'))


@app.route('/admin/shift-planner/edit', methods=['GET'])
def shift_planner_edit():
    if not authorized('view_shift_planner'):
        return redirect(url_for('home'))

    plan = session.get('shift_plan')
    if not plan:
        flash('No plan loaded. Upload a roster first.', 'warning')
        return redirect(url_for('shift_planner'))

    return render_template('admin_shift_planner_edit.html', plan=plan)


@app.route('/admin/shift-planner/download', methods=['POST'])
def shift_planner_download():
    if not authorized('edit_shift_planner'):
        return redirect(url_for('home'))

    try:
        plan = json.loads(request.form.get('plan_data', '{}'))
        html = render_template('shift_plan_print.html', plan=plan)

        from xhtml2pdf import pisa
        buf = BytesIO()
        pisa.CreatePDF(html.encode('utf-8'), dest=buf, encoding='utf-8')
        buf.seek(0)

        slug = re.sub(r'[^\w]', '_', plan.get('date', 'shift'))
        return send_file(buf, mimetype='application/pdf',
                         as_attachment=True, download_name=f'TDR Shift Plan{slug}.pdf')

    except Exception as e:
        logger.error(f'Shift plan PDF error: {e}')
        flash(f'Error generating PDF: {e}', 'danger')
        return redirect(url_for('shift_planner_edit'))


@app.route('/admin/shift-planner/save', methods=['POST'])
def shift_planner_save():
    if not authorized('edit_shift_planner'):
        return redirect(url_for('home'))
    try:
        plan = json.loads(request.form.get('plan_data', '{}'))
        session['shift_plan'] = plan

        existing_file = session.get('shift_plan_file')
        if existing_file:
            # Overwrite the existing history file
            path = os.path.join(SHIFT_HISTORY_DIR, os.path.basename(existing_file))
            with open(path, 'w', encoding='utf-8') as f:
                json.dump({'saved_at': datetime.utcnow().isoformat(), 'plan': plan}, f, indent=2)
        else:
            # Create a new history file and remember it
            fname = _save_shift_history(plan)
            session['shift_plan_file'] = fname

        flash('Shift plan saved.', 'success')
    except Exception as e:
        logger.error(f'Shift plan save error: {e}')
        flash(f'Error saving plan: {e}', 'danger')
    return redirect(url_for('shift_planner_edit'))


@app.route('/admin/shift-planner/history/<filename>/delete', methods=['POST'])
def shift_planner_delete_history(filename):
    if not authorized('edit_shift_planner'):
        return redirect(url_for('home'))
    safe = os.path.basename(filename)
    path = os.path.join(SHIFT_HISTORY_DIR, safe)
    if os.path.isfile(path):
        os.remove(path)
        flash('Shift plan deleted.', 'success')
    else:
        flash('Plan not found.', 'danger')
    return redirect(url_for('shift_planner'))


@app.route('/admin/shift-planner/history/<filename>')
def shift_planner_load_history(filename):
    if not authorized('view_shift_planner'):
        return redirect(url_for('home'))
    safe = os.path.basename(filename)
    path = os.path.join(SHIFT_HISTORY_DIR, safe)
    if not os.path.isfile(path):
        flash('Shift plan not found.', 'danger')
        return redirect(url_for('shift_planner'))
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    session['shift_plan'] = data.get('plan', {})
    session['shift_plan_file'] = safe  # track which history file is loaded
    return redirect(url_for('shift_planner_edit'))


# =====================================================
# TOAST SALES DASHBOARD — PDF PARSER & ROUTES
# =====================================================

def _parse_toast_sales_pdf(pdf_bytes):
    """Parse a Toast Sales Summary PDF.

    Two-pass approach: (1) regex-based section state machine for structured
    extraction, (2) full-text key-value scan as fallback for any zero fields.
    Uses money[0] (first $ value on a line) so that merged two-column rows
    don't grab the wrong value. Also checks the next line when a label appears
    without a dollar amount (pdfplumber sometimes splits key and value).
    """
    import pdfplumber

    MONEY_RE = re.compile(r'-?\$[\d,]+(?:\.\d+)?')

    def _money(s):
        if not s:
            return 0.0
        s = str(s).strip().replace(',', '').replace('$', '')
        if s in ('—', '-', '', 'None'):
            return 0.0
        try:
            return float(s)
        except ValueError:
            return 0.0

    def all_money(line):
        return [_money(m) for m in MONEY_RE.findall(line)]

    def _norm(s):
        """Normalize whitespace and Unicode space variants (incl. non-breaking space u00a0)."""
        import unicodedata
        s = unicodedata.normalize('NFKD', s)
        s = s.replace(u'\u00a0', ' ').replace(u'\u202f', ' ').replace(u'\u2009', ' ')
        s = s.replace(u'\u200b', '').replace(u'\u00ad', '')
        s = re.sub(r'\s+', ' ', s)
        return s.strip()
    # ── Extract text ──────────────────────────────────────────────────────────
    full_text = ''
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    full_text += t + '\n'
    except Exception as e:
        raise ValueError(f'PDF read failed: {e}')

    # Normalize every line on extraction to avoid Unicode space issues
    lines = [_norm(l) for l in full_text.split('\n')]

    # ── Debug log: write first 120 non-blank normalized lines to app log ──────
    debug_preview = [l for l in lines if l][:120]
    app.logger.info('=== PDF PARSER DEBUG START ===')
    for i, dl in enumerate(debug_preview):
        app.logger.info(f'  [{i:03d}] {dl}')
    app.logger.info('=== PDF PARSER DEBUG END ===')

    # ── Section state machine – regex patterns handle whitespace variations ──
    SECTION_PATTERNS = [
        (re.compile(r'^revenue\s+summary$',              re.I), 'Revenue Summary'),
        (re.compile(r'^net\s+sales\s+summary$',          re.I), 'Net Sales Summary'),
        (re.compile(r'^tip\s+summary$',                  re.I), 'Tip Summary'),
        (re.compile(r'^cash\s+summary$',                 re.I), 'Cash Summary'),
        (re.compile(r'^cash\s+activity$',                re.I), 'Cash Activity'),
        (re.compile(r'^payments?\s+summary$',            re.I), 'Payments Summary'),
        (re.compile(r'^unpaid\s+orders?\s+summary$',     re.I), 'Unpaid Orders Summary'),
        (re.compile(r'^sales\s+category\s+summary$',     re.I), 'Sales Category Summary'),
        (re.compile(r'^revenue\s+center\s+summary$',     re.I), 'Revenue Center Summary'),
        (re.compile(r'^dining\s+option\s+summary$',      re.I), 'Dining Option Summary'),
        (re.compile(r'^service\s+mode\s+summary$',       re.I), 'Service Mode Summary'),
        (re.compile(r'^service\s+charge\s+summary$',     re.I), 'Service Charge Summary'),
        (re.compile(r'^discount\s+summary$',             re.I), 'Discount Summary'),
        (re.compile(r'^void\s+summary$',                 re.I), 'Void Summary'),
        (re.compile(r'^tax\s+summary$',                  re.I), 'Tax Summary'),
        (re.compile(r'^service\s*/\s*daypart\s+summary$',re.I), 'Daypart Summary'),
    ]

    sections = {name: [] for _, name in SECTION_PATTERNS}
    current_section = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        matched = False
        for pat, name in SECTION_PATTERNS:
            if pat.match(stripped):
                current_section = name
                matched = True
                break
        if not matched and current_section:
            sections[current_section].append(stripped)

    # ── Result skeleton ────────────────────────────────────────────────────────
    result = {
        'week_start': None, 'week_end': None, 'location': '',
        'net_sales': 0.0, 'gratuity': 0.0, 'tax_amount': 0.0,
        'tips': 0.0, 'paid_in_total': 0.0, 'total_amount': 0.0,
        'gross_sales': 0.0, 'sales_discounts': 0.0, 'sales_refunds': 0.0,
        'tips_collected': 0.0, 'tips_refunded': 0.0,
        'tips_withheld': 0.0, 'tips_after_withholding': 0.0,
        'expected_closeout_cash': 0.0, 'actual_closeout_cash': 0.0,
        'cash_overage': 0.0, 'total_cash_payments': 0.0,
        'quick_service_net': 0.0, 'table_service_net': 0.0,
        'total_guests': 0, 'avg_per_guest': 0.0,
        'total_orders': 0, 'avg_per_order': 0.0,
        'void_amount': 0.0, 'void_order_count': 0, 'void_item_count': 0,
        'total_discounts_amount': 0.0, 'total_discount_count': 0,
        'total_service_charges': 0.0, 'service_charge_count': 0,
        'taxable_amount': 0.0,
        'payments': [], 'categories': [],
        'revenue_centers': [], 'dining_options': [], 'discounts': [],
    }

    # ── Section KV helper – money[0] + adjacent-line fallback ────────────────
    def kv(sec_name, label):
        """Return first $ value in section for label; checks the next line too."""
        sec = sections.get(sec_name, [])
        ll = label.lower()
        for i, line in enumerate(sec):
            if ll in line.lower():
                money = all_money(line)
                if money:
                    return money[0]
                if i + 1 < len(sec):
                    money2 = all_money(sec[i + 1])
                    if money2:
                        return money2[0]
        return 0.0

    # ── Full-text fallback – used when a section is empty ────────────────────
    def kv_ft(label, avoid_3plus=False):
        """Scan full text for label + $ value.
        avoid_3plus skips lines with 3+ $ values (Service Mode rows have 3:
        Quick/Table/Total). Lines with 1-2 values are fine — 2-value lines
        are typically merged two-column rows where money[0] is still correct.
        """
        ll = label.lower()
        best_val = None
        for i, raw in enumerate(lines):
            stripped = raw.strip()
            if ll not in stripped.lower():
                continue
            money = all_money(stripped)
            if money:
                if avoid_3plus and len(money) >= 3:
                    continue
                if best_val is None:
                    best_val = money[0]
            elif i + 1 < len(lines) and best_val is None:
                money2 = all_money(lines[i + 1].strip())
                if money2:
                    best_val = money2[0]
        return best_val or 0.0

    # ── Header: date range & location ─────────────────────────────────────────
    for line in lines[:35]:
        stripped = line.strip()
        low = stripped.lower()
        if 'location' in low:
            loc_m = re.sub(r'(?i)location\(s\)\s*:?\s*', '', stripped).strip()
            if loc_m:
                result['location'] = loc_m
        date_m = re.search(
            r'(\w+\s+\d+,?\s*\d{4})\s*[-–]\s*(\w+\s+\d+,?\s*\d{4})', stripped
        )
        if date_m:
            try:
                def _d(s):
                    return datetime.strptime(
                        re.sub(r'\s+', ' ', s.replace(',', '').strip()), '%B %d %Y'
                    ).date()
                result['week_start'] = _d(date_m.group(1))
                result['week_end']   = _d(date_m.group(2))
            except Exception:
                pass

    # ── Revenue Summary ────────────────────────────────────────────────────────
    result['net_sales']    = kv('Revenue Summary', 'net sales')
    result['gratuity']     = kv('Revenue Summary', 'gratuity')
    result['tax_amount']   = kv('Revenue Summary', 'tax amount')
    result['tips']         = kv('Revenue Summary', 'tips')
    result['paid_in_total']= kv('Revenue Summary', 'paid in total')
    result['total_amount'] = kv('Revenue Summary', 'total amount')

    # Full-text fallbacks (require single $ so we don't grab Service Mode rows)
    if not result['net_sales']:
        result['net_sales']  = kv_ft('net sales', avoid_3plus=True)
    if not result['gratuity']:
        result['gratuity']   = kv_ft('gratuity',  avoid_3plus=True)
    if not result['tax_amount']:
        result['tax_amount'] = kv_ft('tax amount', avoid_3plus=True)
    if not result['tips']:
        result['tips']       = kv_ft('tips',       avoid_3plus=True)
    if not result['total_amount']:
        result['total_amount']= kv_ft('total amount', avoid_3plus=True)

    # ── Net Sales Summary ──────────────────────────────────────────────────────
    result['gross_sales']     = kv('Net Sales Summary', 'gross sales')
    result['sales_discounts'] = kv('Net Sales Summary', 'discounts')
    result['sales_refunds']   = kv('Net Sales Summary', 'refunds')
    if not result['gross_sales']:
        result['gross_sales'] = kv_ft('gross sales', avoid_3plus=True)

    # ── Tip Summary ───────────────────────────────────────────────────────────
    result['tips_collected']        = kv('Tip Summary', 'collected')
    result['tips_refunded']         = kv('Tip Summary', 'refunded')
    result['tips_after_withholding']= kv('Tip Summary', 'after withholding')
    result['tips_withheld']         = kv('Tip Summary', 'withheld')
    if not result['tips_collected']:
        result['tips_collected']         = kv_ft('tips collected',    avoid_3plus=True)
    if not result['tips_after_withholding']:
        result['tips_after_withholding'] = kv_ft('after withholding', avoid_3plus=True)

    # ── Cash Summary ──────────────────────────────────────────────────────────
    result['expected_closeout_cash'] = kv('Cash Summary', 'expected closeout')
    result['actual_closeout_cash']   = kv('Cash Summary', 'actual closeout')
    result['cash_overage']           = kv('Cash Summary', 'overage') or kv('Cash Summary', 'shortage')
    if not result['expected_closeout_cash']:
        result['expected_closeout_cash'] = kv_ft('expected closeout', avoid_3plus=True)
    if not result['actual_closeout_cash']:
        result['actual_closeout_cash']   = kv_ft('actual closeout',   avoid_3plus=True)

    # ── Cash Activity ─────────────────────────────────────────────────────────
    result['total_cash_payments'] = kv('Cash Activity', 'total cash payments')

    # ── Payments Summary ──────────────────────────────────────────────────────
    PAYMENT_TYPES = [
        'Credit/debit', 'Amex', 'Discover', 'Mastercard', 'Visa',
        'Gift Card', 'House Account', 'Cash', 'Other',
    ]
    for line in sections['Payments Summary']:
        money = all_money(line)
        if len(money) < 2:
            continue
        for ptype in PAYMENT_TYPES:
            if line.lower().startswith(ptype.lower()):
                result['payments'].append({
                    'type':    ptype,
                    'amount':  money[0],
                    'tips':    money[1] if len(money) > 1 else 0.0,
                    'grat':    money[2] if len(money) > 2 else 0.0,
                    'refunds': money[3] if len(money) > 3 else 0.0,
                    'total':   money[4] if len(money) > 4 else money[0],
                })
                break

    # ── Sales Category Summary ────────────────────────────────────────────────
    TABLE_ROW = re.compile(r'^(.+?)\s+(\d+)\s+(-?\$[\d,]+\.\d+)\s+(-?\$[\d,]+\.\d+)')
    for line in sections['Sales Category Summary']:
        m = TABLE_ROW.match(line)
        if m and 'total' not in m.group(1).lower():
            result['categories'].append({
                'category':    m.group(1).strip(),
                'items':       int(m.group(2)),
                'net_sales':   _money(m.group(3)),
                'gross_sales': _money(m.group(4)),
            })

    # ── Revenue Center Summary ────────────────────────────────────────────────
    for line in sections['Revenue Center Summary']:
        m = TABLE_ROW.match(line)
        if m and 'total' not in m.group(1).lower():
            result['revenue_centers'].append({
                'center':      m.group(1).strip(),
                'items':       int(m.group(2)),
                'net_sales':   _money(m.group(3)),
                'gross_sales': _money(m.group(4)),
            })

    # ── Dining Option Summary ─────────────────────────────────────────────────
    for line in sections['Dining Option Summary']:
        m = TABLE_ROW.match(line)
        if m and 'total' not in m.group(1).lower():
            result['dining_options'].append({
                'option':      m.group(1).strip(),
                'orders':      int(m.group(2)),
                'net_sales':   _money(m.group(3)),
                'gross_sales': _money(m.group(4)),
            })

    # ── Service Mode Summary ──────────────────────────────────────────────────
    for line in sections['Service Mode Summary']:
        low = line.lower()
        money = all_money(line)
        if 'net sales' in low and len(money) >= 2:
            result['quick_service_net'] = money[0]
            result['table_service_net'] = money[1]
        elif 'total guests' in low:
            nums = re.findall(r'\d+', line)
            if nums:
                result['total_guests'] = int(nums[-1])
        elif 'avg/guest' in low and money:
            result['avg_per_guest'] = money[-1]
        elif 'total orders' in low:
            nums = re.findall(r'\d+', line)
            if nums:
                result['total_orders'] = int(nums[-1])
        elif 'avg/order' in low and money:
            result['avg_per_order'] = money[-1]

    # ── Service Charge Summary ────────────────────────────────────────────────
    for line in sections['Service Charge Summary']:
        if 'total service charges' in line.lower():
            money = all_money(line)
            nums  = re.findall(r'\d+', line)
            if nums:
                result['service_charge_count']  = int(nums[0])
            if money:
                result['total_service_charges'] = money[0]

    # ── Discount Summary ──────────────────────────────────────────────────────
    DISC_ROW = re.compile(r'^(.+?)\s+(\d+)\s+(-?\$[\d,]+\.\d+)')
    for line in sections['Discount Summary']:
        m = DISC_ROW.match(line)
        if not m:
            continue
        name = m.group(1).strip()
        if 'total discounts' in name.lower():
            result['total_discount_count']   = int(m.group(2))
            result['total_discounts_amount'] = _money(m.group(3))
        else:
            result['discounts'].append({
                'name':   name,
                'count':  int(m.group(2)),
                'amount': _money(m.group(3)),
            })

    # ── Void Summary ──────────────────────────────────────────────────────────
    for i, line in enumerate(sections['Void Summary']):
        low = line.lower()
        if 'void amount' in low and '%' not in line:
            money = all_money(line)
            if money:
                result['void_amount'] = money[0]  # first $ = void amount
            elif i + 1 < len(sections['Void Summary']):
                money2 = all_money(sections['Void Summary'][i + 1])
                if money2:
                    result['void_amount'] = money2[0]
        elif 'void order count' in low:
            nums = re.findall(r'\d+', line)
            if nums:
                result['void_order_count'] = int(nums[0])
        elif 'void item count' in low:
            nums = re.findall(r'\d+', line)
            if nums:
                result['void_item_count'] = int(nums[0])

    # ── Tax Summary ───────────────────────────────────────────────────────────
    for line in sections['Tax Summary']:
        money = all_money(line)
        if money and not result['taxable_amount']:
            result['taxable_amount'] = money[0]

    return result


def _parse_toast_csv_zip(zip_bytes, original_filename=''):
    """Parse a Toast SalesSummary ZIP export.

    Toast CSV structure (confirmed from real export):
      - Summary files (Revenue summary, Cash summary, etc.): row 0 = column headers,
        row 1 = single data row.  Read with dict(zip(headers, values)).
      - Table files (Payments, Category, etc.): row 0 = headers, N data rows below.
      - Date range encoded in ZIP filename: SalesSummary_YYYY-MM-DD_YYYY-MM-DD.zip

    Handles common Toast CSV export filenames:
      AllPaymentsByType, SalesByCategory, SalesByCenter/Revenue, SalesByDiningOption,
      CheckDetails (skipped), SalesSummary / any key-value summary.
    """
    import zipfile
    import csv as _csv
    import io as _io

    result = {
        'week_start': None, 'week_end': None, 'location': '',
        'net_sales': 0.0, 'gratuity': 0.0, 'tax_amount': 0.0,
        'tips': 0.0, 'paid_in_total': 0.0, 'total_amount': 0.0,
        'gross_sales': 0.0, 'sales_discounts': 0.0, 'sales_refunds': 0.0,
        'tips_collected': 0.0, 'tips_refunded': 0.0,
        'tips_withheld': 0.0, 'tips_after_withholding': 0.0,
        'expected_closeout_cash': 0.0, 'actual_closeout_cash': 0.0,
        'cash_overage': 0.0, 'total_cash_payments': 0.0,
        'quick_service_net': 0.0, 'table_service_net': 0.0,
        'total_guests': 0, 'avg_per_guest': 0.0,
        'total_orders': 0, 'avg_per_order': 0.0,
        'void_amount': 0.0, 'void_order_count': 0, 'void_item_count': 0,
        'total_discounts_amount': 0.0, 'total_discount_count': 0,
        'total_service_charges': 0.0, 'service_charge_count': 0,
        'taxable_amount': 0.0,
        'payments': [], 'categories': [],
        'revenue_centers': [], 'dining_options': [], 'discounts': [],
    }

    def cm(s):
        try:
            return float(str(s).strip().replace(',', '').replace('$', ''))
        except Exception:
            return 0.0

    def ci(s):
        try:
            return int(float(str(s).strip().replace(',', '')))
        except Exception:
            return 0

    def read_csv(zf, fname):
        """Read a CSV from the ZIP, return (lowercase_headers, list_of_rows)."""
        raw = zf.read(fname).decode('utf-8-sig', errors='replace')
        rows = list(_csv.reader(_io.StringIO(raw)))
        rows = [r for r in rows if any(c.strip() for c in r)]
        if not rows:
            return [], []
        headers = [h.strip().lower() for h in rows[0]]
        return headers, rows[1:]

    def row_dict(headers, row):
        return dict(zip(headers, [c.strip() for c in row]))

    # ── Extract dates from the ZIP filename ───────────────────────────────────
    # Format: SalesSummary_YYYY-MM-DD_YYYY-MM-DD.zip
    date_m = re.search(r'(\d{4}-\d{2}-\d{2})[_\-](\d{4}-\d{2}-\d{2})', original_filename)
    if date_m:
        try:
            result['week_start'] = datetime.strptime(date_m.group(1), '%Y-%m-%d').date()
            result['week_end']   = datetime.strptime(date_m.group(2), '%Y-%m-%d').date()
        except Exception:
            pass

    try:
        with zipfile.ZipFile(_io.BytesIO(zip_bytes)) as zf:
            # Build a lookup: normalised basename → original fname
            file_map = {}
            for fname in zf.namelist():
                if fname.lower().endswith('.csv'):
                    bn = fname.split('/')[-1].lower()
                    bn_norm = re.sub(r'[\s_\-]', '', bn).replace('.csv', '')
                    file_map[bn_norm] = fname

            def get(bn_norm):
                """Return (headers, data_rows) for a normalised basename, or ([], [])."""
                fname = file_map.get(bn_norm)
                if not fname:
                    # fuzzy: find first key that contains bn_norm
                    for k, v in file_map.items():
                        if bn_norm in k or k in bn_norm:
                            fname = v
                            break
                if not fname:
                    return [], []
                return read_csv(zf, fname)

            # ── Revenue summary ────────────────────────────────────────────────
            headers, rows = get('revenuesummary')
            if rows:
                d = row_dict(headers, rows[0])
                result['net_sales']     = cm(d.get('net sales', 0))
                result['gratuity']      = cm(d.get('gratuity', 0))
                result['tax_amount']    = cm(d.get('tax amount', 0))
                result['tips']          = cm(d.get('tips', 0))
                result['paid_in_total'] = cm(d.get('paid in total', 0))
                result['total_amount']  = cm(d.get('total', 0))

            # ── Cash summary ───────────────────────────────────────────────────
            headers, rows = get('cashsummary')
            if rows:
                d = row_dict(headers, rows[0])
                result['expected_closeout_cash'] = cm(d.get('expected closeout cash', 0))
                result['actual_closeout_cash']   = cm(d.get('actual closeout cash', 0))
                result['cash_overage']           = cm(d.get('cash overage/shortage', 0))

            # ── Cash activity ──────────────────────────────────────────────────
            headers, rows = get('cashactivity')
            if rows:
                d = row_dict(headers, rows[0])
                result['total_cash_payments'] = cm(d.get('total cash payments', 0))

            # ── Net sales summary ──────────────────────────────────────────────
            headers, rows = get('netsalessummary')
            if rows:
                d = row_dict(headers, rows[0])
                result['gross_sales']     = cm(d.get('gross sales', 0))
                result['sales_discounts'] = cm(d.get('sales discounts', 0))
                result['sales_refunds']   = cm(d.get('sales refunds', 0))

            # ── Tip summary ────────────────────────────────────────────────────
            headers, rows = get('tipsummary')
            if rows:
                d = row_dict(headers, rows[0])
                result['tips_collected']         = cm(d.get('tips collected', 0))
                result['tips_refunded']          = cm(d.get('tips refunded', 0))
                result['tips_withheld']          = cm(d.get('tips withheld', 0))
                result['tips_after_withholding'] = cm(d.get('tips after withholding', 0))

            # ── Void summary ───────────────────────────────────────────────────
            headers, rows = get('voidsummary')
            if rows:
                d = row_dict(headers, rows[0])
                result['void_amount']      = cm(d.get('void amount', 0))
                result['void_order_count'] = ci(d.get('void order count', 0))
                result['void_item_count']  = ci(d.get('void item count', 0))

            # ── Service charge summary ─────────────────────────────────────────
            headers, rows = get('servicechargesummary')
            for row in rows:
                d = row_dict(headers, row)
                name = d.get('service charge', row[0] if row else '')
                if 'total' in name.lower():
                    result['service_charge_count']  = ci(d.get('count', 0))
                    result['total_service_charges'] = cm(d.get('amount', 0))

            # ── Tax summary ────────────────────────────────────────────────────
            headers, rows = get('taxsummary')
            for row in rows:
                d = row_dict(headers, row)
                rate = d.get('tax rate', row[0] if row else '').lower()
                if 'state' in rate or 'local' in rate:
                    result['taxable_amount'] = cm(d.get('taxable amount', 0))
                    break

            # ── Payments summary ───────────────────────────────────────────────
            # Skip sub-type rows (AMEX, VISA, etc. under Credit/debit)
            headers, rows = get('paymentssummary')
            sub_idx = headers.index('payment sub type') if 'payment sub type' in headers else -1
            for row in rows:
                d = row_dict(headers, row)
                name = d.get('payment type', row[0] if row else '').strip()
                if not name or name.lower() == 'total':
                    continue
                if sub_idx >= 0 and sub_idx < len(row) and row[sub_idx].strip():
                    continue  # skip AMEX/VISA/etc sub-type rows
                result['payments'].append({
                    'type':    name,
                    'amount':  cm(d.get('amount', 0)),
                    'tips':    cm(d.get('tips', 0)),
                    'grat':    cm(d.get('grat', 0)),
                    'refunds': cm(d.get('refunds', 0)),
                    'total':   cm(d.get('total', 0)),
                })

            # ── Sales category summary ─────────────────────────────────────────
            headers, rows = get('salescategorysummary')
            for row in rows:
                d = row_dict(headers, row)
                name = d.get('sales category', row[0] if row else '').strip()
                if not name or name.lower() == 'total':
                    continue
                result['categories'].append({
                    'category':    name,
                    'items':       ci(d.get('items', 0)),
                    'net_sales':   cm(d.get('net sales', 0)),
                    'gross_sales': cm(d.get('gross sales', 0)),
                })

            # ── Revenue center summary ─────────────────────────────────────────
            headers, rows = get('revenuecentersummary')
            for row in rows:
                d = row_dict(headers, row)
                name = d.get('revenue center', row[0] if row else '').strip()
                if not name or name.lower() == 'total':
                    continue
                result['revenue_centers'].append({
                    'center':      name,
                    'items':       ci(d.get('items', 0)),
                    'net_sales':   cm(d.get('net sales', 0)),
                    'gross_sales': cm(d.get('gross sales', 0)),
                })

            # ── Dining options summary ─────────────────────────────────────────
            headers, rows = get('diningoptionssummary')
            for row in rows:
                d = row_dict(headers, row)
                name = d.get('dining option', row[0] if row else '').strip()
                if not name or name.lower() == 'total':
                    continue
                result['dining_options'].append({
                    'option':      name,
                    'orders':      ci(d.get('orders', 0)),
                    'net_sales':   cm(d.get('net sales', 0)),
                    'gross_sales': cm(d.get('gross sales', 0)),
                })

            # ── Service mode summary ───────────────────────────────────────────
            headers, rows = get('servicemodesummary')
            for row in rows:
                d = row_dict(headers, row)
                mode = d.get('service mode', row[0] if row else '').strip().lower()
                if mode == 'quick service':
                    result['quick_service_net'] = cm(d.get('net sales', 0))
                elif mode == 'table service':
                    result['table_service_net'] = cm(d.get('net sales', 0))
                elif mode == 'total':
                    result['total_guests']  = ci(d.get('total guests', 0))
                    result['total_orders']  = ci(d.get('total orders', 0))
                    result['avg_per_guest'] = cm(d.get('avg/guest', 0))
                    result['avg_per_order'] = cm(d.get('avg/order', 0))

            # ── Discounts (merge Menu Item Discounts + Check Discounts) ─────────
            for bn_key in ['menuitemdiscounts', 'checkdiscounts']:
                headers, rows = get(bn_key)
                for row in rows:
                    d = row_dict(headers, row)
                    name = d.get('discount', row[0] if row else '').strip()
                    if not name or name.lower() == 'total':
                        continue
                    result['discounts'].append({
                        'name':   name,
                        'count':  ci(d.get('count', 0)),
                        'amount': cm(d.get('amount', 0)),
                    })
            # Compute totals from accumulated discounts
            if result['discounts']:
                result['total_discount_count']   = sum(d['count']  for d in result['discounts'])
                result['total_discounts_amount'] = sum(d['amount'] for d in result['discounts'])

    except zipfile.BadZipFile:
        raise ValueError('Uploaded file is not a valid ZIP archive.')

    return result


@app.route('/admin/sales-dashboard')
def sales_dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if not authorized('view_sales_dashboard'):
        flash('Access denied.', 'danger')
        return redirect(url_for('home'))

    reports = WeeklySalesReport.query.order_by(WeeklySalesReport.week_start.desc()).all()

    # Which week to show — default to most recent
    selected_id = request.args.get('id', type=int)
    report = None
    if selected_id:
        report = WeeklySalesReport.query.get(selected_id)
    if not report and reports:
        report = reports[0]

    # Parse JSON breakdowns
    payments = []
    categories = []
    revenue_centers = []
    dining_options = []
    discounts = []
    if report:
        try:
            payments        = json.loads(report.payments_json or '[]')
            categories      = json.loads(report.categories_json or '[]')
            revenue_centers = json.loads(report.revenue_centers_json or '[]')
            dining_options  = json.loads(report.dining_options_json or '[]')
            discounts       = json.loads(report.discounts_json or '[]')
        except Exception:
            pass

    # Labor data for selected period
    labor = None
    labor_employees = []
    labor_jobs = []
    labor_pct = None
    rev_per_hour = None
    cost_per_hour = None
    filtered_hours = 0.0
    filtered_cost = 0.0
    filtered_ot_cost = 0.0
    if report:
        labor = LaborReport.query.filter_by(week_start=report.week_start).first()
        if labor:
            try:
                all_emps = json.loads(labor.employees_json or '[]')
                labor_employees = [e for e in all_emps if not e.get('excluded')]
                labor_jobs = [j for j in json.loads(labor.jobs_json or '[]')
                              if not _is_labor_excluded('', j.get('job', ''))]
            except Exception:
                pass
            filtered_hours   = sum(e.get('hours', 0)       for e in labor_employees) or labor.total_hours
            filtered_cost    = sum(e.get('total_pay', 0)   for e in labor_employees) or labor.total_cost
            filtered_ot_cost = sum(e.get('ot_pay', 0)      for e in labor_employees) or labor.overtime_cost
            if report.net_sales:
                labor_pct = round(filtered_cost / report.net_sales * 100, 1)
            if filtered_hours:
                cost_per_hour = round(filtered_cost / filtered_hours, 2)
                if report.net_sales:
                    rev_per_hour = round(report.net_sales / filtered_hours, 2)

    # Trend data for chart (all weeks, ascending)
    trend_reports  = WeeklySalesReport.query.order_by(WeeklySalesReport.week_start.asc()).all()
    labor_by_start = {lr.week_start: lr for lr in LaborReport.query.all()}

    def _tlabor_cost(r):
        lr = labor_by_start.get(r.week_start)
        if not lr:
            return None
        try:
            emps = json.loads(lr.employees_json or '[]')
            active = [e for e in emps if not e.get('excluded')]
            c = sum(e.get('total_pay', 0) for e in active)
            return c if c else lr.total_cost
        except Exception:
            return lr.total_cost

    trend_labels   = [r.week_start.strftime('%b %d') for r in trend_reports]
    trend_net      = [r.net_sales    for r in trend_reports]
    trend_total    = [r.total_amount for r in trend_reports]
    trend_gratuity = [r.gratuity     for r in trend_reports]
    trend_tips     = [r.tips         for r in trend_reports]
    trend_labor    = [_tlabor_cost(r) for r in trend_reports]  # None where no labor uploaded

    return render_template(
        'admin_sales_dashboard.html',
        reports=reports,
        report=report,
        payments=payments,
        categories=categories,
        revenue_centers=revenue_centers,
        dining_options=dining_options,
        discounts=discounts,
        labor=labor,
        labor_employees=labor_employees,
        labor_jobs=labor_jobs,
        labor_pct=labor_pct,
        rev_per_hour=rev_per_hour,
        cost_per_hour=cost_per_hour,
        filtered_hours=filtered_hours,
        filtered_cost=filtered_cost,
        filtered_ot_cost=filtered_ot_cost,
        can_upload_labor=authorized('upload_labor_report'),
        trend_labels=json.dumps(trend_labels),
        trend_net=json.dumps(trend_net),
        trend_total=json.dumps(trend_total),
        trend_gratuity=json.dumps(trend_gratuity),
        trend_tips=json.dumps(trend_tips),
        trend_labor=json.dumps(trend_labor),
        can_upload=authorized('upload_sales_report'),
        can_delete=authorized('delete_sales_report'),
    )


@app.route('/admin/sales-upload', methods=['POST'])
def sales_upload():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if not authorized('upload_sales_report'):
        flash('Access denied.', 'danger')
        return redirect(url_for('sales_dashboard'))

    f = request.files.get('sales_pdf')
    if not f or not f.filename:
        flash('No file selected.', 'danger')
        return redirect(url_for('sales_dashboard'))

    filename = secure_filename(f.filename)
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    if ext not in ('pdf', 'zip'):
        flash('Only PDF or ZIP files are accepted.', 'danger')
        return redirect(url_for('sales_dashboard'))

    file_bytes = f.read()
    try:
        if ext == 'zip':
            data = _parse_toast_csv_zip(file_bytes, original_filename=filename)
        else:
            data = _parse_toast_sales_pdf(file_bytes)
    except Exception as e:
        flash(f'Error parsing file: {e}', 'danger')
        return redirect(url_for('sales_dashboard'))

    # Allow manual date overrides from the form
    override_start = request.form.get('override_start', '').strip()
    override_end   = request.form.get('override_end', '').strip()
    period_label   = request.form.get('period_label', '').strip()
    period_type    = request.form.get('period_type', 'weekly').strip()

    if override_start:
        try:
            data['week_start'] = datetime.strptime(override_start, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid start date format — use YYYY-MM-DD.', 'danger')
            return redirect(url_for('sales_dashboard'))

    if override_end:
        try:
            data['week_end'] = datetime.strptime(override_end, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid end date format — use YYYY-MM-DD.', 'danger')
            return redirect(url_for('sales_dashboard'))

    if not data.get('week_start') or not data.get('week_end'):
        flash('Could not determine date range. Please set the Start and End dates manually.', 'danger')
        return redirect(url_for('sales_dashboard'))

    if not period_label:
        period_label = f'{data["week_start"]} – {data["week_end"]}'

    # Check for duplicate — match on exact start date
    existing = WeeklySalesReport.query.filter_by(week_start=data['week_start']).first()
    if existing:
        rpt = existing
        flash(f'Existing data for period starting {data["week_start"]} has been updated.', 'warning')
    else:
        rpt = WeeklySalesReport()
        db.session.add(rpt)

    rpt.week_start        = data['week_start']
    rpt.week_end          = data['week_end']
    rpt.period_label      = period_label
    rpt.period_type       = period_type
    rpt.location          = data.get('location') or request.form.get('location_override', '').strip()
    rpt.original_filename = filename
    rpt.uploaded_at       = datetime.utcnow()

    for field in [
        'net_sales', 'gratuity', 'tax_amount', 'tips', 'paid_in_total', 'total_amount',
        'gross_sales', 'sales_discounts', 'sales_refunds',
        'tips_collected', 'tips_refunded', 'tips_withheld', 'tips_after_withholding',
        'expected_closeout_cash', 'actual_closeout_cash', 'cash_overage', 'total_cash_payments',
        'quick_service_net', 'table_service_net', 'total_guests', 'avg_per_guest',
        'total_orders', 'avg_per_order',
        'void_amount', 'void_order_count', 'void_item_count',
        'total_discounts_amount', 'total_discount_count',
        'total_service_charges', 'service_charge_count',
        'taxable_amount',
    ]:
        setattr(rpt, field, data.get(field, 0))

    rpt.payments_json        = json.dumps(data.get('payments', []))
    rpt.categories_json      = json.dumps(data.get('categories', []))
    rpt.revenue_centers_json = json.dumps(data.get('revenue_centers', []))
    rpt.dining_options_json  = json.dumps(data.get('dining_options', []))
    rpt.discounts_json       = json.dumps(data.get('discounts', []))

    db.session.commit()
    log_audit('report', f'Uploaded sales report for week {data["week_start"]}')

    if not existing:
        flash(f'Sales report for week of {data["week_start"]} uploaded successfully!', 'success')

    return redirect(url_for('sales_dashboard', id=rpt.id))


@app.route('/admin/sales-delete/<int:report_id>', methods=['POST'])
def sales_delete(report_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if not authorized('delete_sales_report'):
        flash('Access denied.', 'danger')
        return redirect(url_for('sales_dashboard'))

    rpt = WeeklySalesReport.query.get_or_404(report_id)
    label = str(rpt.week_start)
    db.session.delete(rpt)
    db.session.commit()
    log_audit('report', f'Deleted sales report for week {label}')
    flash(f'Sales report for week of {label} deleted.', 'success')
    return redirect(url_for('sales_dashboard'))


@app.route('/admin/sales-debug-parse', methods=['GET', 'POST'])
def sales_debug_parse():
    """Admin-only: upload a PDF and see raw pdfplumber text + detected sections."""
    if 'user_id' not in session or session.get('role') != 'admin':
        return 'Unauthorized', 403
    if request.method == 'GET':
        return '''<!doctype html><html><body style="font-family:monospace;padding:2rem;">
        <h2>PDF Debug Parser</h2>
        <form method="post" enctype="multipart/form-data">
          <input type="file" name="pdf" accept=".pdf" required>
          <button type="submit">Parse &amp; Show</button>
        </form></body></html>'''

    import pdfplumber
    f = request.files.get('pdf')
    if not f:
        return 'No file', 400
    pdf_bytes = f.read()
    MONEY_RE = re.compile(r'-?\$[\d,]+(?:\.\d+)?')
    SECTION_PATTERNS = [
        (re.compile(r'^revenue\s+summary$',              re.I), 'Revenue Summary'),
        (re.compile(r'^net\s+sales\s+summary$',          re.I), 'Net Sales Summary'),
        (re.compile(r'^tip\s+summary$',                  re.I), 'Tip Summary'),
        (re.compile(r'^cash\s+summary$',                 re.I), 'Cash Summary'),
        (re.compile(r'^cash\s+activity$',                re.I), 'Cash Activity'),
        (re.compile(r'^payments?\s+summary$',            re.I), 'Payments Summary'),
        (re.compile(r'^unpaid\s+orders?\s+summary$',     re.I), 'Unpaid Orders Summary'),
        (re.compile(r'^sales\s+category\s+summary$',     re.I), 'Sales Category Summary'),
        (re.compile(r'^revenue\s+center\s+summary$',     re.I), 'Revenue Center Summary'),
        (re.compile(r'^dining\s+option\s+summary$',      re.I), 'Dining Option Summary'),
        (re.compile(r'^service\s+mode\s+summary$',       re.I), 'Service Mode Summary'),
        (re.compile(r'^service\s+charge\s+summary$',     re.I), 'Service Charge Summary'),
        (re.compile(r'^discount\s+summary$',             re.I), 'Discount Summary'),
        (re.compile(r'^void\s+summary$',                 re.I), 'Void Summary'),
        (re.compile(r'^tax\s+summary$',                  re.I), 'Tax Summary'),
        (re.compile(r'^service\s*/\s*daypart\s+summary$',re.I), 'Daypart Summary'),
    ]
    sections = {name: [] for _, name in SECTION_PATTERNS}
    current_section = None
    raw_text = ''
    annotated = []
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                t = page.extract_text() or ''
                raw_text += t + '\n'
    except Exception as e:
        return f'<pre>Error: {e}</pre>'

    lines = [l.rstrip() for l in raw_text.split('\n')]
    for line in lines:
        stripped = line.strip()
        if not stripped:
            annotated.append(f'[blank]')
            continue
        matched = False
        for pat, name in SECTION_PATTERNS:
            if pat.match(stripped):
                current_section = name
                annotated.append(f'[SECTION: {name}] {stripped}')
                matched = True
                break
        if not matched:
            money = MONEY_RE.findall(stripped)
            tag = f'[{current_section or "NO-SECTION"}]'
            if money:
                sections[current_section or ''].append(stripped) if current_section else None
                annotated.append(f'{tag} {stripped}  ← money: {money}')
            else:
                annotated.append(f'{tag} {stripped}')

    import html as _html
    parsed = _parse_toast_sales_pdf(pdf_bytes)
    parsed_html = '<br>'.join(
        f'<b>{k}</b>: {v}' for k, v in parsed.items()
        if k not in ('payments', 'categories', 'revenue_centers', 'dining_options', 'discounts')
    )
    section_html = ''
    for sname, slines in sections.items():
        if slines:
            section_html += f'<h4 style="margin-top:1rem">{sname}</h4><pre style="background:#111;color:#0f0;padding:.5rem">'
            section_html += _html.escape('\n'.join(slines))
            section_html += '</pre>'

    body = f'''<!doctype html><html><body style="font-family:monospace;background:#1a1a1a;color:#eee;padding:2rem">
<h2>Parsed Values</h2><p>{parsed_html}</p>
<h2>Detected Sections</h2>{section_html}
<h2>Annotated Lines</h2>
<pre style="background:#111;color:#aaa;padding:1rem;overflow:auto;max-height:80vh">{_html.escape(chr(10).join(annotated))}</pre>
<h2>Raw Text</h2>
<pre style="background:#0a0a0a;color:#888;padding:1rem;overflow:auto;max-height:60vh">{_html.escape(raw_text)}</pre>
</body></html>'''
    return body


@app.route('/admin/sales-debug-zip', methods=['GET', 'POST'])
def sales_debug_zip():
    """Admin-only: upload a ZIP and see every CSV filename, header row, and first 5 rows."""
    if 'user_id' not in session or session.get('role') != 'admin':
        return 'Unauthorized', 403
    if request.method == 'GET':
        return '''<!doctype html><html><body style="font-family:monospace;padding:2rem;background:#1a1a1a;color:#eee;">
        <h2>ZIP Debug Inspector</h2>
        <form method="post" enctype="multipart/form-data">
          <input type="file" name="zip" accept=".zip" required style="color:#eee">
          <button type="submit" style="margin-left:1rem">Inspect ZIP</button>
        </form></body></html>'''
    import zipfile, csv as _csv
    import io as _io
    f = request.files.get('zip')
    if not f:
        return 'No file', 400
    zip_bytes = f.read()
    import html as _html
    out = ['<html><body style="font-family:monospace;background:#1a1a1a;color:#eee;padding:2rem">']
    out.append(f'<h2>ZIP: {_html.escape(f.filename)}</h2>')
    try:
        with zipfile.ZipFile(_io.BytesIO(zip_bytes)) as zf:
            names = sorted(zf.namelist())
            out.append(f'<p><b>{len(names)} files total</b></p>')
            for fname in names:
                basename = fname.split('/')[-1]
                out.append(f'<h3 style="color:#f5b45c;margin-top:2rem">{_html.escape(fname)}</h3>')
                if not fname.lower().endswith('.csv'):
                    out.append('<p style="color:#888">Not a CSV — skipped</p>')
                    continue
                try:
                    raw = zf.read(fname).decode('utf-8-sig', errors='replace')
                    reader = _csv.reader(_io.StringIO(raw))
                    rows = list(reader)
                    out.append(f'<p style="color:#888">{len(rows)} rows total</p>')
                    # Show first 8 rows as a table
                    out.append('<div style="overflow-x:auto"><table border="1" style="border-collapse:collapse;font-size:0.8rem">')
                    for ri, row in enumerate(rows[:8]):
                        style = 'background:#2a2a2a' if ri == 0 else ''
                        out.append(f'<tr style="{style}">')
                        for cell in row:
                            out.append(f'<td style="padding:4px 8px;border-color:#444">{_html.escape(str(cell))}</td>')
                        out.append('</tr>')
                    out.append('</table></div>')
                except Exception as e:
                    out.append(f'<p style="color:red">Error: {_html.escape(str(e))}</p>')
    except zipfile.BadZipFile:
        out.append('<p style="color:red">Not a valid ZIP file.</p>')
    out.append('</body></html>')
    return ''.join(out)


# ─────────────────────────────────────────────────────────────────────────────
# LABOR / PAYROLL MODULE
# ─────────────────────────────────────────────────────────────────────────────

# Employees/roles to exclude from all labor cost & hour calculations.
# These are internal/system entries (POS terminals, bar computers, etc.)
LABOR_EXCLUDED_NAMES = {
    'low bar, tdr',
    'main bar, tdr',
    'bar computer',
    'room 120',
    'room 120 bartender',
    'room 120 computer',
}


def _is_labor_excluded(name, job=''):
    """Return True if this employee/role should be excluded from labor totals."""
    n = (name or '').strip().lower()
    j = (job  or '').strip().lower()
    return n in LABOR_EXCLUDED_NAMES or j in LABOR_EXCLUDED_NAMES


def _parse_labor_csv_zip(zip_bytes, original_filename=''):
    """Parse a Toast Labor / Employee ZIP export.

    Toast labor ZIPs typically contain one or more of:
      - A shift-level CSV with columns: Employee Name, Job/Role, Date, In, Out,
        Regular Hours, Overtime Hours, Total Hours, Regular Pay, OT Pay, Total Pay
      - A summary CSV with period totals
      - Variations depending on Toast version

    The parser reads every CSV and tries to detect the format from the column headers.
    Date range is extracted from the filename (YYYY-MM-DD_YYYY-MM-DD).
    """
    import zipfile, csv as _csv, io as _io

    result = {
        'week_start': None, 'week_end': None,
        'total_hours': 0.0, 'regular_hours': 0.0, 'overtime_hours': 0.0,
        'total_cost': 0.0,  'regular_cost': 0.0,  'overtime_cost': 0.0,
        'shift_count': 0,   'employee_count': 0,
        'employees': [],    'jobs': [],
    }

    def cm(s):
        try:
            return float(str(s).strip().replace(',', '').replace('$', ''))
        except Exception:
            return 0.0

    def ch(s):
        """Parse hours that may be 'H:MM' or a decimal float."""
        s = str(s).strip()
        if ':' in s:
            parts = s.split(':')
            try:
                return int(parts[0]) + int(parts[1]) / 60.0
            except Exception:
                return 0.0
        return cm(s)

    # Extract dates from filename
    date_m = re.search(r'(\d{4}-\d{2}-\d{2})[_\-](\d{4}-\d{2}-\d{2})', original_filename)
    if date_m:
        try:
            result['week_start'] = datetime.strptime(date_m.group(1), '%Y-%m-%d').date()
            result['week_end']   = datetime.strptime(date_m.group(2), '%Y-%m-%d').date()
        except Exception:
            pass

    try:
        with zipfile.ZipFile(_io.BytesIO(zip_bytes)) as zf:
            for fname in sorted(zf.namelist()):
                if not fname.lower().endswith('.csv'):
                    continue
                try:
                    raw = zf.read(fname).decode('utf-8-sig', errors='replace')
                except Exception:
                    continue
                rows = list(_csv.reader(_io.StringIO(raw)))
                rows = [r for r in rows if any(c.strip() for c in r)]
                if len(rows) < 2:
                    continue

                headers = [h.strip().lower() for h in rows[0]]

                def hdr(*candidates):
                    for c in candidates:
                        if c in headers:
                            return headers.index(c)
                    return -1

                # Toast "Labor cost by job" format uses last name / first name columns
                # and "total cost" / "regular cost" / "overtime cost" instead of "pay"
                has_firstname = hdr('first name', 'firstname') >= 0
                has_lastname  = hdr('last name',  'lastname')  >= 0
                has_employee  = hdr('employee', 'employee name', 'name') >= 0 or has_firstname or has_lastname
                has_hours     = hdr('total hours', 'hours', 'reg hours', 'regular hours') >= 0
                has_pay       = hdr('total pay', 'gross pay', 'regular pay', 'total wages',
                                    'total cost', 'regular cost', 'overtime cost') >= 0

                # Also handle the summary CSV ("Labor cost summary.csv")
                if 'labor cost' in headers and 'net sales' in headers and not has_employee:
                    d = dict(zip(headers, [c.strip() for c in rows[1]] if len(rows) > 1 else []))
                    lc = cm(d.get('labor cost', 0))
                    if lc > 0 and result['total_cost'] == 0.0:
                        result['total_cost'] = lc
                    app.logger.info(f'  → summary CSV, labor cost={lc}')
                    continue

                if has_employee and (has_hours or has_pay):
                    # Column indices — Toast uses first name + last name separately
                    fn_idx   = hdr('first name', 'firstname')
                    ln_idx   = hdr('last name',  'lastname')
                    emp_idx  = hdr('employee', 'employee name', 'name')
                    job_idx  = hdr('job title', 'job', 'role', 'position', 'department')
                    reg_h    = hdr('regular hours', 'reg hours', 'regular hrs', 'reg. hours')
                    ot_h     = hdr('overtime hours', 'ot hours', 'overtime hrs', 'ot hrs')
                    tot_h    = hdr('total hours', 'hours', 'total hrs')
                    reg_p    = hdr('regular cost', 'regular pay', 'reg pay', 'regular wages')
                    ot_p     = hdr('overtime cost', 'overtime pay', 'ot pay', 'overtime wages')
                    tot_p    = hdr('total cost', 'total pay', 'gross pay', 'total wages')

                    def get(row, idx, fn=cm):
                        if idx >= 0 and idx < len(row):
                            return fn(row[idx])
                        return 0.0

                    def emp_name(row):
                        if fn_idx >= 0 or ln_idx >= 0:
                            fn = row[fn_idx].strip() if fn_idx >= 0 and fn_idx < len(row) else ''
                            ln = row[ln_idx].strip() if ln_idx >= 0 and ln_idx < len(row) else ''
                            full = f'{fn} {ln}'.strip()
                            return full if full else 'Unknown'
                        if emp_idx >= 0 and emp_idx < len(row):
                            return row[emp_idx].strip()
                        return 'Unknown'

                    emp_map = {}  # name → {hours, regular_pay, ot_pay, total_pay, job}
                    job_map = {}  # job  → {hours, cost}

                    for row in rows[1:]:
                        if not row or not any(c.strip() for c in row):
                            continue
                        name = emp_name(row)
                        if not name or name.lower() in ('total', 'totals', ' ', ''):
                            continue

                        job = row[job_idx].strip() if job_idx >= 0 and job_idx < len(row) else ''
                        rh  = get(row, reg_h, ch)
                        oh  = get(row, ot_h,  ch)
                        th  = get(row, tot_h, ch) or (rh + oh)
                        rp  = get(row, reg_p)
                        op  = get(row, ot_p)
                        tp  = get(row, tot_p) or (rp + op)

                        if th == 0.0 and tp == 0.0:
                            continue  # skip blank/zero rows

                        excluded = _is_labor_excluded(name, job)
                        result['shift_count'] += 1

                        if name not in emp_map:
                            emp_map[name] = {'name': name, 'job': job,
                                             'hours': 0.0, 'regular_pay': 0.0,
                                             'ot_pay': 0.0, 'total_pay': 0.0,
                                             'excluded': excluded}
                        emp_map[name]['hours']       += th
                        emp_map[name]['regular_pay'] += rp
                        emp_map[name]['ot_pay']      += op
                        emp_map[name]['total_pay']   += tp
                        if job and not emp_map[name]['job']:
                            emp_map[name]['job'] = job

                        if job and not excluded:
                            if job not in job_map:
                                job_map[job] = {'job': job, 'hours': 0.0, 'cost': 0.0}
                            job_map[job]['hours'] += th
                            job_map[job]['cost']  += tp

                    result['employees'] = sorted(emp_map.values(), key=lambda e: -e['total_pay'])
                    result['jobs']      = sorted(job_map.values(), key=lambda j: -j['cost'])
                    result['employee_count'] = sum(1 for e in emp_map.values() if not e.get('excluded'))

                    active = [e for e in emp_map.values() if not e.get('excluded')]
                    if active:
                        result['total_hours']   = sum(e['hours']       for e in active)
                        result['total_cost']    = sum(e['total_pay']   for e in active)
                        result['regular_cost']  = sum(e['regular_pay'] for e in active)
                        result['overtime_cost'] = sum(e['ot_pay']      for e in active)
                    app.logger.info(f'  → parsed {len(emp_map)} employees, total_cost={result["total_cost"]:.2f}')

    except zipfile.BadZipFile:
        raise ValueError('Uploaded file is not a valid ZIP archive.')

    return result


@app.route('/admin/labor-debug-zip', methods=['GET', 'POST'])
def labor_debug_zip():
    """Admin-only: inspect a labor ZIP — shows every CSV's headers and first 8 rows."""
    if 'user_id' not in session or session.get('role') != 'admin':
        return 'Unauthorized', 403
    if request.method == 'GET':
        return '''<!doctype html><html><body style="font-family:monospace;padding:2rem;background:#1a1a1a;color:#eee;">
        <h2>Labor ZIP Inspector</h2>
        <form method="post" enctype="multipart/form-data">
          <input type="file" name="zip" accept=".zip" required style="color:#eee">
          <button type="submit" style="margin-left:1rem">Inspect</button>
        </form></body></html>'''
    import zipfile, csv as _csv
    import io as _io, html as _html
    f = request.files.get('zip')
    if not f:
        return 'No file', 400
    out = [f'<html><body style="font-family:monospace;background:#1a1a1a;color:#eee;padding:2rem"><h2>Labor ZIP: {_html.escape(f.filename)}</h2>']
    try:
        with zipfile.ZipFile(_io.BytesIO(f.read())) as zf:
            for fname in sorted(zf.namelist()):
                out.append(f'<h3 style="color:#f5b45c;margin-top:2rem">{_html.escape(fname)}</h3>')
                if not fname.lower().endswith('.csv'):
                    out.append('<p style="color:#888">Skipped (not CSV)</p>'); continue
                raw  = zf.read(fname).decode('utf-8-sig', errors='replace')
                rows = list(_csv.reader(_io.StringIO(raw)))
                rows = [r for r in rows if any(c.strip() for c in r)]
                out.append(f'<p style="color:#888">{len(rows)} rows</p>')
                out.append('<div style="overflow-x:auto"><table border="1" style="border-collapse:collapse;font-size:0.8rem">')
                for ri, row in enumerate(rows[:8]):
                    style = 'background:#2a2a2a' if ri == 0 else ''
                    out.append(f'<tr style="{style}">')
                    for cell in row:
                        out.append(f'<td style="padding:4px 8px;border-color:#444">{_html.escape(str(cell))}</td>')
                    out.append('</tr>')
                out.append('</table></div>')
    except zipfile.BadZipFile:
        out.append('<p style="color:red">Not a valid ZIP file.</p>')
    out.append('</body></html>')
    return ''.join(out)


@app.route('/admin/labor-upload', methods=['POST'])
def labor_upload():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if not authorized('upload_labor_report'):
        flash('Access denied.', 'danger')
        return redirect(url_for('sales_dashboard'))

    f = request.files.get('labor_zip')
    if not f or not f.filename:
        flash('No file selected.', 'danger')
        return redirect(url_for('sales_dashboard'))

    filename = secure_filename(f.filename)
    if not filename.lower().endswith('.zip'):
        flash('Only ZIP files are accepted for labor data.', 'danger')
        return redirect(url_for('sales_dashboard'))

    file_bytes = f.read()
    try:
        data = _parse_labor_csv_zip(file_bytes, original_filename=filename)
    except Exception as e:
        flash(f'Error parsing labor ZIP: {e}', 'danger')
        return redirect(url_for('sales_dashboard'))

    # Manual date overrides
    override_start = request.form.get('override_start', '').strip()
    override_end   = request.form.get('override_end',   '').strip()
    period_label   = request.form.get('period_label',   '').strip()
    period_type    = request.form.get('period_type', 'weekly').strip()

    if override_start:
        try:
            data['week_start'] = datetime.strptime(override_start, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid start date.', 'danger')
            return redirect(url_for('sales_dashboard'))
    if override_end:
        try:
            data['week_end'] = datetime.strptime(override_end, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid end date.', 'danger')
            return redirect(url_for('sales_dashboard'))

    if not data.get('week_start') or not data.get('week_end'):
        flash('Could not determine date range — set Start and End dates manually.', 'danger')
        return redirect(url_for('sales_dashboard'))

    if not period_label:
        period_label = f'{data["week_start"]} – {data["week_end"]}'

    existing = LaborReport.query.filter_by(week_start=data['week_start']).first()
    if existing:
        rpt = existing
        flash(f'Labor data for period starting {data["week_start"]} updated.', 'warning')
    else:
        rpt = LaborReport()
        db.session.add(rpt)

    rpt.week_start        = data['week_start']
    rpt.week_end          = data['week_end']
    rpt.period_label      = period_label
    rpt.period_type       = period_type
    rpt.uploaded_at       = datetime.utcnow()
    rpt.original_filename = filename

    for field in ['total_hours', 'regular_hours', 'overtime_hours',
                  'total_cost', 'regular_cost', 'overtime_cost',
                  'shift_count', 'employee_count']:
        setattr(rpt, field, data.get(field, 0))

    rpt.employees_json = json.dumps(data.get('employees', []))
    rpt.jobs_json      = json.dumps(data.get('jobs', []))

    db.session.commit()
    log_audit('labor', f'Uploaded labor report for period {data["week_start"]}')
    if not existing:
        flash(f'Labor report for {data["week_start"]} uploaded successfully!', 'success')

    # Redirect to the matching sales period so both are shown together
    sales_rpt = WeeklySalesReport.query.filter_by(week_start=rpt.week_start).first()
    if sales_rpt:
        return redirect(url_for('sales_dashboard', id=sales_rpt.id))
    return redirect(url_for('sales_dashboard'))


@app.route('/admin/labor-delete/<int:report_id>', methods=['POST'])
def labor_delete(report_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if not authorized('delete_labor_report'):
        flash('Access denied.', 'danger')
        return redirect(url_for('sales_dashboard'))
    rpt = LaborReport.query.get_or_404(report_id)
    label = str(rpt.week_start)
    db.session.delete(rpt)
    db.session.commit()
    log_audit('labor', f'Deleted labor report for period {label}')
    flash(f'Labor report for {label} deleted.', 'success')
    return redirect(url_for('sales_dashboard'))


@app.route('/admin/labor-dashboard')
def labor_dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if not authorized('view_labor_dashboard'):
        flash('Access denied.', 'danger')
        return redirect(url_for('home'))

    reports = LaborReport.query.order_by(LaborReport.week_start.desc()).all()

    selected_id = request.args.get('id', type=int)
    report = None
    if selected_id:
        report = LaborReport.query.get(selected_id)
    if not report and reports:
        report = reports[0]

    employees_all = []
    jobs          = []
    if report:
        try:
            employees_all = json.loads(report.employees_json or '[]')
            jobs          = json.loads(report.jobs_json      or '[]')
        except Exception:
            pass

    # Split active vs excluded employees for display
    employees         = [e for e in employees_all if not e.get('excluded')]
    employees_excluded = [e for e in employees_all if e.get('excluded')]

    # Recalculate filtered totals from active employees (handles both old and new uploads)
    filtered_hours   = sum(e.get('hours', 0)       for e in employees)
    filtered_cost    = sum(e.get('total_pay', 0)   for e in employees)
    filtered_reg_cost= sum(e.get('regular_pay', 0) for e in employees)
    filtered_ot_cost = sum(e.get('ot_pay', 0)      for e in employees)
    # Fall back to stored totals if per-employee data not present
    if not employees and report:
        filtered_hours    = report.total_hours
        filtered_cost     = report.total_cost
        filtered_reg_cost = report.regular_cost
        filtered_ot_cost  = report.overtime_cost

    # Filter jobs list to exclude any job present only in excluded employees
    jobs = [j for j in jobs if not _is_labor_excluded('', j.get('job', ''))]

    # Match to a sales report for the same period (for labor % calculations)
    sales = None
    if report:
        sales = WeeklySalesReport.query.filter_by(week_start=report.week_start).first()

    labor_pct     = round(filtered_cost / sales.net_sales * 100, 1) if (sales and sales.net_sales and filtered_cost) else None
    rev_per_hour  = round(sales.net_sales / filtered_hours, 2)       if (sales and filtered_hours) else None
    cost_per_hour = round(filtered_cost / filtered_hours, 2)          if filtered_hours else None

    # Trend data (all periods) — use filtered totals derived from per-employee JSON
    trend_reports = LaborReport.query.order_by(LaborReport.week_start.asc()).all()
    trend_sales   = {s.week_start: s for s in WeeklySalesReport.query.all()}

    def _filtered_cost(r):
        try:
            emps = json.loads(r.employees_json or '[]')
            active = [e for e in emps if not e.get('excluded')]
            c = sum(e.get('total_pay', 0) for e in active)
            return c if c else r.total_cost
        except Exception:
            return r.total_cost

    def _filtered_hours(r):
        try:
            emps = json.loads(r.employees_json or '[]')
            active = [e for e in emps if not e.get('excluded')]
            h = sum(e.get('hours', 0) for e in active)
            return h if h else r.total_hours
        except Exception:
            return r.total_hours

    trend_labels    = [r.week_start.strftime('%b %d') for r in trend_reports]
    trend_cost      = [_filtered_cost(r)              for r in trend_reports]
    trend_hours     = [_filtered_hours(r)             for r in trend_reports]
    trend_labor_pct = [
        round(_filtered_cost(r) / trend_sales[r.week_start].net_sales * 100, 1)
        if r.week_start in trend_sales and trend_sales[r.week_start].net_sales else 0
        for r in trend_reports
    ]
    trend_net_sales = [
        trend_sales[r.week_start].net_sales if r.week_start in trend_sales else 0
        for r in trend_reports
    ]

    return render_template(
        'admin_labor_dashboard.html',
        reports=reports,
        report=report,
        employees=employees,
        employees_excluded=employees_excluded,
        jobs=jobs,
        sales=sales,
        filtered_hours=filtered_hours,
        filtered_cost=filtered_cost,
        filtered_ot_cost=filtered_ot_cost,
        labor_pct=labor_pct,
        rev_per_hour=rev_per_hour,
        cost_per_hour=cost_per_hour,
        # Chart.js — JSON strings
        js_trend_labels=json.dumps(trend_labels),
        js_trend_cost=json.dumps(trend_cost),
        js_trend_hours=json.dumps(trend_hours),
        js_trend_labor_pct=json.dumps(trend_labor_pct),
        js_trend_net_sales=json.dumps(trend_net_sales),
        # Jinja2 table — Python lists
        trend_rows=list(zip(trend_labels, trend_net_sales, trend_cost, trend_labor_pct, trend_hours)),
        can_upload=authorized('upload_labor_report'),
        can_delete=authorized('delete_labor_report'),
        excluded_names=sorted(LABOR_EXCLUDED_NAMES),
    )


@app.route('/admin/sales-export')
def sales_export():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if not authorized('view_sales_dashboard'):
        flash('Access denied.', 'danger')
        return redirect(url_for('home'))

    start = request.args.get('start')
    end   = request.args.get('end')

    q = WeeklySalesReport.query.order_by(WeeklySalesReport.week_start.asc())
    if start:
        try:
            q = q.filter(WeeklySalesReport.week_start >= datetime.strptime(start, '%Y-%m-%d').date())
        except ValueError:
            pass
    if end:
        try:
            q = q.filter(WeeklySalesReport.week_end <= datetime.strptime(end, '%Y-%m-%d').date())
        except ValueError:
            pass

    reports = q.all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'Week Start', 'Week End', 'Location',
        'Net Sales', 'Gross Sales', 'Sales Discounts', 'Sales Refunds',
        'Gratuity', 'Tax', 'Tips', 'Total Amount',
        'Tips Collected', 'Tips Withheld', 'Tips After Withholding',
        'Cash Payments', 'Expected Closeout', 'Actual Closeout', 'Cash Overage',
        'Total Guests', 'Total Orders', 'Avg/Guest', 'Avg/Order',
        'Quick Service Net', 'Table Service Net',
        'Void Amount', 'Void Orders', 'Void Items',
        'Total Discounts', 'Total Service Charges',
        'Taxable Amount',
    ])
    for r in reports:
        writer.writerow([
            r.week_start, r.week_end, r.location,
            r.net_sales, r.gross_sales, r.sales_discounts, r.sales_refunds,
            r.gratuity, r.tax_amount, r.tips, r.total_amount,
            r.tips_collected, r.tips_withheld, r.tips_after_withholding,
            r.total_cash_payments, r.expected_closeout_cash,
            r.actual_closeout_cash, r.cash_overage,
            r.total_guests, r.total_orders, r.avg_per_guest, r.avg_per_order,
            r.quick_service_net, r.table_service_net,
            r.void_amount, r.void_order_count, r.void_item_count,
            r.total_discounts_amount, r.total_service_charges,
            r.taxable_amount,
        ])

    output.seek(0)
    return send_file(
        io.BytesIO(output.read().encode()),
        mimetype='text/csv',
        as_attachment=True,
        download_name='sales_export.csv',
    )


@app.route('/admin/sales-report-builder')
def sales_report_builder():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if not authorized('view_sales_dashboard'):
        flash('Access denied.', 'danger')
        return redirect(url_for('home'))

    # All weeks for filter dropdowns
    reports = WeeklySalesReport.query.order_by(WeeklySalesReport.week_start.asc()).all()

    start      = request.args.get('start')
    end        = request.args.get('end')
    chart_type = request.args.get('chart_type', 'line')
    metrics    = request.args.getlist('metrics') or [
        'net_sales', 'gratuity', 'tax_amount', 'tips', 'total_amount'
    ]

    q = WeeklySalesReport.query.order_by(WeeklySalesReport.week_start.asc())
    if start:
        try:
            q = q.filter(WeeklySalesReport.week_start >= datetime.strptime(start, '%Y-%m-%d').date())
        except ValueError:
            pass
    if end:
        try:
            q = q.filter(WeeklySalesReport.week_end <= datetime.strptime(end, '%Y-%m-%d').date())
        except ValueError:
            pass

    filtered = q.all()

    # Ordered list of (key, label) for template iteration
    ALL_METRICS = [
        ('net_sales',              'Net Sales'),
        ('gross_sales',            'Gross Sales'),
        ('total_amount',           'Total Revenue'),
        ('gratuity',               'Gratuity'),
        ('tax_amount',             'Tax'),
        ('tips',                   'Tips'),
        ('total_service_charges',  'Service Charges'),
        ('tips_collected',         'Tips Collected'),
        ('tips_withheld',          'Tips Withheld'),
        ('tips_after_withholding', 'After Withholding'),
        ('total_cash_payments',    'Cash Payments'),
        ('expected_closeout_cash', 'Expected Closeout'),
        ('actual_closeout_cash',   'Actual Closeout'),
        ('cash_overage',           'Cash Overage'),
        ('total_guests',           'Total Guests'),
        ('total_orders',           'Total Orders'),
        ('avg_per_guest',          'Avg / Guest'),
        ('avg_per_order',          'Avg / Order'),
        ('quick_service_net',      'Quick Service Net'),
        ('table_service_net',      'Table Service Net'),
        ('void_amount',            'Void Amount'),
        ('total_discounts_amount', 'Total Discounts'),
        ('sales_discounts',        'Sales Discounts'),
        ('sales_refunds',          'Sales Refunds'),
    ]
    METRIC_LABELS = dict(ALL_METRICS)

    colors = ['#f5b45c','#4bc4cf','#a8e063','#f7797d','#6a82fb',
              '#ffd89b','#11998e','#fc5c7d','#a18cd1','#ffecd2']

    labels = [
        (r.period_label or f'{r.week_start} – {r.week_end}')
        for r in filtered
    ]
    chart_datasets = []
    for i, m in enumerate(metrics):
        if m in METRIC_LABELS:
            chart_datasets.append({
                'label': METRIC_LABELS[m],
                'data':  [getattr(r, m, 0) for r in filtered],
                'color': colors[i % len(colors)],
            })

    return render_template(
        'admin_sales_report_builder.html',
        reports=reports,
        filtered=filtered,
        metrics=metrics,
        all_metrics=ALL_METRICS,
        metric_labels=METRIC_LABELS,
        chart_type=chart_type,
        start=start or '',
        end=end or '',
        labels=json.dumps(labels),
        chart_datasets=json.dumps(chart_datasets),
        can_export=authorized('export_report'),
    )


# =====================================================
# SCHEDULED DAILY BACKUP (midnight EST)
# =====================================================

def _run_scheduled_backup():
    """Write a full JSON backup to the backups/ folder. Keeps the last 30 files."""
    backup_dir = os.path.join(os.path.dirname(__file__), 'backups')
    os.makedirs(backup_dir, exist_ok=True)

    def _sv(v):
        if v is None:
            return None
        t = type(v).__name__
        if t in ('datetime', 'date'):
            return v.isoformat()
        if t == 'time':
            return v.strftime('%H:%M:%S')
        return v

    def _dump(model_cls):
        return [
            {col.name: _sv(getattr(obj, col.name)) for col in model_cls.__table__.columns}
            for obj in model_cls.query.all()
        ]

    with app.app_context():
        backup = {
            '_meta': {
                'version': 1,
                'exported_at': datetime.utcnow().isoformat(),
                'app': 'room120',
                'source': 'scheduled_backup',
            },
            MembershipType.__tablename__:       _dump(MembershipType),
            StaffRole.__tablename__:            _dump(StaffRole),
            ClubSetting.__tablename__:          _dump(ClubSetting),
            SavedReport.__tablename__:          _dump(SavedReport),
            BlockedDate.__tablename__:          _dump(BlockedDate),
            Event.__tablename__:                _dump(Event),
            User.__tablename__:                 _dump(User),
            Application.__tablename__:          _dump(Application),
            PrivateEventRequest.__tablename__:  _dump(PrivateEventRequest),
            Note.__tablename__:                 _dump(Note),
            Reservation.__tablename__:          _dump(Reservation),
            AdminActionLog.__tablename__:       _dump(AdminActionLog),
            AuditLog.__tablename__:             _dump(AuditLog),
            Order.__tablename__:                _dump(Order),
            OrderItem.__tablename__:            _dump(OrderItem),
            Invoice.__tablename__:              _dump(Invoice),
            InvoiceLineItem.__tablename__:      _dump(InvoiceLineItem),
            Table.__tablename__:                _dump(Table),
            LayoutItem.__tablename__:           _dump(LayoutItem),
            SeatingItem.__tablename__:          _dump(SeatingItem),
            SeatingReservation.__tablename__:   _dump(SeatingReservation),
            ToastTransaction.__tablename__:     _dump(ToastTransaction),
            ToastTransactionItem.__tablename__: _dump(ToastTransactionItem),
            ToastMemberSpending.__tablename__:  _dump(ToastMemberSpending),
            ToastSyncLog.__tablename__:         _dump(ToastSyncLog),
            SetupToken.__tablename__:           _dump(SetupToken),
            WeeklySalesReport.__tablename__:    _dump(WeeklySalesReport),
        }

        fname = f'room120_backup_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.json'
        fpath = os.path.join(backup_dir, fname)
        with open(fpath, 'w', encoding='utf-8') as f:
            json.dump(backup, f, indent=2, default=str)

        logger.info(f'Scheduled backup saved: {fname}')

        # Prune: keep the 30 most recent backup files
        backups = sorted(
            [os.path.join(backup_dir, x) for x in os.listdir(backup_dir) if x.endswith('.json')],
            key=os.path.getmtime, reverse=True
        )
        for old in backups[30:]:
            try:
                os.remove(old)
            except OSError:
                pass


def _start_scheduler():
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    import pytz

    scheduler = BackgroundScheduler(timezone=pytz.utc)
    # midnight EST = 05:00 UTC (EST is UTC-5; during EDT it's 04:00 UTC)
    # Use America/New_York so it auto-adjusts for daylight saving
    est = pytz.timezone('America/New_York')
    scheduler.add_job(
        _run_scheduled_backup,
        CronTrigger(hour=0, minute=0, timezone=est),
        id='daily_backup',
        replace_existing=True,
    )
    scheduler.start()
    logger.info('Daily backup scheduler started (fires at midnight EST)')
    return scheduler


if __name__ == "__main__":
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.config['DEBUG'] = True

    _start_scheduler()

    port = int(os.environ.get("PORT", 5002))
    app.run(host="0.0.0.0", port=port, debug=True)
