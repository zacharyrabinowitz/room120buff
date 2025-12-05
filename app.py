from flask import Flask, render_template, request, redirect, url_for, session
from flask_session import Session
from flask_sqlalchemy import SQLAlchemy
from models import User
import calendar
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import current_user
from flask import Flask, render_template, request, redirect, url_for, session, flash
import csv
import random
import string
from flask import Response
import os
from werkzeug.utils import secure_filename
from flask import send_file
from flask_migrate import Migrate
from flask import send_from_directory
from flask import make_response, render_template_string
from xhtml2pdf import pisa
from io import BytesIO
from flask import make_response
from datetime import datetime
from flask import jsonify
from flask import send_file
from flask import send_from_directory
from flask import render_template, make_response
from xhtml2pdf import pisa
from io import BytesIO
from flask import Flask, render_template, redirect, url_for, session, request, flash
from toast_api import toast_api_get
import json
from flask import request
from calendar import monthcalendar
from datetime import date
from flask import render_template
from sqlalchemy import text  # Import text from sqlalchemy
from dotenv import load_dotenv  # Import load_dotenv from dotenv
import os  # Import os
from flask import send_file, request, jsonify
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
import io
import base64



app = Flask(__name__)
app.secret_key = 'supersecretkey'
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///room120.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

Session(app)
db = SQLAlchemy(app)
migrate = Migrate(app, db)




UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads', 'invoices')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER



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
    notes = db.Column(db.Text)

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

    # Define the relationship with the User model
    admin = db.relationship("User", backref="admin_logs")




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



@app.context_processor
def inject_user():
    return dict(current_user=current_user)

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
            flash('Logged in as Backup Admin.', 'success')
            return redirect(url_for('home'))

        # Normal User Login
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            if not user.active:
                flash('Your account is deactivated. Please contact an administrator.', 'danger')
                return redirect(url_for('login'))
                
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = 'admin' if user.role == 'admin' else 'member'
            flash('Logged in successfully.', 'success')
            return redirect(url_for('home'))
        else:
            flash('Invalid credentials.', 'danger')
    return render_template('login.html')


@app.route('/logout')
def logout():
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
    if filter_type == 'corporate':
        members_query = members_query.filter_by(membership_type='corporate')
    elif filter_type == 'single':
        members_query = members_query.filter_by(membership_type='single')

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
    corporate_count = User.query.filter_by(role='member', membership_type='corporate').count()
    single_count = User.query.filter_by(role='member', membership_type='single').count()

    # Financial summaries
    total_outstanding = sum((m.amount_owed or 0) for m in members)
    total_spent = sum((m.amount_spent or 0) for m in members)

    # Member Balance Chart Data
    member_labels = []
    member_balances = []

    for m in members:
        label = f"{m.first_name} {m.last_name}".strip() or f"Member {m.id}"
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

    user = User.query.get(session['user_id'])
    blocked_dates = [b.date for b in BlockedDate.query.all()]
    error = None

    # Handle pre-filled values from RSVP
    prefill_date = request.args.get('date')
    prefill_time = request.args.get('time')
    prefill_note = request.args.get('note')

    if request.method == 'POST':
        date_str = request.form['date']
        time_str = request.form['time']
        guests_str = request.form['guests']
        notes = request.form.get('notes', '')

        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            error = "Invalid date format."
            return render_template('reservations.html', reservations=[], blocked_dates=blocked_dates, error=error)

        try:
            time_obj = datetime.strptime(time_str, '%H:%M').time()
        except ValueError:
            error = "Invalid time format."
            return render_template('reservations.html', reservations=[], blocked_dates=blocked_dates, error=error)

        try:
            guests_int = int(guests_str)
        except ValueError:
            error = "Guests must be a number."
            return render_template('reservations.html', reservations=[], blocked_dates=blocked_dates, error=error)

        if date_str in blocked_dates:
            error = "Sorry, this date is blocked for reservations."
        else:
            new_reservation = Reservation(
                user_id=user.id,
                date=date_obj,
                time=time_obj,
                guests=guests_int,
                notes=notes
            )
            db.session.add(new_reservation)
            db.session.commit()
            return redirect(url_for('reservations'))

    reservations = Reservation.query.filter_by(user_id=user.id).all()

    return render_template(
        'reservations.html',
        reservations=reservations,
        blocked_dates=blocked_dates,
        error=error,
        prefill_date=prefill_date,
        prefill_time=prefill_time,
        prefill_note=prefill_note
    )


