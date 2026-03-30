# models.py
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

    # Wallet balance in dollars, updated automatically from tasks
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