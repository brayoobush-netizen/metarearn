from app import app, db
from models import User   # adjust if your models are inside a package (e.g. from metaearn.models import User)

with app.app_context():
    users = User.query.all()
    for u in users:
        # Reset tutorial flag for all users
        if u.tutorial_seen is None or u.tutorial_seen is True:
            u.tutorial_seen = False
    db.session.commit()
    print("All users reset: tutorial_seen=False")