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

from fault_management import (
    build_quality_report,
    load_fault_config,
    repair_signal_value,
)
from vehicle_registry import apply_vehicle_profile, load_vehicle_registry

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
VERBOSE_LOGGING = os.getenv("VERBOSE_LOGGING", "false").lower() == "true"

#zenoh env
ZENOH_PEER = os.getenv("ZENOH_PEER", "tcp/localhost:7447")
ZENOH_PUBLISH = os.getenv("ZENOH_PUBLISH", "vehicle")
ZENOH_SUBSCRIBE = os.getenv("ZENOH_SUBSCRIBE", "vehicle/vehicle1/vss")

# get configuration from environment variables
BASE_DIR = Path(__file__).resolve().parent
SIGNAL_MAP_PATH = Path(
    os.getenv("SIGNAL_MAP_PATH", BASE_DIR / "config" / "signal_map.json") 
) #default to config/signal_map.json in the same directory as this script
FAULT_CONFIG = load_fault_config()
VEHICLE_REGISTRY = load_vehicle_registry()

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


def log_bridge_event(vehicle_id, feature_name, quality_report, recovery_result):
    if quality_report["quality"] == "good" and not VERBOSE_LOGGING:
        return

    print(
        f"[{vehicle_id}] {feature_name}: "
        f"quality={quality_report['quality']} "
        f"faults={quality_report['faults'] or ['none']} "
        f"recovery={recovery_result['recovery_action']} "
        f"value={recovery_result['effective_value']}"
    )

#build payload and ship to zenoh
def build_and_ship_feature(
    zenoh_session,
    vehicle_config,
    signal,
    raw_value,
    signal_map,
    quality_report,
    cycle_index,
    recovery_result,
):
    # Include both the original VSS path and mapped feature so the downstream Ditto bridge
    # can update the right feature without re-deriving everything from the key alone.
    payload = {
        "vehicleId": vehicle_config["vehicle_id"],
        "thingId": vehicle_config["thing_id"],
        "path": signal,
        "feature": signal_map[signal],
        "value": recovery_result["effective_value"],
        "rawValue": raw_value,
        "quality": quality_report["quality"],
        "faults": quality_report["faults"],
        "recoveryAction": recovery_result["recovery_action"],
        "pipelineSafe": recovery_result["pipeline_safe"],
        "cycle": cycle_index,
        "timestamp": time.time(),
    }

    # Keep the key path aligned with the VSS hierarchy for easier filtering/subscription.
    zenoh_prefix = vehicle_config.get("zenoh_prefix", ZENOH_PUBLISH)
    key = f"{zenoh_prefix}/{signal.replace('.','/')}"
    zenoh_session.put(key, json.dumps(payload))
    if VERBOSE_LOGGING:
        print(f"Published to Zenoh: {key} with payload: {payload}")


def publish_quality_updates(
    zenoh_session,
    signal_map,
    vehicle_registry,
    current_values,
    last_seen_cycles,
    last_good_values,
    cycle_index,
):
    for signal in signal_map.keys():
        raw_value = current_values.get(signal)
        quality_report = build_quality_report(
            signal=signal,
            value=raw_value,
            last_seen_cycle=last_seen_cycles.get(signal),
            current_cycle=cycle_index,
            fault_config=FAULT_CONFIG,
        )

        if quality_report["quality"] == "good":
            last_good_values.setdefault("base", {})[signal] = raw_value

        for vehicle_id, vehicle_config in vehicle_registry.items():
            last_good_by_vehicle = last_good_values.setdefault(vehicle_id, {})
            profiled_raw_value = apply_vehicle_profile(signal, raw_value, vehicle_config)
            profiled_last_good = last_good_by_vehicle.get(signal)
            if profiled_last_good is None:
                profiled_last_good = apply_vehicle_profile(
                    signal,
                    last_good_values.get("base", {}).get(signal),
                    vehicle_config,
                )

            recovery_result = repair_signal_value(
                signal=signal,
                raw_value=profiled_raw_value,
                quality_report=quality_report,
                last_good_value=profiled_last_good,
                fault_config=FAULT_CONFIG,
            )

            if recovery_result["effective_value"] is None:
                print(
                    f"Skipping unsafe update for {vehicle_id}/{signal}: "
                    "no safe fallback is available."
                )
                continue

            if quality_report["quality"] == "good":
                last_good_by_vehicle[signal] = profiled_raw_value

            if quality_report["quality"] != "good" or signal in current_values:
                log_bridge_event(
                    vehicle_id=vehicle_id,
                    feature_name=signal_map[signal],
                    quality_report=quality_report,
                    recovery_result=recovery_result,
                )
                build_and_ship_feature(
                    zenoh_session=zenoh_session,
                    vehicle_config=vehicle_config,
                    signal=signal,
                    raw_value=profiled_raw_value,
                    signal_map=signal_map,
                    quality_report=quality_report,
                    cycle_index=cycle_index,
                    recovery_result=recovery_result,
                )

#main loop:
#1. load map
#2. connect to kuksa, zenoh
#3. validate signals
#4. subscribe to kuksa
#5. extract values and ship to zenoh
def main():
    signal_map = read_signal_map() #load the signal map from the JSON file
    subscribed_signals = list(signal_map.keys())
    last_seen_cycles = {}
    current_values = {}
    last_good_values = {}
    cycle_index = 0

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
                        cycle_index += 1
                        values = extract_signal_values(updates)
                        current_values.update(values)
                        for signal in values.keys():
                            last_seen_cycles[signal] = cycle_index
                        publish_quality_updates(
                            zenoh_session=zenoh_session,
                            signal_map=signal_map,
                            vehicle_registry=VEHICLE_REGISTRY,
                            current_values=current_values,
                            last_seen_cycles=last_seen_cycles,
                            last_good_values=last_good_values,
                            cycle_index=cycle_index,
                        )
                        if not VERBOSE_LOGGING:
                            good_count = sum(
                                1
                                for signal in signal_map.keys()
                                for _vehicle_id in VEHICLE_REGISTRY.keys()
                                if build_quality_report(
                                    signal=signal,
                                    value=current_values.get(signal),
                                    last_seen_cycle=last_seen_cycles.get(signal),
                                    current_cycle=cycle_index,
                                    fault_config=FAULT_CONFIG,
                                )["quality"] == "good"
                            )
                            print(
                                f"[cycle {cycle_index}] bridge processed "
                                f"{len(values)} source updates across {len(VEHICLE_REGISTRY)} vehicles; "
                                f"healthy_routes={good_count}"
                            )
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