@app.route('/admin/reservations')
def admin_reservations():
    if session.get('role') != 'admin':
        return redirect(url_for('home'))

    all_reservations = Reservation.query.all()
    blocked_dates = BlockedDate.query.all()

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
    if session.get('role') != 'admin':
        return redirect(url_for('home'))

    date = request.form['blocked_date']
    existing = BlockedDate.query.filter_by(date=date).first()

    if not existing:
        db.session.add(BlockedDate(date=date))
        db.session.commit()

    return redirect(url_for('admin_reservations'))

@app.route('/admin/unblock-date/<int:id>', methods=['POST'])
def unblock_date(id):
    if session.get('role') != 'admin':
        return redirect(url_for('home'))

    blocked = BlockedDate.query.get_or_404(id)
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
            return redirect(url_for('view_member', user_id=reservation.user_id))
        
        except ValueError:
            flash('Invalid input. Please check your date, time, and number of guests.', 'danger')
            return render_template('edit_reservation.html', reservation=reservation)

    return render_template('edit_reservation.html', reservation=reservation)




@app.route('/reservations/delete/<int:reservation_id>', methods=['POST'])
def delete_reservation(reservation_id):
    reservation = Reservation.query.get_or_404(reservation_id)

    # Restrict access: Only admin or the reservation owner can delete
    if session.get('role') != 'admin' and session.get('user_id') != reservation.user_id:
        return redirect(url_for('home'))

    db.session.delete(reservation)
    db.session.commit()
    return redirect(url_for('view_member', user_id=reservation.user_id))


