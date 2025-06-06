import requests
from bs4 import BeautifulSoup
import json
from urllib.parse import urlparse, parse_qs

def analyze_connect_auth():
    # Start a session to maintain cookies
    session = requests.Session()
    
    try:
        # First try the main Connect portal
        connect_url = 'https://connect.bracu.ac.bd/'
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        
        print("\n=== Initial Connect Response ===")
        response = session.get(connect_url, headers=headers, allow_redirects=True)
        print(f"Status Code: {response.status_code}")
        print(f"Final URL: {response.url}")
        
        # Try the auth init endpoint
        init_url = 'https://connect.bracu.ac.bd/api/auth/init'
        headers['Accept'] = 'application/json'
        
        print("\n=== Auth Init Response ===")
        response = session.get(init_url, headers=headers)
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            try:
                data = response.json()
                print(json.dumps(data, indent=2))
            except:
                print("Response:", response.text[:500])
                
        # Try the auth status endpoint
        status_url = 'https://connect.bracu.ac.bd/api/auth/status'
        print("\n=== Auth Status Response ===")
        response = session.get(status_url, headers=headers)
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            try:
                data = response.json()
                print(json.dumps(data, indent=2))
            except:
                print("Response:", response.text[:500])
                
        # Try the auth providers endpoint
        providers_url = 'https://connect.bracu.ac.bd/api/auth/providers'
        print("\n=== Auth Providers Response ===")
        response = session.get(providers_url, headers=headers)
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            try:
                data = response.json()
                print(json.dumps(data, indent=2))
            except:
                print("Response:", response.text[:500])
                
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    analyze_connect_auth() 