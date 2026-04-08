from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from sqlalchemy import Column, DateTime


db = SQLAlchemy()

class User(db.Model, UserMixin):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

    wallet_balance = db.Column(db.Float, default=0.0)
    total_views = db.Column(db.Integer, default=0)
    total_earnings = db.Column(db.Float, default=0.0)
    total_withdraw = db.Column(db.Float, default=0.0)
    total_recharge = db.Column(db.Float, default=0.0)
    profile_image = db.Column(db.String(200))

    # ✅ New field to track daily check‑in
    last_checkin = db.Column(db.DateTime, nullable=True)

    # relationships
    recharges = db.relationship("Recharge", backref="user", lazy=True)
    withdrawals = db.relationship("Withdrawal", backref="user", lazy=True)

    def add_views(self, views: int):
        """Helper method to add views and update earnings."""
        rate_per_view = 0.025
        earnings = views * rate_per_view
        self.total_views += views
        self.total_earnings += earnings
        self.wallet_balance += earnings
        return earnings

    def can_checkin(self):
        """Check if user can claim daily reward (after 24h)."""
        if self.last_checkin is None:
            return True
        elapsed = (datetime.utcnow() - self.last_checkin).total_seconds()
        return elapsed >= 86400  # 24 hours in seconds

    def checkin(self, reward=10):
        """Grant daily check‑in reward if eligible."""
        if self.can_checkin():
            self.wallet_balance += reward
            self.last_checkin = datetime.utcnow()
            return True
        return False


class Withdrawal(db.Model):
    __tablename__ = "withdrawals"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    account_number = db.Column(db.String(100), nullable=False)
    recipient_name = db.Column(db.String(100), nullable=False)
    bank_name = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), default="Pending")
    created_at = db.Column(db.DateTime, default=db.func.now())


class Recharge(db.Model):
    __tablename__ = "recharges"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    amount = db.Column(db.Integer, nullable=False)
    provider = db.Column(db.String(50), nullable=False)
    transaction_id = db.Column(db.String(100), nullable=False)
    screenshot_filename = db.Column(db.String(200))
    status = db.Column(db.String(20), default="pending")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)