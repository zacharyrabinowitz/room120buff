import requests
from toast_auth import get_toast_access_token

def fetch_orders():
    access_token = get_toast_access_token()
    if not access_token:
        return

    # Sample: Pull orders from the last 24 hours
    url = "https://toast-api.com/orders/v1/orders"
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    params = {
        "startDate": "2025-07-24T00:00:00.000Z",  # ISO 8601 format
        "endDate": "2025-07-25T23:59:59.999Z",
        "restaurantGuid": "YOUR_RESTAURANT_GUID"  # <- You'll need to provide this
    }

    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        orders = response.json()
        for order in orders:
            print(f"Order ID: {order['guid']} - Total: {order['totalAmount']}")
    else:
        print("Error fetching orders:", response.status_code, response.text)

fetch_orders()
