#Task:
#1. connect to Kuksa
#2. subscribe to vehicle signals
#3. convert data into JSON structure that ditto is expecting
#4. send the update to ditto
#5. repeat steps 2-4 for each update received from Kuksa

#procedure (for our sequence diagram):
#1. read the signal map from config/signal_map.json to get the mapping of Kuksa signal paths to Ditto feature names
#2. connect to Kuksa using the VSSClient
#3. validate that the signal paths in the signal map exist in Kuksa before subscribing
#4. subscribe to the current values of the signals in Kuksa using the subscribe_current_values  
#5. for each update received from Kuksa, extract the signal values and build the feature updates for Ditto
#6. send the feature updates to Ditto using HTTP PUT requests to the appropriate feature endpoints
#7. handle any errors that occur during the process and print appropriate error messages

#integration 2: zenoh
#this script now subscribe to vehicle data from zenoh instead of kuksa

#tasks for integration 2:
#1. connect to Zenoh
#2. subscribe to the key prefix where the vehicle signals are published in Zenoh
#3. decode incoming payload
#4. convert payload to Ditto feature update format
#5. updates Ditto via HTTP PUT requests

import os
import time
import json

import requests
from requests import HTTPError

from connect_kuksa_zenoh import connect_to_zenoh

ZENOH_SUBSCRIBE = os.getenv("ZENOH_SUBSCRIBE", "vehicle")

DITTO_URL = os.getenv("DITTO_URL", "http://localhost:8080")
DITTO_USERNAME = os.getenv("DITTO_USERNAME", "ditto")
DITTO_THING_ID = os.getenv("DITTO_THING_ID", "org.eclipse.kuksa:vehicle1")
DITTO_PASSWORD = os.getenv("DITTO_PASSWORD", "ditto")
REQUEST_TIMEOUT_SECONDS = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "5"))
VERBOSE_LOGGING = os.getenv("VERBOSE_LOGGING", "false").lower() == "true"


def create_zenoh_session():
    session = connect_to_zenoh()
    print("Connected to Zenoh successfully.")

    subscriber = session.declare_subscriber(f"{ZENOH_SUBSCRIBE}/**")
    print(f"Subscribed to Zenoh key: {ZENOH_SUBSCRIBE}/**")

    return session, subscriber


def build_feature_updates(payload):
    if hasattr(payload.payload, "to_bytes"):
        raw_payload = payload.payload.to_bytes().decode("utf-8")
    else:
        raw_payload = bytes(payload.payload).decode("utf-8")

    actual_payload = json.loads(raw_payload)

    thing_id = actual_payload.get("thingId", DITTO_THING_ID)
    vehicle_id = actual_payload.get("vehicleId", "vehicle1")
    feature_name = actual_payload.get("feature")
    value = actual_payload.get("value")
    raw_value = actual_payload.get("rawValue")
    quality = actual_payload.get("quality", "good")
    faults = actual_payload.get("faults", [])
    recovery_action = actual_payload.get("recoveryAction", "pass_through")
    pipeline_safe = actual_payload.get("pipelineSafe", True)
    source_timestamp = actual_payload.get("timestamp")
    cycle = actual_payload.get("cycle")

    if not feature_name:
        raise ValueError(f"Zenoh payload is missing feature name: {actual_payload}")

    return {
        "thing_id": thing_id,
        "vehicle_id": vehicle_id,
        "quality": quality,
        "faults": faults,
        "recovery_action": recovery_action,
        "feature_updates": {
            feature_name: {
                "properties": {
                    "vehicleId": vehicle_id,
                    "value": value,
                    "rawValue": raw_value,
                    "quality": quality,
                    "faults": faults,
                    "recoveryAction": recovery_action,
                    "pipelineSafe": pipeline_safe,
                    "sourceTimestamp": source_timestamp,
                    "receivedTimestamp": time.time(),
                    "cycle": cycle,
                    "isHealthy": quality == "good",
                }
            }
        }
    }


def update_ditto(feature_updates):
    headers = {"Content-Type": "application/json"}
    thing_id = feature_updates["thing_id"]
    vehicle_id = feature_updates["vehicle_id"]
    quality = feature_updates["quality"]
    faults = feature_updates["faults"]
    recovery_action = feature_updates["recovery_action"]

    for feature_name, payload in feature_updates["feature_updates"].items():
        url = f"{DITTO_URL}/api/2/things/{thing_id}/features/{feature_name}"

        response = requests.put(
            url,
            auth=(DITTO_USERNAME, DITTO_PASSWORD),
            headers=headers,
            json=payload,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )

        try:
            response.raise_for_status()
        except HTTPError as exc:
            raise RuntimeError(
                f"Ditto update failed for feature '{feature_name}' "
                f"at '{url}': {response.status_code} {response.text}"
            ) from exc

        if quality != "good" or VERBOSE_LOGGING:
            print(
                f"[Ditto:{vehicle_id}] {feature_name}: "
                f"status={response.status_code} "
                f"quality={quality} "
                f"faults={faults or ['none']} "
                f"recovery={recovery_action}"
            )




def main():
    while True:
        try:
            session, subscriber = create_zenoh_session()

            try:
                for payload in subscriber:
                    feature_updates = build_feature_updates(payload)
                    update_ditto(feature_updates)
            finally:
                subscriber.undeclare()
                session.close()
        except Exception as e:
            print("Error in Zenoh-Ditto bridge:", e)
            time.sleep(1)


if __name__ == "__main__":
    main()




    

