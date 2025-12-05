import requests
from toast_auth import get_toast_access_token

def get_restaurant_guid():
    access_token = get_toast_access_token()
    if not access_token:
        return

    url = "https://toast-api.com/config/v1/restaurants"
    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        restaurants = response.json()
        for restaurant in restaurants:
            print(f"Restaurant Name: {restaurant['name']}")
            print(f"Restaurant GUID: {restaurant['guid']}")
    else:
        print("Failed to get restaurants:", response.status_code, response.text)

get_restaurant_guid()
