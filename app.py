# app.py
import streamlit as st
from streamlit_player import st_player
import streamlit.components.v1 as components
import os
import face_recognition
from gtts import gTTS
import glob
import bcrypt
from sqlalchemy import create_engine, Column, Integer, String, text, ForeignKey, LargeBinary
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from auth import signup_user, login_user, login_user_with_face, get_user_id_by_email
from book_appointment import book_appointment
import google.generativeai as genai
from api import GEMINI_API_KEY


# --- Streamlit App Config ---
st.set_page_config(page_title="AI Receptionist", layout="centered")

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

    # If you want a backref relationship:
    appointments = relationship("Appointment", back_populates="user")

class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    specialist = Column(String, nullable=False)
    date = Column(String, nullable=False)
    time_slot = Column(String, nullable=False)

    # Relationship back to User
    user = relationship("User", back_populates="appointments")

# 3) Create tables if they don't exist
Base.metadata.create_all(engine)
session = SessionLocal()

# --- Session State Initialization ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_email" not in st.session_state:
    st.session_state.user_email = ""
if "conversation" not in st.session_state or not isinstance(st.session_state.conversation, list):
    st.session_state.conversation = []
if "appointments" not in st.session_state:
    st.session_state.appointments = []


# IMPORTANT: Initialize chat_input BEFORE creating the widget
if "chat_input" not in st.session_state:
    st.session_state.chat_input = ""

def clear_audio_files():
    for file in glob.glob("*.mp3"):
        try:
            os.remove(file)
        except Exception as e:
            st.error(f"Error removing file {file}: {e}")


# --- Main Title ---
st.title("AI Receptionist")

# --- Sidebar for Navigation ---
page_options = ["Sign Up", "Login", "Chat", "Book Appointment"]
choice = st.sidebar.selectbox("Navigate", page_options)

# --- SIGN UP PAGE ---
if choice == "Sign Up":
    st.subheader("Create a New Account (with optional face)")

    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    # Use st.camera_input or st.file_uploader for face capture
    face_image = st.camera_input("Capture your face (optional)")

    if st.button("Sign Up"):
        if not email or not password:
            st.warning("Please enter email & password.")
        else:
            # 1. If face_image is provided, encode it
            face_encoding_bytes = None
            if face_image is not None:
                # Convert to numpy array for face_recognition
                img = face_recognition.load_image_file(face_image)
                encodings = face_recognition.face_encodings(img)
                if len(encodings) > 0:
                    face_encoding = encodings[0]
                    face_encoding_bytes = face_encoding.tobytes()
                else:
                    st.warning("No face detected. Your account will be created without face data.")

            # 2. Call signup_user from auth
            success = signup_user(email, password, face_encoding_bytes)
            if success:
                st.success("User created successfully! Please log in.")
            else:
                st.error("User with that email already exists. Try a different one.")

# --- LOGIN PAGE ---
elif choice == "Login":
    st.subheader("Login to Your Account")

    # Let user pick login method
    login_mode = st.radio("Choose login method", ["Email + Password", "Face"])

    if login_mode == "Email + Password":
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        if st.button("Login"):
            if login_user(email, password):
                st.session_state.logged_in = True
                st.session_state.user_email = email
                clear_audio_files()  # Clear old audio files
                st.success("Login successful!")
            else:
                st.error("Invalid email or password.")

    else:  # Face login
        email = st.text_input("Email (for face matching)")
        # Alternatively, do a "who is this face?" by matching DB encodings, but we keep it simpler here
        face_image = st.camera_input("Capture your face")

        if st.button("Login with Face"):
            if email and face_image is not None:
                img = face_recognition.load_image_file(face_image)
                encodings = face_recognition.face_encodings(img)
                if len(encodings) > 0:
                    new_encoding = encodings[0]
                    # Compare with DB
                    if login_user_with_face(email, new_encoding):
                        st.session_state.logged_in = True
                        st.session_state.user_email = email
                        clear_audio_files()  # Clear old audio files
                        st.success("Face login successful!")
                        
                    else:
                        st.error("Face login failed: no match or user doesn't have face data.")
                else:
                    st.error("No face detected in the captured image.")
            else:
                st.warning("Please provide email and capture your face.")

