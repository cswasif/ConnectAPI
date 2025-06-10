from fastapi import FastAPI, Response, HTTPException, Header, Request, Cookie, status, Query, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
import httpx
from typing import Optional, Dict, Any
from pydantic import BaseModel
import secrets
from urllib.parse import urlencode, urlparse
from starlette.middleware.sessions import SessionMiddleware
from auth_config import settings
import logging
import traceback
from datetime import datetime
import json
import hashlib
import base64
import os
import time
import redis.asyncio as redis
import jwt
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get OAuth2 credentials from environment variables
OAUTH_CLIENT_ID = os.getenv('OAUTH_CLIENT_ID', 'connect-portal')
OAUTH_CLIENT_SECRET = os.getenv('OAUTH_CLIENT_SECRET', '')
OAUTH_TOKEN_URL = os.getenv('OAUTH_TOKEN_URL', 'https://sso.bracu.ac.bd/realms/bracu/protocol/openid-connect/token')

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

# Create FastAPI app first
app = FastAPI()

# Add middleware in correct order
app.add_middleware(SessionMiddleware, secret_key="super-secret-session-key")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL] if not DEV_MODE else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def session_error_handler(request: Request, call_next):
    response = await call_next(request)
    return response

# Upstash Redis config
REDIS_URL = os.environ.get("REDIS_URL") or "rediss://default:AajsAAIjcDExN2MxMjVlNmRhMTc0ODI1OTlhMzRkZjY1MGFjZGJiNXAxMA@willing-husky-43244.upstash.io:6379"

async def get_redis():
    return redis.from_url(REDIS_URL, decode_responses=True)

def decode_jwt_token(token: str) -> dict:
    """Decode a JWT token without verification to get expiration time."""
    try:
        # Split the token and get the payload part (second part)
        parts = token.split('.')
        if len(parts) != 3:
            logger.error("Invalid JWT token format")
            return {}
        
        # Decode the payload
        # Add padding if needed
        padding = len(parts[1]) % 4
        if padding:
            parts[1] += '=' * (4 - padding)
        
        payload = json.loads(base64.b64decode(parts[1]).decode('utf-8'))
        return payload
    except Exception as e:
        logger.error(f"Error decoding JWT token: {str(e)}")
        return {}

async def save_tokens_to_redis(session_id, tokens):
    """Save tokens to Redis with proper expiration time from JWT."""
    try:
        redis_conn = await get_redis()
        now = int(time.time())
        
        # Get expiration from JWT if we have an access token
        if "access_token" in tokens:
            jwt_data = decode_jwt_token(tokens["access_token"])
            if "exp" in jwt_data:
                tokens["expires_at"] = jwt_data["exp"]
                tokens["expires_in"] = max(0, jwt_data["exp"] - now)
                logger.info(f"Got token expiration from JWT: {tokens['expires_in']} seconds remaining")
            else:
                # Fallback to default 5 minutes if no exp in JWT
                tokens["expires_at"] = now + 300
                tokens["expires_in"] = 300
                logger.warning("No expiration found in JWT, using default 5 minutes")
        
        # Always set refresh token expiration to 30 minutes from now if we have a refresh token
        if "refresh_token" in tokens:
            tokens["refresh_expires_at"] = now + (30 * 60)  # 30 minutes
        
        # Save tokens with expiration
        key = f"tokens:{session_id}"
        await redis_conn.set(key, json.dumps(tokens))
        
        # Set key expiration to match the refresh token expiration
        await redis_conn.expire(key, 30 * 60)  # 30 minutes
        
        logger.info(f"Tokens saved in Redis for session {session_id}. Access token expires in {tokens.get('expires_in', 0)}s")
        return True
    except Exception as e:
        logger.error(f"Error saving tokens to Redis: {str(e)}")
        raise

async def load_tokens_from_redis(session_id):
    """Load tokens from Redis with validation."""
    try:
        redis_conn = await get_redis()
        key = f"tokens:{session_id}"
        data = await redis_conn.get(key)
        
        if data:
            tokens = json.loads(data)
            # Validate token expiration
            if not is_token_expired(tokens):
                logger.info(f"Valid tokens loaded from Redis for session {session_id}")
                return tokens
            else:
                logger.info(f"Expired tokens found for session {session_id}, attempting refresh")
                if "refresh_token" in tokens:
                    try:
                        new_tokens = await refresh_access_token(tokens["refresh_token"])
                        if new_tokens:
                            await save_tokens_to_redis(session_id, new_tokens)
                            return new_tokens
                    except Exception as e:
                        logger.error(f"Token refresh failed: {str(e)}")
                
                # If we get here, tokens are expired and refresh failed
                await redis_conn.delete(key)
                return None
        else:
            logger.info(f"No tokens found in Redis for session {session_id}")
            return None
    except Exception as e:
        logger.error(f"Error loading tokens from Redis: {str(e)}")
        return None

