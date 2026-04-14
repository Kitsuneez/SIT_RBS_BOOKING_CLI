"""
Main entry point for the booking system. 
Initializes the Booking class and retrieves available slots.
"""
from datetime import date, datetime
import os

from dotenv import find_dotenv, load_dotenv
import asyncio
import math
import sys
from booking import Booking
from errors import LoginException, BookingException


ROOMS_PER_PAGE = 5
TIMESLOTS_PER_ROW = 5

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
MAGENTA = "\033[35m"
BLUE = "\033[34m"
RED = "\033[31m"


def display_timeslots(slots):
    """Display rooms and timeslots in a paginated terminal HUD.

    Returns:
        Selected room name when user chooses via HUD index, otherwise None.
    """
    if not slots:
        print(f"{YELLOW}{BOLD}No slots available.{RESET}")
        return None

    rooms = sorted(slots.items())
    total_pages = math.ceil(len(rooms) / ROOMS_PER_PAGE)
    page = 0

    while True:
        start = page * ROOMS_PER_PAGE
        page_rooms = rooms[start : start + ROOMS_PER_PAGE]

        print(f"\n{BLUE}{'=' * 92}{RESET}")
        print(f"{BLUE}{BOLD}Slots HUD{RESET} {DIM}- page {page + 1}/{total_pages}{RESET}")
        print(f"{BLUE}{'=' * 92}{RESET}")

        for room_offset, (room_name, room_slots) in enumerate(page_rooms):
            room_index = start + room_offset
            print(
                f"\n{MAGENTA}{BOLD}[{room_index:02d}] {room_name}{RESET} "
                f"{DIM}({len(room_slots)} slots){RESET}"
            )
            if not room_slots:
                print(f"  {RED}No available timeslots{RESET}")
                continue

            for row_start in range(0, len(room_slots), TIMESLOTS_PER_ROW):
                row = room_slots[row_start : row_start + TIMESLOTS_PER_ROW]
                row_text = "  " + "  ".join(
                    f"{CYAN}[{row_start + offset:02d}]{RESET} {GREEN}{slot['time']}{RESET}"
                    for offset, slot in enumerate(row)
                )
                print(row_text)

        print(
            f"\n{YELLOW}[n]{RESET} next page  "
            f"{YELLOW}[p]{RESET} previous page  "
            f"{YELLOW}[index]{RESET} book room  "
            f"{YELLOW}[q]{RESET} quit"
        )
        command = input(f"{BOLD}HUD>{RESET} ").strip().lower()
        if command in {"q", "quit", "exit"}:
            return None
        if command.isdigit():
            room_index = int(command)
            if 0 <= room_index < len(rooms):
                return rooms[room_index][0]
            print(f"{RED}Invalid room index.{RESET} Use a number from the left label.")
            continue
        if command in {"n", "next"} and page < total_pages - 1:
            page += 1
            continue
        if command in {"p", "prev", "previous"} and page > 0:
            page -= 1
            continue

        if total_pages == 1:
            print(f"{YELLOW}Use room index to select a room or q to quit.{RESET}")
        else:
            print(f"{YELLOW}Unknown command. Use n, p, room index, or q.{RESET}")


async def main():
    """
    Main function to initialize the booking system and retrieve available slots.
    """
    booking = Booking()
    await booking.get_slots()
    selected_room = display_timeslots(booking.slots)
    if not selected_room:
        print(f"{YELLOW}No room selected. Exiting.{RESET}")
        return
    booking.book(room_name=selected_room)

def handle_env_errors():
    """Checks for .env file and required variables, printing warnings or errors as needed."""
    dotenv_path = find_dotenv(usecwd=True)
    if not dotenv_path:
        print(f"{YELLOW}No .env file found. Creating a new one...{RESET}")
        with open(".env", "w") as fl:
            fl.write(f"USERNAME=your_username_here\nPASSWORD=your_password_here\nDATE=\"{date.today().strftime('%d %b %Y')}\"\nDEFAULT_SLOT_START_TIME=\"07:00\"\nDEFAULT_SLOT_END_TIME=\"22:00\"\n")
        print(f"{GREEN}.env file created. Please fill in your credentials and try again.{RESET}")
        sys.exit(1)
    if not load_dotenv(dotenv_path, override=True):
        print(f"{RED}Failed to load .env file. Check the file and try again.{RESET}")
        sys.exit(1)
    if not os.getenv("DEFAULT_SLOT_START_TIME") or not os.getenv("DEFAULT_SLOT_END_TIME"):
        print(f"{YELLOW}Warning: Default start or end time not set. Using defaults...{RESET}")
    if os.getenv("DATE"):
        try:
            date_obj = datetime.strptime(os.getenv("DATE"), "%d %b %Y").date()
            if date_obj < date.today():
                print(f"{YELLOW}Warning: specified date is in the past or not specified. Defaulting to today's date.{RESET}")
        except ValueError:
            print(f"{RED}Error: Invalid date format. Please use the format 'DD MMM YYYY'.{RESET}")
            sys.exit(1)

if __name__ == "__main__":
    handle_env_errors()
    dotenv_path = find_dotenv(usecwd=True)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nExiting... Goodbye!")
        sys.exit(0)
    except LoginException as e:
        print(f"{RED}Login failed: {e}{RESET}")
        sys.exit(1)
    except BookingException as e:
        print(f"{RED}Booking failed: {e}{RESET}")
        sys.exit(1)
    except ValueError as e:
        print(f"{RED}Configuration error: {e}{RESET}")
        sys.exit(1)
