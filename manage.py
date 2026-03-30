from flask import Flask
from flask_migrate import Migrate, Manager
from flask.cli import FlaskGroup
from models import db, User
import app  # import your app.py

# Use the app from app.py
application = app.app
db.init_app(application)
migrate = Migrate(application, db)

cli = FlaskGroup(application)

if __name__ == "__main__":
    cli()