@app.route("/seating_map")
def seating_map():
    event_id = request.args.get("event_id")

    events = Event.query.all()
    items = SeatingItem.query.all()
    members = User.query.filter_by(role="member").all()

    selected_event = Event.query.get(event_id) if event_id else None

    reservation_map = {}

    if selected_event:
        reservations = SeatingReservation.query.filter_by(event_id=selected_event.id).all()

        for r in reservations:
            reservation_map[r.seating_item_id] = r

    return render_template(
        "seating_map.html",
        events=events,
        items=items,
        selected_event=selected_event,
        members=members,
        reservation_map=reservation_map
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
            "name": f"{m.first_name} {m.last_name}",
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
    data = request.json

    # Clear old layout
    SeatingItem.query.delete()

    # Add new items
    for item in data:
        db_item = SeatingItem(
            kind=item.get("kind"),
            label=item.get("label"),
            x=item.get("x"),
            y=item.get("y"),
            width=item.get("width"),
            height=item.get("height"),
            rotation=item.get("rotation", 0),
            extra=item.get("extra")
        )
        db.session.add(db_item)

    db.session.commit()

    return {"status": "success"}

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
    member_id = data.get("member_id")
    guest_name = data.get("guest_name")

    # If member exists, ALWAYS override guest name
    if member_id:
        reservation.member_id = member_id
        reservation.guest_name = None   # << IMPORTANT
    else:
        reservation.member_id = None
        reservation.guest_name = guest_name or None

    reservation.num_guests = data.get("num_guests") or None
    reservation.timeslots = data.get("timeslots") or None
    reservation.notes = data.get("notes") or None

    db.session.commit()

    # Compute label for the front-end
    if reservation.member_id:
        member = User.query.get(reservation.member_id)
        label = f"{member.first_name} {member.last_name}"
    elif reservation.guest_name:
        label = reservation.guest_name
    else:
        label = "Reserved"

    return jsonify({
        "status": "ok",
        "display_label": label
    })



@app.route("/get_members_json")
def get_members_json():
    members = User.query.filter_by(role="member").all()
    data = []

    for m in members:
        data.append({
            "id": m.id,
            "name": f"{m.first_name} {m.last_name}",
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
        new_admin.set_password(password)  # ✅ HASH THE PASSWORD

        db.session.add(new_admin)
        db.session.commit()
        Flask('Admin registered successfully. You can now log in.')
        return redirect(url_for('login'))

    return render_template('register_admin.html')

@app.route('/toggle-admin/<int:user_id>', methods=['POST'])
def toggle_admin(user_id):
    if session.get('role') != 'admin':
        return redirect(url_for('home'))

    admin = User.query.get(user_id)
    if admin and admin.role == 'admin':
        admin.active = not admin.active
        db.session.commit()
    return redirect(url_for('manage_admins'))

@app.route('/manage-admins')
def manage_admins():
    if session.get('role') != 'admin':
        return redirect(url_for('home'))

    admins = User.query.filter_by(role='admin').all()  # ✅ This returns a list
    return render_template('manage_admins.html', admins=admins)


@app.route('/edit-admin/<int:user_id>', methods=['GET', 'POST'])
def edit_admin(user_id):
    if session.get('role') != 'admin':
        return redirect(url_for('home'))
    admin = User.query.get(user_id)
    if request.method == 'POST':
        admin.first_name = request.form['first_name']
        admin.last_name = request.form['last_name']
        admin.password = request.form['password']
        db.session.commit()
        return redirect(url_for('manage_admins'))
    return render_template('edit_admin.html', admin=admin)

@app.route('/delete-admin/<int:user_id>', methods=['POST'])
def delete_admin(user_id):
    if session.get('role') != 'admin':
        return redirect(url_for('home'))
    admin = User.query.get(user_id)
    db.session.delete(admin)
    db.session.commit()
    return redirect(url_for('manage_admins'))

@app.route('/manage-members')
def manage_members():
    if session.get('role') != 'admin':
        return redirect(url_for('home'))

    search_term = request.args.get('search', '').strip()

    if search_term:
        members = User.query.filter(
            User.role == 'member',
            (User.first_name.ilike(f'%{search_term}%')) |
            (User.last_name.ilike(f'%{search_term}%')) |
            (User.username.ilike(f'%{search_term}%'))
        ).all()
    else:
        members = User.query.filter_by(role='member').all()

    return render_template('manage_members.html', members=members, search_term=search_term)




@app.route('/toggle-member/<int:user_id>', methods=['POST'])
def toggle_member(user_id):
    if session.get('role') != 'admin':
        return redirect(url_for('home'))
    
    member = User.query.get(user_id)
    if member and member.role == 'member':
        member.active = not member.active
        db.session.commit()
    return redirect(url_for('view_member', user_id=user_id))

@app.route('/bulk_delete_members', methods=['POST'])
def bulk_delete_members():
    if session.get('role') != 'admin':
        return redirect(url_for('home'))

    selected_ids = request.form.getlist('selected_members')

    if not selected_ids:
        flash('No members selected.', 'warning')
        return redirect(url_for('manage_members'))

    for member_id in selected_ids:
        member = User.query.get(member_id)
        if member and member.role == 'member':
            db.session.delete(member)

    db.session.commit()
    flash(f'{len(selected_ids)} member(s) deleted successfully.', 'success')
    return redirect(url_for('manage_members'))


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
    if session.get('role') != 'admin':
        return redirect(url_for('home'))
    applications = Application.query.order_by(Application.submitted_at.desc()).all()
    return render_template('admin_applications.html', applications=applications)


@app.route('/admin/application/<int:app_id>')
def view_application(app_id):
    if session.get('role') != 'admin':
        return redirect(url_for('home'))
    application = Application.query.get_or_404(app_id)
    return render_template('admin_application_detail.html', application=application)


@app.route('/admin/approve_application/<int:app_id>', methods=['POST'])
def approve_application(app_id):
    if session.get('role') != 'admin':
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

    flash(f'Member {new_user.first_name} {new_user.last_name} created.', 'success')
    return redirect(url_for('admin_applications'))


@app.route('/admin/application/<int:app_id>/deny', methods=['POST'])
def deny_application(app_id):
    if session.get('role') != 'admin':
        return redirect(url_for('home'))
    application = Application.query.get_or_404(app_id)
    application.status = 'denied'
    db.session.commit()
    flash('Application denied.', 'warning')
    return redirect(url_for('admin_applications'))


@app.route('/admin/application/<int:app_id>/delete', methods=['POST'])
def delete_application(app_id):
    if session.get('role') != 'admin':
        return redirect(url_for('home'))
    application = Application.query.get_or_404(app_id)
    db.session.delete(application)
    db.session.commit()
    flash('Application deleted.', 'info')
    return redirect(url_for('admin_applications'))




@app.route('/admin/application/<int:app_id>/download')
def download_application_pdf(app_id):
    if session.get('role') != 'admin':
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
            member_number=member_number,
            active=True
        )
        member.set_password(password)
        db.session.add(member)
        db.session.commit()
        flash('Member added successfully.', 'success')

    return redirect(url_for('manage_members'))


@app.route('/import_members', methods=['POST'])
def import_members():
    if session.get('role') != 'admin':
        return redirect(url_for('home'))

    file = request.files.get('csv_file')
    if not file:
        flash('No file selected.', 'danger')
        return redirect(url_for('manage_members'))

    try:
        import csv
        stream = file.stream.read().decode("UTF8").splitlines()
        csv_reader = csv.DictReader(stream)

        for row in csv_reader:
            first_name = row.get('first_name', '').strip()
            last_name = row.get('last_name', '').strip()
            email = row.get('email', '').strip()
            username = row.get('username', '').strip()

            if not first_name or not last_name:
                continue  # Skip incomplete rows

            if not username:
                username = f"{first_name}{last_name}".lower()

            member = User.query.filter_by(username=username).first()

            try:
                amount_spent = float(row.get('total_spend', 0))
            except (TypeError, ValueError):
                amount_spent = 0

            try:
                amount_owed = float(row.get('outstanding_balance', 0))
            except (TypeError, ValueError):
                amount_owed = 0

            membership_type = 'single'
            if 'company_name' in row and row['company_name']:
                if 'single' not in row['company_name'].lower():
                    membership_type = 'corporate'

            if member:
                member.amount_spent += amount_spent
                member.amount_owed += amount_owed
            else:
                password = f"{first_name}{last_name}room120".lower()
                new_member = User(
                    username=username.lower(),
                    first_name=first_name,
                    last_name=last_name,
                    email=email,
                    member_number=None,
                    role='member',
                    active=True,
                    membership_type=membership_type,
                    amount_spent=amount_spent,
                    amount_owed=amount_owed
                )
                new_member.set_password(password)
                db.session.add(new_member)

        db.session.commit()
        flash('Members imported and updated successfully.', 'success')

    except Exception as e:
        flash(f'Error importing members: {str(e)}', 'danger')

    return redirect(url_for('manage_members'))





@app.route('/export-members')
def export_members():
    if session.get('role') != 'admin':
        return redirect(url_for('home'))

    members = User.query.filter_by(role='member').all()

    csv_data = "username,first_name,last_name,email,member_number,active\n"
    for m in members:
        csv_data += f"{m.username},{m.first_name},{m.last_name},{m.email or ''},{m.member_number or ''},{'Active' if m.active else 'Inactive'}\n"

    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=members.csv"}
    )

@app.route('/add-member', methods=['GET', 'POST'])
def add_member_page():
    if session.get('role') != 'admin':
        return redirect(url_for('home'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        email = request.form.get('email')
        member_number = request.form.get('member_number')
        membership_type = request.form.get('membership_type', 'single')  # Default to 'single'

        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'danger')
        else:
            member = User(
                username=username,
                role='member',
                first_name=first_name,
                last_name=last_name,
                email=email,
                member_number=member_number,
                membership_type=membership_type,
                active=True
            )
            member.set_password(password)
            db.session.add(member)
            db.session.commit()
            flash('Member added successfully.', 'success')
            return redirect(url_for('manage_members'))

    return render_template('add_member.html')

@app.route('/upload-invoice/<int:user_id>', methods=['POST'])
def upload_invoice(user_id):
    if session.get('role') != 'admin':
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

        # Update member balances
        member = User.query.get(member_id)
        member.amount_owed += subtotal
        member.tax_owed += tax_amount
        member.gratuity_owed += gratuity_amount

        db.session.add(invoice)
        db.session.commit()

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
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], invoice.stored_filename)

    if os.path.exists(filepath):
        os.remove(filepath)

    db.session.delete(invoice)
    db.session.commit()
    flash('Invoice deleted.', 'success')
    return redirect(url_for('view_member', user_id=invoice.member_id))




