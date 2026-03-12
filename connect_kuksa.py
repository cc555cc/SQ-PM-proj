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


import os
import time
import json
from pathlib import Path

import requests
from requests import HTTPError

KUKSA_IMPORT_ERROR = None

try:
    from kuksa_client.grpc import VSSClient
except Exception as exc:
    VSSClient = None
    KUKSA_IMPORT_ERROR = exc

# get configuration from environment variables
BASE_DIR = Path(__file__).resolve().parent
SIGNAL_MAP_PATH = Path(
    os.getenv("SIGNAL_MAP_PATH", BASE_DIR / "config" / "signal_map.json") 
) #default to config/signal_map.json in the same directory as this script

#kuksa env
KUKSA_HOST = os.getenv("KUKSA_HOST", "localhost")
KUKSA_PORT = int(os.getenv("KUKSA_PORT", "55555"))

#ditto env
DITTO_URL = os.getenv("DITTO_URL", "http://localhost:8080")
DITTO_USERNAME = os.getenv("DITTO_USERNAME", "ditto")
DITTO_THING_ID = os.getenv("DITTO_THING_ID", "org.eclipse.kuksa:vehicle1")
DITTO_PASSWORD = os.getenv("DITTO_PASSWORD", "ditto")
REQUEST_TIMEOUT_SECONDS = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "5"))

def load_signal_map():
    try:
        with SIGNAL_MAP_PATH.open("r", encoding="utf-8") as signal_map_file: #read the signal map file in the config directory
            signal_map = json.load(signal_map_file) #load the JSON file into a dictionary
    except FileNotFoundError as exc: #in case the file doesn't exist or path is wrong
        raise FileNotFoundError(
            f"Signal map file not found: {SIGNAL_MAP_PATH}"
        ) from exc

    #validate that the signal map is a dictionary of Kuksa path to Ditto feature name
    if not isinstance(signal_map, dict):
        raise ValueError(
            f"Signal map must be a JSON object of Kuksa path to Ditto feature name: {SIGNAL_MAP_PATH}"
        )

    return signal_map

#read signal from map and extract the value and store in a dictionary to be sent to ditto
def extract_signal_values(updates):
    values = {}

    #loop through the updates from kuksa
    for signal, datapoint in updates.items():
        values[signal] = getattr(datapoint, "value", datapoint) #extract the value from datapoint with "value" attribute

    return values

#confirm signal path exist in kuksa before subscrition
def validate_signal_paths(client, signal_map):
    missing_signals = []

    #check each signal path in kuksa
    for signal in signal_map.keys():
        try:
            client.get_metadata([signal]) #get metatdata for the signal path
        except Exception:
            missing_signals.append(signal)

    #signal paths missing
    if missing_signals:
        raise ValueError(
            "These signals were not found in Kuksa: "
            + ", ".join(missing_signals)
        )

#connect to kuksa
def connect_to_kuksa():
    #create new client instance
    new_client = VSSClient(KUKSA_HOST, KUKSA_PORT)

    return VSSClient(KUKSA_HOST, KUKSA_PORT)

#for each update of signal values, build a dictionary of feature updates
def build_feature_updates(values, signal_map):
    feature_updates = {}

    #loop through signal values and map to feature names using the signal map
    for signal, value in values.items():
        #build the payload for the feature update
        feature_name = signal_map[signal]
        feature_updates[feature_name] = {"properties": {"value": value}}

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
    #variables
    signal_map = load_signal_map()
    subscribed_signals = list(signal_map.keys())

    #confirm there are subscribed signal before listening to updates
    if not subscribed_signals:
        raise ValueError(
            f"No signals configured in {SIGNAL_MAP_PATH}. Add signal mappings first."
        )

    #print startup configuration for confirmation
    print(
        f"Starting bridge: Kuksa={KUKSA_HOST}:{KUKSA_PORT}, "
        f"Ditto={DITTO_URL}, Thing={DITTO_THING_ID}"
    )

    #main loop
    while True:
        try:
            with connect_to_kuksa() as client:
                validate_signal_paths(client, signal_map)
                for updates in client.subscribe_current_values(subscribed_signals):
                    signal_values = extract_signal_values(updates)
                    feature_updates = build_feature_updates(signal_values, signal_map)
                    update_ditto(feature_updates)
        except (ImportError, ValueError) as e:
            raise RuntimeError(f"Startup error: {e}") from e
        except Exception as e:
            print("Error at kuksa connection: ", e)
            time.sleep(1)

if __name__ == "__main__":
    main()




    

