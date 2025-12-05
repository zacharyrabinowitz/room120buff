from sqlalchemy import create_engine, Column, Integer, String, Boolean, Text, Date, Time, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from app import app
from extensions import db
from models import User, Invoice


Base = declarative_base()

# --- User Model ---
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
    notes = Column(Text)

# --- Reservation Model ---
class Reservation(Base):
    __tablename__ = 'reservations'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    date = Column(String)
    time = Column(String)
    guests = Column(Integer)
    notes = Column(Text)

    user = relationship("User", back_populates="reservations")

with app.app_context():
    db.create_all()
    print("Database tables created.")