from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

# Single SQLAlchemy instance
db = SQLAlchemy()

class User(db.Model):
    __tablename__ = "user"   # table name is "user"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

    # Wallet balance in dollars
    wallet_balance = db.Column(db.Float, default=0.0)

    # Optional: track total views submitted by user
    total_views = db.Column(db.Integer, default=0)

    # Optional: track total earnings from tasks
    total_earnings = db.Column(db.Float, default=0.0)

    def add_views(self, views: int):
        """Helper method to add views and update earnings."""
        rate_per_view = 0.025
        earnings = views * rate_per_view
        self.total_views += views
        self.total_earnings += earnings
        self.wallet_balance += earnings
        return earnings


class Recharge(db.Model):
    __tablename__ = "recharges"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))  # matches User.__tablename__
    amount = db.Column(db.Integer, nullable=False)
    provider = db.Column(db.String(50), nullable=False)
    transaction_id = db.Column(db.String(100), nullable=False)
    screenshot_filename = db.Column(db.String(200))
    status = db.Column(db.String(20), default="pending")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref="recharges")