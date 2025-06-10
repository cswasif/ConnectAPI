# ConnectAPI

A FastAPI-based API service for accessing BRACU (BRAC University) student schedules. This API provides a simplified interface to fetch schedule data from the BRACU Connect portal.

## Features

- Public schedule endpoint
- Token management and auto-refresh
- Redis-based caching
- Error handling and fallback mechanisms

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

3. Set up Redis:
- Install Redis server
- Make sure it's running on default port (6379)

4. Create a .env file with your configuration:
```env
OAUTH_CLIENT_ID=your_client_id
OAUTH_CLIENT_SECRET=your_client_secret
REDIS_URL=redis://localhost:6379
```

5. Run the server:
```bash
uvicorn main:app --reload
```

## API Endpoints

### GET /raw-schedule
Fetches the current schedule using the most recent valid token.

- No authentication required
- Returns schedule data in JSON format
- Falls back to cached data if available

## Dependencies

- Python 3.7+
- FastAPI
- Redis
- httpx
- python-jose[cryptography]

## License

MIT License 