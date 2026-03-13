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

#zenoh env
ZENOH_PEER = os.getenv("ZENOH_PEER", "tcp/localhost:7447")
ZENOH_SUBSCRIBE = os.getenv("ZENOH_SUBSCRIBE", "vehicle/vehicle1/vss")

#ditto env
DITTO_URL = os.getenv("DITTO_URL", "http://localhost:8080")
DITTO_USERNAME = os.getenv("DITTO_USERNAME", "ditto")
DITTO_THING_ID = os.getenv("DITTO_THING_ID", "org.eclipse.kuksa:vehicle1")
DITTO_PASSWORD = os.getenv("DITTO_PASSWORD", "ditto")
REQUEST_TIMEOUT_SECONDS = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "5"))

#create a zenoh session
def create_zenoh_session():
    session = connect_to_zenoh()
    print("Connected to Zenoh successfully.")
    
    # Subscribe to the full subtree so every published vehicle signal is received.
    subscriber = session.declare_subscriber(f"{ZENOH_SUBSCRIBE}/**")
    print(f"Subscribed to Zenoh key: {ZENOH_SUBSCRIBE}/**")

    return session, subscriber

#decode zenoh payload and build feature updates for ditto
def build_feature_updates(payload):
    #decode first
    # The zenoh payload object may expose bytes slightly differently across versions.
    if hasattr(payload.payload, "to_bytes"):
        raw_payload = payload.payload.to_bytes().decode("utf-8")
    else:
        raw_payload = bytes(payload.payload).decode("utf-8")
    actual_payload = json.loads(raw_payload)

    # Match the field names produced by connect_kuksa_zenoh.py.
    feature_name = actual_payload.get("feature")
    value = actual_payload.get("value")

    #build feature
    feature_updates = {
        feature_name: {
            "properties": {
                "value": value
            }
        }
    }

    return feature_updates    

#send payload to ditto
def update_ditto(feature_updates):
    #define HTTP request headers
    headers = {"Content-Type": "application/json"}

    #loop through each feature update and send a request
    for feature_name, payload in feature_updates.items():
        #define url
        url = (
            f"{DITTO_URL}/api/2/things/{DITTO_THING_ID}"
            f"/features/{feature_name}"
        )

        #push HTTP PUT request
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
        
        #terminal confirmation of successful update, successful response --> 204
        print(f"Ditto [{feature_name}]: {response.status_code}")

def main():
    while True:
        try:
            session, subscriber = create_zenoh_session()

            try:
                # Iterate over the declared subscriber, not the raw session.
                for payload in subscriber:
                    features_updates = build_feature_updates(payload)
                    update_ditto(features_updates)
            finally:
                # Clean shutdown keeps reconnect loops from leaking subscriber/session handles.
                subscriber.undeclare()
                session.close()
        except Exception as e:
            print("Error in Zenoh-Ditto bridge:", e)
            time.sleep(1)

    return None

if __name__ == "__main__":
    main()




    

