#this script measures end-to-end latency from Kuksa to Ditto by sending a
#test value to a Kuksa signal and timing how long it takes for the matching
#Ditto feature to reflect the same update.

#steps:
#1. Load environment variables for Kuksa and Ditto connections.
#2. Read the current Ditto feature value used for the latency test.
#3. Send a new test value to the matching Kuksa VSS signal.
#4. Poll the Ditto Thing until the same value appears in the mapped feature.
#5. Print the measured latency in milliseconds or fail on timeout.
import asyncio
import os
import time

import requests
from dotenv import load_dotenv

load_dotenv()

from kuksa_client.grpc import Datapoint
from kuksa_client.grpc.aio import VSSClient

#kuksa
KUKSA_HOST = os.getenv("KUKSA_HOST", "localhost")
KUKSA_PORT = int(os.getenv("KUKSA_PORT", "55555"))

#ditto
DITTO_URL = os.getenv("DITTO_URL", "http://localhost:8080")
DITTO_USERNAME = os.getenv("DITTO_USERNAME", "ditto")
DITTO_PASSWORD = os.getenv("DITTO_PASSWORD", "ditto")
DITTO_THING_ID = os.getenv("DITTO_THING_ID", "org.eclipse.kuksa:vehicle1")

KUKSA_TEST_SIGNAL = "Vehicle.OBD.VehicleSpeed"
DITTO_TEST_FEATURE = "VehicleSpeed"

#send a GET request to ditto to fetch feature updates, then convert it to python data and extract 
#target data
def get_ditto_feature_value():
    #ditto api
    url = f"{DITTO_URL}/api/2/things/{DITTO_THING_ID}"
    response = requests.get(
        url,
        auth=(DITTO_USERNAME, DITTO_PASSWORD),
        timeout=5,
    )
    response.raise_for_status() #get response from ditto as parsed JSON data

    thing = response.json() #turns response to python data

    return (
        thing.get("features", {})
        .get(DITTO_TEST_FEATURE, {})
        .get("properties", {})
        .get("value")
    )

#send a test update to Kuksa and measure how long it takes for Ditto to
#reflect the same value in the mapped feature
async def main():
    #pick a value that is different from the current Ditto value so that the update
    #is visible when it propagates through the pipeline.
    current_value = get_ditto_feature_value()
    test_value = 222 if current_value != 222 else 223

    print(f"Sending test value {test_value} to Kuksa signal {KUKSA_TEST_SIGNAL}")

    #open async connection to kuksa
    async with VSSClient(KUKSA_HOST, KUKSA_PORT) as client:
        #start timing immediately before publishing the Kuksa update.
        start = time.perf_counter()

        await client.set_current_values({
            KUKSA_TEST_SIGNAL: Datapoint(test_value)
        })

        timeout_seconds = 10

        while True:
            #poll Ditto until the same value appears in the mapped feature.
            observed = get_ditto_feature_value()

            if observed == test_value:
                elapsed_ms = (time.perf_counter() - start) * 1000
                print(f"Latency: {elapsed_ms:.2f} ms")
                return

            if (time.perf_counter() - start) > timeout_seconds:
                #stop waiting if the end-to-end update takes too long.
                raise TimeoutError(
                    "Ditto did not reflect the Kuksa update within 10 seconds."
                )

            time.sleep(0.1)


if __name__ == "__main__":
    asyncio.run(main())
