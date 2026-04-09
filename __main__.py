"""
Main entry point for the booking system. 
Initializes the Booking class and retrieves available slots.
"""
import asyncio
import math
import sys
from booking import Booking


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
    """Display rooms and timeslots in a paginated terminal HUD."""
    if not slots:
        print(f"{YELLOW}{BOLD}No slots available.{RESET}")
        return

    rooms = sorted(slots.items())
    total_pages = math.ceil(len(rooms) / ROOMS_PER_PAGE)
    page = 0

    while True:
        start = page * ROOMS_PER_PAGE
        page_rooms = rooms[start : start + ROOMS_PER_PAGE]

        print(f"\n{BLUE}{'=' * 92}{RESET}")
        print(f"{BLUE}{BOLD}Slots HUD{RESET} {DIM}- page {page + 1}/{total_pages}{RESET}")
        print(f"{BLUE}{'=' * 92}{RESET}")

        for room_name, room_slots in page_rooms:
            print(f"\n{MAGENTA}{BOLD}{room_name}{RESET} {DIM}({len(room_slots)} slots){RESET}")
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

        if total_pages == 1:
            break

        print(
            f"\n{YELLOW}[n]{RESET} next page  \
                {YELLOW}[p]{RESET} previous page  \
                {YELLOW}[q]{RESET} quit"
        )
        command = input(f"{BOLD}HUD>{RESET} ").strip().lower()
        if command in {"q", "quit", "exit"}:
            break
        if command in {"n", "next"} and page < total_pages - 1:
            page += 1
            continue
        if command in {"p", "prev", "previous"} and page > 0:
            page -= 1
            continue


async def main():
    """
    Main function to initialize the booking system and retrieve available slots.
    """
    booking = Booking()
    await booking.get_slots()
    display_timeslots(booking.slots)
    booking.book()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nExiting... Goodbye!")
        sys.exit(0)
