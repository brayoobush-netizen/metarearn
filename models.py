from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
import uuid

db = SQLAlchemy()

class User(db.Model, UserMixin):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)


    # Tutorial flag: defaults to False so new users see tutorial
    tutorial_seen = db.Column(db.Boolean, default=False, nullable=False)

    # Wallet & stats
    wallet_balance = db.Column(db.Float, default=0.0, nullable=False)
    total_views = db.Column(db.Integer, default=0, nullable=False)
    total_earnings = db.Column(db.Float, default=0.0, nullable=False)
    total_withdraw = db.Column(db.Float, default=0.0, nullable=False)
    total_recharge = db.Column(db.Float, default=0.0, nullable=False)

    profile_image = db.Column(db.String(200))
    last_checkin = db.Column(db.DateTime, nullable=True)

    # Referral system
    referral_code = db.Column(
        db.String(20),
        unique=True,
        default=lambda: str(uuid.uuid4())[:8],
        nullable=False
    )
    referred_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    referrals = db.relationship("User", backref=db.backref("referrer", remote_side=[id]))

    # Relationships
    recharges = db.relationship("Recharge", back_populates="user", lazy=True)
    withdrawals = db.relationship("Withdrawal", back_populates="user", lazy=True)
    purchases = db.relationship("Purchase", back_populates="user", lazy=True)

    # Helper methods
    def add_views(self, views: int):
        rate_per_view = 0.025
        earnings = views * rate_per_view
        self.total_views += views
        self.total_earnings += earnings
        self.wallet_balance += earnings
        return earnings

    def can_checkin(self):
        if self.last_checkin is None:
            return True
        elapsed = (datetime.utcnow() - self.last_checkin).total_seconds()
        return elapsed >= 86400  # 24 hours

    def checkin(self, reward=10):
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
    status = db.Column(db.String(50), default="Pending", nullable=False)
    note = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.now(), nullable=False)

    # Relationship back to User
    user = db.relationship("User", back_populates="withdrawals")


class Recharge(db.Model):
    __tablename__ = "recharges"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    amount = db.Column(db.Integer, nullable=False)
    provider = db.Column(db.String(50), nullable=False)
    transaction_id = db.Column(db.String(100), nullable=False)
    screenshot_filename = db.Column(db.String(200))
    status = db.Column(db.String(20), default="pending", nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.now(), nullable=False)

    # Relationship back to User
    user = db.relationship("User", back_populates="recharges")


class Purchase(db.Model):
    __tablename__ = "purchase"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    product_sku = db.Column(db.String(50), nullable=False)
    product_name = db.Column(db.String(120), nullable=False)
    price = db.Column(db.Float, nullable=False)
    income_per_day = db.Column(db.Float, nullable=False)
    period_days = db.Column(db.Integer, nullable=False)
    start_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    end_date = db.Column(db.DateTime)
    earned = db.Column(db.Float, default=0.0, nullable=False)
    status = db.Column(db.String(20), default="Active", nullable=False)

    # Relationship back to User
    user = db.relationship("User", back_populates="purchases")


class Product(db.Model):
    __tablename__ = "product"

    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    price = db.Column(db.Float, nullable=False)
    income_per_day = db.Column(db.Float, nullable=False)
    period_days = db.Column(db.Integer, nullable=False)
    image = db.Column(db.String(120), nullable=False)
    available = db.Column(db.Integer, default=1, nullable=False)  # 1 = available, 0 = sold out