@app.route('/member/<int:user_id>/update_balance', methods=['POST'])
def update_balance(user_id):
    if not session.get('user_id') or session.get('role') != 'admin':
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
        flash('Balance updated successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating balance: {str(e)}', 'danger')

    return redirect(url_for('view_member', user_id=user.id))










@app.route('/add_order/<int:user_id>', methods=['GET', 'POST'])
def add_order(user_id):
    if not session.get('user_id') or session.get('role') != 'admin':
        return redirect(url_for('login'))

    user = User.query.get_or_404(user_id)

    if request.method == 'POST':
        date_str = request.form.get('date')
        time_str = request.form.get('time')
        notes = request.form.get('notes')
        paid_by_credit = bool(request.form.get('paid_by_credit'))

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

        if paid_by_credit:
            user.amount_spent += total
            user.tax_paid += tax
            user.gratuity_paid += gratuity
        else:
            user.amount_owed += subtotal
            user.tax_owed += tax
            user.gratuity_owed += gratuity

        db.session.commit()
        flash("Order successfully added.", "success")
        return redirect(url_for('view_member', user_id=user.id))

    return render_template('add_order.html', user=user)







@app.route('/order/edit/<int:order_id>', methods=['GET', 'POST'])
def edit_order(order_id):
    order = Order.query.get_or_404(order_id)
    user = order.user

    if request.method == 'POST':
        # Revert old values
        if order.paid_by_credit:
            user.amount_spent -= order.total
            user.tax_paid -= order.tax
            user.gratuity_paid -= order.gratuity
        else:
            user.amount_owed -= order.subtotal
            user.tax_owed -= order.tax
            user.gratuity_owed -= order.gratuity

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

        # Apply new values
        if order.paid_by_credit:
            user.amount_spent += order.total
            user.tax_paid += order.tax
            user.gratuity_paid += order.gratuity
        else:
            user.amount_owed += order.subtotal
            user.tax_owed += order.tax
            user.gratuity_owed += order.gratuity

        db.session.commit()
        flash('Order updated successfully.', 'success')
        return redirect(url_for('view_member', user_id=user.id))

    return render_template('edit_order.html', order=order, user=user)








