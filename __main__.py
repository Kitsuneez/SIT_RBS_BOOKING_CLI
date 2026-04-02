"""
Main module for SIT Room Booking System.
Handles user authentication, room search, availability check, and booking.
"""

import asyncio
import json
import os
import re
import sys
import aiohttp
import requests

from auth import get_verification_tokens, login


class SessionExpiredError(Exception):
    """Raised when the authentication session has expired."""


DATE = "04 Apr 2026"
BOOKING_URL = "https://rbs.singaporetech.edu.sg/SRB001/SearchSRB001List"
CHECK_AVAILABILITY_URL = (
    "https://rbs.singaporetech.edu.sg/SRB001/GetTimeSlotListByresidNdatetime"
)
GET_ALL_ROOMS_URL = "https://rbs.singaporetech.edu.sg/MRB002/ResourceReload"
CONFIRM_URL = "https://rbs.singaporetech.edu.sg/SRB001/NormalBookingConfirmation"
FINALIZE_URL = "https://rbs.singaporetech.edu.sg/SRB001/BookingSaving"
START_URL = "https://rbs.singaporetech.edu.sg/SRB001/SRB001Page"
BATCH_SIZE = 10
SESSION_POOL_SIZE = 4
REQUEST_TIMEOUT_SECONDS = 12
MAPPING_FILE = "mapping.json"


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
room_mapping: dict[str, str] = {}


def get_rsrc_typ_id() -> str:
    """Return the active room type id for booking payloads."""
    if not ls_dict:
        return ""
    return str(ls_dict[0].get("RSRC_TYP_ID", ""))


def get_credentials() -> tuple[str, str]:
    """Load account credentials from environment variables."""
    username = os.getenv("USERNAME")
    password = os.getenv("PASSWORD")
    if username is None or password is None:
        print("[-] USERNAME or PASSWORD environment variables not set.")
        sys.exit(1)
    return username, password


def fetch_rooms(session: requests.Session, token: str) -> list[dict[str, str]]:
    """
    Fetch room metadata required for availability checks.

    :param session: Active authenticated requests session
    :param token: Verification token string
    :return: List of room metadata dictionaries
    """
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
        "LocationID": "",
    }

    response = session.post(BOOKING_URL, data=payload)
    response.raise_for_status()
    if response.text.strip().startswith("{") or response.text.strip().startswith("["):
        return response.json()
    return []


def load_room_mapping() -> None:
    """Load room->resource id mapping from mapping.json into runtime structures."""
    try:
        with open(MAPPING_FILE, "r", encoding="utf-8") as f:
            loaded = json.load(f)
    except (OSError, json.JSONDecodeError):
        print(f"[-] Failed to load valid room mapping from {MAPPING_FILE}")
        sys.exit(1)

    if not isinstance(loaded, dict) or not loaded:
        print(f"[-] Room mapping in {MAPPING_FILE} is empty or invalid")
        sys.exit(1)

    room_mapping.update({str(room): str(rsrc_id) for room, rsrc_id in loaded.items()})

    ls_dict.extend(
        {"RSRC_ID": rsrc_id, "RSRC_TYP_ID": ""}
        for rsrc_id in room_mapping.values()
    )


def hydrate_resource_type(rooms: list[dict[str, str]]) -> None:
    """Populate RSRC_TYP_ID for booking payloads from fetched room metadata."""
    typ_id = next((str(r.get("RSRC_TYP_ID", "")) for r in rooms if r.get("RSRC_TYP_ID")), "")
    if not typ_id:
        return

    for item in ls_dict:
        item["RSRC_TYP_ID"] = typ_id


def create_new_session_with_token(
    username: str, password: str
) -> tuple[requests.Session, str] | None:
    """Create a fresh authenticated session and its verification token."""
    session = login(username, password)
    if not session:
        return None
    token = get_verification_tokens(session)
    if not token:
        return None
    return session, token


async def build_session_pool() -> list[tuple[requests.Session, str]]:
    """Build a pool of authenticated sessions for availability requests."""
    username, password = get_credentials()
    if SESSION_POOL_SIZE <= 0:
        print("[-] Invalid session pool size; forcing single session.")
        return []

    creation_tasks = [
        asyncio.to_thread(create_new_session_with_token, username, password)
        for _ in range(SESSION_POOL_SIZE)
    ]

    print(f"[*] Creating {SESSION_POOL_SIZE} fresh session(s)...")
    created = await asyncio.gather(*creation_tasks, return_exceptions=True)
    print("sessions created")
    pool: list[tuple[requests.Session, str]] = []
    for item in created:
        if isinstance(item, BaseException) or item is None:
            continue
        if not isinstance(item, tuple) or len(item) != 2:
            continue
        pool.append(item)

    if not pool:
        print("[-] Could not create any authenticated sessions.")
        return []

    print(f"[*] Availability session pool size: {len(pool)}")
    return pool


