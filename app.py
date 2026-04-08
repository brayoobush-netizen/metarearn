from flask import (
    Flask, render_template, render_template_string, request,
    redirect, url_for, session, flash, send_from_directory, abort
)
from datetime import datetime, timedelta
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from flask_migrate import Migrate
from flask_login import LoginManager, current_user, login_required, login_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from models import db, User, Recharge, Withdrawal
import random
import os
import traceback
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

# -------------------------
# App setup
# -------------------------
app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///users.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = os.environ.get("SECRET_KEY", "dev_secret")

db.init_app(app)
migrate = Migrate(app, db)

with app.app_context():
    db.create_all()

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# -------------------------
# Helpers
# -------------------------
ALLOWED_IMAGE_EXT = (".png", ".jpg", ".jpeg", ".gif")

def get_current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return User.query.get(user_id)

def allowed_file(filename):
    return filename and filename.lower().endswith(ALLOWED_IMAGE_EXT)

# -------------------------
# Public / Landing
# -------------------------
@app.route("/")
def landing():
    try:
        logged_in = bool(session.get("user_id"))
        return render_template("landing.html", logged_in=logged_in)
    except Exception as e:
        traceback.print_exc()
        return render_template_string("""
            <h1>Welcome</h1>
            {% if logged_in %}
              <p>You are logged in. <a href="{{ url_for('dashboard') }}">Go to Dashboard</a></p>
            {% else %}
              <p><a href="{{ url_for('register') }}">Register</a> · <a href="{{ url_for('login') }}">Login</a></p>
            {% endif %}
        """, logged_in=bool(session.get("user_id")))

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

@app.route("/team")
def team():
    return render_template("team.html")

@app.route("/home")
def home():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    return redirect(url_for("landing"))

