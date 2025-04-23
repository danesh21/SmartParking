from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_socketio import SocketIO, emit
import paho.mqtt.client as mqtt
import json
import time
import os
from datetime import datetime, timedelta
from functools import wraps
from sqlalchemy import inspect
import logging

# Configure logging to help debug database issues
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create the Flask application
app = Flask(__name__)
app.config['SECRET_KEY'] = "smart_parking_secret"
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///smart_parking.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Import models after app is created to avoid circular imports
from models import db, User, Reservation, ParkingSlot, Notification

# Initialize database with app
db.init_app(app)

# Initialize SocketIO
socketio = SocketIO(app, cors_allowed_origins="*")

# MQTT Configuration
MQTT_BROKER = "broker.emqx.io"
MQTT_PORT = 1883
PUBLISH_TOPIC = "parking/reservations"
SUBSCRIBE_TOPIC = "parking/status"

# MQTT Client
mqtt_client = mqtt.Client()
mqtt_connected = False

# Ensure static folder exists
os.makedirs(os.path.join(app.static_folder, 'images'), exist_ok=True)

# MQTT Callback functions
def on_connect(client, userdata, flags, rc):
    global mqtt_connected
    if rc == 0:
        print("Connected to MQTT broker!")
        mqtt_connected = True
        client.subscribe(SUBSCRIBE_TOPIC)
    else:
        print(f"Failed to connect to MQTT broker with code: {rc}")
        mqtt_connected = False

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        if "slots" in payload:
            for slot in payload["slots"]:
                slot_id = slot["id"]
                status = slot["status"]
                
                # Update database
                with app.app_context():
                    parking_slot = ParkingSlot.query.get(slot_id)
                    if parking_slot:
                        parking_slot.status = status
                        parking_slot.last_updated = datetime.utcnow()
                    else:
                        parking_slot = ParkingSlot(id=slot_id, status=status)
                        db.session.add(parking_slot)
                    db.session.commit()
                    
            # Emit WebSocket event with updated parking data
            slots_data = [{"id": s.id, "status": s.status} for s in ParkingSlot.query.all()]
            socketio.emit('parking_update', {"slots": slots_data})
            print("Updated parking slots from MQTT")
    except Exception as e:
        print(f"Error processing MQTT message: {e}")

mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

# Authentication decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Admin-only decorator
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page', 'danger')
            return redirect(url_for('login'))
        
        user = User.query.get(session['user_id'])
        if not user or not user.is_admin:
            flash('You do not have permission to access this page', 'danger')
            return redirect(url_for('dashboard'))
            
        return f(*args, **kwargs)
    return decorated_function