# --- CHAT PAGE ---
elif choice == "Chat":
    if not st.session_state.logged_in:
        st.warning("You must log in before you can chat.")
    else:
        #clear_audio_files()  # Clear old audio files
        st.subheader(f"Welcome, {st.session_state.user_email}!")
        st.write("Feel free to chat with AI Receptionist. Type 'exit' to clear conversation.")

        # Display conversation
        st.write("---")
        for idx, msg in enumerate(st.session_state.conversation):
            if isinstance(msg, dict) and "type" in msg and "text" in msg:
                if msg["type"] == "user":
                    st.markdown(f"**User:** {msg['text']}")
                elif msg["type"] == "ai":
                    st.markdown(f"**AI:** {msg['text']}")
                    if "audio" in msg:
                        st.audio(msg["audio"], format="audio/mp3")
            # else:
            #     st.error(f"Invalid message format in conversation at index {idx}: {msg}")
        st.write("---")


        # Create the text input widget with key="chat_input"
        user_input = st.text_input("Enter your message:", key="chat_input")

        if st.button("Send"):
            if user_input.strip() == "":
                st.warning("Please enter a message.")
            else:
                # If user types 'exit', clear conversation
                if user_input.lower().strip() == "exit":
                    st.session_state.conversation = []
                    st.info("Conversation cleared.")
                else:
                  st.session_state.conversation.append({"type": "user", "text": user_input})
                  #Append user message to conversation
                  if os.path.exists("ai_response.mp3"):
                      os.remove("ai_response.mp3")

                  st.session_state.conversation.append(f"User: {user_input}")

                  # Configure the API key from your environment variables
                  genai.configure(api_key=GEMINI_API_KEY)

                  # Create the model with custom generation settings
                  generation_config = {
                  "temperature": 1,
                  "top_p": 0.95,
                  "top_k": 40,
                  "max_output_tokens": 8192,
                  "response_mime_type": "text/plain",
                  }

                  # Instantiate a GenerativeModel
                  model = genai.GenerativeModel(
                  model_name="gemini-2.0-flash-exp",
                  generation_config=generation_config,
                  )

                  # Start the chat session with a role-play scenario
                  chat_session = model.start_chat(
                  history=[
                  {
                    "role": "user",
                    "parts": [
                        "You are an AI Hospital Receptionist. Your job is to analyse the patient's "
                        "symptoms and redirect to a specialist doctor. You can ask questions to the patient to "
                        "gather more information. Guide them on the next steps to be taken and tell which doctor to meet. "
                        "Suggest which tests are to be done and the specialist to be consulted."
                        "Remember to be empathetic and supportive; and be very friendly. Finally tell the user to book the "
                        "appointment in our website under the 'Book Appointment' section."
                    ],
                  },
                  {
                    "role": "model",
                    "parts": [
                        "Okay, I understand. I'm ready to help. Please, tell me what's been going on. "
                        "What symptoms are you experiencing? The more details you can give me, the better "
                        "I can understand what might be happening. Don't worry, I'm here to listen and "
                        "help you figure this out.\n"
                    ],
                  },
                  ]
                  )

                  # Send the user's new message to the model
                  response = chat_session.send_message(user_input)

                  # Append AI's response to conversation
                  st.session_state.conversation.append(f"AI: {response.text}")
                  ai_reply = response.text
                  ai_reply_clean = ai_reply.replace("*", "")
                  # Convert AI response to speech
                  audio_file_path = f"response_{len(st.session_state.conversation)}.mp3"
                  tts = gTTS(ai_reply)
                  tts.save(audio_file_path)

                  st.session_state.conversation.append({"type": "ai", "text": ai_reply, "audio": audio_file_path})



                #   try:
                #       ai_reply = response.text
                #       ai_reply_clean = ai_reply.replace("*", "")
                #       tts = gTTS(ai_reply_clean)
                #       audio_file_path = "ai_response.mp3"
                #       tts.save(audio_file_path)
                #       if os.path.exists(audio_file_path):
                #         audio_url = f"data:audio/mp3;base64,{open(audio_file_path, 'rb').read().hex()}"
                #         autoplay_html = f"""
                #             <audio autoplay>
                #                 <source src="{audio_url}" type="audio/mp3">
                #             </audio>
                #         """
                #         components.html(autoplay_html)
                #   except Exception as e:
                #       st.error(f"Error generating audio: {e}")

                      # Check if the file exists
                #       if os.path.exists(audio_file_path):
                #           # Stream the audio to the browser
                #           #st.audio(audio_file_path, format="audio/mp3")
                #           st_player(audio_file_path, playing=True, loop=False)
                #       else:
                #           st.error("Audio file not found.")
                #   except Exception as e:
                #       st.error(f"Error generating audio: {e}")

                #   ai_reply = response.text
                #   ai_reply_clean = ai_reply.replace("*", "")
                #   tts = gTTS(ai_reply_clean)
                #   tts.save("ai_response.mp3")
                #   pygame.mixer.init()
                #   # Load and play the audio file
                #   pygame.mixer.music.load("ai_response.mp3")
                #   pygame.mixer.music.play()
                #   # Wait for playback to finish
                #   while pygame.mixer.music.get_busy():
                #       continue
                #   pygame.mixer.quit()
                #   st.audio("ai_response.mp3", format="audio/mp3")

                  # Reset text input, then rerun so the widget re-initializes
                  #st.session_state.chat_input = "---"
                st.experimental_rerun()
        

