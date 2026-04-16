from flask import (
    Flask, render_template, Blueprint, request,
    redirect, url_for, session, flash,
    send_from_directory, abort, jsonify
)
from datetime import datetime, timedelta, timezone, date
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from sqlalchemy import func
from flask_login import (
    LoginManager, current_user,
    login_required, login_user, logout_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from models import db, User, Recharge, Withdrawal, Purchase, Product
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
import os
import random
import traceback
import requests
from requests.auth import HTTPBasicAuth
import base64



# -------------------------
# App setup
# -------------------------
app = Flask(__name__, static_folder="static", template_folder="templates")

# Config
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///users.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = os.environ.get("SECRET_KEY", "dev_secret")

# Database + migrations
db.init_app(app)
migrate = Migrate(app, db)

with app.app_context():
    db.create_all()

# -------------------------
# Login Manager
# -------------------------
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
@login_required
def product():
    user = current_user
    purchases = Purchase.query.filter_by(user_id=user.id).all()

    accumulated_income = 0
    todays_income = 0
    total_investments = len(purchases)

    for p in purchases:
        days_elapsed = (date.today() - p.start_date.date()).days
        days_elapsed = max(0, min(days_elapsed, p.period_days))

        earned = days_elapsed * p.income_per_day
        accumulated_income += earned

        if p.end_date.date() >= date.today():
            todays_income += p.income_per_day
            p.status = "Active"
        else:
            p.status = "Expired"

        # Attach extra fields
        p.calculated_earned = earned
        p.days_remaining = max((p.end_date.date() - date.today()).days, 0)
        p.total_return = p.income_per_day * p.period_days

        # Map product name and image using product_sku
        if p.product_sku in product_map:
            product_info = product_map[p.product_sku]
            p.product_name = product_info["name"]
            p.image = product_info["image"]
        else:
            p.product_name = "Unknown Product"
            p.image = "default.png"

    active_purchases = [p for p in purchases if p.status == "Active"]

    # Query all products
    products = Product.query.all()

    # Build a set of SKUs the user already owns
    purchased_skus = {p.product_sku for p in purchases}

    # Attach product_map info and flags to each product
    for prod in products:
        if prod.sku in product_map:
            meta = product_map[prod.sku]
            prod.name = meta["name"]
            prod.price = meta["price"]
            prod.income_per_day = meta["income"]
            prod.period_days = meta["days"]
            prod.image = meta["image"]
            prod.total_return = (
                meta["income"] * meta["days"] if meta["income"] and meta["days"] else None
            )
        else:
            prod.name = "Unknown Product"
            prod.price = None
            prod.income_per_day = None
            prod.period_days = None
            prod.image = "default.png"
            prod.total_return = None

        # Flag ownership
        prod.is_owned = prod.sku in purchased_skus

    return render_template(
        "product.html",
        products=products,
        purchases=purchases,
        active_purchases=active_purchases,
        accumulated_income=accumulated_income,
        todays_income=todays_income,
        total_investments=total_investments,
        available_balance=user.wallet_balance
    )

@app.route("/buy/<sku>", methods=["POST"])
@login_required
def buy_product(sku):
    user = current_user

    if sku not in product_map:
        flash("Invalid product SKU", "danger")
        return redirect(url_for("product"))

    product_info = product_map[sku]

    # Prevent buying if already owned
    existing = Purchase.query.filter_by(user_id=user.id, product_sku=sku).first()
    if existing:
        flash("You already own this product.", "warning")
        return redirect(url_for("product"))

    # ✅ Check wallet balance
    if user.wallet_balance < product_info["price"]:
        flash("Insufficient funds. Please recharge your wallet.", "danger")
        return redirect(url_for("product"))

    # Deduct price from wallet
    user.wallet_balance -= product_info["price"]

    # Calculate dates
    start_date = datetime.utcnow()
    end_date = start_date + timedelta(days=product_info["days"])

    # Create purchase
    purchase = Purchase(
        user_id=user.id,
        product_sku=sku,
        product_name=product_info["name"],
        price=product_info["price"],
        income_per_day=product_info["income"],
        period_days=product_info["days"],
        start_date=start_date,
        end_date=end_date,
        earned=0.0,
        status="Active"
    )

    db.session.add(purchase)
    db.session.commit()

    flash(f"You successfully bought {product_info['name']}!", "success")
    return redirect(url_for("product"))










@app.route("/team")
@login_required
def team():
    # Level 1: direct referrals
    lv1 = current_user.referrals

    # Level 2: referrals of Lv1
    lv2 = [u for ref in lv1 for u in ref.referrals]

    # Level 3: referrals of Lv2
    lv3 = [u for ref in lv2 for u in ref.referrals]

    # Totals for summary card
    total_people = len(lv1) + len(lv2) + len(lv3)
    total_investment = sum(p.price for u in lv1+lv2+lv3 for p in u.purchases)
    total_rebate = (
        sum(p.price * 0.09 for u in lv1 for p in u.purchases) +
        sum(p.price * 0.02 for u in lv2 for p in u.purchases) +
        sum(p.price * 0.01 for u in lv3 for p in u.purchases)
    )

    return render_template(
        "team.html",
        lv1=lv1,
        lv2=lv2,
        lv3=lv3,
        total_people=total_people,
        total_investment=total_investment,
        total_rebate=total_rebate
    )

@app.route("/home")
def home():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    return redirect(url_for("dashboard"))

# -------------------------
# Authentication
# -------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        profile_file = request.files.get("profile")

        # Referral code can come from form OR link (?ref=...)
        ref_code = request.form.get("referral_code") or request.args.get("ref")

        # ✅ Require Gmail
        if not email.endswith("@gmail.com"):
            flash("Only Gmail addresses are allowed.", "danger")
            return redirect(url_for("register"))

        if not email or not password:
            flash("Please provide email and password.", "danger")
            return redirect(url_for("register"))

        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash("Email already registered. Please log in.", "warning")
            return redirect(url_for("login"))

        # Hash password
        hashed_pw = generate_password_hash(password)

        # Create new user
        new_user = User(
            email=email,
            password=hashed_pw,
            wallet_balance=0.0,
            total_views=0,
            total_earnings=0.0
        )

        # Referral linking
        if ref_code:
            inviter = User.query.filter_by(referral_code=ref_code).first()
            if inviter:
                new_user.referred_by = inviter.id
                flash(f"You were referred by {inviter.email}", "success")
            else:
                flash("Invalid referral code.", "warning")

        # Handle profile image upload
        if profile_file and allowed_file(profile_file.filename):
            filename = secure_filename(profile_file.filename)
            upload_folder = os.path.join(app.root_path, "static", "uploads")
            os.makedirs(upload_folder, exist_ok=True)
            profile_file.save(os.path.join(upload_folder, filename))
            if hasattr(new_user, "profile_image"):
                new_user.profile_image = filename

        db.session.add(new_user)
        db.session.commit()

        flash("Account created successfully. Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


# -------------------------
# STK Push Route
# -------------------------

@app.route('/transactions')
@login_required
def transactions():
    try:
        withdrawals = Withdrawal.query.filter_by(
            user_id=current_user.id
        ).order_by(Withdrawal.created_at.desc()).all()

        return render_template(
            'transactions.html',
            withdrawals=withdrawals,
            current_user=current_user
        )
    except Exception as e:
        traceback.print_exc()
        flash('Could not load transactions.', 'error')
        return render_template(
            'transactions.html',
            withdrawals=[],
            current_user=current_user
        )



# Define product_map globally so all routes can use it
product_map = {
    "SKU-1": {
        "name": "MetaEarn Intern",
        "price": 250,
        "income": 50,
        "days": 8,
        "image": "intern.png"
    },
    "SKU-2": {
        "name": "MetaEarn 1",
        "price": 900,
        "income": 100,
        "days": 25,
        "image": "metearn1.png"
    },
    "SKU-3": {
        "name": "MetaEarn 2",
        "price": 2200,
        "income": 200,
        "days": 30,
        "image": "metearn2.png"
    },
    "SKU-4": {
        "name": "MetaEarn 3",
        "price": 3500,
        "income": 301,
        "days": 40,
        "image": "metearn3.png"
    },
    "SKU-5": {
        "name": "MetaEarn 4",
        "price": 5500,
        "income": 450,
        "days": 45,
        "image": "metearn4.png"
    },
    "SKU-6": {
        "name": "MetaEarn 5",
        "price": 12000,
        "income": 1020,
        "days": 60,
        "image": "metearn5.png"
    },
    "SKU-7": {
        "name": "MetaEarn 6",
        "price": 21000,
        "income": 1890,
        "days": 90,
        "image": "metearn6.png"
    },
    "SKU-8": {
        "name": "MetaEarn 7",
        "price": 35000,
        "income": 3150,
        "days": 100,
        "image": "metearn7.png"
    },
    "SKU-9": {
        "name": "MetaEarn 8",
        "price": 49000,
        "income": 4410,
        "days": 120,
        "image": "metearn8.png"
    },
    "SKU-10": {
        "name": "MetaEarn 9",
        "price": 68000,
        "income": 6120,
        "days": 150,
        "image": "metearn9.png"
    },
    "SKU-11": {
        "name": "MetaEarn Pro",
        "price": None,   # Coming Soon
        "income": None,
        "days": None,
        "image": "metearn10.png"
    }
}










@app.route("/buy/<int:product_id>", methods=["GET", "POST"])
@login_required
def buy(product_id):
    # Convert product_id to SKU string
    sku = f"SKU-{product_id}"
    product = product_map.get(sku)

    if not product:
        flash("Product not found.", "danger")
        return redirect(url_for("dashboard"))

    purchased = Purchase.query.filter_by(user_id=current_user.id, product_sku=sku).first()

    if request.method == "POST":
        if purchased:
            flash("You already purchased this product.", "warning")
            return redirect(url_for("product"))

        if current_user.wallet_balance < product["price"]:
            flash("Insufficient balance.", "danger")
            return redirect(url_for("buy", product_id=product_id))

        # Deduct balance
        current_user.wallet_balance -= product["price"]

        # Create purchase
        purchase = Purchase(
            user_id=current_user.id,
            product_sku=sku,
            product_name=product["name"],
            price=product["price"],
            income_per_day=product["income"],
            period_days=product["days"],
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=product["days"]),
            earned=0.0,
            status="Active"
        )
        db.session.add(purchase)
        db.session.commit()

        flash("Purchase successful!", "success")
        return redirect(url_for("product"))

    return render_template("buy.html", product=product, purchased=purchased)








@app.route("/password", methods=["GET", "POST"])
@login_required
def password():
    if request.method == "POST":
        new_password = request.form.get("new_password")
        if not new_password or len(new_password) < 6:
            flash("Password must be at least 6 characters.", "warning")
            return redirect(url_for("password"))

        current_user.password = generate_password_hash(new_password)
        db.session.commit()

        session.clear()
        logout_user()
        flash("Password updated. Please log in with your new passcode.", "success")
        return redirect(url_for("login"))

    return render_template("password.html")

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

        # ✅ Only allow Gmail
        if not email.endswith("@gmail.com"):
            flash("Only Gmail addresses are allowed.", "danger")
            return redirect(url_for("login"))

        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            flash("Logged in successfully.", "success")

            # ✅ Redirect new users to tutorial first
            if not user.tutorial_seen:
                return redirect(url_for("tutorial"))
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid email or password.", "danger")
            return redirect(url_for("login"))

    return render_template("login.html")



@app.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()
    flash("You have been logged out." "info")
    return redirect(url_for("login"))

@app.route("/tutorial")
@login_required
def tutorial():
    user = current_user
    # If user already saw tutorial, send them to dashboard
    if user.tutorial_seen:
        return redirect(url_for("dashboard"))

    return render_template("tutorial.html", user=user)


# -------------------------
# Recharge
# -------------------------
@app.route("/recharge", methods=["GET", "POST"])
@login_required
def recharge():
    user = current_user

    if request.method == "POST":
        amount_str = request.form.get("amount")
        provider = request.form.get("provider")
        transaction_id = request.form.get("transaction_id")
        screenshot_file = request.files.get("screenshot")

        if not amount_str:
            flash("Please select or enter an amount.", "error")
            return redirect(url_for("recharge"))

        try:
            amount = int(amount_str)
        except ValueError:
            flash("Invalid amount entered.", "error")
            return redirect(url_for("recharge"))

        filename = None
        if screenshot_file:
            filename = secure_filename(screenshot_file.filename)
            upload_folder = os.path.join(app.root_path, "static", "uploads")
            os.makedirs(upload_folder, exist_ok=True)
            screenshot_file.save(os.path.join(upload_folder, filename))

        new_recharge = Recharge(
            user_id=user.id,
            amount=amount,
            provider=provider,
            transaction_id=transaction_id,
            screenshot_filename=filename,
            status="pending"
        )
        db.session.add(new_recharge)
        db.session.commit()

        flash("Recharge request submitted successfully! Pending admin approval.", "recharge")
        return redirect(url_for("recharge"))

    # Calculate today's confirmed recharge
    now = datetime.utcnow()
    last_24h = now - timedelta(hours=24)
    todays_recharge = db.session.query(func.sum(Recharge.amount)).filter(
        Recharge.user_id == user.id,
        Recharge.status == "confirmed",
        Recharge.created_at >= last_24h
    ).scalar() or 0

    # Calculate total confirmed recharge
    total_recharge = db.session.query(func.sum(Recharge.amount)).filter(
        Recharge.user_id == user.id,
        Recharge.status == "confirmed"
    ).scalar() or 0

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

    if recharge.status != "confirmed":
        recharge.status = "confirmed"

        # ✅ Bonus map
        bonus_map = {
            900: 150,
            5500: 400,
            21000: 900,
            35000: 2500,
            49000: 6250
        }
        bonus = bonus_map.get(recharge.amount, 0)

        # ✅ Update user balance with amount + bonus
        recharge.user.wallet_balance += recharge.amount + bonus

        db.session.commit()
        flash(
            f"Recharge {recharge.transaction_id} confirmed for {recharge.user.email}. "
            f"Amount {recharge.amount} KSh + Bonus {bonus} KSh added!",
            "success"
        )

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

@app.route("/deposit-history")
def deposit_history():
    # Fetch all recharge requests from DB
    recharges = Recharge.query.order_by(Recharge.created_at.desc()).all()
    return render_template("deposit_history.html", recharges=recharges)

@app.route("/withdraw-history")
def withdraw_history():
    # Fetch all withdrawal requests from DB
    withdrawals = Withdrawal.query.order_by(Withdrawal.created_at.desc()).all()
    return render_template("withdraw_history.html", withdrawals=withdrawals)

@app.route("/bank-history")
@login_required
def bank_history():
    # Fetch both deposits and withdrawals for the current user
    recharges = Recharge.query.filter_by(user_id=current_user.id).order_by(Recharge.created_at.desc()).all()
    withdrawals = Withdrawal.query.filter_by(user_id=current_user.id).order_by(Withdrawal.created_at.desc()).all()
    return render_template("bank_history.html", recharges=recharges, withdrawals=withdrawals)

@app.route("/update_account", methods=["POST"])
@login_required
def update_account():
    user = current_user

    # Get form data
    username = request.form.get("username")
    nationality = request.form.get("nationality")

    # Update fields if provided
    if username:
        user.username = username
    if nationality:
        user.nationality = nationality

    db.session.commit()
    flash("Account updated successfully!", "success")

    return redirect(url_for("account"))

@app.route("/upload_profile_pic", methods=["POST"])
@login_required
def upload_profile_pic():
    if "profile_pic" not in request.files:
        flash("No file selected", "error")
        return redirect(url_for("account"))

    file = request.files["profile_pic"]
    if file.filename == "":
        flash("No file selected", "error")
        return redirect(url_for("account"))

    # Save file to static folder (or better: user-specific folder)
    filename = secure_filename(file.filename)
    file.save(os.path.join("static/uploads", filename))

    # Update user profile in DB
    current_user.profile_pic = f"/static/uploads/{filename}"
    db.session.commit()

    flash("Profile picture updated!", "success")
    return redirect(url_for("account"))

@app.route("/bills")
@login_required
def bills():
    # Placeholder bills list
    sample_bills = [
        {"name": "Electricity", "amount": "KSh1500", "status": "Pending"},
        {"name": "Water", "amount": "KSh800", "status": "Paid"},
    ]
    return render_template("bills.html", bills=sample_bills)

@app.route("/account")
@login_required
def account():
    user = current_user
    return render_template("account.html", user=user)

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

@app.route('/withdraw', methods=['GET', 'POST'])
@login_required
def withdraw():
    try:
        # POST: create withdrawal request
        if request.method == 'POST':
            recipient_name = request.form.get('recipient_name', '').strip()
            bank_name = request.form.get('bank_name', '').strip()
            account_number = request.form.get('account_number', '').strip()
            amount = request.form.get('amount', type=float)
            note = request.form.get('note', '').strip()

            # Basic validation
            if not recipient_name or not bank_name or not account_number or not amount or amount <= 0:
                flash('Please complete all required fields with valid values.', 'withdrawal')
                return redirect(url_for('withdraw'))

            # Check balance
            if current_user.wallet_balance < amount:
                flash('Insufficient wallet balance for this withdrawal.', 'withdrawal')
                return redirect(url_for('withdraw'))

            # Create withdrawal record
            w = Withdrawal(
                user_id=current_user.id,
                recipient_name=recipient_name,
                bank_name=bank_name,
                account_number=account_number,
                amount=amount,
                status='Pending',
                note=note,
                created_at=datetime.utcnow()
            )
            db.session.add(w)

            # Option A: deduct immediately
            current_user.wallet_balance = current_user.wallet_balance - amount

            db.session.commit()
            flash('Withdrawal request submitted. We will process it shortly.', 'withdrawal')
            return redirect(url_for('withdraw'))

        # GET: compute sums
        now = datetime.utcnow()
        last_24h = now - timedelta(hours=24)

        todays_withdraw = db.session.query(
            func.coalesce(func.sum(Withdrawal.amount), 0.0)
        ).filter(
            Withdrawal.user_id == current_user.id,
            Withdrawal.created_at >= last_24h
        ).scalar() or 0.0

        total_withdraw = db.session.query(
            func.coalesce(func.sum(Withdrawal.amount), 0.0)
        ).filter(
            Withdrawal.user_id == current_user.id
        ).scalar() or 0.0

        withdrawals = Withdrawal.query.filter_by(user_id=current_user.id).order_by(Withdrawal.created_at.desc()).all()

        # safe transactions_url to avoid BuildError
        try:
            transactions_url = url_for('transactions')
        except Exception:
            transactions_url = None

        return render_template(
            'withdraw.html',
            current_user=current_user,
            withdrawals=withdrawals,
            todays_withdraw=todays_withdraw,
            total_withdraw=total_withdraw,
            transactions_url=transactions_url
        )

    except Exception as e:
        traceback.print_exc()
        flash('An error occurred while loading withdrawals. Try again later.', 'withdrawal')
        return render_template(
            'withdraw.html',
            current_user=current_user,
            withdrawals=[],
            todays_withdraw=0.0,
            total_withdraw=0.0,
            transactions_url=None
        )

# -------------------------
# Dashboard & Mine
# -------------------------
@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user

    try:
        # Query user-related data
        purchases = Purchase.query.filter_by(user_id=user.id).all()
        recharges = Recharge.query.filter_by(user_id=user.id).order_by(Recharge.created_at.desc()).all()
        withdrawals = Withdrawal.query.filter_by(user_id=user.id).order_by(Withdrawal.created_at.desc()).all()
        products = Product.query.filter_by(available=1).all()

        # Enrich products with product_map details
        for p in products:
            if p.sku in product_map:
                details = product_map[p.sku]
                p.name = details.get("name", p.name)
                p.price = details.get("price", p.price)
                p.income_per_day = details.get("income", p.income_per_day)
                p.period_days = details.get("days", p.period_days)
                p.image = details.get("image", p.image)

        # Tutorial flag: show only if user has NOT seen it
        show_tutorial = not bool(user.tutorial_seen)

        return render_template(
            "dashboard.html",
            user=user,
            purchases=purchases,
            recharges=recharges,
            withdrawals=withdrawals,
            products=products,
            show_tutorial=show_tutorial
        )

    except Exception as e:
        traceback.print_exc()
        flash("Could not load dashboard.", "danger")
        return render_template(
            "dashboard.html",
            user=user,
            purchases=[],
            recharges=[],
            withdrawals=[],
            products=[],
            show_tutorial=False
        )


@app.route("/skip_tutorial", methods=["POST"])
@login_required
def skip_tutorial():
    user = current_user
    user.tutorial_seen = True
    db.session.commit()
    db.session.refresh(user)
    return jsonify({"status": "ok"})

              





@app.route("/financial")
@login_required
def financial():
    user = current_user

    available_balance = f"KSh{(user.wallet_balance or 0):.2f}"
    total_withdraw = f"KSh{(user.total_withdraw or 0):.2f}"
    total_recharge = f"KSh{(user.total_recharge or 0):.2f}"

    return render_template(
        "financial.html",
        available_balance=available_balance,
        total_withdraw=total_withdraw,
        total_recharge=total_recharge,
        user=user
    )

@app.route("/mine")
@login_required
def mine():
    user = current_user

    context = {
    "available_balance": f"KSh{(user.wallet_balance or 0):.2f}",
    "total_withdraw": f"KSh{(user.total_withdraw or 0):.2f}",
    "total_recharge": f"KSh{(user.total_recharge or 0):.2f}",
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