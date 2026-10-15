
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


BASE_DIR = Path(__file__).resolve().parent
TOKEN_FILE = BASE_DIR / "token.json"
CLIENT_FILE = BASE_DIR / "credentials.json"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly"
]


def main():
    creds = None

    # Load the saved token, if present.
    if TOKEN_FILE.exists():
        try:
            creds = Credentials.from_authorized_user_file(
                str(TOKEN_FILE),
                SCOPES,
            )
        except (ValueError, OSError) as exc:
            print(f"Could not load saved token: {exc}")

    # Try refreshing the token.
    if creds and creds.expired and creds.refresh_token:
        try:
            print("Refreshing the saved Gmail token...")
            creds.refresh(Request())
            print("Token refreshed successfully.")

        except Exception as exc:
            print(f"Saved token cannot be refreshed: {exc}")
            creds = None

    # Start Google authorization if credentials are invalid.
    if not creds or not creds.valid:
        if not CLIENT_FILE.exists():
            raise FileNotFoundError(
                f"Missing Google OAuth file: {CLIENT_FILE}"
            )

        print("Opening Google sign-in...")
        flow = InstalledAppFlow.from_client_secrets_file(
            str(CLIENT_FILE),
            SCOPES,
        )

        creds = flow.run_local_server(
    port=0,
    authorization_prompt_message="",
    success_message="Gmail connected successfully.",
    open_browser=True,
    login_hint="",
)

    # Save the newly authorized or refreshed token.
    TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")

    # Test access to Gmail.
    service = build(
        "gmail",
        "v1",
        credentials=creds,
        cache_discovery=False,
    )

    profile = service.users().getProfile(userId="me").execute()

    print("\nGmail authentication successful!")
    print("Connected Gmail account:", profile.get("emailAddress"))
    print("Total messages:", profile.get("messagesTotal"))
    print("Total threads:", profile.get("threadsTotal"))


if __name__ == "__main__":
    main()