@app.route("/", methods=["GET"])
def home():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['is_admin'] = user.is_admin
            session['username'] = user.username
            
            if user.is_admin:
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid credentials. Please try again.", "danger")
            
    return render_template("index.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        name = request.form.get("name")
        email = request.form.get("email")
        phone = request.form.get("phone")
        
        # Check if username or email already exists
        if User.query.filter_by(username=username).first():
            flash("Username already exists", "danger")
            return redirect(url_for('register'))
            
        if email and User.query.filter_by(email=email).first():
            flash("Email already exists", "danger")
            return redirect(url_for('register'))
        
        # Create new user
        new_user = User(username=username, name=name, email=email, phone=phone)
        new_user.set_password(password)
        
        db.session.add(new_user)
        db.session.commit()
        
        flash("Registration successful! Please log in.", "success")
        return redirect(url_for('login'))
        
    return render_template("register.html")

@app.route("/dashboard")
@login_required
def dashboard():
    user_id = session.get('user_id')
    
    # Get parking slots from database
    parking_slots = ParkingSlot.query.all()
    
    # If no slots exist in DB yet, initialize with default 5 slots
    if not parking_slots:
        for i in range(5):
            slot = ParkingSlot(id=i, status=0)
            db.session.add(slot)
        db.session.commit()
        parking_slots = ParkingSlot.query.all()
    
    # Get user's active reservations
    user_reservations = Reservation.query.filter_by(
        user_id=user_id, 
        status='active'
    ).all()
    
    # Get user's unread notifications
    notifications = Notification.query.filter_by(
        user_id=user_id,
        is_read=False
    ).all()
    
    return render_template("dashboard.html", 
                          slots=parking_slots, 
                          user_reservations=user_reservations,
                          notifications=notifications)

@app.route("/notifications")
@login_required
def view_notifications():
    user_id = session.get('user_id')
    
    # Get all user notifications
    notifications = Notification.query.filter_by(
        user_id=user_id
    ).order_by(Notification.created_at.desc()).all()
    
    # Mark notifications as read
    for notification in notifications:
        if not notification.is_read:
            notification.is_read = True
    
    db.session.commit()
    
    return render_template("notifications.html", notifications=notifications)

@app.route("/mark_notification_read/<int:notification_id>")
@login_required
def mark_notification_read(notification_id):
    notification = Notification.query.get(notification_id)
    
    if notification and notification.user_id == session.get('user_id'):
        notification.is_read = True
        db.session.commit()
    
    return redirect(url_for('dashboard'))

@app.route("/reserve", methods=["POST"])
@login_required
def reserve():
    user_id = session.get("user_id")
    slot_id = int(request.form.get("slot_id"))
    
    # Check if slot is available
    slot = ParkingSlot.query.get(slot_id)
    if not slot or slot.status != 0:
        flash("This parking spot is no longer available.", "danger")
        return redirect(url_for("dashboard"))
    
    # Create reservation record
    reservation = Reservation(
        parking_spot=slot_id,
        user_id=user_id,
        date=datetime.utcnow().date(),
        time_in=datetime.utcnow(),
        status="active"
    )
    
    # Update slot status to reserved
    slot.status = 2  # Reserved
    
    try:
        db.session.add(reservation)
        db.session.commit()
        
        # Publish to MQTT if connected
        if mqtt_connected:
            try:
                mqtt_client.publish(PUBLISH_TOPIC, json.dumps({
                    "slot": slot_id, 
                    "user_id": user_id,
                    "status": 2  # Reserved
                }))
                flash(f"Slot {slot_id + 1} reserved successfully!", "success")
                
                # Emit the update via WebSocket
                slots_data = [{"id": s.id, "status": s.status} for s in ParkingSlot.query.all()]
                socketio.emit('parking_update', {"slots": slots_data})
            except Exception as e:
                flash(f"Reserved locally but couldn't publish to MQTT: {e}", "warning")
        else:
            flash(f"Slot {slot_id + 1} reserved locally. MQTT connection is down.", "warning")
            
    except Exception as e:
        db.session.rollback()
        flash(f"Error creating reservation: {e}", "danger")
    
    return redirect(url_for("dashboard"))

@app.route("/cancel_reservation/<int:reservation_id>", methods=["POST"])
@login_required
def cancel_reservation(reservation_id):
    reservation = Reservation.query.get(reservation_id)
    
    if not reservation or reservation.user_id != session.get('user_id'):
        flash("Invalid reservation or unauthorized access", "danger")
        return redirect(url_for("dashboard"))
    
    # Update reservation status
    reservation.status = "cancelled"
    
    # Update slot status back to empty
    slot = ParkingSlot.query.get(reservation.parking_spot)
    if slot:
        slot.status = 0  # Empty
    
    try:
        db.session.commit()
        
        # Publish to MQTT if connected
        if mqtt_connected and slot:
            mqtt_client.publish(PUBLISH_TOPIC, json.dumps({
                "slot": slot.id, 
                "user_id": session.get('user_id'),
                "status": 0  # Empty
            }))
            
        flash("Reservation cancelled successfully", "success")
        
        # Emit the update via WebSocket
        slots_data = [{"id": s.id, "status": s.status} for s in ParkingSlot.query.all()]
        socketio.emit('parking_update', {"slots": slots_data})
    except Exception as e:
        db.session.rollback()
        flash(f"Error cancelling reservation: {e}", "danger")
    
    return redirect(url_for("dashboard"))

@app.route("/admin")
@admin_required
def admin_dashboard():
    # Get all users
    users = User.query.all()
    
    # Get all active reservations
    reservations = Reservation.query.order_by(Reservation.created_at.desc()).all()
    
    # Get all parking slots
    parking_slots = ParkingSlot.query.all()
    
    return render_template("admin_dashboard.html", 
                          users=users, 
                          reservations=reservations,
                          slots=parking_slots)

@app.route("/admin/user/add", methods=["GET", "POST"])
@admin_required
def admin_add_user():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        name = request.form.get("name")
        email = request.form.get("email")
        phone = request.form.get("phone")
        is_admin = "is_admin" in request.form
        
        # Check if username or email already exists
        if User.query.filter_by(username=username).first():
            flash("Username already exists", "danger")
            return redirect(url_for('admin_add_user'))
            
        if email and User.query.filter_by(email=email).first():
            flash("Email already exists", "danger")
            return redirect(url_for('admin_add_user'))
        
        # Create new user
        new_user = User(
            username=username, 
            name=name, 
            email=email, 
            phone=phone,
            is_admin=is_admin
        )
        new_user.set_password(password)
        
        db.session.add(new_user)
        db.session.commit()
        
        flash("User added successfully!", "success")
        return redirect(url_for('admin_dashboard'))
        
    return render_template("admin_add_user.html")

@app.route("/admin/user/delete/<int:user_id>", methods=["POST"])
@admin_required
def admin_delete_user(user_id):
    user = User.query.get(user_id)
    
    if not user:
        flash("User not found", "danger")
        return redirect(url_for("admin_dashboard"))
    
    # Delete user's reservations
    Reservation.query.filter_by(user_id=user_id).delete()
    
    # Delete user's notifications
    Notification.query.filter_by(user_id=user_id).delete()
    
    # Delete user
    db.session.delete(user)
    db.session.commit()
    
    flash("User and their reservations deleted successfully", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/reservation/cancel/<int:reservation_id>", methods=["POST"])
@admin_required
def admin_cancel_reservation(reservation_id):
    reservation = Reservation.query.get(reservation_id)
    
    if not reservation:
        flash("Reservation not found", "danger")
        return redirect(url_for("admin_dashboard"))
    
    # Update reservation status
    reservation.status = "cancelled"
    
    # Update slot status back to empty
    slot = ParkingSlot.query.get(reservation.parking_spot)
    if slot and slot.status == 2:  # Only if it's still in reserved state
        slot.status = 0  # Empty
    
    # Create notification for the user
    notification = Notification(
        user_id=reservation.user_id,
        message=f"Your reservation for Slot {reservation.parking_spot + 1} has been cancelled by an administrator. Please contact support for more information.",
        type="reservation_cancelled",
        is_read=False
    )
    
    db.session.add(notification)
    db.session.commit()
    
    # Publish to MQTT if connected
    if mqtt_connected and slot and slot.status == 0:
        mqtt_client.publish(PUBLISH_TOPIC, json.dumps({
            "slot": slot.id, 
            "status": 0  # Empty
        }))
    
    flash("Reservation cancelled successfully and user notified", "success")
    
    # Emit the update via WebSocket
    slots_data = [{"id": s.id, "status": s.status} for s in ParkingSlot.query.all()]
    socketio.emit('parking_update', {"slots": slots_data})
    
    # Emit notification to the specific user if they're online
    socketio.emit('new_notification', {
        "message": notification.message,
        "id": notification.id
    }, room=f"user_{reservation.user_id}")
    
    return redirect(url_for("admin_dashboard"))

@app.route("/api/slots", methods=["GET"])
def get_slots():
    slots = ParkingSlot.query.all()
    slots_data = [{"id": slot.id, "status": slot.status} for slot in slots]
    return jsonify({"slots": slots_data})

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# Add a route to manually simulate parking status changes (for testing)
@app.route("/simulate/<int:slot_id>/<int:status>")
@admin_required
def simulate(slot_id, status):
    if 0 <= status <= 2:
        slot = ParkingSlot.query.get(slot_id)
        
        if not slot:
            slot = ParkingSlot(id=slot_id, status=status)
            db.session.add(slot)
        else:
            slot.status = status
            
        db.session.commit()
        
        # Emit slot update
        slots_data = [{"id": s.id, "status": s.status} for s in ParkingSlot.query.all()]
        socketio.emit('parking_update', {"slots": slots_data})
        
        return f"Updated slot {slot_id} to status {status}"
    return "Invalid request", 400

# Socket.IO event handlers
@socketio.on('connect')
def handle_connect():
    if 'user_id' in session:
        # Join a room specific to this user
        user_id = session['user_id']
        socketio.emit('join', {'room': f'user_{user_id}'})

# Create database tables and admin user function
def create_database():
    with app.app_context():
        logger.info("Creating database tables...")
        
        # Check if database file exists and create database tables
        db.create_all()
        
        # Verify tables were created
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        logger.info(f"Tables created: {tables}")
        
        # Create admin user if not exists
        admin = User.query.filter_by(username="admin").first()
        if not admin:
            admin = User(username="admin", name="Administrator", is_admin=True)
            admin.set_password("admin123")
            db.session.add(admin)
            db.session.commit()
            logger.info("Admin user created successfully")
        else:
            logger.info("Admin user already exists")

# For direct execution
if __name__ == "__main__":
    # Create the database and admin user right at startup
    create_database()
    
    # Try to connect to MQTT
    try:
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_start()
        print("Started MQTT client loop")
    except Exception as e:
        print(f"MQTT connection failed: {e}")
        print("Flask will run without MQTT functionality")

    # Run Flask with SocketIO
    print("Starting Flask-SocketIO server on 0.0.0.0:5000")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)
