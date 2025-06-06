import httpx
import json
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs, urljoin

async def analyze_sso_flow():
    """Analyze the exact SSO request from Connect portal"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    }
    
    async with httpx.AsyncClient(follow_redirects=False) as client:
        # Step 1: Visit Connect portal
        print("\n=== Step 1: Visit Connect Portal ===")
        response = await client.get("https://connect.bracu.ac.bd", headers=headers)
        print(f"Status: {response.status_code}")
        print(f"URL: {response.url}")
        
        # Step 2: Visit login page and capture redirect
        print("\n=== Step 2: Visit Login Page ===")
        login_response = await client.get(
            "https://connect.bracu.ac.bd/auth/login",
            headers={
                **headers,
                "Referer": "https://connect.bracu.ac.bd/"
            }
        )
        print(f"Status: {login_response.status_code}")
        if login_response.status_code in (301, 302, 303, 307, 308):
            redirect_url = login_response.headers.get("Location")
            print(f"Redirects to: {redirect_url}")
            if redirect_url:
                parsed = urlparse(redirect_url)
                params = parse_qs(parsed.query)
                print("\nSSO Parameters:")
                print(json.dumps(params, indent=2))
                
                # Step 3: Follow SSO redirect
                print("\n=== Step 3: Follow SSO Redirect ===")
                try:
                    sso_response = await client.get(
                        redirect_url,
                        headers={
                            **headers,
                            "Referer": "https://connect.bracu.ac.bd/auth/login"
                        }
                    )
                    print(f"Status: {sso_response.status_code}")
                    print(f"URL: {sso_response.url}")
                    if sso_response.status_code == 200:
                        # Parse the SSO login form
                        soup = BeautifulSoup(sso_response.text, 'html.parser')
                        form = soup.find('form')
                        if form:
                            print("\nSSO Login Form:")
                            print(f"Action: {form.get('action')}")
                            print("\nForm Inputs:")
                            for input_tag in form.find_all('input'):
                                print(f"- {input_tag.get('name')}: {input_tag.get('value', '')}")
                except Exception as e:
                    print(f"Error following redirect: {str(e)}")
        else:
            # If no redirect, try to parse the login page
            soup = BeautifulSoup(login_response.text, 'html.parser')
            print("\nPage Content:")
            print(login_response.text[:500])  # Print first 500 chars
            
            # Look for any SSO-related links or forms
            forms = soup.find_all('form')
            for form in forms:
                print(f"\nForm found:")
                print(f"Action: {form.get('action')}")
                print("Inputs:")
                for input_tag in form.find_all('input'):
                    print(f"- {input_tag.get('name')}: {input_tag.get('value', '')}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(analyze_sso_flow()) 