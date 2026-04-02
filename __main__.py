"""
Main module for SIT Room Booking System.
Handles user authentication, room search, availability check, and booking.
"""
import asyncio
import json
import os
import random
import re
import sys
from datetime import datetime
from pathlib import Path
from time import perf_counter
import aiohttp
import requests

from auth import get_verification_tokens, login


class SessionExpiredError(Exception):
    """Raised when the authentication session has expired."""


BOOKING_URL = "https://rbs.singaporetech.edu.sg/SRB001/SearchSRB001List"
CHECK_AVAILABILITY_URL = "https://rbs.singaporetech.edu.sg/SRB001/GetTimeSlotListByresidNdatetime"
GET_ALL_ROOMS_URL = "https://rbs.singaporetech.edu.sg/MRB002/ResourceReload"
DATE = "03 Apr 2026"
CONFIRM_URL = "https://rbs.singaporetech.edu.sg/SRB001/NormalBookingConfirmation"
FINALIZE_URL = "https://rbs.singaporetech.edu.sg/SRB001/BookingSaving"
START_URL = "https://rbs.singaporetech.edu.sg/SRB001/SRB001Page"
MAX_ROOMS_PER_REQUEST = 10
BATCH_SIZE = min(MAX_ROOMS_PER_REQUEST, max(1, 10))
SESSION_POOL_SIZE = 4
MAX_CONCURRENT_REQUESTS = 1
REQUEST_TIMEOUT_SECONDS = 12
MAX_BATCH_RETRIES = 2
SHOW_AVAILABLE_SLOTS = False
FAST_MODE = False
ROOMS_CACHE_FILE = Path("rooms_cache.json")


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

SLOT_START = datetime.strptime("07:00", "%H:%M").time()
SLOT_END = datetime.strptime("22:00", "%H:%M").time()


def normalize_room_slots(slots: list[dict[str, str]]) -> list[dict[str, str]]:
    """Keep only 30-minute slots within 07:00-22:00, sorted by time."""
    normalized: list[tuple[datetime, dict[str, str]]] = []
    for slot in slots:
        time_range = slot.get("time", "")
        if not re.fullmatch(r"\d{2}:\d{2}-\d{2}:\d{2}", time_range):
            continue

        start_s, end_s = time_range.split("-")
        start_dt = datetime.strptime(start_s, "%H:%M")
        end_dt = datetime.strptime(end_s, "%H:%M")

        if (end_dt - start_dt).seconds != 30 * 60:
            continue
        if start_dt.time() < SLOT_START or end_dt.time() > SLOT_END:
            continue
        if start_dt.minute not in (0, 30) or end_dt.minute not in (0, 30):
            continue

        normalized.append((start_dt, slot))

    normalized.sort(key=lambda item: item[0])
    return [slot for _, slot in normalized]


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
        "LocationID": ""
    }

    response = session.post(BOOKING_URL, data=payload)
    response.raise_for_status()
    if response.text.strip().startswith("{") or response.text.strip().startswith("["):
        return response.json()
    return []


def load_rooms_from_cache() -> list[dict[str, str]] | None:
    """Load cached room metadata to avoid a slow room search request."""
    if not ROOMS_CACHE_FILE.exists():
        return None
    try:
        with ROOMS_CACHE_FILE.open("r", encoding="utf-8") as f:
            rooms = json.load(f)
        if isinstance(rooms, list) and rooms:
            print(f"[*] Loaded cached room list from {ROOMS_CACHE_FILE}")
            return rooms
    except (OSError, json.JSONDecodeError):
        return None
    return None


def save_rooms_cache(rooms: list[dict[str, str]]) -> None:
    """Persist room metadata for faster subsequent runs."""
    try:
        with ROOMS_CACHE_FILE.open("w", encoding="utf-8") as f:
            json.dump(rooms, f)
    except OSError:
        pass


