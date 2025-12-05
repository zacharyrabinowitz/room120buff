import cloudscraper
from datetime import datetime

def toast_api_get(endpoint, api_key, client_id, client_secret, secret_key):
    """
    Fetch data from the Toast API.

    Args:
        endpoint (str): The API endpoint to fetch data from.
        api_key (str): The API key for authentication.
        client_id (str): The client ID for authentication.
        client_secret (str): The client secret for authentication.
        secret_key (str): The secret key for additional security.

    Returns:
        dict: The JSON response from the API.
    """
    base_url = "https://www.toasttab.com"  # Updated base URL
    url = f"{base_url}/{endpoint}"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Client-ID": client_id,
        "Client-Secret": client_secret,
        "Secret-Key": secret_key,
        "Content-Type": "application/json"
    }

    # Use cloudscraper to handle Cloudflare challenges
    scraper = cloudscraper.create_scraper()

    response = scraper.get(url, headers=headers)

    if response.status_code != 200:
        raise Exception(f"Toast API request failed with status code {response.status_code}: {response.text}")

    return response.json()
