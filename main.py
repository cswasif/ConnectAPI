from fastapi import FastAPI, Response, HTTPException, Header, Request, Cookie, status, Query, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
import httpx
from typing import Optional, Dict, Any
from pydantic import BaseModel
import secrets
from urllib.parse import urlencode, urlparse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from auth_config import settings
import logging
import traceback
from datetime import datetime
import json
import hashlib
import base64
import os
import time

# Development mode - set to False in production
DEV_MODE = False

# Record server start time
start_time = time.time()

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if DEV_MODE else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    error_code: str
    details: Optional[Dict[str, Any]] = None
    timestamp: str = datetime.now().isoformat()

# Paths that require password
password_protected_paths = ["/enter-tokens", "/mytokens"]

class ConnectPortalMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        logger.debug(f"Incoming request path: {path}")

        # Check for password protection
        if path in password_protected_paths:
            password = request.query_params.get("password")
            if not password or password != settings.SECRET_PASSWORD:
                logger.warning(f"Unauthorized access attempt to {path}")
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content=ErrorResponse(
                        error="Authentication failed",
                        error_code="PASSWORD_REQUIRED",
                        details={"message": "Password required to access this endpoint."} if DEV_MODE else None
                    ).dict()
                )

        try:
            return await call_next(request)

        except Exception as e:
            logger.error(f"Error in middleware: {str(e)}")
            logger.debug(traceback.format_exc())
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=ErrorResponse(
                    error="Internal server error",
                    error_code="MIDDLEWARE_ERROR",
                    details={"message": str(e)} if DEV_MODE else None
                ).dict()
            )

app = FastAPI()

token_file = "tokens.json"

def save_tokens(tokens):
    # If expires_in is present, store the expiry timestamp
    if "expires_in" in tokens:
        tokens["expires_at"] = int(time.time()) + int(tokens["expires_in"])
    with open(token_file, "w") as f:
        json.dump(tokens, f)

def load_tokens():
    if not os.path.exists(token_file):
        return None
    with open(token_file, "r") as f:
        return json.load(f)

def is_token_expired(tokens, buffer=60):
    # buffer: seconds before expiry to refresh
    if not tokens or "expires_at" not in tokens:
        return True
    return int(time.time()) > int(tokens["expires_at"]) - buffer