async def main_async():
    """
    Main function to handle authentication, token retrieval, room search, and booking.
    """
    session_pool = await build_session_pool()
    if not session_pool:
        sys.exit(1)

    load_room_mapping()

    session, token = session_pool[0]
    print("[*] Session and tokens are ready for booking operations.")
    try:
        rooms = await asyncio.to_thread(fetch_rooms, session, token)
        hydrate_resource_type(rooms)
        if not get_rsrc_typ_id():
            print("[-] Failed to determine resource type ID from room metadata.")
            sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")
        return
    except json.JSONDecodeError as e:
        print(f"JSON decode error: {e}")
        return

    await check_availability_async(session_pool)
    if available_slots:
        booking(token, session)
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
or ('-' for a range, e.g., 0-2): "
    ).strip()
    try:
        if "-" in slot_input:
            start, end = map(int, slot_input.split("-"))
            slot_indices = list(range(start, end + 1))
        else:
            slot_indices = [int(x.strip()) for x in slot_input.split(",")]
        confirm_booking(room_name, slot_indices, token, session)
    except ValueError:
        print("Invalid input. Please enter numbers separated by commas.")


async def fetch_availability_batch(session, token, resource_batch, mapping):
    """
    Fetch availability for a batch of resources asynchronously.

    :param session: Active aiohttp session
    :param token: Verification token string
    :param resource_batch: List of resource dictionaries
    :param mapping: Room name to RSRC_ID mapping dictionary
    :return: Dictionary of room names to available slots
    """
    parameter = [
        {
            "MRB002Date": DATE,
            "MRB002StartTime": "07:00",
            "MRB002EndTime": "22:00",
            "ResourceList": resource_batch,
        }
    ]

    payload = {
        "__RequestVerificationToken": token,
        "bookingstatus": "Available",
        "parameter": json.dumps(parameter),
        "_rsrcCat": "facilities",
    }
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
    html = ""
    async with session.post(GET_ALL_ROOMS_URL, data=payload, timeout=timeout) as resp:
        resp.raise_for_status()
        html = await resp.text()
    results = {}

    blocks = re.findall(
        r'<div class="card fa-sm">[\s\S]*?(?=<div class="card fa-sm">|$)', html
    )

    for block in blocks:
        name_match = re.search(
            r'<span class="d-block d-md-none font-weight-bold">Name:</span>\s*([A-Z0-9\-]+)',
            block,
        )
        if not name_match:
            continue

        room = name_match.group(1)
        slots = re.findall(
            r"data-sltid=([a-f0-9\-]+)[\s\S]*?>\s*(\d{2}:\d{2}-\d{2}:\d{2})", block
        )

        if slots:
            results[room] = [
                {
                    "slot_id": s[0],
                    "time": s[1],
                    "rsrc_id": mapping[room],
                    "rsrc_typ_id": get_rsrc_typ_id(),
                }
                for s in slots
            ]

    return results


async def check_availability_async(session_pool: list[tuple[requests.Session, str]]):
    """
    Asynchronously check room availability and display available slots.

    :param token: Verification token string
    :param requests_session: Active session object
    """
    resource_list = [
        {
            "RSRC_ID": d["RSRC_ID"],
            "IS_SLD": False,
            "Event_Type": 0,
            "Disclaimer": "Sample layout",
        }
        for d in ls_dict
    ]

    aiohttp_sessions: list[tuple[aiohttp.ClientSession, str]] = []
    results = []
    try:
        for requests_session, token in session_pool:
            jar = aiohttp.CookieJar()
            for c in requests_session.cookies:
                if c.value is not None:
                    jar.update_cookies({c.name: c.value})
            connector = aiohttp.TCPConnector()
            aiohttp_sessions.append(
                (
                    aiohttp.ClientSession(
                        headers=headers, cookie_jar=jar, connector=connector
                    ),
                    token,
                )
            )

        tasks = []
        for batch_index, i in enumerate(range(0, len(resource_list), BATCH_SIZE)):
            batch = resource_list[i : i + BATCH_SIZE]
            session_index = batch_index % len(aiohttp_sessions)
            aio_session, session_token = aiohttp_sessions[session_index]
            tasks.append(
                asyncio.create_task(
                    fetch_availability_batch(
                        aio_session, session_token, batch, room_mapping
                    )
                )
            )

        gathered = await asyncio.gather(*tasks, return_exceptions=True)
        results = []
        for result in gathered:
            if isinstance(result, BaseException):
                print(f"[!] Availability check error: {result}")
                continue
            results.append(result)
    finally:
        await asyncio.gather(
            *(s.close() for s, _ in aiohttp_sessions), return_exceptions=True
        )

    for batch in results:
        for room, slots in batch.items():
            if slots:
                available_slots[room] = slots


    total_slots = sum(len(slots) for slots in available_slots.values())
    print(
        f"[*] Availability summary: rooms_checked={len(resource_list)}, "
        f"rooms_with_slots={len(available_slots)}, total_slots={total_slots}"
    )
    print_availability_table()