def create_new_session_with_token(username: str, password: str) -> tuple[requests.Session, str] | None:
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

    session, token = session_pool[0]
    print("[*] Session and tokens are ready for booking operations.")
    try:
        rooms = load_rooms_from_cache() if FAST_MODE else None
        if rooms is None:
            rooms_start = perf_counter()
            rooms = await asyncio.to_thread(fetch_rooms, session, token)
            rooms_elapsed = perf_counter() - rooms_start
            print(f"[*] Room search response time: {rooms_elapsed:.2f}s")
            save_rooms_cache(rooms)
        else:
            print("[*] Room search response time: 0.00s (cache)")
    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")
        return
    except json.JSONDecodeError as e:
        print(f"JSON decode error: {e}")
        return

    map_rooms(rooms)

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


async def fetch_availability_batch(session, token, resource_batch, mapping):
    """
    Fetch availability for a batch of resources asynchronously.

    :param session: Active aiohttp session
    :param token: Verification token string
    :param resource_batch: List of resource dictionaries
    :param mapping: Room name to RSRC_ID mapping dictionary
    :return: Dictionary of room names to available slots
    """
    parameter = [{
        "MRB002Date": DATE,
        "MRB002StartTime": "07:00",
        "MRB002EndTime": "22:00",
        "ResourceList": resource_batch
    }]

    payload = {
        "__RequestVerificationToken": token,
        "bookingstatus": "Available",
        "parameter": json.dumps(parameter),
        "_rsrcCat": "facilities"
    }
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
    batch_start = perf_counter()
    html = ""
    for attempt in range(MAX_BATCH_RETRIES + 1):
        try:
            async with session.post(GET_ALL_ROOMS_URL, data=payload, timeout=timeout) as resp:
                resp.raise_for_status()
                html = await resp.text()
            break
        except (asyncio.TimeoutError, aiohttp.ClientError):
            if attempt >= MAX_BATCH_RETRIES:
                raise
            # Backoff + jitter reduces synchronized retry storms against the same endpoint.
            await asyncio.sleep((0.35 * (2 ** attempt)) + random.uniform(0.05, 0.20))
    batch_elapsed = perf_counter() - batch_start
    results = {}

    blocks = re.findall(
        r'<div class="card fa-sm">[\s\S]*?(?=<div class="card fa-sm">|$)',
        html
    )

    for block in blocks:
        name_match = re.search(
            r'<span class="d-block d-md-none font-weight-bold">Name:</span>\s*([A-Z0-9\-]+)',
            block
        )
        if not name_match:
            continue

        room = name_match.group(1)
        slots = re.findall(
            r"data-sltid=([a-f0-9\-]+)[\s\S]*?>\s*(\d{2}:\d{2}-\d{2}:\d{2})",
            block
        )

        if slots:
            results[room] = [
                {
                    "slot_id": s[0],
                    "time": s[1],
                    "rsrc_id": mapping[room],
                    "rsrc_typ_id": ls_dict[0]["RSRC_TYP_ID"]
                } for s in slots
            ]

    return results, batch_elapsed


