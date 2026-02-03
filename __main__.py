"""
Main module for SIT Room Booking System.
Handles user authentication, room search, availability check, and booking.
"""
import json
import os
import re
import sys
import pickle
import requests

from auth import get_verification_tokens, login
from booking import BookingSystem


class SessionExpiredError(Exception):
    """Raised when the authentication session has expired."""


BOOKING_URL = "https://rbs.singaporetech.edu.sg/SRB001/SearchSRB001List"
CHECK_AVAILABILITY_URL = "https://rbs.singaporetech.edu.sg/SRB001/GetTimeSlotListByresidNdatetime"
GET_ALL_ROOMS_URL = "https://rbs.singaporetech.edu.sg/MRB002/ResourceReload"
DATE = "05 Feb 2026"
CONFIRM_URL = "https://rbs.singaporetech.edu.sg/SRB001/NormalBookingConfirmation"
FINALIZE_URL = "https://rbs.singaporetech.edu.sg/SRB001/BookingSaving"
START_URL = "https://rbs.singaporetech.edu.sg/SRB001/SRB001Page"


headers = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko)\
          Chrome/142.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-GB,en;q=0.6",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "https://rbs.singaporetech.edu.sg",
    "Referer": "https://rbs.singaporetech.edu.sg/SRB001/SRB001Page",
}


available_slots: dict[str, list[dict[str, str]]] = {}
ls_dict: list[dict[str, str]] = []


def menu() -> None:
    """
    Display the main menu and handle user choices.

    :param token: Verification token string
    :param session: Authenticated session object
    """
    print("\n" + "="*60)
    print("SIT Room Booking System")
    print("="*60)
    print("\nOptions:")
    print("1. Search and book a room")
    print("2. Exit")
    print("="*60)
    choice = input("\nEnter your choice (1-2): ").strip()
    match choice:
        case "1":
            return
        case "2":
            print("\nExiting... Goodbye!")
            sys.exit(0)
        case _:
            print("\nInvalid choice. Please run the program again.")
            return

def check_session(session: requests.Session) -> bool:
    """
    Check if the current session is still valid.
    
    :param session: Active session object
    :type session: requests.Session
    :return: True if session is expired, False otherwise
    :rtype: bool
    """
    response = session.get(START_URL)
    return bool(re.search("Your session may have expired", response.text))

def load_session() -> tuple[requests.Session | None, bool]:
    """
    Load saved session from file.

    :return: Tuple of (Session object or None, is_cached flag)
    """
    try:
        with open("auth_session.pkl", "rb") as f:
            print("[*] Loading saved session...")
            session = pickle.load(f)
        if check_session(session):
            raise SessionExpiredError("[-] Session has expired.")
        return session, True
    except (FileNotFoundError, pickle.UnpicklingError, OSError, SessionExpiredError) as e:
        print(f"[-] Could not load session: {e}")
    print("[*] Creating new session...")
    username = os.getenv("USERNAME")
    password = os.getenv("PASSWORD")
    if username is None or password is None:
        print("[-] USERNAME or PASSWORD environment variables not set.")
        sys.exit(1)
    session = login(username, password)
    with open("auth_session.pkl", "wb") as f:
        pickle.dump(session, f)
    return session, False

def load_token(session: requests.Session, is_session_cached: bool) -> str | None:
    """
    Load saved verification token from file.

    :param session: Active session object
    :param is_session_cached: Whether the session was loaded from cache
    :return: Verification token string or None
    """
    try:
        if is_session_cached:
            with open("token.pkl", "rb") as f:
                print("[*] Loading saved verification token...")
                token = pickle.load(f)
            return token
        raise SessionExpiredError("Session was renewed, need new token.")
    except (SessionExpiredError, FileNotFoundError, pickle.UnpicklingError, OSError) as e:
        print(f"[-] Could not load verification token: {e}")
    print("[*] Retrieving new verification token...")
    token = get_verification_tokens(session)
    with open("token.pkl", "wb") as f:
        pickle.dump(token, f)
    return token

