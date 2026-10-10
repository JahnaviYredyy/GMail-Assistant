import os
import sys
import base64
from datetime import datetime

from mcp.server.mcpserver import MCPServer

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build



# MCP SERVER

server = MCPServer("Gmail Agent Server")

# GMAIL SETTINGS


SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly"
]

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

TOKEN_PATH = os.path.join(
    BASE_DIR,
    "token.json"
)

CREDENTIALS_PATH = os.path.join(
    BASE_DIR,
    "credentials.json"
)



# CONNECT TO GMAIL

def get_gmail_service():

    print(
        "Connecting to Gmail...",
        file=sys.stderr,
        flush=True
    )
    creds = None
    # Check for existing token
    if os.path.exists(TOKEN_PATH):

        print(
            "Found token.json",
            file=sys.stderr,
            flush=True
        )

        creds = Credentials.from_authorized_user_file(
            TOKEN_PATH,
            SCOPES
        )
    
    # If token doesn't exist or isn't valid
    

    if not creds or not creds.valid:
        # Try refreshing existing token

        if (
            creds
            and creds.expired
            and creds.refresh_token
        ):

            print(
                "Refreshing Gmail token...",
                file=sys.stderr,
                flush=True
            )

            creds.refresh(
                Request()
            )

        # Start Google OAuth
        else:

            print(
                "Starting Gmail OAuth...",
                file=sys.stderr,
                flush=True
            )

            if not os.path.exists(
                CREDENTIALS_PATH
            ):

                raise FileNotFoundError(
                    "credentials.json was not found."
                )

            flow = (
                InstalledAppFlow
                .from_client_secrets_file(
                    CREDENTIALS_PATH,
                    SCOPES
                )
            )

            print(
                "Opening browser for Gmail login...",
                file=sys.stderr,
                flush=True
            )

            creds = flow.run_local_server(
                port=0
            )

        # Save token

        with open(
            TOKEN_PATH,
            "w"
        ) as token:

            token.write(
                creds.to_json()
            )

        print("New token.json created!",
            file=sys.stderr,
            flush=True
        )

   
    # Build Gmail API service

    service = build(
        "gmail",
        "v1",
        credentials=creds
    )

    print("Gmail connected successfully!",
        file=sys.stderr,
        flush=True
    )

    return service

# EXTRACT EMAIL BODY


def extract_body(payload):
    body = payload.get(
        "body",
        {}
    )
    if body.get("data"):
        try:
            return base64.urlsafe_b64decode(
                body["data"]
            ).decode(
                "utf-8",
                errors="ignore"
            )
        except Exception:
            pass

    
    # Multipart email

    parts = payload.get(
        "parts",
        []
    )

    for part in parts:
        mime_type = part.get(
            "mimeType",
            ""
        )

        
        # Plain text

        if mime_type == "text/plain":
            body_data = (
                part
                .get("body", {})
                .get("data")
            )

            if body_data:

                try:

                    return base64.urlsafe_b64decode(
                        body_data
                    ).decode(
                        "utf-8",
                        errors="ignore"
                    )

                except Exception:

                    pass

        # Nested parts

        if part.get("parts"):

            text = extract_body(part)

            if text:

                return text

    return ""


# TOOL 1 GET TODAY'S EMAILS


@server.tool()
def get_todays_emails() -> str:

    """
    Get emails received today from Gmail.
    """

    try:

        print(
            "Gmail tool: get_todays_emails()",
            file=sys.stderr,
            flush=True
        )

        service = get_gmail_service()

        # Today's date
        today = datetime.now().strftime(
            "%Y/%m/%d"
        )

        query = f"after:{today}"

        print(
            f"Gmail query: {query}",
            file=sys.stderr,
            flush=True
        )

        results = (
            service
            .users()
            .messages()
            .list(
                userId="me",
                q=query
            )
            .execute()
        )

        messages = results.get(
            "messages",
            []
        )

        print(
            f"Emails found: {len(messages)}",
            file=sys.stderr,
            flush=True
        )

        if not messages:

            return (
                "No emails received today."
            )

        email_list = []


        for message in messages:

            email = (
                service
                .users()
                .messages()
                .get(
                    userId="me",
                    id=message["id"],
                    format="full"
                )
                .execute()
            )

            payload = email.get(
                "payload",
                {}
            )

            headers = payload.get(
                "headers",
                []
            )

            sender = ""
            subject = ""


            for header in headers:

                name = (
                    header["name"]
                    .lower()
                )

                if name == "from":

                    sender = header["value"]

                elif name == "subject":

                    subject = header["value"]


            body = extract_body(
                payload
            )
            body = body[:3000]
            email_list.append(

                f"Email ID: {message['id']}\n"
                f"From: {sender}\n"
                f"Subject: {subject}\n"
                f"Body:\n{body}"

            )

        return (
            "\n\n--------------------\n\n"
            .join(email_list)
        )

    except Exception as e:

        print(
            f"ERROR: {type(e).__name__}: {e}",
            file=sys.stderr,
            flush=True
        )

        return (
            f"Error: {type(e).__name__}: {e}"
        )


# TOOL 2 GET UNREAD EMAILS

