## Demo
![demo video](images/demo.webm)

## Setup environment
`pip install -r requirements.txt`
## Add username and password for login into `.env`
USERNAME = ""<br>
PASSWORD = ""
## To run script
`python .`

## Example
1. Set `DATE`, `DEFAULT_SLOT_START_TIME`, and `DEFAULT_SLOT_END_TIME` in `constants.py` to your desired booking date and time
2. run program and program will login using your credentials and fetch rooms
![create session](images/fetch.png)
3. navigate through the pages using n and p, enter the room number to select the room
![time slots](images/slots.png)
4. Select time slots to confirm booking*
![bookings](images/timeslot.png)
5. The system will confirm the booking when it is successful
![confirmation](images/confirmation.png)


*Note: You can only select timeslots using commas OR a range using a dash. For example, "0,2,4" or "0-2". You cannot mix both formats in the same input.

Mapping.json is used to map room names to their corresponding resource IDs for system queries. This enables the application to retrieve room information from the booking system. Resource IDs are extracted from the mapping and used to fetch availability and booking details.
