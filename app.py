from flask import (
    Flask, render_template, render_template_string, request,
    redirect, url_for, session, flash, send_from_directory, abort
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from models import db, User, Recharge
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
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///users.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Secret key and DB config
app.secret_key = os.environ.get("SECRET_KEY", "dev_secret")

# Initialize DB + migrations
db.init_app(app)
migrate = Migrate(app, db)

# -------------------------
# Helpers
# -------------------------
ALLOWED_IMAGE_EXT = (".png", ".jpg", ".jpeg", ".gif")

def get_current_user():
    """Return the logged-in User object or None."""
    user_id = session.get("user_id")
    if not user_id:
        return None
    return User.query.get(user_id)

def allowed_file(filename):
    return filename and filename.lower().endswith(ALLOWED_IMAGE_EXT)

def login_required(redirect_endpoint="login"):
    """Decorator to protect routes that require authentication."""
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not session.get("user_id"):
                flash("Please log in to access that page.", "warning")
                return redirect(url_for(redirect_endpoint))
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

@app.route("/recharge", methods=["POST"])
@login_required()
def recharge():
    user = get_current_user()
    amount = request.form.get("amount")
    provider = request.form.get("provider")
    transaction_id = request.form.get("transaction_id")
    screenshot_file = request.files.get("screenshot")

    filename = None
    if screenshot_file:
        filename = secure_filename(screenshot_file.filename)
        screenshot_file.save(os.path.join("static/uploads", filename))

    new_recharge = Recharge(
        user_id=user.id,
        amount=int(amount),
        provider=provider,
        transaction_id=transaction_id,
        screenshot_filename=filename,
        status="pending"
    )
    db.session.add(new_recharge)
    db.session.commit()

    return {"message": "Request for recharge sent. Your account will be credited shortly."}

@app.route("/team")
def team():
    return render_template("team.html")
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

@app.route("/recharge", methods=["GET"])
@login_required()
def show_recharge():
    return render_template("recharge.html")


@app.route("/admin/recharges")
@login_required()
def admin_recharges():
    # Get all recharge requests, newest first
    recharges = Recharge.query.order_by(Recharge.created_at.desc()).all()
    return render_template("admin_recharges.html", recharges=recharges)

@app.route("/admin/recharges/<int:recharge_id>/confirm", methods=["POST"])
@login_required()
def confirm_recharge(recharge_id):
    recharge = Recharge.query.get_or_404(recharge_id)
    recharge.status = "confirmed"
    recharge.user.wallet_balance += recharge.amount
    db.session.commit()
    flash(f"Recharge {recharge.transaction_id} confirmed for {recharge.user.email}", "success")
    return redirect(url_for("admin_recharges"))

@app.route("/admin/recharges/<int:recharge_id>/reject", methods=["POST"])
@login_required()
def reject_recharge(recharge_id):
    recharge = Recharge.query.get_or_404(recharge_id)
    recharge.status = "rejected"
    db.session.commit()
    flash(f"Recharge {recharge.transaction_id} rejected for {recharge.user.email}", "danger")
    return redirect(url_for("admin_recharges"))

@app.route("/recharge", methods=["POST"])
@login_required()
def submit_recharge():
    user = get_current_user()
    amount = request.form.get("amount")
    provider = request.form.get("provider")
    transaction_id = request.form.get("transaction_id")
    screenshot_file = request.files.get("screenshot")

    filename = None
    if screenshot_file:
        from werkzeug.utils import secure_filename
        import os
        filename = secure_filename(screenshot_file.filename)
        upload_folder = os.path.join(app.root_path, "static", "uploads")
        os.makedirs(upload_folder, exist_ok=True)
        screenshot_file.save(os.path.join(upload_folder, filename))

    new_recharge = Recharge(
        user_id=user.id,
        amount=int(amount),
        provider=provider,
        transaction_id=transaction_id,
        screenshot_filename=filename,
        status="pending"
    )
    db.session.add(new_recharge)
    db.session.commit()

    flash("Recharge request submitted successfully! Pending admin approval.", "success")
    return redirect(url_for("dashboard"))

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
    recharges=Recharge.query.filter_by(user_id=user.id).order_by(Recharge.created_at.desc()).all()
    return render_template("dashboard.html", user=user, recharges=recharges)

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