async def save_global_student_tokens(student_id, tokens):
    try:
        redis_conn = await get_redis()
        if "expires_in" in tokens:
            tokens["expires_at"] = int(time.time()) + int(tokens["expires_in"])
        await redis_conn.set(f"student_tokens:{student_id}", json.dumps(tokens))
        logger.info(f"Global tokens updated for student_id {student_id}.")
        return True
    except Exception as e:
        logger.error(f"Error saving global student tokens to Redis: {str(e)}")
        raise

async def load_global_student_tokens(student_id):
    try:
        redis_conn = await get_redis()
        data = await redis_conn.get(f"student_tokens:{student_id}")
        if data:
            tokens = json.loads(data)
            logger.info(f"Global tokens loaded for student_id {student_id}.")
            return tokens
        else:
            logger.info(f"No global tokens found for student_id {student_id}.")
            return None
    except Exception as e:
        logger.error(f"Error loading global student tokens from Redis: {str(e)}")
        return None

async def save_student_schedule(student_id, schedule):
    try:
        redis_conn = await get_redis()
        await redis_conn.set(f"student_schedule:{student_id}", json.dumps(schedule))
        logger.info(f"Schedule cached for student_id {student_id} (no expiration).")
        return True
    except Exception as e:
        logger.error(f"Error saving student schedule to Redis: {str(e)}")
        raise

async def load_student_schedule(student_id):
    try:
        redis_conn = await get_redis()
        data = await redis_conn.get(f"student_schedule:{student_id}")
        if data:
            schedule = json.loads(data)
            logger.info(f"Schedule loaded from cache for student_id {student_id}.")
            return schedule
        else:
            logger.info(f"No cached schedule found for student_id {student_id}.")
            return None
    except Exception as e:
        logger.error(f"Error loading student schedule from Redis: {str(e)}")
        return None

def get_basic_auth_header():
    """Generate Basic Auth header from environment variables."""
    if not OAUTH_CLIENT_SECRET:
        logger.warning("OAuth client secret not configured! Token refresh may fail.")
    
    credentials = f"{OAUTH_CLIENT_ID}:{OAUTH_CLIENT_SECRET}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return f"Basic {encoded}"

async def refresh_access_token(refresh_token: str) -> dict:
    """Refresh the access token using the refresh token."""
    token_url = "https://sso.bracu.ac.bd/realms/bracu/protocol/openid-connect/token"
    data = {
        "grant_type": "refresh_token",
        "client_id": "slm",  # Using the working client_id from old implementation
        "refresh_token": refresh_token,
    }
    
    try:
        async with httpx.AsyncClient() as client:
            logger.debug(f"Trying token refresh at: {token_url}")
            resp = await client.post(token_url, data=data, timeout=10.0)
            logger.debug(f"Token refresh response: {resp.status_code} {resp.text}")
            
            if resp.status_code == 200:
                try:
                    new_tokens = resp.json()
                    if isinstance(new_tokens, dict) and "access_token" in new_tokens:
                        logger.info("Successfully refreshed access token")
                        now = int(time.time())
                        
                        # Get expiration from new access token
                        access_jwt_data = decode_jwt_token(new_tokens["access_token"])
                        if "exp" in access_jwt_data:
                            new_tokens["expires_at"] = access_jwt_data["exp"]
                            new_tokens["expires_in"] = max(0, access_jwt_data["exp"] - now)
                        
                        # If we got a new refresh token, get its expiration
                        if "refresh_token" in new_tokens:
                            refresh_jwt_data = decode_jwt_token(new_tokens["refresh_token"])
                            if "exp" in refresh_jwt_data:
                                new_tokens["refresh_expires_at"] = refresh_jwt_data["exp"]
                            else:
                                new_tokens["refresh_expires_at"] = now + (30 * 60)  # 30 minutes default
                        else:
                            # Keep the old refresh token if we didn't get a new one
                            new_tokens["refresh_token"] = refresh_token
                            refresh_jwt_data = decode_jwt_token(refresh_token)
                            if "exp" in refresh_jwt_data:
                                new_tokens["refresh_expires_at"] = refresh_jwt_data["exp"]
                            else:
                                new_tokens["refresh_expires_at"] = now + (30 * 60)  # 30 minutes default
                        
                        logger.info(f"New tokens: Access expires in {new_tokens.get('expires_in')}s, "
                                  f"Refresh expires in {new_tokens.get('refresh_expires_at', 0) - now}s")
                        return new_tokens
                    else:
                        logger.error(f"Invalid token refresh response format")
                        return None
                except Exception as e:
                    logger.error(f"Failed to parse token refresh response: {str(e)}")
                    return None
            elif resp.status_code == 401:
                logger.error("Refresh token has expired or is invalid")
                return None
            else:
                logger.error(f"Failed to refresh token: {resp.status_code} {resp.text}")
                return None
    except Exception as e:
        logger.error(f"Error refreshing token: {str(e)}")
        return None

