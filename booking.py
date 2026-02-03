import pickle
import re
import os
import auth

BOOKING_URL = "https://rbs.singaporetech.edu.sg/SRB001/SearchSRB001List"
CHECK_AVAILABILITY_URL = "https://rbs.singaporetech.edu.sg/SRB001/GetTimeSlotListByresidNdatetime"
GET_ALL_ROOMS_URL = "https://rbs.singaporetech.edu.sg/MRB002/ResourceReload"
DATE = "05 Feb 2026"
CONFIRM_URL = "https://rbs.singaporetech.edu.sg/SRB001/NormalBookingConfirmation"
FINALIZE_URL = "https://rbs.singaporetech.edu.sg/SRB001/BookingSaving"
START_URL = "https://rbs.singaporetech.edu.sg/SRB001/SRB001Page"

class BookingSystem:
    def __init__(self):
        self.available_slots: dict[str, list[dict[str, str]]|str] = {}
        self.room_list: list[dict[str, str]] = []
        self.mapping: dict[str, str] = {}
        self.session = None
        self.token = None
        self.is_session_cached = False
    
    def load_session(self):
        try:
            with open("auth_session.pkl", "rb") as f:
                session = pickle.load(f)
            response = session.get(START_URL)
            if bool(re.search("Your session may have expired", response.text)):
                print("[-] Session has expired. Please re-authenticate.")
                raise Exception("Session expired")
            self.session = session
            self.is_session_cached = True
            print("[*] Session loaded successfully.")
        except (FileNotFoundError, pickle.UnpicklingError):
            print("[-] No valid session found. Please authenticate first.")
            return None
        except Exception:
            print("[-] Session has expired")
            print("[*] Creating new session")
            username = os.getenv("USERNAME")
            password = os.getenv("PASSWORD")
            if username is None or password is None:
                print("[-] USERNAME or PASSWORD environment variables not set.")
                return None
            session = auth.login(username, password)
            with open("auth_session.pkl", "wb") as f:
                pickle.dump(session, f)
            self.session = session
        return self.session

    def load_token(self):
        if self.is_session_cached:
            with open("token.pkl", "rb") as f:
                token = pickle.load(f)
            self.token = token
        else:
            if self.session is None:
                print("[-] Session is not initialized.")
                return None
            token = auth.get_verification_tokens(self.session)
            if not token:
                print("[-] Could not retrieve verification token.")
                return None
            self.token = token
            with open("token.pkl", "wb") as f:
                pickle.dump(token, f)
        return self.token