@server.tool()
def get_unread_emails() -> str:
    """Get unread emails from Gmail."""

    try:

        print(
            "Gmail tool: get_unread_emails()",
            file=sys.stderr,
            flush=True
        )

        service = get_gmail_service()

        messages = []
        page_token = None

        while True:

            results = service.users().messages().list(
                userId="me",
                q="is:unread",
                maxResults=100,
                pageToken=page_token
            ).execute()

            messages.extend(
                results.get("messages", [])
            )

            page_token = results.get(
                "nextPageToken"
            )

            if not page_token:
                break

        count = len(messages)

        print(
            f"Total unread emails: {count}",
            file=sys.stderr,
            flush=True
        )

        if count == 0:
            return "You have 0 unread emails."

        email_list = []

        for message in messages[:10]:

            email = service.users().messages().get(
                userId="me",
                id=message["id"],
                format="full"
            ).execute()

            payload = email.get(
                "payload",
                {}
            )

            headers = payload.get(
                "headers",
                []
            )

            sender = ""
            subject = ""

            for header in headers:

                name = header["name"].lower()

                if name == "from":
                    sender = header["value"]

                elif name == "subject":
                    subject = header["value"]


            body = extract_body(payload)

            # Limit body size
            body = body[:1500]

            email_list.append(
                f"Email ID: {message['id']}\n"
                f"From: {sender}\n"
                f"Subject: {subject}\n"
                f"Body:\n{body}"
            )

        result = (
            f"You have {count} unread emails.\n"
            f"Showing details for up to 10 unread emails.\n\n"
        )

        result += (
            "\n\n--------------------\n\n"
            .join(email_list)
        )

        return result

    except Exception as e:

        print(
            f"ERROR: {type(e).__name__}: {e}",
            file=sys.stderr,
            flush=True
        )

        return (
            f"Error: {type(e).__name__}: {e}"
        )



# TOOL 3 GET UNREAD EMAIL COUNT

@server.tool()
def get_unread_email_count() -> str:
    """Get the total number of unread emails in Gmail."""

    try:

        print(
            "Gmail tool: get_unread_email_count()",
            file=sys.stderr,
            flush=True
        )

        service = get_gmail_service()

        count = 0
        page_token = None

        while True:

            results = service.users().messages().list(
                userId="me",
                q="is:unread",
                maxResults=100,
                pageToken=page_token
            ).execute()

            messages = results.get(
                "messages",
                []
            )

            count += len(messages)

            page_token = results.get(
                "nextPageToken"
            )

            if not page_token:
                break

        print(
            f"Total unread emails: {count}",
            file=sys.stderr,
            flush=True
        )

        return f"You have {count} unread emails."

    except Exception as e:

        print(
            f"ERROR: {type(e).__name__}: {e}",
            file=sys.stderr,
            flush=True
        )

        return (
            f"Error: {type(e).__name__}: {e}"
        )
    
# TOOL 4 SEARCH EMAILS

@server.tool()
def search_emails(query: str) -> str:

    """
    Search Gmail using a Gmail search query.

    Examples:
    from:company.com
    subject:interview
    newer_than:7d
    is:unread
    is:unread subject:interview newer_than:7d
    """

    try:

        print(f"[INPUT RECEIVED] Gmail tool: search_emails:query={query!r}",
            file=sys.stderr,
            flush=True
        )

        service = get_gmail_service()

        results = (
            service
            .users()
            .messages()
            .list(
                userId="me",
                q=query,
                maxResults=20
            )
            .execute()
        )

        messages = results.get(
            "messages",
            []
        )

        if not messages:

            return "No emails found."

        email_list = []

        # ------------------------------------------
        # Get each email
        # ------------------------------------------

        for message in messages:

            email = (
                service
                .users()
                .messages()
                .get(
                    userId="me",
                    id=message["id"],
                    format="full"
                )
                .execute()
            )

            payload = email.get(
                "payload",
                {}
            )

            headers = payload.get(
                "headers",
                []
            )

            sender = ""
            subject = ""

            for header in headers:

                name = (
                    header["name"]
                    .lower()
                )

                if name == "from":

                    sender = header["value"]

                elif name == "subject":

                    subject = header["value"]

            body = extract_body(
                payload
            )

            body = body[:3000]

            email_list.append(

                f"Email ID: {message['id']}\n"
                f"From: {sender}\n"
                f"Subject: {subject}\n"
                f"Body:\n{body}"

            )

        return (
            "\n\n--------------------\n\n"
            .join(email_list)
        )

    except Exception as e:

        print(
            f"ERROR: {type(e).__name__}: {e}",
            file=sys.stderr,
            flush=True
        )

        return (
            f"Error: {type(e).__name__}: {e}"
        )
# TOOL 5 GET ONE EMAIL

@server.tool()
def get_email(email_id: str) -> str:

    """
    Get the complete contents of a Gmail email
    using its email ID.
    """

    try:

        print(
            f"Gmail tool: get_email({email_id})",
            file=sys.stderr,
            flush=True
        )

        service = get_gmail_service()

        email = (
            service
            .users()
            .messages()
            .get(
                userId="me",
                id=email_id,
                format="full"
            )
            .execute()
        )

        payload = email.get(
            "payload",
            {}
        )

        headers = payload.get(
            "headers",
            []
        )

        sender = ""
        subject = ""

        for header in headers:

            name = (
                header["name"]
                .lower()
            )

            if name == "from":

                sender = header["value"]

            elif name == "subject":

                subject = header["value"]

        body = extract_body(
            payload
        )

        return (

            f"From: {sender}\n"
            f"Subject: {subject}\n"
            f"Body:\n{body[:5000]}"

        )

    except Exception as e:

        print(
            f"ERROR: {type(e).__name__}: {e}",
            file=sys.stderr,
            flush=True
        )

        return (
            f"Error: {type(e).__name__}: {e}"
        )

# START MCP SERVER

if __name__ == "__main__":

    print(
        "Starting Gmail MCP server...",
        file=sys.stderr,
        flush=True
    )

    server.run()