def is_token_expired(tokens, buffer=60):
    """Check if tokens are expired with a buffer time."""
    if not tokens:
        return True
    now = int(time.time())
    # Check access token expiration
    if "expires_at" in tokens:
        if now + buffer >= tokens["expires_at"]:
            return True
    return False

async def get_latest_valid_token():
    """Get the most recent valid token from Redis, attempting to refresh if needed."""
    try:
        # Get all token keys
        redis_conn = await get_redis()
        token_keys = await redis_conn.keys("tokens:*")
        if not token_keys:
            logger.warning("No tokens found in Redis")
            return None
            
        latest_token = None
        latest_expiry = 0
        needs_refresh = True
        session_id = None
        
        # First try to find the most recent valid token
        for key in token_keys:
            tokens_str = await redis_conn.get(key)
            if tokens_str:
                tokens = json.loads(tokens_str)
                if "expires_at" in tokens:
                    # If this token expires later than our current latest, update it
                    if tokens["expires_at"] > latest_expiry:
                        latest_token = tokens
                        latest_expiry = tokens["expires_at"]
                        needs_refresh = is_token_expired(tokens)
                        session_id = key.split(":")[-1]
        
        # If we found a valid token that doesn't need refresh, use it
        if latest_token and not needs_refresh:
            logger.info("Using existing valid token")
            return latest_token.get("access_token")
        
        # If we have a token but it needs refresh, try to refresh it
        if latest_token and "refresh_token" in latest_token and session_id:
            logger.info("Attempting to refresh token")
            try:
                new_tokens = await refresh_access_token(latest_token["refresh_token"])
                if new_tokens and "access_token" in new_tokens:
                    # Save the refreshed tokens
                    await save_tokens_to_redis(session_id, new_tokens)
                    logger.info("Successfully refreshed token")
                    return new_tokens.get("access_token")
            except Exception as e:
                logger.error(f"Error refreshing token: {str(e)}")
                # Delete the expired/invalid tokens
                await redis_conn.delete(f"tokens:{session_id}")
        
        logger.warning("No valid tokens found and refresh attempts failed")
        return None
    except Exception as e:
        logger.error(f"Error in get_latest_valid_token: {str(e)}")
        return None

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    session_id = request.session.get("id")
    if not session_id:
        session_id = secrets.token_urlsafe(16)
        request.session["id"] = session_id
    # Calculate token uptime (remaining time)
    token_uptime_display = "No active token."
    try:
        tokens = await load_tokens_from_redis(session_id)
        if tokens and "expires_at" in tokens:
            now = int(time.time())
            remaining = max(0, tokens["expires_at"] - now)
            days, remainder = divmod(remaining, 86400)
            hours, remainder = divmod(remainder, 3600)
            minutes, seconds = divmod(remainder, 60)
            uptime_str = []
            if days:
                uptime_str.append(f"{days} day{'s' if days != 1 else ''}")
            if hours:
                uptime_str.append(f"{hours} hour{'s' if hours != 1 else ''}")
            if minutes:
                uptime_str.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
            if seconds or not uptime_str:
                uptime_str.append(f"{seconds} second{'s' if seconds != 1 else ''}")
            token_uptime_display = 'Token active for: ' + ', '.join(uptime_str)
    except Exception:
        pass
    html_content = f"""
    <html><head><title>BRACU Schedule Viewer</title>
    <style>
    body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #f5f5f5; margin: 0; }}
    .container {{ max-width: 480px; margin: 60px auto; background: #fff; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); padding: 40px 32px; }}
    h1 {{ color: #2d3748; margin-bottom: 12px; }}
    .desc {{ color: #4a5568; margin-bottom: 24px; }}
    .button-container {{ display: flex; gap: 12px; justify-content: center; margin-bottom: 24px; }}
    .button {{ background: #3182ce; color: #fff; border: none; border-radius: 6px; padding: 10px 22px; font-size: 1rem; cursor: pointer; text-decoration: none; transition: background 0.2s; }}
    .button:hover {{ background: #225ea8; }}
    .session-id {{ font-size: 0.9em; color: #718096; margin-top: 18px; text-align: center; }}
    .uptime {{ font-size: 0.9em; color: #718096; margin-top: 8px; text-align: center; }}
    .token-uptime {{ font-size: 0.9em; color: #718096; margin-top: 8px; text-align: center; }}
    </style></head><body>
    <div class='container'>
        <h1>BRACU Schedule Viewer</h1>
        <div class='desc'>A simple client to view your BRACU Connect schedule.<br>Session-based, no password required.</div>
        <div class='button-container'>
            <a class='button' href='/enter-tokens'>Enter Tokens</a>
            <a class='button' href='/mytokens'>View Tokens</a>
            <a class='button' href='/raw-schedule'>View Raw Schedule</a>
        </div>
        <div class='session-id'>Session: {session_id}</div>
        <div class='token-uptime'>{token_uptime_display}</div>
    </div></body></html>
    """
    return HTMLResponse(html_content)

