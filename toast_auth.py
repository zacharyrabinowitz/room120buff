import requests

def get_toast_access_token():
    url = "https://partner.toasttab.com/api/v1/oauth/token"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {
        "grant_type": "client_credentials",
        "client_id": "Jd4jZk55DCFsZsUACvQyR7x72EjynLsI",
        "client_secret": "gAdNjaQghgCd_5cv1-mwcpjr9qmMDGk5zNoYUpYHnD73Ewd-Z67fJ1nzKD_ekDzw",
        "scope": "restaurants.read orders.read checks.read"
    }

    response = requests.post(url, headers=headers, data=data)

    if response.status_code == 200:
        token_data = response.json()
        return token_data["access_token"]
    else:
        print("Error getting token:", response.text)
        return None
