#the role of this script is to send data to zenoh from kuksa
#
#tasks:
#1. read the signal map from the JSON file specified by the SIGNAL_MAP_PATH environment variable
#2. connect to the Kuksa server using the VSSClient from the kuksa-client
#3. validate that the signal paths in the signal map exist in Kuksa before subscribing to them
#4. subscribe to the signal paths in Kuksa and receive updates when their values change
#5. for each update of signal values, build a dictionary of feature updates using the signal names from the signal map and the new values from Kuksa
#6. send the feature updates to zenoh using the zenoh-python library
#7. handle any errors that occur during the process and print appropriate error messages


import os
import time
import json
from pathlib import Path

KUKSA_IMPORT_ERROR = None
ZENOH_IMPORT_ERROR = None

try:
    from kuksa_client.grpc import VSSClient
except Exception as exc:
    VSSClient = None
    KUKSA_IMPORT_ERROR = exc

try:
    import zenoh
except Exception as exc:
    zenoh = None
    ZENOH_IMPORT_ERROR = exc

#kuksa env
KUKSA_HOST = os.getenv("KUKSA_HOST", "localhost")
KUKSA_PORT = int(os.getenv("KUKSA_PORT", "55555"))

#zenoh env
ZENOH_PEER = os.getenv("ZENOH_PEER", "tcp/localhost:7447")
ZENOH_PUBLISH = os.getenv("ZENOH_PUBLISH", "vehicle/vehicle1/vss")
ZENOH_SUBSCRIBE = os.getenv("ZENOH_SUBSCRIBE", "vehicle/vehicle1/vss")

# get configuration from environment variables
BASE_DIR = Path(__file__).resolve().parent
SIGNAL_MAP_PATH = Path(
    os.getenv("SIGNAL_MAP_PATH", BASE_DIR / "config" / "signal_map.json") 
) #default to config/signal_map.json in the same directory as this script

#read signal map from JSON file
def read_signal_map():
    try:
        with SIGNAL_MAP_PATH.open("r", encoding="utf-8") as signal_map_file: #read the signal map file in the config directory
            signal_map = json.load(signal_map_file) #load the JSON file into a dictionary
    except FileNotFoundError as exc: #in case the file doesn't exist or path is wrong
        raise FileNotFoundError(
            f"Signal map file not found: {SIGNAL_MAP_PATH}"
        ) from exc

    #validate that the signal map is a dictionary of Kuksa path to Zenoh feature name
    if not isinstance(signal_map, dict):
        raise ValueError(
            f"Signal map must be a JSON object of Kuksa path to Zenoh feature name: {SIGNAL_MAP_PATH}"
        )

    return signal_map

#read signal from map and extract the value and store in a dictionary to be sent to zenoh
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
    if VSSClient is None:
        raise ImportError(f"Failed to import kuksa-client: {KUKSA_IMPORT_ERROR}")
    return VSSClient(KUKSA_HOST, KUKSA_PORT)

#connect to zenoh
def connect_to_zenoh():
    if zenoh is None:
        raise ImportError(f"Failed to import eclipse-zenoh: {ZENOH_IMPORT_ERROR}")

    #The installed zenoh Python API expects an explicit config object when opening a session.
    config = zenoh.Config()

    #Pin the bridge to the configured router endpoint instead of relying only on discovery.
    if ZENOH_PEER:
        config.insert_json5("connect/endpoints", json.dumps([ZENOH_PEER]))

    return zenoh.open(config)

#build payload and ship to zenoh
def build_and_ship_feature(zenoh_session, values, signal_map):
    #loop through 'values'
    for signal, value in values.items():
        # Include both the original VSS path and mapped feature so the downstream Ditto bridge
        # can update the right feature without re-deriving everything from the key alone.
        payload = {
            "path": signal,
            "feature": signal_map[signal],
            "value": value
        }
    
        # Keep the key path aligned with the VSS hierarchy for easier filtering/subscription.
        key = f"{ZENOH_PUBLISH}/{signal.replace('.','/')}"
        zenoh_session.put(key, json.dumps(payload))
        print(f"Published to Zenoh: {key} with payload: {payload}")

#main loop:
#1. load map
#2. connect to kuksa, zenoh
#3. validate signals
#4. subscribe to kuksa
#5. extract values and ship to zenoh
def main():
    signal_map = read_signal_map() #load the signal map from the JSON file
    subscribed_signals = list(signal_map.keys())

    #confirm there are subscribed signal before listening to updates
    if not subscribed_signals:
        raise ValueError(
            f"No signals configured in {SIGNAL_MAP_PATH}. Add signal mappings first."
        )

    print(
        f"Starting bridge: Kuksa={KUKSA_HOST}:{KUKSA_PORT}, "
        f"Zenoh={ZENOH_PEER}, PublishPrefix={ZENOH_PUBLISH}"
    )

    while True:
        try:
            with connect_to_kuksa() as client:
                zenoh_session = connect_to_zenoh()
                try:
                    validate_signal_paths(client, signal_map)

                    #use the same kuksa API in ditto bridge.
                    for updates in client.subscribe_current_values(subscribed_signals):
                        values = extract_signal_values(updates)
                        build_and_ship_feature(zenoh_session, values, signal_map)
                finally:
                    #close the zenoh session cleanly so reconnects do not leak handles.
                    zenoh_session.close()
        except (ImportError, ValueError) as e:
            raise RuntimeError(f"Startup error: {e}") from e
        except Exception as e:
            print("Error at Kuksa/Zenoh bridge:", e)
            time.sleep(1)

if __name__ == "__main__":
    main()

