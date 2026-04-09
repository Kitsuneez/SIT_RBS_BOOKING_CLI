## Setup environment
`pip install -r requirements.txt`
## Add username and password for login into .env
USERNAME = ""<br>
PASSWORD = ""
## To run script
`python .`

## Example
1. Change DATE and time in constants.py (line 1) to desired booking date and time
2. run program and choose room
    
3. select time slot (',' for different slots, '-' for range)
    ![alt text](images/image4.png)

Mapping.json is used to map the resource type ID to a human readable name. This is used to display the room names in the output. The resource type ID is extracted from the room metadata and is used to determine the type of room (e.g. study room, meeting room, etc.).