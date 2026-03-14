import asyncio
import os
import time

import requests
from dotenv import load_dotenv

load_dotenv()

from kuksa_client.grpc import Datapoint
from kuksa_client.grpc.aio import VSSClient

KUKSA_HOST = os.getenv("KUKSA_HOST", "localhost")
KUKSA_PORT = int(os.getenv("KUKSA_PORT", "55555"))

DITTO_URL = os.getenv("DITTO_URL", "http://localhost:8080")
DITTO_USERNAME = os.getenv("DITTO_USERNAME", "ditto")
DITTO_PASSWORD = os.getenv("DITTO_PASSWORD", "ditto")
DITTO_THING_ID = os.getenv("DITTO_THING_ID", "org.eclipse.kuksa:vehicle1")

KUKSA_TEST_SIGNAL = "Vehicle.OBD.Speed"
DITTO_TEST_FEATURE = "VehicleSpeed"


def get_ditto_feature_value():
    url = f"{DITTO_URL}/api/2/things/{DITTO_THING_ID}"
    response = requests.get(
        url,
        auth=(DITTO_USERNAME, DITTO_PASSWORD),
        timeout=5,
    )
    response.raise_for_status()

    thing = response.json()
    return (
        thing.get("features", {})
        .get(DITTO_TEST_FEATURE, {})
        .get("properties", {})
        .get("value")
    )


async def main():
    current_value = get_ditto_feature_value()
    test_value = 222 if current_value != 222 else 223

    print(f"Sending test value {test_value} to Kuksa signal {KUKSA_TEST_SIGNAL}")

    async with VSSClient(KUKSA_HOST, KUKSA_PORT) as client:
        start = time.perf_counter()

        await client.set_current_values({
            KUKSA_TEST_SIGNAL: Datapoint(test_value)
        })

        timeout_seconds = 10

        while True:
            observed = get_ditto_feature_value()

            if observed == test_value:
                elapsed_ms = (time.perf_counter() - start) * 1000
                print(f"Latency: {elapsed_ms:.2f} ms")
                return

            if (time.perf_counter() - start) > timeout_seconds:
                raise TimeoutError(
                    "Ditto did not reflect the Kuksa update within 10 seconds."
                )

            time.sleep(0.1)


if __name__ == "__main__":
    asyncio.run(main())