def main():
    """
    Main function to handle authentication, token retrieval, room search, and booking.
    """
    session, is_cached = load_session()
    if not session:
        print("[-] Could not establish a session.")
        sys.exit(1)
    token = load_token(session, is_cached)
    if not token:
        print("[-] Could not retrieve verification tokens.")
        sys.exit(1)
    print("[*] Session and tokens are ready for booking operations.")
    menu()

    # bookingSystem = BookingSystem()
    # session = bookingSystem.load_session()
    # token = bookingSystem.load_token()

    payload = {
        "__RequestVerificationToken": token,
        "CapacityOperator": "<",
        "SingleCapacity": "",
        "MinCapacity": "",
        "MaxCapacity": "",
        "campusID": "",
        "buildingID": "",
        "bookingstatus": "Available",
        "faciequip": "facilities",
        "BookingStatus": "Available",
        "Search": "",
        "ResourceType": "Discussion Room",
        "LocationID": ""
    }

    try:
        response = session.post(BOOKING_URL, data=payload)
        response.raise_for_status()
        print(f"Status code: {response.status_code}")
        rooms: list[dict[str, str]] = []
        # Try to parse as JSON if it looks like JSON
        if response.text.strip().startswith('{') or response.text.strip().startswith('['):
            rooms = response.json()
    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")
        return
    except json.JSONDecodeError as e:
        print(f"JSON decode error: {e}")
        return
    while True:
        map_rooms(rooms)

        # room_num = input("\nEnter room number to check availability: ").strip()
        check_availability(token, session)

        if available_slots:
            booking(token,session)
        else:
            print("\nNo available slots for this room.")
            sys.exit(1)

def booking(token, session):
    """
    confirms with user if they want to book slots from this room
    
    :param token: Verification token string
    :param session: Active session object
    """
    print(f"\n{'='*60}")
    room_name = input("Enter room name (E2-XX-XXX-DRXXX): ").strip().upper()
    slot_input = input(
            "Enter slot numbers to book (comma-separated, e.g., 0,1,2) \
or ('-' for a range, e.g., 0-2): ").strip()
    try:
        if '-' in slot_input:
            start, end = map(int, slot_input.split('-'))
            slot_indices = list(range(start, end + 1))
        else:
            slot_indices = [int(x.strip()) for x in slot_input.split(',')]
        confirm_booking(room_name, slot_indices, token, session)
    except ValueError:
        print("Invalid input. Please enter numbers separated by commas.")


def check_availability(token, session):
    """
    Check room availability for a given room number.

    :param num: Room number as string
    :param token: Verification token string
    """
    resourceList = []
    for d in ls_dict:
        resourceList.append({
            "RSRC_ID": d["RSRC_ID"],
            "IS_SLD": False,
            "Event_Type": 0,
            "Disclaimer": "Photo is a sample/illustration for typical DR layout."
        })
    with open("mapping.json", "r", encoding="utf-8") as f:
        mapping = json.load(f)
    try:
        parameter = [{
            "MRB002Date": "04 Feb 2026",
            "MRB002StartTime": "07:00",
            "MRB002EndTime": "22:00",
            "ResourceList": resourceList[:9]
        }]
        avail_payload = {
            "__RequestVerificationToken": token,
            "bookingstatus": "Available",
            "parameter": json.dumps(parameter),
            "_rsrcCat": "facilities"
        }
        # print(f"\nChecking availability for room {num}...")
        response = session.post(GET_ALL_ROOMS_URL, data=avail_payload)
        response.raise_for_status()
        html = response.text
        rooms = []
        room_blocks = re.findall(r'<div class="card fa-sm">[\s\S]*?(?=<div class="card fa-sm">|$)',
            html
        )

        for block in room_blocks:
            name_match = re.search(
                r'<span class="d-block d-md-none font-weight-bold">Name:</span>\s*([A-Z0-9\-]+)',
                block
            )

            if not name_match:
                continue

            name = name_match.group(1)

            slots = re.findall(
                r"data-sltid=([a-f0-9\-]+)[\s\S]*?class='time-slot-white[\s\S]*?>\s*(\d{2}:\d{2}-\d{2}:\d{2})",
                block
            )

            rooms.append({
                name: slots
            })

        for room in rooms:
            #displays room with available slots and store into available_slots dict
            for room_name, slots in room.items():
                if slots:
                    available_slots[room_name] = []
                    for slot in slots:
                        available_slots[room_name].append({
                            "slot_id": slot[0],
                            "time": slot[1],
                            "rsrc_id": mapping[room_name],
                            "rsrc_typ_id": ls_dict[0]["RSRC_TYP_ID"]
                        })
                    print(f"\nAvailable slots for room {room_name}:")
                    for i, slot in enumerate(available_slots[room_name]):
                        print(f"  [{i}] {slot['time']}")

    except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
        print(f"An error occurred: {e}")

