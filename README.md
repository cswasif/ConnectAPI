# BRACU Schedule Viewer API

## Project Description

This project is a simple FastAPI application that serves as a backend API to fetch and display student class schedules from the BRACU Connect portal. It uses manually acquired access and refresh tokens for authentication with the Connect API and includes a basic mechanism for token auto-refresh and storage.

**Disclaimer:** This project was developed for personal use and learning. The current authentication and security mechanisms (especially password handling via URL) are **not suitable for production environments** or for handling sensitive user data for multiple users. Use at your own risk.

## Features

*   Fetches raw schedule data from the BRACU Connect API.
*   Supports manual entry and storage of access and refresh tokens.
*   Includes logic to auto-refresh expired access tokens using a stored refresh token.
*   Provides web pages to manually enter/view stored tokens and view raw schedule data.
*   Basic password protection for token management pages.

## Setup

### Prerequisites

*   Python 3.7+
*   `pip` (Python package installer)
*   `git` (for cloning the repository)

### Installation

1.  Clone the repository:

    ```bash
    git clone https://github.com/cswasif/connect-api-schedule.git
    cd connect-api-schedule
    ```

2.  Install the required Python dependencies:

    ```bash
    pip install -r requirements.txt
    ```

## Running the Application

### Development Mode (with auto-reloading)

This mode is convenient for development as it automatically restarts the server when code changes are detected.

1.  Set the `SECRET_PASSWORD` environment variable (used for accessing token management pages):

    *   **Windows (PowerShell):**
        ```powershell
        $env:SECRET_PASSWORD="your_secure_password_here"
        ```
    *   **Linux/macOS (Bash/Zsh):**
        ```bash
        export SECRET_PASSWORD="your_secure_password_here"
        ```
    Replace `"your_secure_password_here"` with your desired password.

2.  Run the server:

    ```bash
    uvicorn main:app --reload --port 8000
    ```

    The API will be available at `http://127.0.0.1:8000`.

### Production Mode (using Gunicorn)

For better performance under load, use a production-ready ASGI server like Gunicorn.

1.  Set the `SECRET_PASSWORD` environment variable (same as development mode step 1).
2.  Run the server using Gunicorn (example with 4 worker processes):

    ```bash
    gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app -b 0.0.0.0:8000
    ```
    Adjust `-w 4` based on your server's CPU cores (a common rule is `2 * cores + 1`).

## API Documentation

Base URL: `http://127.0.0.1:8000` (or your deployed URL)

### `GET /`

*   **Description:** Serves the root HTML page with API status, uptime, and navigation links to the token management and schedule viewing pages.
*   **Authentication:** None required.

### `GET /enter-tokens`

*   **Description:** Serves an HTML form to manually enter your BRACU Connect access and refresh tokens.
*   **Authentication:** Requires the `SECRET_PASSWORD` passed as a query parameter (`?password=your_password`). The root page's JavaScript handles adding this when using the button.

### `POST /enter-tokens`

*   **Description:** Receives the access and refresh tokens submitted via the `/enter-tokens` form and saves them to the PostgreSQL database.
*   **Parameters:**
    *   `access_token` (form data, required): Your BRACU Connect access token.
    *   `refresh_token` (form data, required): Your BRACU Connect refresh token.
*   **Authentication:** Requires the `SECRET_PASSWORD` passed as a query parameter (`?password=your_password`).

### `GET /mytokens`

*   **Description:** Displays the currently stored access and refresh tokens from the PostgreSQL database in a raw JSON format.
*   **Authentication:** Requires the `SECRET_PASSWORD` passed as a query parameter (`?password=your_password`). The root page's JavaScript prompts for this and adds it when using the button.
*   **Response:** Raw JSON content of the stored tokens, or an error message if no tokens are stored or authentication fails.

### `GET /raw-schedule`

*   **Description:** Fetches and displays your raw class schedule data directly from the BRACU Connect API using a Bearer token.
*   **Parameters:**
    *   `access_token` (query parameter, optional): You can optionally provide an access token directly here (`?access_token=your_token`). If not provided, the API will attempt to load tokens from the database.
*   **Authentication:** Requires a valid Bearer access token. If the token loaded from the database is expired, it will attempt to use the refresh token to get a new one and save it.
*   **Response:** Raw JSON content of the schedule data, or an error message if fetching fails (e.g., invalid/expired token without a valid refresh token).

## Token Management

1.  Obtain your BRACU Connect access and refresh tokens manually from your browser's developer tools after logging into the Connect portal.
2.  Visit the root page (`/`) and click the "Enter Tokens" button. Enter your `SECRET_PASSWORD` when prompted by the browser. This will redirect you with the password in the URL query parameter.
3.  On the "Enter Tokens" page, paste your access and refresh tokens into the respective fields and click "Save Tokens".
4.  The API will now use these stored tokens from the PostgreSQL database to fetch your schedule via `/raw-schedule`. The API will attempt to auto-refresh the access token using the refresh token when it's close to expiring and update the tokens in the database.

## Security Notes and Limitations

*   **Insecure Password in URL:** Passing the `SECRET_PASSWORD` as a query parameter (`?password=...`) is **highly insecure**. It can be easily exposed in server logs, browser history, and referrer headers. This method is used here for simplicity in a controlled, non-production environment only.
*   **Database Storage:** Tokens are now stored in a PostgreSQL database. While better than a flat file, ensure your database itself is secured.
*   **Single User Focused:** The application is hardcoded for student ID 42749 and designed for a single user managing their own tokens. It is not built to securely handle multiple users.
*   **No API User Authentication:** There is no authentication mechanism for users *of this API* other than the basic password for token management pages. The `/raw-schedule` endpoint is accessible if a valid token is available.
*   **Limited Scalability:** The current architecture is not designed for high concurrency from thousands of users.

## Future Improvements

*   Implement a secure user authentication system for the API.
*   Replace `tokens.json` with a secure database for storing tokens and user data.
*   Handle multiple users securely, possibly linking API users to their student IDs and tokens.
*   Implement more robust error handling and logging.
*   Add proper API documentation generated by FastAPI (e.g., using Swagger UI/OpenAPI).
*   Containerize the application (e.g., using Docker) for easier deployment. 