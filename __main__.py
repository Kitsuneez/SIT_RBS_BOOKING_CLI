"""
Main module for SIT Room Booking System.
Handles user authentication, room search, availability check, and booking.
"""
import json
import os
import sys
import requests
import pickle

from auth import get_verification_tokens, login

BOOKING_URL = "https://rbs.singaporetech.edu.sg/SRB001/SearchSRB001List"
CHECK_AVAILABILITY_URL = "https://rbs.singaporetech.edu.sg/SRB001/GetTimeSlotListByresidNdatetime"
DATE = "25 Feb 2026"
CONFIRM_URL = "https://rbs.singaporetech.edu.sg/SRB001/NormalBookingConfirmation"
FINALIZE_URL = "https://rbs.singaporetech.edu.sg/SRB001/BookingSaving"

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

ls_dict = []
available_slots = []


def menu():
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
            return
        case _:
            print("\nInvalid choice. Please run the program again.")
            return


def load_session():
    """
    Load saved session from file.

    :return: Session object or None
    """
    # try:
    #     with open("auth_session.pkl", "rb") as f:
    #         print("[*] Loading saved session...")
    #         session = pickle.load(f)
    # except Exception:
    #     print("[*] No saved session found. Logging in...")
    #     session = login(os.getenv("USERNAME"), os.getenv("PASSWORD"))
    #     with open("auth_session.pkl", "wb") as f:
    #         pickle.dump(session, f)
    session = login(os.getenv("USERNAME"), os.getenv("PASSWORD"))
    with open("auth_session.pkl", "wb") as f:
        pickle.dump(session, f)
    return session

def main():
    """
    Main function to handle authentication, token retrieval, room search, and booking.
    """
    session = load_session()
    if not session:
        print("[-] Could not establish a session.")
        sys.exit(1)
    token = get_verification_tokens(session)
    if not token:
        print("[-] Could not retrieve verification tokens.")
        sys.exit(1)
    print("[*] Session and tokens are ready for booking operations.")
    menu()

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
        rooms = None
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
        display_rooms(rooms)
        if not ls_dict:
            print("\nNo rooms available.")
        else:
            room_num = input("\nEnter room number to check availability: ").strip()
            check_availability(room_num, token, session)

            if available_slots:
                booking(token,session)
            else:
                print("\nNo available slots for this room.")

def booking(token, session):
    print(f"\n{'='*60}")
    book = input(
        "Do you want to book slots? (Y/n): ").strip().lower()

    if book in ['y', 'Y', '']:
        slot_input = input(
            "Enter slot numbers to book (comma-separated, e.g., 0,1,2) \
or ('-' for a range, e.g., 0-2): ").strip()
        try:
            if '-' in slot_input:
                start, end = map(int, slot_input.split('-'))
                slot_indices = list(range(start, end + 1))
            else:
                slot_indices = [int(x.strip()) for x in slot_input.split(',')]
            confirm_booking(slot_indices, token, session)
        except ValueError:
            print("Invalid input. Please enter numbers separated by commas.")
            # to do handle invalid input better
    else:
        print("Returning to room selection...")


def check_availability(num, token, session):
    """
    Check room availability for a given room number.

    :param num: Room number as string
    :param token: Verification token string
    """
    avail_payload = {
        "__RequestVerificationToken": token,
        "rsrcID": ls_dict[int(num)]["RSRC_ID"],
        "rsrcTypID": ls_dict[int(num)]["RSRC_TYP_ID"],
        "bookingstatus": "Available",
        "SearchDate": DATE,
        "SearchStartTime": "07:00",
        "SearchEndTime": "22:00",
        "BKG_RUL": "true",
        "IS_SLD_Resource": "false",
    }
    try:
        print(f"\nChecking availability for room {num}...")
        response = session.post(CHECK_AVAILABILITY_URL, data=avail_payload)
        response.raise_for_status()
        if response.text.strip().startswith('['):
            slots_data = response.json()
            print(f"\n{'='*60}")
            print(f"Available Time Slots for {DATE}")
            print(f"{'='*60}")

            for slot in slots_data:
                if slot['SLT_STATUS'] == 1:
                    available_slots.append({
                        'rsrc_id': ls_dict[int(num)]["RSRC_ID"],
                        'rsrc_typ_id': ls_dict[int(num)]["RSRC_TYP_ID"],
                        'time': slot['SLT_Desc'],
                        'datetime': slot['SLT_Date_Time'],
                        'canBooked': slot['canBooked'],
                        'slot_id': slot['SLT_ID']
                    })
            # Display in a nice format
            for i, slot in enumerate(available_slots):
                print(f"{i:2d}. {slot['time']}")
        else:
            print(f"Response: {response.text}")

    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")
    except json.JSONDecodeError as e:
        print(f"JSON decode error: {e}")
        print(f"Response text: {response.text}")

def display_rooms(rooms):
    # prints the room and rsrc_id
    print("============Available Rooms===============")
    print("No.|Resource ID | Resource Name")
    for i, res in enumerate(rooms):
        ls_dict.append({
            "RSRC_ID": res['RSRC_ID'],
            "RSRC_TYP_ID": res['RSRC_TYP_ID']
        })
        print(f"{i:2d} | {res['RSRC_ID']} | {res['RSRC_NAME']}")


def confirm_booking(slot_indices, token, session):
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
        if idx < len(available_slots):
            slot = available_slots[idx]
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

    # Get resource info from first selected slot
    first_slot = available_slots[slot_indices[0]]

    booking_payload = {
        "__RequestVerificationToken": token,
        "RSRC_ID": first_slot['rsrc_id'],
        "RSRC_TYP_ID": first_slot['rsrc_typ_id'],
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
                "RSRC_TYP_ID": first_slot['rsrc_typ_id'],
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


if __name__ == "__main__":
    main()