async def refresh_access_token(refresh_token):
    token_url = "https://sso.bracu.ac.bd/realms/bracu/protocol/openid-connect/token"
    data = {
        "grant_type": "refresh_token",
        "client_id": "slm",
        "refresh_token": refresh_token,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(token_url, data=data)
        if resp.status_code == 200:
            return resp.json()
        else:
            return f"<pre>Failed to refresh token: {resp.text}</pre>"

@app.get("/", response_class=HTMLResponse)
async def root():
    """Show API status and navigation links"""
    # Calculate uptime
    current_time = time.time()
    uptime_seconds = int(current_time - start_time)

    # Format uptime
    hours, remainder = divmod(uptime_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    uptime_str = f"Uptime: {hours}h {minutes}m {seconds}s"

    html_content = f"""
    <html>
        <head>
            <title>BRACU Schedule Viewer API</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    margin: 0;
                    padding: 0;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    min-height: 100vh;
                    background-color: #f5f5f5;
                }}
                .container {{
                    background-color: white;
                    padding: 40px;
                    border-radius: 10px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                    text-align: center;
                }}
                h1 {{
                    color: #333;
                    margin-bottom: 20px;
                }}
                .button-container {{
                    margin-top: 20px;
                }}
                .button {{
                    display: inline-block;
                    padding: 12px 24px;
                    margin: 5px;
                    background-color: #007bff;
                    color: white;
                    text-decoration: none;
                    border-radius: 5px;
                    font-weight: bold;
                    transition: background-color 0.2s;
                }}
                .button:hover {{
                    background-color: #0056b3;
                }}
                .status {{
                    margin-top: 20px;
                    color: #555;
                    font-size: 0.9em;
                }}
                 .uptime-status {{
                    margin-top: 10px;
                    color: #555;
                    font-size: 0.9em;
                 }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>BRACU Schedule Viewer API</h1>
                <p>Your local API server is running.</p>
                <div class="button-container">
                    <a href="/enter-tokens" class="button">Enter Tokens</a>
                    <a href="/raw-schedule" class="button">View Schedule</a>
                    <a href="/mytokens" class="button">View Stored Tokens</a>
                </div>
                 <p class="status">API Status: Active</p>
                 <p class="uptime-status">{uptime_str}</p>
            </div>
            <script>
                document.addEventListener('DOMContentLoaded', function() {{
                    const enterTokensLink = document.querySelector('a[href="/enter-tokens"]');
                    const viewTokensLink = document.querySelector('a[href="/mytokens"]');

                    if (enterTokensLink) {{
                        enterTokensLink.addEventListener('click', function(event) {{
                            event.preventDefault();
                            const password = prompt('Please enter the password:');
                            if (password !== null && password !== '') {{
                                window.location.href = '/enter-tokens?password=' + encodeURIComponent(password);
                            }}
                        }});
                    }}

                    if (viewTokensLink) {{
                        viewTokensLink.addEventListener('click', function(event) {{
                            event.preventDefault();
                            const password = prompt('Please enter the password:');
                            if (password !== null && password !== '') {{
                                window.location.href = '/mytokens?password=' + encodeURIComponent(password);
                            }}
                        }});
                    }}
                }});
            </script>
        </body>
    </html>
    """

    return HTMLResponse(content=html_content)

@app.get("/raw-schedule", response_class=HTMLResponse)
async def raw_schedule(request: Request, access_token: str = None):
    """Display raw schedule JSON data using a Bearer access_token, auto-refresh if expired."""
    try:
        tokens = None
        if not access_token:
            tokens = load_tokens()
            if tokens and "access_token" in tokens:
                # Auto-refresh if expired or about to expire
                if is_token_expired(tokens):
                    if "refresh_token" in tokens:
                        new_tokens = await refresh_access_token(tokens["refresh_token"])
                        save_tokens(new_tokens)
                        tokens = new_tokens
                    else:
                        return '''<html><body><h2>Token expired and no refresh token found.</h2><p>Please <a href="/enter-tokens">enter your tokens</a> again.</p></body></html>'''
                access_token = tokens["access_token"]
            else:
                return '''
                <html>
                    <head><title>Provide Access Token</title></head>
                    <body>
                        <h2>No access token found.</h2>
                        <p>Please <a href="/enter-tokens">enter your tokens</a> first.</p>
                    </body>
                </html>
                '''
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }
        schedule_url = "https://connect.bracu.ac.bd/api/adv/v1/advising/sections/student/42749/schedules"
        async with httpx.AsyncClient() as client:
            resp = await client.get(schedule_url, headers=headers)
            if resp.status_code != 200:
                return f"<pre>Failed: {resp.status_code}\n{resp.text}</pre>"
            data = resp.json()
            return f"<pre>{json.dumps(data, indent=2)}</pre>"
    except Exception as e:
        return f"<pre>Error: {str(e)}</pre>"

@app.get("/mytokens", response_class=HTMLResponse)
async def view_tokens(request: Request):
    """View stored tokens (requires authentication)."""
    tokens = load_tokens()
    if not tokens:
        return "<h2>No tokens stored. Please login and save your tokens first.</h2>"
    return f"<h2>Stored Tokens</h2><pre>{json.dumps(tokens, indent=2)}</pre>"

@app.get("/enter-tokens", response_class=HTMLResponse)
async def enter_tokens_form(request: Request):
    """Serve the form to manually enter tokens."""
    return """
    <html>
        <head>
            <title>Enter Tokens</title>
            <style>
                body { font-family: Arial, sans-serif; background: #f5f5f5; }
                .container { max-width: 600px; margin: 40px auto; background: #fff; padding: 30px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
                input, textarea { width: 100%; padding: 10px; margin: 10px 0 20px 0; border-radius: 4px; border: 1px solid #ccc; }
                button { padding: 10px 20px; background: #007bff; color: #fff; border: none; border-radius: 4px; cursor: pointer; }
                button:hover { background: #0056b3; }
            </style>
        </head>
        <body>
            <div class="container">
                <h2>Manually Enter Your Tokens</h2>
                <form method="post">
                    <label>Access Token:</label>
                    <textarea name="access_token" rows="4" required></textarea>
                    <label>Refresh Token:</label>
                    <textarea name="refresh_token" rows="4" required></textarea>
                    <button type="submit">Save Tokens</button>
                </form>
            </div>
        </body>
    </html>
    """

@app.post("/enter-tokens", response_class=HTMLResponse)
async def save_tokens_form(access_token: str = Form(...), refresh_token: str = Form(...)):
    """Handle saving tokens."""
    tokens = {
        "access_token": access_token,
        "refresh_token": refresh_token
    }
    save_tokens(tokens)
    return """
    <html>
        <body>
            <h2>Tokens saved!</h2>
            <a href='/mytokens'>View Tokens</a>
        </body>
    </html>
    """

# Add CORS middleware with development settings
if DEV_MODE:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5175", "http://localhost:5176", "http://localhost:8000", "https://connect.bracu.ac.bd"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
        max_age=3600,
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.FRONTEND_URL, "https://connect.bracu.ac.bd"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["*"],
        max_age=3600,
    )

# Add Connect portal middleware
app.add_middleware(ConnectPortalMiddleware)

# Add global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {str(exc)}")
    logger.debug(traceback.format_exc())
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error="Internal server error",
            error_code="UNHANDLED_ERROR",
            details={"message": str(exc)} if DEV_MODE else None
        ).dict()
    ) 