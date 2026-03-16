#this script runs integration checks for the current pipeline that uses
#official external component stacks.
#it verifies that:
#- OpenDuT CARL is reachable from the Docker-hosted CARL image.
#- Eclipse Ditto is reachable and contains the expected vehicle features.
#- The real OpenSOVD CDA service is reachable on its health endpoints.
#- The real OpenSOVD CDA service can return diagnostic component data.
#
#steps:
#1. Load environment variables for OpenDuT, Ditto, and OpenSOVD.
#2. Confirm the Docker-hosted OpenDuT CARL service is reachable.
#3. Request the current vehicle Thing from Eclipse Ditto.
#4. Verify the required vehicle features exist in the Ditto twin.
#5. Call the real OpenSOVD CDA health endpoint and validate its response.
#6. Call the real OpenSOVD CDA readiness and component-list endpoints.
import os
import unittest
import requests
from dotenv import load_dotenv

load_dotenv()

#openDut
OPENDUT_CARL_URL = os.getenv("OPENDUT_URL", "http://localhost:8085")

#ditto
DITTO_URL = os.getenv("DITTO_URL", "http://localhost:8080")
DITTO_USERNAME = os.getenv("DITTO_USERNAME", "ditto")
DITTO_PASSWORD = os.getenv("DITTO_PASSWORD", "ditto")
DITTO_THING_ID = os.getenv("DITTO_THING_ID", "org.eclipse.kuksa:vehicle1")
SOVD_URL = os.getenv("SOVD_URL", "http://localhost:20002")

REQUIRED_FEATURES = [
    "VehicleSpeed",
    "EngineSpeed",
    "FuelLevel",
    "BatteryVoltage",
    "ThrottlePosition",
    "CoolantTemperature",
]

#test: does ditto response on expected url
def get_ditto_thing():
    url = f"{DITTO_URL}/api/2/things/{DITTO_THING_ID}"
    response = requests.get(
        url,
        auth=(DITTO_USERNAME, DITTO_PASSWORD),
        timeout=5,
    )
    response.raise_for_status()
    return response.json()

#test: attempt to fetch raw vehicle data via SOVD
def get_raw_values():
    response = requests.get(f"{SOVD_URL}/vehicle/v15/components", timeout=5)
    response.raise_for_status()
    return response.json()

#test: openDut service running
def get_opendut_carl():
    response = requests.get(OPENDUT_CARL_URL, timeout=5, allow_redirects = False)
    return response

#test the pipeline if all componenet are running
class PipelineTests(unittest.TestCase):
    def assert_opendut_available(self):
        response = get_opendut_carl()
        self.assertIn(
            response.status_code,
            [200, 302, 401, 403],
            f"OpenDuT CARL is not reachable at {OPENDUT_CARL_URL}",
        )

    def setUp(self):
        self.assert_opendut_available()

    def test_opendut_connection(self):
        self.assert_opendut_available()

    def test_ditto_is_reachable(self):
        thing = get_ditto_thing()
        self.assertIn("features", thing)

    def test_required_features_exist(self):
        thing = get_ditto_thing()
        features = thing.get("features", {})

        for feature in REQUIRED_FEATURES:
            self.assertIn(feature, features)

    def test_sovd_status_endpoint(self):
        response = requests.get(f"{SOVD_URL}/health", timeout=5)
        self.assertEqual(response.status_code, 200)

        body = response.json()
        self.assertIn("status", body)
        self.assertIn("components", body)

    def test_pipeline_values_are_live(self):
        response = requests.get(f"{SOVD_URL}/health/ready", timeout=5)
        self.assertEqual(response.status_code, 204)

        body = get_raw_values()
        self.assertIn("items", body)
        self.assertGreater(
            len(body["items"]),
            0,
            "No SOVD components were returned by the actual CDA service."
        )


if __name__ == "__main__":
    unittest.main()
