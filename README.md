## Setup Guide (Windows)
1. create virtual environment `python -m venv .venv`
2. activate virtual environment 
    - **powershell:** `.venv/Scripts/Activate.ps1`
    - **CMD:** `.venv/Scripts/activate.bat`
3. `pip install -r requirements.txt`
4. Add username and password for login into `.env`
    ```env
    USERNAME=<email_address>
    PASSWORD=<your_password>
    ```
5. Run script
    `python .`

## Setup Guide (Linux)
1. create virtual environment `python -m venv .venv`
2. activate virtual environment `source .venv/bin/activate`
3. `pip install -r requirements.txt`
4. Add username and password for login into `.env`
    ```env
    USERNAME=<email_address>
    PASSWORD=<your_password>
    ```
5. Run script
    `python .`

**Note:** Confirmation of booking may take a while, so please be patient after confirming the booking. If you encounter a timeout error, please try again as it may be due to network issues or server response time.
<hr>

## Demo
![demo video](images/demo.gif)

<hr>

## Example
1. Set `DATE`, `DEFAULT_SLOT_START_TIME`, and `DEFAULT_SLOT_END_TIME` in `constants.py` to your desired booking date and time
<br>

2. run program and program will login using your credentials and fetch rooms
![create session](images/fetch.png)
<br>

3. navigate through the pages using n and p, enter the room number to select the room
![time slots](images/slots.png)
<br>

4. Select time slots to confirm booking*
![bookings](images/timeslot.png)
<br>

5. The system will confirm the booking when it is successful
![confirmation](images/confirmation.png)


*Note: You can only select timeslots using commas OR a range using a dash. For example, "0,2,4" or "0-2". You cannot mix both formats in the same input.