@app.route('/delete_order/<int:order_id>', methods=['POST'])
def delete_order(order_id):
    if not session.get('user_id') or session.get('role') != 'admin':
        return redirect(url_for('login'))

    order = Order.query.get_or_404(order_id)
    user = order.user

    was_paid = order.paid_by_credit
    subtotal = order.subtotal
    tax = order.tax
    gratuity = order.gratuity
    total = order.total

    for item in order.items:
        db.session.delete(item)
    db.session.delete(order)
    db.session.commit()

    remaining_orders = Order.query.filter_by(user_id=user.id).all()

    if not remaining_orders:
        user.amount_spent = 0
        user.amount_owed = 0
        user.tax_owed = 0
        user.tax_paid = 0
        user.gratuity_owed = 0
        user.gratuity_paid = 0
    else:
        if was_paid:
            user.amount_spent -= total
            user.tax_paid -= tax
            user.gratuity_paid -= gratuity
        else:
            user.amount_owed -= subtotal
            user.tax_owed -= tax
            user.gratuity_owed -= gratuity

    user.amount_spent = max(0, user.amount_spent)
    user.amount_owed = max(0, user.amount_owed)
    user.tax_owed = max(0, user.tax_owed)
    user.tax_paid = max(0, user.tax_paid)
    user.gratuity_owed = max(0, user.gratuity_owed)
    user.gratuity_paid = max(0, user.gratuity_paid)

    db.session.commit()

    flash('Order deleted and balances updated.', 'success')
    return redirect(url_for('view_member', user_id=user.id))