def print_availability_table() -> None:
    """Render room availability in a compact table format."""
    if not available_slots:
        print("\nNo room availability to display.")
        return

    rows: list[tuple[str, int, list[str]]] = []
    for room in sorted(available_slots.keys()):
        slots = available_slots[room]
        slot_entries = [
            f"[{i}] {slot['time'].replace(':', '')}" for i, slot in enumerate(slots)
        ]
        rows.append((room, len(slots), slot_entries))

    rows.sort(key=lambda row: (row[1], row[0]), reverse=True)

    room_w = max(len("Room"), *(len(room) for room, _, _ in rows))
    count_w = max(len("Slots"), *(len(str(count)) for _, count, _ in rows))
    slots_per_row = 5

    wrapped_rows: list[tuple[str, str, list[str]]] = []
    for room, slot_count, entries in rows:
        wrapped_lines = [
            " | ".join(entries[i : i + slots_per_row])
            for i in range(0, len(entries), slots_per_row)
        ]
        wrapped_rows.append((room, str(slot_count), wrapped_lines))

    avail_w = max(
        len("Availability"), *(len(line) for _, _, lines in wrapped_rows for line in lines)
    )

    sep = f"+-{'-' * room_w}-+-{'-' * count_w}-+-{'-' * avail_w}-+"
    header = f"| {'Room'.ljust(room_w)} | {'Slots'.ljust(count_w)} | {'Availability'.ljust(avail_w)} |"

    print("\nRoom Availability")
    print(sep)
    print(header)
    print(sep)
    for room, slot_count, wrapped_lines in wrapped_rows:
        for i, line in enumerate(wrapped_lines):
            room_cell = room if i == 0 else ""
            count_cell = slot_count if i == 0 else ""
            print(f"| {room_cell.ljust(room_w)} | {count_cell.ljust(count_w)} | {line.ljust(avail_w)} |")
        print(sep)

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
            slot_list.append(
                {
                    "SRNO": i + 1,
                    "SLT_ID": slot["slot_id"],
                    "SLT_Time": slot["time"].split("-")[0],  # Get start time
                    "SLT_Desc": slot["time"],
                    "encryptedSlotStatus": None,
                    "SLT_STATUS": 1,
                    "encryptedSLT_Time": None,
                }
            )

    if not slot_list:
        print("Invalid slot selection")
        return
    first_slot = available_slots[room_name][slot_indices[0]]["rsrc_id"]

    booking_payload = {
        "__RequestVerificationToken": token,
        "RSRC_ID": first_slot,
        "RSRC_TYP_ID": get_rsrc_typ_id(),
        "SearchDate": DATE,
        "SlotList": json.dumps(slot_list),
        "APPRV_EXEMP": "false",
        "SUPPT_EXEMP": "false",
        "checkReorNot": "0",
        "IS_IN4SIT": "false",
        "IS_SUPT": "false",
        "IS_APPRVL": "false",
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
                "RSRC_TYP_ID": get_rsrc_typ_id(),
                "NUM_ATTND": "1",
                "Event_TypeText": "",
                "Acad_Text": "",
                "Purpose": "Study",
                "supptList": "[]",
                "OVERWRITE": "0",
                "slcPurpose": "",
            }
            response = session.post(FINALIZE_URL, data=payload)
            response.raise_for_status()
            if response.status_code == 200:
                print("Booking finalized successfully.")
                sys.exit(0)
            else:
                print(
                    f"Failed to finalize booking. Status code: {response.status_code}"
                )

    except requests.exceptions.RequestException as e:
        print(f"Booking failed: {e}")
        print("Checking your remaining booking hours")
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\n\nExiting... Goodbye!")
        sys.exit(0)
