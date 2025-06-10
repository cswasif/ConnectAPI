# ConnectAPI

A FastAPI-based API service for accessing BRACU (BRAC University) student schedules. This API provides a simplified interface to fetch schedule data from the BRACU Connect portal.

## Features

- Public schedule endpoint
- Token management and auto-refresh
- Upstash Redis for token storage and caching
- Error handling and fallback mechanisms
- Deployed on Vercel
- **Session-based security for sensitive endpoints**: Only users with a valid session can access `/enter-tokens` and `/mytokens`. The `/raw-schedule` endpoint remains public.

## Tech Stack

- **Backend Framework**: FastAPI
- **Database**: Upstash Redis (Serverless Redis)
- **Deployment**: Vercel
- **Runtime**: Python 3.7+

## Setup

1. Clone the repository:
```bash
git clone https://github.com/cswasif/ConnectAPI.git
cd ConnectAPI
```

2. Create a virtual environment and install dependencies:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. Set up Upstash Redis:
- Go to [Upstash Console](https://console.upstash.com/)
- Create a new Redis database
- Copy the connection details

4. Create a .env file with your configuration:
```env
# Upstash Redis Configuration
REDIS_URL=rediss://default:your-password@willing-husky-43244.upstash.io:6379
```

5. Run the server locally:
```bash
uvicorn main:app --reload
```

## Deployment

This project is configured for deployment on Vercel:

1. Fork this repository
2. Connect your fork to Vercel
3. Add your environment variables in Vercel:
   - `REDIS_URL` (from Upstash)
4. Deploy!

## API Endpoints

### GET /raw-schedule
Fetches the current schedule using the most recent valid token, or falls back to the latest cached schedule if no valid token is available.

- No authentication required
- Returns schedule data in JSON format
- Uses Upstash Redis for token management and caching
- **How it works:**
  - The endpoint always tries to fetch the latest real schedule from the Connect API using the most recent valid token.
  - If the live API call is successful, it updates the cache and returns the fresh data.
  - If the live API call fails (e.g., network error, token expired), it falls back to the most recently cached schedule (if available).
  - **If no valid token is available at all, it will show the most recently cached schedule (from any student) if present.**
  - If neither a valid token nor any cached schedule exists, an error is returned.
- **Everyone sees the same schedule**—it is not user-specific.

### GET/POST /enter-tokens
Allows users to enter and save their access and refresh tokens.

- **Requires a valid session** (users must start from the home page to get a session)
- Tokens are stored securely in Redis, scoped to the session
- Not accessible to the public without a session

### GET /mytokens
View the tokens associated with the current session.

- **Requires a valid session**
- Not accessible to the public without a session

## Dependencies

- Python 3.7+
- FastAPI
- Upstash Redis
- httpx
- python-jose[cryptography]

## Infrastructure

### Upstash Redis
We use Upstash Redis as our primary database for:
- Token storage and management
- Schedule data caching
- Session handling

Benefits of using Upstash:
- Serverless Redis solution
- Global data replication
- Pay-per-use pricing
- Built-in REST API

### Vercel
Our deployment platform offering:
- Serverless Functions
- Automatic deployments
- Edge Network
- Zero configuration

## License

MIT License 