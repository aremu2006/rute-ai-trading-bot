import requests
import json

url = "http://localhost:8000/market/live"
symbols = ["EURUSD=X", "GBPUSD=X", "AAPL", "TSLA", "GOOGL", "MSFT"]

response = requests.post(url, json={"symbols": symbols})
print(f"Status Code: {response.status_code}")
print(f"\nResponse:")
print(json.dumps(response.json(), indent=2))
