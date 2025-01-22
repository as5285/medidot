# auth.py
import os
import bcrypt
import numpy as np
import face_recognition
from sqlalchemy import create_engine, Column, Integer, String, text, LargeBinary
from sqlalchemy.orm import sessionmaker, declarative_base

# 1) Initialize database
DATABASE_URL = "sqlite:///database.db"
Base = declarative_base()
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)

# 2) Define a User model
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    face_encoding = Column(LargeBinary, nullable=True)

# 3) Create tables if they don't exist
Base.metadata.create_all(engine)

# 4) Functions to sign up and log in
def signup_user(email: str, password: str, face_encoding: bytes = None) -> bool:
    """
    Creates a new user in the DB. Returns True on success, False if user already exists.
    """
    session = SessionLocal()
    try:
        # Check if the user already exists
        existing_user = session.query(User).filter_by(email=email).first()
        if existing_user:
            return False
        
        # Hash the password using bcrypt
        hashed_pw = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        user = User(email=email, password_hash=hashed_pw.decode('utf-8'), face_encoding=face_encoding)
        session.add(user)
        session.commit()
        return True
    finally:
        session.close()


def login_user(email: str, password: str) -> bool:
    """
    Verify user credentials. Returns True if valid, else False.
    """
    session = SessionLocal()
    try:
        user = session.query(User).filter_by(email=email).first()
        if not user:
            return False
        
        # Compare hashed password
        return bcrypt.checkpw(password.encode('utf-8'), user.password_hash.encode('utf-8'))
    finally:
        session.close()

def login_user_with_face(email: str, face_encoding: np.ndarray) -> bool:
    """
    Compare 'face_encoding' from camera with the stored face_encoding in DB for user 'email'.
    Returns True if match, otherwise False.
    """
    session = SessionLocal()
    try:
        user = session.query(User).filter_by(email=email).first()
        if not user or not user.face_encoding:
            # user doesn't exist or hasn't registered a face
            return False

        # Convert stored binary back to numpy
        stored_encoding = np.frombuffer(user.face_encoding, dtype=np.float64)

        # Compare using face_recognition
        results = face_recognition.compare_faces([stored_encoding], face_encoding, tolerance=0.6)
        return results[0]  # True if it's a match
    finally:
        session.close()

def get_user_id_by_email(email: str):
    """Returns the user's ID for the given email, or None if not found."""
    session = SessionLocal()
    try:
        user = session.query(User).filter(User.email == email).first()
        if user:
            return user.id
        else:
            return None
    finally:
        session.close()