async def check_availability_async(session_pool: list[tuple[requests.Session, str]]):
    """
    Asynchronously check room availability and display available slots.

    :param token: Verification token string
    :param requests_session: Active session object
    """
    resource_list = [{
        "RSRC_ID": d["RSRC_ID"],
        "IS_SLD": False,
        "Event_Type": 0,
        "Disclaimer": "Sample layout"
    } for d in ls_dict]

    availability_start = perf_counter()
    aiohttp_sessions: list[tuple[aiohttp.ClientSession, str]] = []
    results = []
    try:
        for requests_session, token in session_pool:
            jar = aiohttp.CookieJar()
            for c in requests_session.cookies:
                if c.value is not None:
                    jar.update_cookies({c.name: c.value})
            connector = aiohttp.TCPConnector(limit_per_host=MAX_CONCURRENT_REQUESTS, limit=MAX_CONCURRENT_REQUESTS)
            aiohttp_sessions.append((
                aiohttp.ClientSession(
                    headers=headers,
                    cookie_jar=jar,
                    connector=connector
                ),
                token
            ))

        tasks = []
        effective_batch_size = min(MAX_ROOMS_PER_REQUEST, BATCH_SIZE)
        for batch_index, i in enumerate(range(0, len(resource_list), effective_batch_size)):
            batch = resource_list[i:i + effective_batch_size]
            session_index = batch_index % len(aiohttp_sessions)
            aio_session, session_token = aiohttp_sessions[session_index]
            tasks.append(
                asyncio.create_task(
                    fetch_availability_batch(aio_session, session_token, batch, room_mapping)
                )
            )

        available_slots.clear()
        results = await asyncio.gather(*tasks)
    finally:
        await asyncio.gather(*(s.close() for s, _ in aiohttp_sessions), return_exceptions=True)
    availability_elapsed = perf_counter() - availability_start

    batch_timings: list[float] = []
    for batch, batch_elapsed in results:
        batch_timings.append(batch_elapsed)
        for room, slots in batch.items():
            normalized = normalize_room_slots(slots)
            if normalized:
                available_slots[room] = normalized

    print(
        f"[*] Availability request time: {availability_elapsed:.2f}s "
        f"({len(results)} batch request(s), batch_size={effective_batch_size}, "
        f"concurrency={MAX_CONCURRENT_REQUESTS}, sessions={len(session_pool)})"
    )
    if batch_timings:
        print(
            f"[*] Batch response times (s): min={min(batch_timings):.2f}, "
            f"max={max(batch_timings):.2f}, avg={sum(batch_timings)/len(batch_timings):.2f}"
        )

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

    slots_per_line = 4
    rows: list[tuple[str, str, list[str]]] = []
    for room in sorted(available_slots.keys()):
        slots = available_slots[room]
        slot_count = str(len(slots))
        slot_entries = [f"[{i}] {slot['time'].replace(':', '')}" for i, slot in enumerate(slots)]
        wrapped_lines = [
            " | ".join(slot_entries[i:i + slots_per_line])
            for i in range(0, len(slot_entries), slots_per_line)
        ]
        rows.append((room, slot_count, wrapped_lines))

    rows.sort(key=lambda row: (-int(row[1]), row[0]))

    room_w = max(len("Room"), *(len(r[0]) for r in rows))
    count_w = max(len("Slots"), *(len(r[1]) for r in rows))
    avail_w = max(
        len("Availability"),
        *(len(line) for _, _, lines in rows for line in lines)
    )

    sep = f"+-{'-' * room_w}-+-{'-' * count_w}-+-{'-' * avail_w}-+"
    header = f"| {'Room'.ljust(room_w)} | {'Slots'.ljust(count_w)} | {'Availability'.ljust(avail_w)} |"

    print("\nRoom Availability")
    print(sep)
    print(header)
    print(sep)
    for room, slot_count, wrapped_lines in rows:
        for i, line in enumerate(wrapped_lines):
            room_cell = room if i == 0 else ""
            count_cell = slot_count if i == 0 else ""
            print(
                f"| {room_cell.ljust(room_w)} | {count_cell.ljust(count_w)} | {line.ljust(avail_w)} |"
            )
        print(sep)


def map_rooms(rooms: list[dict[str, str]]) -> None:
    """
    Display available rooms in a formatted table.

    :param rooms: List of room dictionaries
    """
    ls_dict.clear()
    room_mapping.clear()

    for _, res in enumerate(rooms):
        ls_dict.append({
            "RSRC_ID": res['RSRC_ID'],
            "RSRC_TYP_ID": res['RSRC_TYP_ID']
        })
        room_mapping[res["RSRC_NAME"]] = res["RSRC_ID"]

    with open("mapping.json", "w", encoding="utf-8") as f:
        json.dump(room_mapping, f, indent=4)


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
                print(
                    f"Failed to finalize booking. Status code: {response.status_code}")

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
