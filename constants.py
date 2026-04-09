DATE = "11 Apr 2026"
DEFAULT_SLOT_START_TIME = "07:00"
DEFAULT_SLOT_END_TIME = "22:00"
START_URL = "https://rbs.singaporetech.edu.sg/SRB001/SRB001Page"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) \
        AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;\
        q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
}
BOOKING_URL = "https://rbs.singaporetech.edu.sg/SRB001/SearchSRB001List"
CHECK_AVAILABILITY_URL = "https://rbs.singaporetech.edu.sg/SRB001/GetTimeSlotListByresidNdatetime"
GET_ALL_ROOMS_URL = "https://rbs.singaporetech.edu.sg/MRB002/ResourceReload"
CONFIRM_URL = "https://rbs.singaporetech.edu.sg/SRB001/NormalBookingConfirmation"
FINALIZE_URL = "https://rbs.singaporetech.edu.sg/SRB001/BookingSaving"
SESSION_POOL_SIZE = 4
AVAILABILITY_BATCH_SIZE = 10
REQUEST_TIMEOUT_SECONDS = 12
MAPPING_FILE = "mapping.json"
BOOKING_HEADER = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko)\
          Chrome/142.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-GB,en;q=0.6",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "https://rbs.singaporetech.edu.sg",
    "Referer": "https://rbs.singaporetech.edu.sg/SRB001/SRB001Page",
}
REQUEST_VERIFICATION_TOKEN_REGEX = (
    r'<input name="__RequestVerificationToken" type="hidden" value="([^"]+)" />'
)
WSFED_HIDDEN_INPUT_REGEX = r'<input type="hidden" name="([^"]+)" value="([^"]+)"'
WSFED_FORM_ACTION_REGEX = r'action="([^"]+)"'
AVAILABILITY_CARD_BLOCK_REGEX = (
    r'<div class="card fa-sm">[\s\S]*?(?=<div class="card fa-sm">|$)'
)
AVAILABILITY_MOBILE_ROOM_NAME_REGEX = (
    r'<span class="d-block d-md-none font-weight-bold">Name:</span>\s*([A-Z0-9\-]+)'
)
AVAILABILITY_ROOM_NAME_REGEX = r'<div class="card-header">([^<]+)</div>'
AVAILABILITY_SLOT_REGEX = (
    r"data-sltid=([a-f0-9\-]+)[\s\S]*?>\s*(\d{2}:\d{2}-\d{2}:\d{2})"
)
CONFIRMATION_SLOT_STATUS = 1
CONFIRMATION_APPRV_EXEMP = "false"
CONFIRMATION_SUPPT_EXEMP = "false"
CONFIRMATION_CHECK_REOR_NOT = "0"
CONFIRMATION_IS_IN4SIT = "false"
CONFIRMATION_IS_SUPT = "false"
CONFIRMATION_IS_APPRVL = "false"
FINALIZE_NUM_ATTND = "1"
FINALIZE_PURPOSE = "Study"
FINALIZE_SUPPT_LIST = "[]"
FINALIZE_OVERWRITE = "0"