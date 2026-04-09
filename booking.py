"""Handles the booking process, including retrieving available slots and making reservations."""

from asyncio import gather, to_thread, create_task
import json
import re
import os
from typing import TypeAlias
import requests
import aiohttp
from auth import Auth
from constants import (
    AVAILABILITY_BATCH_SIZE,
    AVAILABILITY_CARD_BLOCK_REGEX,
    AVAILABILITY_MOBILE_ROOM_NAME_REGEX,
    AVAILABILITY_ROOM_NAME_REGEX,
    AVAILABILITY_SLOT_REGEX,
    CONFIRMATION_APPRV_EXEMP,
    CONFIRMATION_CHECK_REOR_NOT,
    CONFIRMATION_IS_APPRVL,
    CONFIRMATION_IS_IN4SIT,
    CONFIRMATION_IS_SUPT,
    CONFIRMATION_SLOT_STATUS,
    CONFIRMATION_SUPPT_EXEMP,
    DEFAULT_SLOT_END_TIME,
    DEFAULT_SLOT_START_TIME,
    FINALIZE_NUM_ATTND,
    FINALIZE_OVERWRITE,
    FINALIZE_PURPOSE,
    FINALIZE_SUPPT_LIST,
    SESSION_POOL_SIZE,
    MAPPING_FILE,
    BOOKING_URL,
    BOOKING_HEADER,
    DATE,
    REQUEST_TIMEOUT_SECONDS,
    GET_ALL_ROOMS_URL,
    CONFIRM_URL,
    FINALIZE_URL,
)
from errors import BookingException

USERNAME: TypeAlias = str
PASSWORD: TypeAlias = str
MAPPING: TypeAlias = dict[str, str]
SESSIONPOOL: TypeAlias = list[tuple[requests.Session, str]]

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
MAGENTA = "\033[35m"
RED = "\033[31m"


