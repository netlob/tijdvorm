import requests

def get_weather_data(url):
    """Fetch weather data JSON from the specified URL."""
    print(f"Fetching weather data from: {url}")
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        print("Weather data fetched successfully.")
        return data
    except requests.exceptions.RequestException as e:
        print(f"Error fetching weather data: {e}")
        return None

