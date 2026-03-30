# app.py
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from models import db, User
import random, os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from flask_migrate import Migrate   # <-- NEW

app = Flask(__name__)
app.secret_key = "your_secret_key"

# Database config
# Use Postgres in production (Render), SQLite locally
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///users.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)
migrate = Migrate(app, db)   # <-- NEW

# Uploads folder for proof images
UPLOAD_FOLDER = "uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ⚠️ REMOVE db.create_all() — migrations handle table creation now
# with app.app_context():
#     db.create_all()

# Landing page
@app.route("/")
def landing():
    return render_template("landing.html")

# Register → send OTP
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        hashed_pw = generate_password_hash(password)
        new_user = User(email=email, password=hashed_pw,
                        wallet_balance=0.0, total_views=0, total_earnings=0.0)
        db.session.add(new_user)
        db.session.commit()

        # Generate OTP
        otp = str(random.randint(100000, 999999))
        session["otp"] = otp
        session["pending_user_id"] = new_user.id

        # Send OTP
        message = Mail(
            from_email="metarearn@gmail.com",
            to_emails=email,
            subject="MetaEarn OTP Verification",
            html_content=f"<h3>Your OTP code is <b>{otp}</b></h3>"
        )
        try:
            sg = SendGridAPIClient(os.environ.get("SENDGRID_API_KEY"))
            sg.send(message)
            flash("OTP sent to your email. Please verify.")
        except Exception as e:
            flash(f"⚠️ Error sending OTP: {str(e)}")
            return redirect(url_for("register"))

        return redirect(url_for("verify"))

    return render_template("register.html")

# Verify OTP
@app.route("/verify", methods=["GET", "POST"])
def verify():
    if request.method == "POST":
        entered_otp = request.form["otp"]
        if entered_otp == session.get("otp"):
            session["user_id"] = session["pending_user_id"]
            session.pop("otp", None)
            session.pop("pending_user_id", None)
            flash("✅ OTP Verified! You can now log in.")
            return redirect(url_for("login"))
        else:
            flash("❌ Invalid OTP. Try again.")
    return render_template("verify.html")

# Login
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            session["user_id"] = user.id
            return redirect(url_for("dashboard"))
        else:
            flash("❌ Invalid credentials")
    return render_template("login.html")

# Dashboard
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))
    user = User.query.get(session["user_id"])
    return render_template("dashboard.html", user=user)

# Upload views proof → earn money
@app.route("/upload_views", methods=["POST"])
def upload_views():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user = User.query.get(session["user_id"])
    views = int(request.form["views"])
    earnings = views * 0.025

    user.total_views += views
    user.total_earnings += earnings
    user.wallet_balance += earnings
    db.session.commit()

    if "proof" in request.files:
        file = request.files["proof"]
        if file.filename.endswith(".png"):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

    flash(f"✅ {views} views recorded. ${earnings:.2f} added to your wallet!")
    return redirect(url_for("dashboard"))

# Logout
@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.")
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(debug=True)