@app.route('/toggle_order_paid/<int:order_id>')
def toggle_order_paid(order_id):
    if session.get('role') != 'admin':
        return redirect(url_for('home'))

    order = Order.query.get_or_404(order_id)
    user = order.user

    if order.paid_by_credit:
        # Revert payment: move back to owed
        user.amount_spent -= order.total
        user.tax_paid -= order.tax
        user.gratuity_paid -= order.gratuity

        user.amount_owed += order.subtotal
        user.tax_owed += order.tax
        user.gratuity_owed += order.gratuity

        order.paid_by_credit = False
    else:
        # Mark as paid: move owed to paid
        user.amount_spent += order.total
        user.tax_paid += order.tax
        user.gratuity_paid += order.gratuity

        user.amount_owed -= order.subtotal
        user.tax_owed -= order.tax
        user.gratuity_owed -= order.gratuity

        order.paid_by_credit = True

    # Prevent negatives
    user.amount_spent = max(0, user.amount_spent)
    user.amount_owed = max(0, user.amount_owed)
    user.tax_owed = max(0, user.tax_owed)
    user.tax_paid = max(0, user.tax_paid)
    user.gratuity_owed = max(0, user.gratuity_owed)
    user.gratuity_paid = max(0, user.gratuity_paid)

    db.session.commit()
    return redirect(url_for('view_member', user_id=user.id))











@app.route('/edit_member/<int:user_id>', methods=['GET', 'POST'])
def edit_member(user_id):
    user = User.query.get_or_404(user_id)

    if request.method == 'POST':
        user.first_name = request.form['first_name']
        user.last_name = request.form['last_name']
        user.username = request.form['username']
        user.email = request.form['email']
        user.member_number = request.form['member_number']
        user.membership_type = request.form['membership_type']

        # Handle optional password change
        new_password = request.form.get('password')
        if new_password:
            user.password = generate_password_hash(new_password)

        db.session.commit()
        flash('Member updated successfully.', 'success')
        return redirect(url_for('view_member', user_id=user.id))

    return render_template('edit_member.html', member=user)





@app.route('/delete_member/<int:user_id>', methods=['POST'])
def delete_member(user_id):
    if not session.get('user_id') or session.get('role') != 'admin':
        return redirect(url_for('login'))

    user = User.query.get_or_404(user_id)

    # Just delete the user from your app (no Stripe)
    db.session.delete(user)
    db.session.commit()

    flash("Member deleted successfully.", "success")
    return redirect(url_for('manage_members'))



@app.route('/member/<int:user_id>')
def view_member(user_id):
    if not session.get('user_id'):
        return redirect(url_for('login'))

    member = User.query.get_or_404(user_id)

    # Only allow access if admin or the user themself
    if session.get('role') != 'admin' and session['user_id'] != member.id:
        return redirect(url_for('home'))

    reservations = Reservation.query.filter_by(user_id=member.id).all()
    orders = Order.query.filter_by(user_id=member.id).order_by(Order.date.desc()).all()
    invoices = Invoice.query.filter_by(member_id=member.id).order_by(Invoice.date_created.desc()).all()

    is_admin = session.get('role') == 'admin'

    return render_template(
        'member_profile.html',
        member=member,
        user=member,
        reservations=reservations,
        orders=orders,
        invoices=invoices,
        is_admin=is_admin
    )






@app.route('/add-note/<int:user_id>', methods=['POST'])
def add_note(user_id):
    if session.get('role') != 'admin':
        return redirect(url_for('home'))

    content = request.form['note']
    note = Note(content=content, member_id=user_id, author_id=session['user_id'])
    db.session.add(note)
    db.session.commit()
    return redirect(url_for('view_member', user_id=user_id))

@app.route('/edit_note/<int:note_id>', methods=['GET', 'POST'])
def edit_note(note_id):
    if not session.get('user_id'):
        return redirect(url_for('login'))

    note = Note.query.get_or_404(note_id)

    if request.method == 'POST':
        note.content = request.form['content']
        db.session.commit()
        flash('Note updated.')
        return redirect(url_for('view_member', user_id=note.member_id))

    return render_template('edit_note.html', note=note)