# -------------------------
# Authentication
# -------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        profile_file = request.files.get("profile")

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

        if profile_file and allowed_file(profile_file.filename):
            filename = secure_filename(profile_file.filename)
            upload_folder = os.path.join(app.root_path, "static", "uploads")
            os.makedirs(upload_folder, exist_ok=True)
            profile_file.save(os.path.join(upload_folder, filename))
            if hasattr(new_user, "profile_image"):
                new_user.profile_image = filename

        db.session.add(new_user)
        db.session.commit()

        otp = str(random.randint(100000, 999999))
        session["otp"] = otp
        session["pending_user_id"] = new_user.id
        session["pending_email"] = email

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
            login_user(user)  # <-- this tells Flask-Login you’re authenticated
            flash("Welcome back!", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid credentials", "error")
            return redirect(url_for("login"))

    return render_template("login.html")

@app.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()
    flash("You have been logged out.")
    return redirect(url_for("landing"))

# -------------------------
# Recharge
# -------------------------
@app.route("/recharge", methods=["GET", "POST"])
@login_required
def recharge():
    user = current_user

    if request.method == "POST":
        amount = request.form.get("amount")
        provider = request.form.get("provider")
        transaction_id = request.form.get("transaction_id")
        screenshot_file = request.files.get("screenshot")

        filename = None
        if screenshot_file:
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

        flash("Recharge request submitted successfully! Pending admin approval.", "recharge")

        # ✅ Redirect after POST to avoid duplicate submissions
        return redirect(url_for("recharge"))

    # Calculate today's recharge (last 24 hours, confirmed only)
    now = datetime.utcnow()
    last_24h = now - timedelta(hours=24)
    todays_recharge = db.session.query(func.sum(Recharge.amount)).filter(
        Recharge.user_id == user.id,
        Recharge.status == "confirmed",
        Recharge.created_at >= last_24h
    ).scalar() or 0

    # Calculate total confirmed recharge (all time)
    total_recharge = db.session.query(func.sum(Recharge.amount)).filter(
        Recharge.user_id == user.id,
        Recharge.status == "confirmed"
    ).scalar() or 0

    # Only show this user's recharges
    recharges = Recharge.query.filter_by(user_id=user.id).order_by(Recharge.created_at.desc()).all()

    return render_template(
        "recharge.html",
        user=user,
        recharges=recharges,
        todays_recharge=todays_recharge,
        total_recharge=total_recharge
    )

@app.route("/admin/recharges")
@login_required
def admin_recharges():
    recharges = Recharge.query.order_by(Recharge.created_at.desc()).all()
    return render_template("admin_recharges.html", recharges=recharges)

@app.route("/admin/recharges/<int:recharge_id>/confirm", methods=["POST"])
@login_required
def confirm_recharge(recharge_id):
    recharge = Recharge.query.get_or_404(recharge_id)
    recharge.status = "confirmed"
    recharge.user.wallet_balance += recharge.amount
    db.session.commit()
    flash(f"Recharge {recharge.transaction_id} confirmed for {recharge.user.email}", "success")
    return redirect(url_for("admin_recharges"))

@app.route("/admin/recharges/<int:recharge_id>/reject", methods=["POST"])
@login_required
def reject_recharge(recharge_id):
    recharge = Recharge.query.get_or_404(recharge_id)
    recharge.status = "rejected"
    db.session.commit()
    flash(f"Recharge {recharge.transaction_id} rejected for {recharge.user.email}", "danger")
    return redirect(url_for("admin_recharges"))

# -------------------------
# Withdrawals
# -------------------------
@app.route("/admin/withdrawals")
def admin_withdrawals():
    withdrawals = Withdrawal.query.order_by(Withdrawal.created_at.desc()).all()
    return render_template("admin_withdrawals.html", withdrawals=withdrawals)

@app.route("/admin/withdrawals/<int:withdrawal_id>/paid", methods=["POST"])
def mark_paid(withdrawal_id):
    withdrawal = Withdrawal.query.get_or_404(withdrawal_id)
    withdrawal.status = "Paid"
    db.session.commit()
    flash(f"Withdrawal {withdrawal.id} marked as Paid.")
    return redirect(url_for("admin_withdrawals"))

@app.route("/admin/withdrawals/<int:withdrawal_id>/reject", methods=["POST"])
def reject_withdrawal(withdrawal_id):
    withdrawal = Withdrawal.query.get_or_404(withdrawal_id)
    withdrawal.status = "Rejected"
    db.session.commit()
    flash(f"Withdrawal {withdrawal.id} has been Rejected.")
    return redirect(url_for("admin_withdrawals"))

# -------------------------
# Wallet / Deposit / Withdraw
# -------------------------
@app.route("/wallet")
def wallet():
    user_id = session.get("user_id")
    if not user_id:
        flash("Please log in first.")
        return redirect(url_for("login"))
    user = User.query.get(user_id)
    return render_template("wallet.html", user=user)

@app.route("/checkin", methods=["POST"])
@login_required
def checkin():
    user = current_user
    if user.checkin(reward=10):
        db.session.commit()
        flash("✅ You’ve successfully checked in! +10 KSh added 🎉", "success")
    else:
        flash("⚠️ Already claimed! Come back after 24 hours ⏳", "warning")
    return redirect(url_for("dashboard"))

@app.route("/deposit", methods=["POST"])
def deposit():
    user_id = session.get("user_id")
    if not user_id:
        flash("Please log in first.")
        return redirect(url_for("login"))
    amount = int(request.form["amount"])
    user = User.query.get(user_id)
    user.wallet_balance = (user.wallet_balance or 0) + amount
    db.session.commit()
    flash(f"Deposited {amount} KES successfully!")
    return redirect(url_for("wallet"))

@app.route("/withdraw_page", methods=["GET", "POST"])
def withdraw_page():
    user_id = session.get("user_id")
    if not user_id:
        flash("Please log in first.")
        return redirect(url_for("login"))

    user = User.query.get(user_id)

    if request.method == "POST":
        account_number = request.form["account_number"]
        recipient_name = request.form["recipient_name"]
        bank_name = request.form["bank_name"]
        amount = float(request.form["amount"])

        if (user.wallet_balance or 0) >= amount:
            user.wallet_balance -= amount
            withdrawal = Withdrawal(
                user_id=user.id,
                account_number=account_number,
                recipient_name=recipient_name,
                bank_name=bank_name,
                amount=amount,
                status="Pending"
            )
            db.session.add(withdrawal)
            db.session.commit()
            flash("Withdrawal request submitted successfully!")
        else:
            flash("Insufficient balance!")

        return redirect(url_for("withdraw_page"))

    withdrawals = Withdrawal.query.filter_by(user_id=user.id).all()
    return render_template("withdraw.html", current_user=user, withdrawals=withdrawals)

@app.route("/withdraw", methods=["GET", "POST"])
@login_required
def withdraw():
    user = current_user

    if request.method == "POST":
        account_number = request.form["account_number"]
        recipient_name = request.form["recipient_name"]
        bank_name = request.form["bank_name"]
        amount = float(request.form["amount"])

        if (user.wallet_balance or 0) >= amount:
            # Deduct balance
            user.wallet_balance -= amount

            # Record withdrawal
            new_withdrawal = Withdrawal(
                user_id=user.id,
                account_number=account_number,
                recipient_name=recipient_name,
                bank_name=bank_name,
                amount=amount,
                status="Pending"
            )
            db.session.add(new_withdrawal)
            db.session.commit()

            flash(f"Withdrew {amount} KES successfully!", "withdrawal")
        else:
            flash("Insufficient balance!", "withdrawal")

        return redirect(url_for("withdraw"))

    # GET → show page with history
    withdrawals = Withdrawal.query.filter_by(user_id=user.id).order_by(Withdrawal.created_at.desc()).all()
    return render_template("withdraw.html", withdrawals=withdrawals)

# -------------------------
# Dashboard & Mine
# -------------------------
@app.route("/dashboard")
@login_required
def dashboard():
    # current_user is automatically set by Flask-Login
    user = current_user  

    # Query only if the user is authenticated
    recharges = Recharge.query.filter_by(user_id=user.id).order_by(Recharge.created_at.desc()).all()

    return render_template("dashboard.html", user=user, recharges=recharges)

@app.route("/financial")
@login_required
def financial():
    user = get_current_user()
    available_balance = f"KSh{user.wallet_balance:.2f}" if getattr(user, "wallet_balance", None) else "KSh0.00"
    total_withdraw = f"KSh{getattr(user, 'total_withdraw', 0):.2f}"
    total_recharge = f"KSh{getattr(user, 'total_recharge', 0):.2f}"
    return render_template("financial.html",
                           available_balance=available_balance,
                           total_withdraw=total_withdraw,
                           total_recharge=total_recharge,
                           user=user)

@app.route("/mine")
@login_required
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
# Run
# -------------------------
if __name__ == "__main__":
    app.run(debug=True)