def map_rooms(rooms: list[dict[str, str]]) -> None:
    """
    Display available rooms in a formatted table.

    :param rooms: List of room dictionaries
    """
    # prints the room and rsrc_id
    for _, res in enumerate(rooms):
        ls_dict.append({
            "RSRC_ID": res['RSRC_ID'],
            "RSRC_TYP_ID": res['RSRC_TYP_ID']
        })
    with open("mapping.json", "w", encoding="utf-8") as f:
        json.dump({res["RSRC_NAME"]: res["RSRC_ID"] for res in rooms}, f, indent=4)


def confirm_booking(room_name, slot_indices, token, session):
    """
    Book multiple consecutive time slots
    slot_indices: list of slot numbers to book (e.g., [0, 1] for first two slots)
    """
    if not available_slots:
        print("No slots available. Check availability first.")
        return
    # Build the slot list for booking
    slot_list = []
    for i, idx in enumerate(slot_indices):
        if idx < len(available_slots[room_name]):
            slot = available_slots[room_name][idx]
            slot_list.append({
                "SRNO": i + 1,
                "SLT_ID": slot['slot_id'],
                "SLT_Time": slot['time'].split('-')[0],  # Get start time
                "SLT_Desc": slot['time'],
                "encryptedSlotStatus": None,
                "SLT_STATUS": 1,
                "encryptedSLT_Time": None
            })

    if not slot_list:
        print("Invalid slot selection")
        return
    first_slot = available_slots[room_name][slot_indices[0]]["rsrc_id"]

    booking_payload = {
        "__RequestVerificationToken": token,
        "RSRC_ID": first_slot,
        "RSRC_TYP_ID": ls_dict[0]["RSRC_TYP_ID"],
        "SearchDate": DATE,
        "SlotList": json.dumps(slot_list),
        "APPRV_EXEMP": "false",
        "SUPPT_EXEMP": "false",
        "checkReorNot": "0",
        "IS_IN4SIT": "false",
        "IS_SUPT": "false",
        "IS_APPRVL": "false"
    }

    try:
        print(f"\n{'='*60}")
        print(f"Confirming booking for {len(slot_list)} slot(s)...")
        print(f"{'='*60}")
        print(f"Slots to book: {[s['SLT_Desc'] for s in slot_list]}")

        response = session.post(CONFIRM_URL, data=booking_payload)
        response.raise_for_status()

        if response.status_code == 200:
            print("[*] Finalizing booking...")
            payload = {
                "__RequestVerificationToken": token,
                "RSRC_TYP_ID": first_slot,
                "NUM_ATTND": "1",
                "Event_TypeText": "",
                "Acad_Text": "",
                "Purpose": "Study",
                "supptList": "[]",
                "OVERWRITE": "0",
                "slcPurpose": ""
            }
            response = session.post(FINALIZE_URL, data=payload)
            response.raise_for_status()
            if response.status_code == 200:
                print("Booking finalized successfully.")
                sys.exit(0)
            else:
                print(f"Failed to finalize booking. Status code: {response.status_code}")

    except requests.exceptions.RequestException as e:
        print(f"Booking failed: {e}")
        print("Checking your remaining booking hours")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nExiting... Goodbye!")
        sys.exit(0)
