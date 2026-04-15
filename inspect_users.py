from app import app
from models import db, User
from sqlalchemy import inspect

with app.app_context():
    inspector = inspect(db.engine)
    print("Tables:", inspector.get_table_names())

    for u in User.query.all():
        print(
            f"ID={u.id}, Email={u.email}, Wallet={u.wallet_balance}, "
            f"Joined={u.date_joined}, Referral={u.referral_code}"
        )
