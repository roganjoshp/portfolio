from app import db

import datetime as dt


class Messages(db.Model):

    id = db.Column(db.Integer, primary_key=True)
    datetime = db.Column(db.DateTime, default=dt.datetime.utcnow)
    name = db.Column(db.String)
    email = db.Column(db.String)
    phone = db.Column(db.String)
    message = db.Column(db.String)