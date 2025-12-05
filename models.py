from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
from sqlalchemy import create_engine
from extensions import db

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    role = Column(String, nullable=False)  # 'admin' or 'member'
    first_name = Column(String)
    last_name = Column(String)
    email = Column(String)
    member_number = Column(String)
    active = Column(Boolean, default=True)

    reservations = relationship("Reservation", back_populates="user")
    notes = relationship("Note", back_populates="user")


class Reservation(Base):
    __tablename__ = 'reservations'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    date = Column(String)
    time = Column(String)
    guests = Column(String)
    notes = Column(Text)

    user = relationship("User", back_populates="reservations")


class Note(Base):
    __tablename__ = 'notes'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="notes")


class BlockedDate(Base):
    __tablename__ = 'blocked_dates'

    id = Column(Integer, primary_key=True)
    date = Column(String, unique=True)


class AdminActionLog(db.Model):
    __tablename__ = 'admin_action_logs'

    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    action = db.Column(db.String(255))
    details = db.Column(db.Text, nullable=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)

    admin = db.relationship("User", backref="admin_logs")

# Only needed to generate the DB once
def init_db():
    engine = create_engine('sqlite:///room120.db')
    Base.metadata.create_all(engine)

# Uncomment and run once to initialize the database:
# init_db()