@app.get("/enter-tokens", response_class=HTMLResponse)
async def enter_tokens_form(request: Request):
    session_id = request.session.get("id")
    if not session_id:
        # No session, redirect to home
        return RedirectResponse("/", status_code=302)
    html_content = """
    <html><head><title>Enter Tokens</title>
    <style>
    body { font-family: 'Segoe UI', Arial, sans-serif; background: #f5f5f5; margin: 0; }
    .container { max-width: 420px; margin: 60px auto; background: #fff; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); padding: 36px 28px; }
    h2 { color: #2d3748; margin-bottom: 18px; }
    form { display: flex; flex-direction: column; gap: 16px; }
    input { padding: 10px; border-radius: 6px; border: 1px solid #cbd5e0; font-size: 1rem; }
    button { background: #3182ce; color: #fff; border: none; border-radius: 6px; padding: 10px 0; font-size: 1rem; cursor: pointer; transition: background 0.2s; }
    button:hover { background: #225ea8; }
    .back { display: block; margin-top: 18px; color: #3182ce; text-decoration: none; }
    .back:hover { text-decoration: underline; }
    </style></head><body>
    <div class='container'>
        <h2>Enter Your Tokens</h2>
        <form action='/enter-tokens' method='post'>
            <input name='access_token' placeholder='Access Token' required autocomplete='off'>
            <input name='refresh_token' placeholder='Refresh Token' required autocomplete='off'>
            <button type='submit'>Save Tokens</button>
        </form>
        <a class='back' href='/'>Back to Home</a>
    </div></body></html>
    """
    return HTMLResponse(html_content)

@app.post("/enter-tokens", response_class=HTMLResponse)
async def save_tokens_form(request: Request, access_token: str = Form(...), refresh_token: str = Form(...)):
    session_id = request.session.get("id")
    if not session_id:
        # No session, redirect to home
        return RedirectResponse("/", status_code=302)
    
    # Get token expiration from JWT
    now = int(time.time())
    access_jwt_data = decode_jwt_token(access_token)
    refresh_jwt_data = decode_jwt_token(refresh_token)
    
    tokens = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": access_jwt_data.get("exp", now + 300),  # 5 minutes default
        "refresh_expires_at": refresh_jwt_data.get("exp", now + 1800)  # 30 minutes default
    }
    
    await save_tokens_to_redis(session_id, tokens)
    html_content = """
    <html><head><title>Tokens Saved</title>
    <style>
    body { font-family: 'Segoe UI', Arial, sans-serif; background: #f5f5f5; margin: 0; }
    .container { max-width: 420px; margin: 60px auto; background: #fff; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); padding: 36px 28px; text-align: center; }
    .msg { color: #2d3748; font-size: 1.1em; margin-bottom: 18px; }
    .back { display: block; margin-top: 18px; color: #3182ce; text-decoration: none; }
    .back:hover { text-decoration: underline; }
    </style></head><body>
    <div class='container'>
        <div class='msg'>Tokens saved successfully!</div>
        <a class='back' href='/'>Back to Home</a>
    </div></body></html>
    """
    return HTMLResponse(html_content)

