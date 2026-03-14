import os
import time
import unittest

import requests
from dotenv import load_dotenv

load_dotenv()

DITTO_URL = os.getenv("DITTO_URL", "http://localhost:8080")
DITTO_USERNAME = os.getenv("DITTO_USERNAME", "ditto")
DITTO_PASSWORD = os.getenv("DITTO_PASSWORD", "ditto")
DITTO_THING_ID = os.getenv("DITTO_THING_ID", "org.eclipse.kuksa:vehicle1")
SOVD_URL = os.getenv("SOVD_URL", "http://localhost:9000")

REQUIRED_FEATURES = [
    "VehicleSpeed",
    "EngineSpeed",
    "ThrottlePosition",
    "CoolantTemperature",
]


def get_ditto_thing():
    url = f"{DITTO_URL}/api/2/things/{DITTO_THING_ID}"
    response = requests.get(
        url,
        auth=(DITTO_USERNAME, DITTO_PASSWORD),
        timeout=5,
    )
    response.raise_for_status()
    return response.json()


def get_raw_values():
    response = requests.get(f"{SOVD_URL}/vehicle/raw", timeout=5)
    response.raise_for_status()
    return response.json()


class PipelineTests(unittest.TestCase):
    def test_ditto_is_reachable(self):
        thing = get_ditto_thing()
        self.assertIn("features", thing)

    def test_required_features_exist(self):
        thing = get_ditto_thing()
        features = thing.get("features", {})

        for feature in REQUIRED_FEATURES:
            self.assertIn(feature, features)

    def test_sovd_status_endpoint(self):
        response = requests.get(f"{SOVD_URL}/vehicle/status", timeout=5)
        self.assertEqual(response.status_code, 200)

        body = response.json()
        self.assertIn("overall_status", body)
        self.assertIn("signals", body)

    def test_pipeline_values_are_live(self):
        first = get_raw_values()
        time.sleep(3)
        second = get_raw_values()

        self.assertNotEqual(
            first,
            second,
            "Values did not change. Make sure publisher + bridges are running."
        )


if __name__ == "__main__":
    unittest.main()