@app.route('/delete_note/<int:note_id>', methods=['POST'])
def delete_note(note_id):
    if not session.get('user_id'):
        return redirect(url_for('login'))

    note = Note.query.get_or_404(note_id)
    member_id = note.member_id
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
        # Convert string date to date object if necessary
        if isinstance(event.date, str):
            try:
                event.date = datetime.strptime(event.date, '%Y-%m-%d').date()
            except:
                pass

        # Convert string time to time object if necessary
        if isinstance(event.time, str):
            try:
                event.time = datetime.strptime(event.time, '%H:%M:%S').time()
            except:
                try:
                    event.time = datetime.strptime(event.time, '%H:%M').time()
                except:
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
    if session.get('role') != 'admin':
        return redirect(url_for('events'))

    if request.method == 'POST':
        name = request.form['name']
        date = request.form['date']
        time = request.form['time']
        description = request.form['description']
        

        event = Event(name=name, date=date, time=time, description=description)
        db.session.add(event)
        db.session.commit()
        return redirect(url_for('events'))

    return render_template('add_event.html')

@app.route('/admin/events', methods=['GET', 'POST'])
def admin_events():
    if session.get('role') != 'admin':
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

    # Convert string times to datetime.time objects if necessary
    for event in events:
        if isinstance(event.time, str):
            try:
                event.time = datetime.strptime(event.time, "%H:%M:%S").time()
            except ValueError:
                try:
                    event.time = datetime.strptime(event.time, "%H:%M").time()
                except ValueError:
                    pass  # Leave as-is if parsing fails

    return render_template('admin_events.html', events=events)

@app.route('/admin/events/edit/<int:event_id>', methods=['GET', 'POST'])
def edit_event(event_id):
    if session.get('role') != 'admin':
        return redirect(url_for('home'))
    
    event = Event.query.get_or_404(event_id)
    
    if request.method == 'POST':
        event.name = request.form['name']
        event.date = request.form['date']
        event.time = request.form['time']
        event.description = request.form['description']
        db.session.commit()
        return redirect(url_for('admin_events'))

    return render_template('edit_event.html', event=event)

@app.route("/delete_event/<int:event_id>", methods=["POST"])
def delete_event(event_id):
    event = Event.query.get_or_404(event_id)

    # Delete all reservations FIRST
    SeatingReservation.query.filter_by(event_id=event_id).delete()

    db.session.delete(event)
    db.session.commit()

    return redirect(url_for("events_page"))


@app.route('/generate_invoice/<int:order_id>', methods=['POST'])
def generate_invoice(order_id):
    if not session.get('user_id') or session.get('role') != 'admin':
        return redirect(url_for('login'))

    order = Order.query.get_or_404(order_id)
    member = order.user

    # Create a new invoice from the order
    invoice = Invoice(
        member_id=member.id,
        original_filename="Generated from Order",
        stored_filename="generated_order_invoice",
        date_created=datetime.utcnow(),
        total_amount=order.total,
        tax_amount=order.tax,
        notes=order.notes
    )

    # Add line items from the order
    for item in order.items:
        line_item = InvoiceLineItem(
            description=item.item_name,
            amount=item.price
        )
        invoice.line_items.append(line_item)

    # Update member balances
    member.amount_owed += order.subtotal
    member.tax_owed += order.tax
    member.gratuity_owed += order.gratuity

    db.session.add(invoice)
    db.session.commit()

    flash('Invoice generated successfully.', 'success')
    return redirect(url_for('view_member', user_id=member.id))


@app.route('/members_table')
def members_table():
    if session.get('role') != 'admin':
        return redirect(url_for('home'))

    members = User.query.filter_by(role='member').all()
    return render_template('members_table.html', members=members)


# ...existing code...

@app.route('/update_member/<int:member_id>', methods=['POST'])
def update_member(member_id):
    if session.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    member = User.query.get_or_404(member_id)
    data = request.json

    try:
        for field, value in data.items():
            if hasattr(member, field):
                setattr(member, field, value if field != 'active' else value == 'True')
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/update_members', methods=['POST'])
def update_members():
    if session.get('role') != 'admin':
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
    if session.get('role') != 'admin':
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
    if session.get('role') != 'admin':
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
# Run it
# ----------------------
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)

