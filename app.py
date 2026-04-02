# app.py
from flask import (
    Flask, render_template, render_template_string, request,
    redirect, url_for, session, flash, send_from_directory, abort
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from models import db, User
import random
import os
import traceback
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from flask_migrate import Migrate
from functools import wraps

# -------------------------
# App setup
# -------------------------
app = Flask(__name__, static_folder="static", template_folder="templates")

# Secret key and DB config
app.secret_key = os.environ.get("SECRET_KEY", "dev_secret")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///users.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Uploads folder for user images (profile proofs, PNGs you mentioned)
UPLOAD_FOLDER = os.path.join(app.root_path, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
ALLOWED_IMAGE_EXT = (".png", ".jpg", ".jpeg", ".gif")

# Initialize DB + migrations
db.init_app(app)
migrate = Migrate(app, db)

# -------------------------
# Helpers
# -------------------------
def get_current_user():
    """Return the logged-in User object or None."""
    user_id = session.get("user_id")
    if not user_id:
        return None
    return User.query.get(user_id)

def allowed_file(filename):
    return filename and filename.lower().endswith(ALLOWED_IMAGE_EXT)

def login_required(redirect_endpoint="login"):
    """
    Decorator to protect routes that require authentication.
    If the user is not logged in, redirect to the login page.
    """
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not session.get("user_id"):
                flash("Please log in to access that page.", "warning")
                return redirect(url_for(redirect_endpoint))
            # Optionally verify the user still exists
            user = get_current_user()
            if not user:
                session.clear()
                flash("Session invalid. Please log in again.", "error")
                return redirect(url_for(redirect_endpoint))
            return f(*args, **kwargs)
        return wrapped
    return decorator

# -------------------------
# Public / Landing
# -------------------------
@app.route("/")
def landing():
    """
    Public landing page.
    Always render landing.html for both guests and logged-in users.
    Logged-in users will see a 'Go to Dashboard' button on the landing page.
    """
    try:
        logged_in = bool(session.get("user_id"))
        return render_template("landing.html", logged_in=logged_in)
    except Exception as e:
        print("ERROR rendering landing.html:", e)
        traceback.print_exc()
        return render_template_string("""
            <h1>Welcome</h1>
            {% if logged_in %}
              <p>You are logged in. <a href="{{ url_for('dashboard') }}">Go to Dashboard</a></p>
            {% else %}
              <p><a href="{{ url_for('register') }}">Register</a> · <a href="{{ url_for('login') }}">Login</a></p>
            {% endif %}
        """, logged_in=bool(session.get("user_id")))

@app.route("/home")
def home():
    """
    Home route used by navigation:
    - If logged in -> dashboard
    - If not -> landing
    """
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    return redirect(url_for("landing"))

# -------------------------
# Static-like pages
# -------------------------
@app.route("/features")
def features():
    return render_template("features.html")

@app.route("/product")
def product():
    sample_products = [
        {"name": "MetaEarn 1", "sku": "ME1", "price": "KSh100"},
        {"name": "MetaEarn 10", "sku": "ME10", "price": "KSh900"},
    ]
    return render_template("product.html", products=sample_products)

@app.route("/financial")
@login_required()
def financial():
    user = get_current_user()
    available_balance = f"KSh{user.wallet_balance:.2f}" if getattr(user, "wallet_balance", None) is not None else "KSh0.00"
    total_withdraw = f"KSh{getattr(user, 'total_withdraw', 0):.2f}"
    total_recharge = f"KSh{getattr(user, 'total_recharge', 0):.2f}"
    return render_template("financial.html",
                           available_balance=available_balance,
                           total_withdraw=total_withdraw,
                           total_recharge=total_recharge,
                           user=user)

@app.route("/team")
def team():
    return render_template("team.html")

# -------------------------
# Authentication: Register / Verify / Login / Logout
# -------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        profile_file = request.files.get("profile")  # optional PNG upload

        if not email or not password:
            flash("Please provide email and password.", "error")
            return redirect(url_for("register"))

        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash("Email already registered. Please log in.", "error")
            return redirect(url_for("login"))

        hashed_pw = generate_password_hash(password)
        new_user = User(
            email=email,
            password=hashed_pw,
            wallet_balance=0.0,
            total_views=0,
            total_earnings=0.0
        )

        # Save profile image if provided
        if profile_file and allowed_file(profile_file.filename):
            filename = secure_filename(profile_file.filename)
            save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            profile_file.save(save_path)
            if hasattr(new_user, "profile_image"):
                new_user.profile_image = filename

        db.session.add(new_user)
        db.session.commit()

        # Generate OTP and store pending info in session
        otp = str(random.randint(100000, 999999))
        session["otp"] = otp
        session["pending_user_id"] = new_user.id
        session["pending_email"] = email

        # Send OTP via SendGrid (best-effort)
        try:
            message = Mail(
                from_email="metarearn@gmail.com",
                to_emails=email,
                subject="MetaEarn OTP Verification",
                html_content=f"<h3>Your OTP code is <b>{otp}</b></h3>"
            )
            sg = SendGridAPIClient(os.environ.get("SENDGRID_API_KEY"))
            sg.send(message)
            flash("OTP sent to your email. Please verify.")
        except Exception as e:
            print("SendGrid error:", e)
            flash("Could not send OTP email. Check server logs.", "warning")

        return redirect(url_for("verify"))

    return render_template("register.html")

@app.route("/verify", methods=["GET", "POST"])
def verify():
    if request.method == "POST":
        entered_otp = request.form.get("otp", "").strip()
        if entered_otp and entered_otp == session.get("otp"):
            session["user_id"] = session.get("pending_user_id")
            session.pop("otp", None)
            session.pop("pending_user_id", None)
            session.pop("pending_email", None)
            flash("OTP verified. You are now logged in.")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid OTP. Try again.", "error")
    return render_template("verify.html")

@app.route("/resend_otp", methods=["POST"])
def resend_otp():
    email = session.get("pending_email")
    if not email:
        flash("No pending registration found. Please register again.", "error")
        return redirect(url_for("register"))

    otp = str(random.randint(100000, 999999))
    session["otp"] = otp
    try:
        message = Mail(
            from_email="metarearn@gmail.com",
            to_emails=email,
            subject="MetaEarn OTP Resend",
            html_content=f"<h3>Your new OTP code is <b>{otp}</b></h3>"
        )
        sg = SendGridAPIClient(os.environ.get("SENDGRID_API_KEY"))
        sg.send(message)
        flash("New OTP sent. Check your inbox.")
    except Exception as e:
        print("SendGrid resend error:", e)
        flash("Could not resend OTP. Check server logs.", "warning")
    return redirect(url_for("verify"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            session["user_id"] = user.id
            flash("Welcome back!", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid credentials", "error")
    return render_template("login.html")

@app.route("/logout", methods=["GET", "POST"])
def logout():
    """
    Clear session and redirect to landing.
    Prefer POST from UI; GET is allowed for convenience.
    """
    session.clear()
    flash("You have been logged out.")
    return redirect(url_for("landing"))

# -------------------------
# Dashboard & user actions
# -------------------------
@app.route("/dashboard")
@login_required()
def dashboard():
    """
    Private dashboard. Requires login via @login_required.
    """
    user = get_current_user()
    # Prepare safe subscription list for template
    subs = []
    if hasattr(user, "subscriptions") and user.subscriptions:
        try:
            subs = list(user.subscriptions)
        except Exception:
            subs = user.subscriptions or []

    products = [
        {"name": "MetaEarn 1", "sku": "ME1", "price": "KSh100"},
        {"name": "MetaEarn 10", "sku": "ME10", "price": "KSh900"},
    ]

    available_balance = f"KSh{user.wallet_balance:.2f}" if getattr(user, "wallet_balance", None) is not None else "KSh0.00"

    try:
        return render_template("dashboard.html",
                               user=user,
                               subs=subs,
                               products=products,
                               available_balance=available_balance)
    except Exception as e:
        print("TEMPLATE ERROR while rendering dashboard.html:")
        traceback.print_exc()
        return render_template_string("""
            <h1>Dashboard rendering error</h1>
            <pre>{{ err }}</pre>
            <p>Check server console for full traceback.</p>
        """, err=str(e)), 500

@app.route("/upload_views", methods=["POST"])
@login_required()
def upload_views():
    user = get_current_user()
    if not user:
        flash("User not found. Please log in again.", "error")
        return redirect(url_for("login"))

    try:
        views = int(request.form.get("views", 0))
    except Exception:
        flash("Invalid views value.", "error")
        return redirect(url_for("dashboard"))

    earnings = views * 0.025
    user.total_views = getattr(user, "total_views", 0) + views
    user.total_earnings = getattr(user, "total_earnings", 0.0) + earnings
    user.wallet_balance = getattr(user, "wallet_balance", 0.0) + earnings
    db.session.commit()

    if "proof" in request.files:
        file = request.files["proof"]
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

    flash(f"{views} views recorded. KSh{earnings:.2f} added to your wallet.", "success")
    return redirect(url_for("dashboard"))

# -------------------------
# Mine page (balances)
# -------------------------
@app.route("/mine")
@login_required()
def mine():
    user = get_current_user()
    context = {
        "available_balance": f"KSh{user.wallet_balance:.2f}",
        "total_withdraw": f"KSh{getattr(user, 'total_withdraw', 0):.2f}",
        "total_recharge": f"KSh{getattr(user, 'total_recharge', 0):.2f}",
        "user": user
    }
    return render_template("mine.html", **context)

# -------------------------
# Serve uploaded files
# -------------------------
@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

# -------------------------
# Error handlers
# -------------------------
@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404

# -------------------------
# Run (development)
# -------------------------
if __name__ == "__main__":
    app.run(debug=True)