@app.get("/mytokens", response_class=HTMLResponse)
async def view_tokens(request: Request, session_id: str = None):
    """View tokens for the current session."""
    try:
        current_session = request.session.get("id")
        if not current_session:
            # No session, redirect to home
            return RedirectResponse("/", status_code=302)
        
        # If a specific session_id is requested, verify it matches the current session
        if session_id and session_id != current_session:
            return HTMLResponse("""
                <html><head><title>Error</title>
                <style>
                body { font-family: 'Segoe UI', Arial, sans-serif; background: #f5f5f5; margin: 0; }
                .container { max-width: 520px; margin: 60px auto; background: #fff; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); padding: 36px 28px; text-align: center; }
                .error { color: #e53e3e; margin-bottom: 18px; }
                .back { display: block; margin-top: 18px; color: #3182ce; text-decoration: none; }
                .back:hover { text-decoration: underline; }
                </style></head><body>
                <div class='container'>
                    <div class='error'>You can only view tokens for your own session.</div>
                    <a class='back' href='/'>Back to Home</a>
                </div></body></html>
            """, status_code=403)

        # Load tokens for the current session
        redis_conn = await get_redis()
        tokens = await load_tokens_from_redis(current_session)
        
        # If no tokens found in current session, try to get the latest valid token
        if not tokens:
            latest_token = await get_latest_valid_token()
            if latest_token:
                # Create new tokens object with the latest token
                tokens = {
                    "access_token": latest_token,
                    "expires_at": int(time.time()) + 300,  # 5 minutes default
                    "refresh_expires_at": int(time.time()) + 1800  # 30 minutes default
                }
                # Save these tokens to the current session
                await save_tokens_to_redis(current_session, tokens)
                logger.info(f"Saved latest valid token to session {current_session}")
        
        # Calculate token expiration times if tokens exist
        token_info = ""
        if tokens:
            now = int(time.time())
            access_expires_in = max(0, tokens.get("expires_at", 0) - now)
            refresh_expires_in = max(0, tokens.get("refresh_expires_at", 0) - now)
            
            # If tokens are expired, try to refresh them
            if access_expires_in <= 0 and "refresh_token" in tokens:
                try:
                    new_tokens = await refresh_access_token(tokens["refresh_token"])
                    if new_tokens:
                        await save_tokens_to_redis(current_session, new_tokens)
                        tokens = new_tokens
                        access_expires_in = max(0, tokens.get("expires_at", 0) - now)
                        refresh_expires_in = max(0, tokens.get("refresh_expires_at", 0) - now)
                        logger.info(f"Refreshed tokens for session {current_session}")
                except Exception as e:
                    logger.error(f"Token refresh failed: {str(e)}")
            
            token_info = f"""
            <div class='token-info'>
                <div class='expiry'>Access token expires in: {access_expires_in} seconds</div>
                <div class='expiry'>Refresh token expires in: {refresh_expires_in} seconds</div>
            </div>
            """

        html_content = f"""
        <html><head><title>My Tokens</title>
        <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #f5f5f5; margin: 0; }}
        .container {{ max-width: 520px; margin: 60px auto; background: #fff; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); padding: 36px 28px; }}
        h2 {{ color: #2d3748; margin-bottom: 18px; }}
        pre {{ background: #f7fafc; border-radius: 6px; padding: 18px; font-size: 1em; color: #2d3748; overflow-x: auto; }}
        .msg {{ color: #e53e3e; margin-bottom: 18px; }}
        .back {{ display: block; margin-top: 18px; color: #3182ce; text-decoration: none; }}
        .back:hover {{ text-decoration: underline; }}
        .token-info {{ margin: 12px 0; padding: 12px; background: #ebf8ff; border-radius: 6px; }}
        .expiry {{ color: #2b6cb0; margin: 4px 0; }}
        .session {{ font-size: 0.9em; color: #718096; margin-top: 12px; }}
        </style></head><body>
        <div class='container'>
            <h2>Your Tokens</h2>
            {token_info if tokens else '<div class="msg">No tokens found for your session.</div>'}
            {('<pre>' + json.dumps(tokens, indent=2) + '</pre>') if tokens else ''}
            <div class='session'>Session ID: {current_session}</div>
            <a class='back' href='/'>Back to Home</a>
        </div></body></html>
        """
        return HTMLResponse(html_content)
    except Exception as e:
        logger.error(f"Error in view_tokens: {str(e)}")
        return HTMLResponse(f"""
            <html><head><title>Error</title>
            <style>
            body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #f5f5f5; margin: 0; }}
            .container {{ max-width: 520px; margin: 60px auto; background: #fff; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); padding: 36px 28px; text-align: center; }}
            .error {{ color: #e53e3e; margin-bottom: 18px; }}
            .back {{ display: block; margin-top: 18px; color: #3182ce; text-decoration: none; }}
            .back:hover {{ text-decoration: underline; }}
            </style></head><body>
            <div class='container'>
                <div class='error'>An error occurred while loading tokens.</div>
                <div class='error'>{str(e)}</div>
                <a class='back' href='/'>Back to Home</a>
            </div></body></html>
        """, status_code=500)

