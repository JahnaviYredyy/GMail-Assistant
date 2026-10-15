import traceback
import os
import secrets
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from agent import run_agent

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
TOKEN_DIR = BASE_DIR / "tokens"
TOKEN_DIR.mkdir(exist_ok=True)

FRONTEND_URL = os.getenv(
    "FRONTEND_URL", "http://localhost:5173"
).rstrip("/")

BACKEND_URL = os.getenv(
    "BACKEND_URL", "http://localhost:8000"
).rstrip("/")

CLIENT_SECRETS = Path(
    os.getenv("GOOGLE_CLIENT_SECRETS_FILE", "credentials.json")
)
if not CLIENT_SECRETS.is_absolute():
    CLIENT_SECRETS = BASE_DIR / CLIENT_SECRETS

REDIRECT_URI = os.getenv(
    "GOOGLE_REDIRECT_URI",
    f"{BACKEND_URL}/auth/google/callback",
).strip()

SESSION_SECRET = os.getenv("SESSION_SECRET")

if not os.getenv("GROQ_API_KEY"):
    raise RuntimeError("GROQ_API_KEY is missing from .env")

if not SESSION_SECRET:
    raise RuntimeError("SESSION_SECRET is missing from .env")

if not CLIENT_SECRETS.is_file():
    raise RuntimeError(f"Google OAuth file not found: {CLIENT_SECRETS}")

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/gmail.readonly",
]

app = FastAPI(title="Gmail Assistant API")

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    same_site="lax",
    https_only=False,  # Local development only.
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Temporary development storage. Conversations disappear after restart.
conversations = {}


def get_current_user(request: Request):
    user = request.session.get("user")

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Please sign in with Google.",
        )

    return user


def get_token_path(user_id: str) -> Path:
    # Google supplies the verified ID. Keep filenames restricted to safe characters.
    if not user_id.isdigit():
        raise HTTPException(status_code=400, detail="Invalid Google user ID.")

    return TOKEN_DIR / f"{user_id}.json"


@app.get("/")
def root():
    return {
        "message": "Gmail Assistant API is running.",
        "oauth_redirect_uri": REDIRECT_URI,
    }


@app.get("/api/health")
def health():
    return {"status": "ok"}



@app.get("/auth/google")
def google_login(request: Request):
    flow = Flow.from_client_secrets_file(
        str(CLIENT_SECRETS),
        scopes=SCOPES,
        code_verifier=secrets.token_urlsafe(64),
    )
    flow.redirect_uri = REDIRECT_URI

    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="select_account consent",
        code_challenge_method="S256",
    )

    request.session["oauth_state"] = state
    request.session["oauth_code_verifier"] = flow.code_verifier

    return RedirectResponse(authorization_url)




@app.get("/auth/google/callback")
def google_callback(
    request: Request,
    state: str,
    code: str,
):
    saved_state = request.session.get("oauth_state")
    code_verifier = request.session.get("oauth_code_verifier")

    if (
        not saved_state
        or not secrets.compare_digest(saved_state, state)
        or not code_verifier
    ):
        request.session.clear()
        raise HTTPException(
            status_code=400,
            detail="OAuth session expired or invalid. Please sign in again.",
        )

    flow = Flow.from_client_secrets_file(
        str(CLIENT_SECRETS),
        scopes=SCOPES,
        state=state,
        code_verifier=code_verifier,
    )
    flow.redirect_uri = REDIRECT_URI

    flow.fetch_token(code=code)

    credentials = flow.credentials

    oauth_service = build(
        "oauth2",
        "v2",
        credentials=credentials,
        cache_discovery=False,
    )
    google_user = oauth_service.userinfo().get().execute()

    user_id = str(google_user["id"])
    token_path = get_token_path(user_id)
    token_path.write_text(credentials.to_json(), encoding="utf-8")

    request.session.clear()
    request.session["user"] = {
        "id": user_id,
        "name": google_user.get("name", ""),
        "email": google_user.get("email", ""),
    }

    return RedirectResponse(FRONTEND_URL)



@app.get("/api/auth/me")
def current_user(request: Request):
    return {"user": get_current_user(request)}


@app.post("/api/auth/logout")
def logout(request: Request):
    request.session.clear()
    return Response(status_code=204)


@app.get("/api/chats")
def get_chats(request: Request):
    user = get_current_user(request)

    user_chats = [
        {
            "id": conversation_id,
            "title": conversation["title"],
        }
        for conversation_id, conversation in conversations.items()
        if conversation["user_id"] == user["id"]
    ]

    user_chats.reverse()
    return {"chats": user_chats}


@app.get("/api/chats/{conversation_id}/messages")
def get_chat_messages(conversation_id: str, request: Request):
    user = get_current_user(request)
    conversation = conversations.get(conversation_id)

    if not conversation or conversation["user_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    return {"messages": conversation["messages"]}


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None


@app.post("/api/chat")
async def chat(body: ChatRequest, request: Request):
    user = get_current_user(request)
    user_id = user["id"]

    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    token_path = get_token_path(user_id)

    if not token_path.is_file():
        raise HTTPException(
            status_code=401,
            detail="Gmail is not connected. Please sign in with Google again.",
        )

    conversation_id = body.conversation_id

    if conversation_id:
        conversation = conversations.get(conversation_id)

        if not conversation or conversation["user_id"] != user_id:
            raise HTTPException(status_code=404, detail="Conversation not found.")
    else:
        conversation_id = str(uuid4())
        conversation = {
            "user_id": user_id,
            "title": message[:50],
            "messages": [],
        }
        conversations[conversation_id] = conversation

    messages = conversation["messages"]
    messages.append({"role": "user", "content": message})

    try:
        answer = await run_agent(
            user_id=user_id,
            messages=messages,
            token_path=str(token_path),
        )
    

    except Exception as exc:
        print("\n========== FULL AGENT ERROR ==========", flush=True)
        traceback.print_exception(exc)
        print("=======================================\n", flush=True)

        messages.pop()
        raise HTTPException(
            status_code=500,
            detail="The Gmail assistant encountered an error. Check the backend terminal.",
        ) from exc



    messages.append({"role": "assistant", "content": answer})

    return {
        "answer": answer,
        "conversation_id": conversation_id,
    }
