"""
Handles the authentication process for the booking system, 
including retrieving necessary tokens and performing login operations.
"""
import html
import re
from typing import TypedDict
from urllib.parse import urlparse
import requests
from dotenv import load_dotenv
from constants import (
    HEADERS,
    REQUEST_VERIFICATION_TOKEN_REGEX,
    START_URL,
    WSFED_FORM_ACTION_REGEX,
    WSFED_HIDDEN_INPUT_REGEX,
    REQUEST_TIMEOUT_SECONDS
)
from errors import LoginException


load_dotenv()


class LoginURLInfo(TypedDict):
    """TypedDict to hold information about the login URL and payload."""
    wsfed_payload: dict[str, str]
    callback_headers: dict[str, str]
    action_url: str


class Auth:
    """Handles the authentication process for the booking system."""
    def __init__(self):
        self.session = requests.Session()
        self.token = ""

    def __call__(self, username: str, password: str):
        self.login(username, password)
        self._get_verification_token()

    def login(self, username: str, password: str):
        """Performs the login process using the provided username and password."""
        info = self._get_login_url(username, password)
        final_response = self.session.post(
            info["action_url"],
            data=info["wsfed_payload"],
            headers=info["callback_headers"],
            timeout=REQUEST_TIMEOUT_SECONDS
        )
        final_response.raise_for_status()
        if final_response.status_code == 200:
            if "Sign In" in final_response.text or "adfs/ls" in final_response.url:
                raise LoginException("Login loop detected. Back at login page.")

    def _get_login_url(self, username: str, password: str) -> LoginURLInfo:
        payload = {
            "UserName": username,
            "Password": password,
            "AuthMethod": "FormsAuthentication",
            "Kmsi": "true",
        }
        adfs_url = self._get_adfs_url()
        login_response = self.session.post(adfs_url, data=payload, timeout=REQUEST_TIMEOUT_SECONDS)
        login_response.raise_for_status()
        if "Incorrect user ID or password" in login_response.text:
            raise LoginException("Incorrect user ID or password.")
        action_url, wsfed_payload = self._extract_wsfed_payload(login_response)
        if action_url.startswith("/"):
            parsed_url = urlparse(adfs_url)
            action_url = f"{parsed_url.scheme}://{parsed_url.netloc}{action_url}"
        callback_headers = {
            "Referer": adfs_url,
            "Origin": f"{urlparse(adfs_url).scheme}://{urlparse(adfs_url).netloc}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        return LoginURLInfo(
            wsfed_payload=wsfed_payload,
            callback_headers=callback_headers,
            action_url=action_url,
        )

    def _get_adfs_url(self) -> str:
        self.session.headers.update(HEADERS)
        response = self.session.get(START_URL, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        if "Sign In" not in response.text and "adfs/ls" not in response.url:
            raise LoginException("ADFS URL not found on initial login page.")
        return response.url

    def _get_verification_token(self) -> None:
        response = self.session.get(START_URL, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()

        token_match = re.search(REQUEST_VERIFICATION_TOKEN_REGEX, response.text)
        if not token_match:
            raise LoginException("Request verification token not found.")
        token = token_match.group(1)
        self.token = token

    def _extract_wsfed_payload(
        self, response_text: requests.Response
    ) -> tuple[str, dict[str, str]]:
        hidden_inputs = re.findall(WSFED_HIDDEN_INPUT_REGEX, response_text.text)
        # HTML unescape values
        wsfed_payload = {name: html.unescape(value) for name, value in hidden_inputs}

        form_action_match = re.search(WSFED_FORM_ACTION_REGEX, response_text.text)
        if not form_action_match:
            raise LoginException("Form action URL not found in login response.")
        action_url = form_action_match.group(1)
        return action_url, wsfed_payload