@app.get("/raw-schedule", response_class=JSONResponse)
async def raw_schedule(request: Request):
    """Get the raw schedule data. Public endpoint using most recent valid token or latest cached schedule."""
    try:
        session_id = request.session.get("id")
        # Try to get a valid token
        if session_id:
            tokens = await load_tokens_from_redis(session_id)
            if tokens and "access_token" in tokens and not is_token_expired(tokens):
                token = tokens["access_token"]
            else:
                token = await get_latest_valid_token()
        else:
            token = await get_latest_valid_token()

        if not token:
            # No valid token, try to return the most recently cached schedule
            redis_conn = await get_redis()
            keys = await redis_conn.keys("student_schedule:*")
            if keys:
                # Get the latest schedule by key (lexicographically last, or you can sort by last modified if needed)
                latest_key = sorted(keys)[-1]
                cached_schedule = await redis_conn.get(latest_key)
                if cached_schedule:
                    return JSONResponse({
                        "cached": True,
                        "data": json.loads(cached_schedule),
                        "message": "Showing latest cached schedule (no valid token available)"
                    })
            return JSONResponse({"error": "No valid token or cached schedule available"}, status_code=503)

        # Set up headers with the token
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "Mozilla/5.0",
            "Origin": "https://connect.bracu.ac.bd",
            "Referer": "https://connect.bracu.ac.bd/"
        }
        
        # First fetch student_id from portfolios endpoint
        portfolios_url = "https://connect.bracu.ac.bd/api/mds/v1/portfolios"
        async with httpx.AsyncClient() as client:
            resp = await client.get(portfolios_url, headers=headers)
            if resp.status_code == 401:  # Unauthorized - token might be invalid
                logger.warning("Token unauthorized, attempting refresh")
                # Clear the invalid token and try again with a fresh token
                if session_id:
                    await redis_conn.delete(f"tokens:{session_id}")
                return JSONResponse({"error": "Token expired, please refresh page"}, status_code=401)
            
            if resp.status_code != 200:
                return JSONResponse({
                    "error": "Failed to fetch student info", 
                    "status_code": resp.status_code, 
                    "details": resp.text
                }, status_code=resp.status_code)
            
            data = resp.json()
            if not isinstance(data, list) or not data or "id" not in data[0]:
                return JSONResponse({"error": "Could not find student id in response."}, status_code=500)
            
            student_id = data[0]["id"]

            # Try to fetch the schedule
            schedule_url = f"https://connect.bracu.ac.bd/api/adv/v1/advising/sections/student/{student_id}/schedules"
            resp = await client.get(schedule_url, headers=headers)
            
            if resp.status_code == 200:
                data = resp.json()
                # Cache the successful response
                await save_student_schedule(student_id, data)
                return JSONResponse(data)
            elif resp.status_code == 401:  # Unauthorized - token might be invalid
                logger.warning("Token unauthorized, attempting refresh")
                # Clear the invalid token
                if session_id:
                    await redis_conn.delete(f"tokens:{session_id}")
                return JSONResponse({"error": "Token expired, please refresh page"}, status_code=401)
            else:
                # On any error, try to return cached schedule
                cached_schedule = await load_student_schedule(student_id)
                if cached_schedule:
                    return JSONResponse({
                        "cached": True,
                        "data": cached_schedule,
                        "message": f"Using cached schedule due to API error: {resp.status_code}"
                    })
                return JSONResponse({
                    "error": f"Failed to fetch schedule: {resp.text}",
                    "status_code": resp.status_code
                }, status_code=resp.status_code)
                
    except Exception as e:
        logger.error(f"Error in raw_schedule: {str(e)}")
        return JSONResponse({
            "error": f"Internal server error: {str(e)}"
        }, status_code=500)

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