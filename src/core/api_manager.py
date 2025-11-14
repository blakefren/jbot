"""
Generic manager for handling API calls.
"""
import requests


class APIManager:
    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def get(self, endpoint: str, params: dict = None) -> dict:
        """
        Sends a GET request to the specified endpoint.
        """
        try:
            response = requests.get(
                f"{self.base_url}/{endpoint}", headers=self.headers, params=params
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"An error occurred: {e}")
            return None

    def post(self, endpoint: str, data: dict) -> dict:
        """
        Sends a POST request to the specified endpoint.
        """
        try:
            response = requests.post(
                f"{self.base_url}/{endpoint}", headers=self.headers, json=data
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"An error occurred: {e}")
            return None