elif choice == "Book Appointment":
    if not st.session_state.logged_in:
        st.warning("You must log in before booking an appointment.")
    else:
        st.subheader("Book an Appointment")

        st.write("---")
        st.write("**Schedule a new appointment**")

        # Example list of specialists (in real app, might query from DB)
        specialists = ["Cardiologist", "Neurologist", "Dermatologist", "Orthopedist", "Pediatrician"]

        with st.form("appointment_form"):
            specialist = st.selectbox("Select a Specialist", specialists)
            date = st.date_input("Select Date")
            time_slot = st.selectbox("Select Time Slot", ["09:00 AM", "10:00 AM", "11:00 AM", "02:00 PM", "04:00 PM"])

            confirm_btn = st.form_submit_button("Book Appointment")

        if confirm_btn:
            # In production, you'd also check if the slot is available, handle conflicts, etc.
            appointment_info = {
                "specialist": specialist,
                "date": date.strftime("%Y-%m-%d"),
                "time": time_slot
            }
            st.session_state.appointments.append(appointment_info)
            booked_appt = book_appointment(get_user_id_by_email(st.session_state.user_email), specialist, date.strftime("%Y-%m-%d"), time_slot)
            st.success(f"Appointment booked with {specialist} on {appointment_info['date']} at {time_slot}! \n Booking ID: {booked_appt.id}")  
            user_appointments = session.query(Appointment).filter_by(user_id=get_user_id_by_email(st.session_state.user_email)).all()

            # 2) Display them right here in the Login page
            if user_appointments:
                st.write("## Your Current Appointments:")
                for i, appt in enumerate(user_appointments, start=1):
                    st.write(
                        f"{i}. [ID: {appt.id}] {appt.specialist} on {appt.date} at {appt.time_slot}"
                    )
            else:
                st.info("No appointments found for this user.")  

        # Option to log out
        if st.button("Log Out"):
            st.session_state.logged_in = False
            st.session_state.user_email = ""
            st.session_state.conversation = []
            st.experimental_rerun()
