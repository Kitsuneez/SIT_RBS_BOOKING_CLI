import os
import html
import re
import sys
from urllib.parse import urlparse
import requests
from dotenv import load_dotenv
import pickle

load_dotenv()
START_URL = "https://rbs.singaporetech.edu.sg/SRB001/SRB001Page"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
}

def login(username, password):
    session = requests.Session()
    adfs_url = get_login_page(session)
    if adfs_url is None:
        print("[-] ADFS URL not found.")
        sys.exit(1)
    payload = {
        "UserName": username,
        "Password": password,
        "AuthMethod": "FormsAuthentication",
        "Kmsi": "true"
    }
    # Placeholder for login function if authentication is needed
    try:
        login_response = session.post(adfs_url, data=payload)
    except requests.exceptions.RequestException as e:
        print(f"[-] Login request failed: {e}")
        return
    if "Incorrect user ID or password" in login_response.text:
        print("[-] Login failed: Incorrect username or password")
        return
    action_url, wsfed_payload = extract_wsfed_payload(login_response)
    if action_url.startswith("/"):
        parsed_url = urlparse(adfs_url)
        action_url = f"{parsed_url.scheme}://{parsed_url.netloc}{action_url}"

    callback_headers = {
        "Referer": adfs_url,
        "Origin": f"{urlparse(adfs_url).scheme}://{urlparse(adfs_url).netloc}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    try:
        final_response = session.post(action_url, data=wsfed_payload, headers=callback_headers)
    except requests.RequestException as e:
        print(f"[!] Failed to post WS-Fed token: {e}")
        return

    if final_response.status_code == 200:
        if "Sign In" in final_response.text or "adfs/ls" in final_response.url:
            print("[!] Login loop detected. Back at login page.")
            return
        return session
    print(f"[!] Unexpected response after WS-Fed post: {final_response.status_code}")
    return


def extract_wsfed_payload(response_text):
    """
    Extracts the WS-Fed payload and action URL from the login response.
    
    :param response_text: Response object from the login POST request.
    :return: Tuple of (action_url, wsfed_payload)
    """
    hidden_inputs = re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]+)"', response_text.text)
    # HTML unescape values
    wsfed_payload = {name: html.unescape(value) for name, value in hidden_inputs}
    
    form_action_match = re.search(r'action="([^"]+)"', response_text.text)
    if not form_action_match:
        print("[-] Failed to find form action URL for WS-Fed submission")
        sys.exit(1)
    action_url = form_action_match.group(1)
    return action_url, wsfed_payload

def get_login_page(session):
    """
    Retrieves the login page to initiate the authentication process.
    
    :param session: requests.Session object
    :return: URL of the ADFS login page
    """
    session.headers.update(HEADERS)
    print("[*] Attempting to get login page...")
    response = session.get(START_URL)
    if "Sign In" not in response.text and "adfs/ls" not in response.url:
        print("[*] Failed to get login page")
        return
    adfs_url = response.url
    print("[*] Submitting login form...")
    return adfs_url

    
def get_verification_tokens(session):
    """
    Retrieves verification tokens required for booking.
    
    :param session: requests.Session object
    :return: Verification token string
    """
    try:
        response = session.get(START_URL)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"[!] Failed to fetch booking page: {e}")
        return None
    token_match = re.search(r'<input name="__RequestVerificationToken" type="hidden" value="([^"]+)" />', response.text)
    if not token_match:
        print("[-] Verification token not found on booking page.")
        return None
    token = token_match.group(1)
    print("[*] Verification token extracted.")
    return token

def main():
    """
    Main function to handle authentication and token retrieval.
    """
    session = login(os.getenv("USERNAME"), os.getenv("PASSWORD"))
    if not session:
        print("[-] Could not establish a session.")
        sys.exit(1)
    with open("auth_session.pkl", "wb") as f:
        pickle.dump(session, f)


if __name__ == "__main__":
    main()
