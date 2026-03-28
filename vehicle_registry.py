import json
from pathlib import Path


DEFAULT_VEHICLES = {
    "vehicle1": {
        "thing_id": "org.eclipse.kuksa:vehicle1",
        "zenoh_prefix": "vehicle/vehicle1/vss",
        "signal_offsets": {},
    },
    "vehicle2": {
        "thing_id": "org.eclipse.kuksa:vehicle2",
        "zenoh_prefix": "vehicle/vehicle2/vss",
        "signal_offsets": {
            "Vehicle.OBD.VehicleSpeed": 4,
            "Vehicle.OBD.EngineSpeed": 120,
            "Vehicle.OBD.FuelLevel": -3,
            "Vehicle.OBD.BatteryVoltage": -0.1,
            "Vehicle.OBD.ThrottlePosition": 2,
            "Vehicle.OBD.CoolantTemperature": 1,
        },
    },
    "vehicle3": {
        "thing_id": "org.eclipse.kuksa:vehicle3",
        "zenoh_prefix": "vehicle/vehicle3/vss",
        "signal_offsets": {
            "Vehicle.OBD.VehicleSpeed": -6,
            "Vehicle.OBD.EngineSpeed": -90,
            "Vehicle.OBD.FuelLevel": 5,
            "Vehicle.OBD.BatteryVoltage": 0.15,
            "Vehicle.OBD.ThrottlePosition": -1,
            "Vehicle.OBD.CoolantTemperature": 3,
        },
    },
}


BASE_DIR = Path(__file__).resolve().parent
VEHICLE_CONFIG_PATH = BASE_DIR / "config" / "vehicles.json"


def load_vehicle_registry(path=VEHICLE_CONFIG_PATH):
    if not Path(path).exists():
        return _normalize_registry(DEFAULT_VEHICLES)

    with Path(path).open("r", encoding="utf-8") as config_file:
        loaded = json.load(config_file)

    return _normalize_registry(loaded)


def _normalize_registry(raw_registry):
    if not isinstance(raw_registry, dict):
        raise ValueError("Vehicle registry must be a JSON object keyed by vehicle ID.")

    normalized = {}
    for vehicle_id, config in raw_registry.items():
        if not isinstance(config, dict):
            raise ValueError(f"Vehicle config for '{vehicle_id}' must be a JSON object.")

        normalized[vehicle_id] = {
            "vehicle_id": vehicle_id,
            "thing_id": config.get("thing_id", f"org.eclipse.kuksa:{vehicle_id}"),
            "zenoh_prefix": config.get("zenoh_prefix", f"vehicle/{vehicle_id}/vss"),
            "signal_offsets": config.get("signal_offsets", {}),
        }

    return normalized


def apply_vehicle_profile(signal, value, vehicle_config):
    if value is None:
        return None

    offset = vehicle_config.get("signal_offsets", {}).get(signal, 0)
    adjusted_value = value + offset

    if isinstance(value, int):
        return int(round(adjusted_value))
    if isinstance(value, float):
        return round(float(adjusted_value), 2)
    return adjusted_value