class Booking:
    """Handles the booking process, including retrieving available slots and making reservations."""

    def __init__(self):
        self.session_pool: SESSIONPOOL = []
        self.mapping: MAPPING = {}
        self.rsrc_list: list[MAPPING] = []
        self.slots = {}

    async def get_slots(self):
        """
        1. Logins to the booking system,
        2. builds a pool of authenticated sessions,
        3. retrieves room mappings
        4. checks availability for all rooms.
        """
        print(f"{CYAN}{BOLD}[*] Logging in{RESET}")
        await self._build_session_pool()
        print(f"{GREEN}{BOLD}[*] Login successful, building session pool{RESET}")
        print(f"{CYAN}[*] Mapping rooms to resource IDs{RESET}")
        self._load_mapping()

        session, token = self.session_pool[0]
        try:
            print(f"{CYAN}[*] Fetching rooms{RESET}")
            rooms = await to_thread(self._fetch_rooms, session, token)
            print(f"{CYAN}[*] Hydrating resource types{RESET}")
            self._hydrate_resource_type(rooms)
            if not self.rsrc_list or not self.rsrc_list[0].get("RSRC_TYP_ID"):
                raise BookingException("Could not determine RSRC_TYP_ID from fetched room metadata.")
        except requests.RequestException as e:
            raise BookingException(f"Failed to fetch rooms: {e}") from e
        print(f"{CYAN}[*] Checking availability{RESET}")
        await self._check_availability()

    def book(self, room_name: str | None = None):
        """
        prompts the user to select a room and time slots,
        then attempts to make a booking using one of the authenticated sessions from the pool.
        """
        session, token = self.session_pool[0]
        if room_name is None:
            room_name = input(
                f"{BOLD}Enter room name{RESET} (E2-XX-XXX-DRXXX): "
            ).strip().upper()
        else:
            room_name = room_name.strip().upper()
            print(f"{CYAN}[*] Selected room from HUD:{RESET} {MAGENTA}{room_name}{RESET}")

        room_slots = self.slots.get(room_name, [])
        if not room_slots:
            print(f"{RED}Room '{room_name}' not found or has no available slots.{RESET}")
            return

        max_slot_index = len(room_slots) - 1
        while True:
            slot_input = input(
                f"{BOLD}Enter slot numbers to book{RESET} (comma-separated, e.g., 0,1,2) \
    or ('-' for a range, e.g., 0-2): "
            ).strip()

            try:
                if "-" in slot_input:
                    start, end = map(int, slot_input.split("-"))
                    if start > end:
                        print(
                            f"{RED}Invalid range.{RESET} Start index cannot be greater than end index."
                        )
                        continue
                    slot_indices = list(range(start, end + 1))
                else:
                    slot_indices = [int(x.strip()) for x in slot_input.split(",") if x.strip()]

                if not slot_indices:
                    print(f"{RED}No slot indices provided.{RESET}")
                    continue

                if any(i < 0 or i > max_slot_index for i in slot_indices):
                    print(
                        f"{RED}Invalid slot index.{RESET} Enter values between 0 and {max_slot_index}."
                    )
                    continue

                self._confirm_booking(room_name, slot_indices, token, session)
                break
            except ValueError:
                print(
                    f"{RED}Invalid slot input format.{RESET} Please enter numbers separated by commas or a range with '-'."
                )

    def _confirm_booking(
        self,
        room_name: str,
        slot_indices: list[int],
        token: str,
        session: requests.Session,
    ):
        """
        Confirms the booking for the selected room and time slots.

        Args:
            room_name: The name of the room to book.
            slot_indices: A list of indices corresponding to the time slots to book.
            token: The verification token required for booking.
            session: An authenticated requests.Session to use for making booking requests.
        """
        print(f"{MAGENTA}[*] Attempting to book{RESET} {room_name} {DIM}for slots {slot_indices}{RESET}")
        if room_name not in self.slots:
            print(f"{RED}Room '{room_name}' not found or has no available slots.{RESET}")
            return
        room_slots = self.slots.get(room_name, [])
        if not slot_indices or any(i < 0 or i >= len(room_slots) for i in slot_indices):
            print(f"{RED}Invalid slot indices.{RESET}")
            return

        slot_list = []
        for i, idx in enumerate(slot_indices):
            slot_info = room_slots[idx]
            slot_list.append(
                {
                    "SRNO": i + 1,
                    "SLT_ID": slot_info["slot_id"],
                    "SLT_TIME": slot_info["time"].split("-")[0],
                    "SLT_Desc": slot_info["time"],
                    "encryptedSlotStatus": None,
                    "SLT_STATUS": CONFIRMATION_SLOT_STATUS,
                    "encryptedSLT_Time": None,
                }
            )
        first_slot = room_slots[slot_indices[0]]["rsrc_id"]
        booking_payload = {
            "__RequestVerificationToken": token,
            "RSRC_ID": first_slot,
            "RSRC_TYP_ID": self.rsrc_list[0]["RSRC_TYP_ID"],
            "SearchDate": DATE,
            "SlotList": json.dumps(slot_list),
            "APPRV_EXEMP": CONFIRMATION_APPRV_EXEMP,
            "SUPPT_EXEMP": CONFIRMATION_SUPPT_EXEMP,
            "checkReorNot": CONFIRMATION_CHECK_REOR_NOT,
            "IS_IN4SIT": CONFIRMATION_IS_IN4SIT,
            "IS_SUPT": CONFIRMATION_IS_SUPT,
            "IS_APPRVL": CONFIRMATION_IS_APPRVL,
        }
        try:
            response = session.post(CONFIRM_URL, data=booking_payload, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            if response.status_code == 200:
                print(f"{CYAN}[*] Finalizing booking...{RESET}")
                payload = {
                    "__RequestVerificationToken": token,
                    "RSRC_TYP_ID": self.rsrc_list[0]["RSRC_TYP_ID"],
                    "NUM_ATTND": FINALIZE_NUM_ATTND,
                    "Event_TypeText": "",
                    "Acad_Text": "",
                    "Purpose": FINALIZE_PURPOSE,
                    "supptList": FINALIZE_SUPPT_LIST,
                    "OVERWRITE": FINALIZE_OVERWRITE,
                    "slcPurpose": "",
                }
                response = session.post(FINALIZE_URL, data=payload, timeout=REQUEST_TIMEOUT_SECONDS)
                response.raise_for_status()
                if response.status_code != 200:
                    raise BookingException(
                        f"Failed to finalize booking: {response.status_code} {response.text}"
                    )
                print(f"{GREEN}{BOLD}[+] Booking successful!{RESET}")
        except requests.RequestException as e:
            raise BookingException(f"Booking hours might be used up: {e}") from e

    async def _check_availability(self):
        """
        checks the availability of all rooms by sending asynchronous requests using aiohttp sessions from the pool.
        """
        resource_list = [
            {
                "RSRC_ID": d["RSRC_ID"],
                "IS_SLD": False,
                "Event_Type": 0,
                "Disclaimer": "Sample layout",
            }
            for d in self.rsrc_list
        ]
        aiohttp_sessions = []
        results = []
        try:
            for request_session, token in self.session_pool:
                jar = aiohttp.CookieJar()
                for c in request_session.cookies:
                    if c.value is not None:
                        jar.update_cookies({c.name: c.value})
                connector = aiohttp.TCPConnector()
                aiohttp_sessions.append(
                    (
                        aiohttp.ClientSession(
                            headers=BOOKING_HEADER, cookie_jar=jar, connector=connector
                        ),
                        token,
                    )
                )
            tasks = []
            for batch_index, i in enumerate(
                range(0, len(resource_list), AVAILABILITY_BATCH_SIZE)
            ):
                batch = resource_list[i : i + AVAILABILITY_BATCH_SIZE]
                session_index = batch_index % len(aiohttp_sessions)
                session, token = aiohttp_sessions[session_index]
                tasks.append(
                    create_task(self._check_availability_batch(session, token, batch))
                )
            gathered = await gather(*tasks, return_exceptions=True)
            results = []
            for r in gathered:
                if isinstance(r, BaseException):
                    print(f"{YELLOW}[*] Availability batch failed: {r}{RESET}")
                    continue
                results.append(r)
        finally:
            await gather(*(s.close() for s, _ in aiohttp_sessions))
        for batch in results:
            self.slots.update(batch)

    async def _check_availability_batch(
        self, session: aiohttp.ClientSession, token: str, batch: list[dict[str, str]]
    ):
        """
        gets the availability for a batch of rooms and
        returns a mapping of room names to available time slots.

        Args:
            session: An aiohttp.ClientSession to use for making requests.
            token: The verification token required for making requests.
            batch: A list of dictionaries containing resource information for a batch of rooms.
        """
        parameter = [
            {
                "MRB002Date": DATE,
                "MRB002StartTime": DEFAULT_SLOT_START_TIME,
                "MRB002EndTime": DEFAULT_SLOT_END_TIME,
                "ResourceList": batch,
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
        async with session.post(
            GET_ALL_ROOMS_URL, data=payload, timeout=timeout
        ) as response:
            response.raise_for_status()
            html = await response.text()
        results = {}

        blocks = re.findall(AVAILABILITY_CARD_BLOCK_REGEX, html)

        for block in blocks:
            name_match = re.search(AVAILABILITY_ROOM_NAME_REGEX, block)
            if name_match:
                room = name_match.group(1).strip()
            else:
                mobile_name_match = re.search(
                    AVAILABILITY_MOBILE_ROOM_NAME_REGEX, block
                )
                if not mobile_name_match:
                    continue
                room = mobile_name_match.group(1).strip()

            slots = re.findall(AVAILABILITY_SLOT_REGEX, block)

            if slots:
                results[room] = [
                    {
                        "slot_id": s[0],
                        "time": s[1],
                        "rsrc_id": self.mapping[room],
                        "rsrc_typ_id": self.rsrc_list[0]["RSRC_TYP_ID"],
                    }
                    for s in slots
                ]
        return results

    async def _build_session_pool(self):
        """Builds a pool of authenticated sessions by logging in multiple times concurrently."""
        username, password = self._get_credentials()

        print(f"{CYAN}[*] Creating {SESSION_POOL_SIZE} authenticated session(s)...{RESET}")

        creation_tasks = [
            to_thread(self._create_new_session, username, password)
            for _ in range(SESSION_POOL_SIZE)
        ]
        self.session_pool = await gather(*creation_tasks)

    def _load_mapping(self):
        """
        Loads the room to resource ID mapping from a JSON file and
        the resource list for availability checks.
        """
        with open(MAPPING_FILE, "r", encoding="utf-8") as f:
            loaded = json.load(f)

        self.mapping = {str(room): str(rsrc_id) for room, rsrc_id in loaded.items()}
        self.rsrc_list = [
            {"RSRC_ID": rsrc_id, "RSRC_TYP_ID": ""} for rsrc_id in self.mapping.values()
        ]

    def _create_new_session(
        self, username: USERNAME, password: PASSWORD
    ) -> tuple[requests.Session, str]:
        """Creates a new authenticated session by logging in with the provided credentials."""
        auth = Auth()
        auth(username, password)
        return auth.session, auth.token

    def _get_credentials(self) -> tuple[USERNAME, PASSWORD]:
        """
        Retrieves the username and password from environment variables.

        Returns:
            A tuple containing the username and password.
        """
        username = os.getenv("USERNAME")
        password = os.getenv("PASSWORD")
        if not username or not password:
            raise ValueError("Username or password not found in environment variables.")
        return username, password

    def _fetch_rooms(
        self, session: requests.Session, token: str
    ) -> list[dict[str, str]]:
        """
        Fetches the list of rooms using the provided authenticated session and verification token.

        Args:
            session: An authenticated requests.Session to use for making the request.
            token: The verification token required for making the request.
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

        response = session.post(BOOKING_URL, data=payload, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()

    def _hydrate_resource_type(self, rooms: list[dict[str, str]]):
        """
        Hydrates the resource type ID for all rooms in the resource
        list based on the fetched room data.

        Args:
            rooms: A list of dictionaries containing room information
                    fetched from the booking system.
        """
        typ_id = next(
            (str(r.get("RSRC_TYP_ID", "")) for r in rooms if r.get("RSRC_TYP_ID")), ""
        )
        if not typ_id:
            return

        for item in self.rsrc_list:
            item["RSRC_TYP_ID"] = typ_id
