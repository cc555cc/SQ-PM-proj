#This script sends simulated OBD data to Kuksa for testing purposes.
import asyncio
import os
import random

from fault_management import FaultInjector, load_fault_config

KUKSA_IMPORT_ERROR = None

try:
    from kuksa_client.grpc import Datapoint
    from kuksa_client.grpc.aio import VSSClient
except Exception as exc:
    Datapoint = None
    VSSClient = None
    KUKSA_IMPORT_ERROR = exc

KUKSA_HOST = os.getenv("KUKSA_HOST", "localhost")
KUKSA_PORT = int(os.getenv("KUKSA_PORT", "55555"))
FAULT_CONFIG = load_fault_config()
PUBLISH_INTERVAL_SECONDS = float(
    os.getenv(
        "PUBLISH_INTERVAL_SECONDS",
        str(FAULT_CONFIG.get("cycle_interval_seconds", "1")),
    )
)

SIGNALS = {
    "VehicleSpeed": "Vehicle.OBD.VehicleSpeed",
    "EngineSpeed": "Vehicle.OBD.EngineSpeed",
    "FuelLevel": "Vehicle.OBD.FuelLevel",
    "BatteryVoltage": "Vehicle.OBD.BatteryVoltage",
    "ThrottlePosition": "Vehicle.OBD.ThrottlePosition",
    "CoolantTemperature": "Vehicle.OBD.CoolantTemperature",
}


def generate_obd_values():
    return {
        SIGNALS["VehicleSpeed"]: random.randint(0, 255),
        SIGNALS["EngineSpeed"]: random.randint(0, 1000),
        SIGNALS["FuelLevel"]: random.randint(0, 100),
        SIGNALS["BatteryVoltage"]: round(random.uniform(11.5, 14.8), 2),
        SIGNALS["ThrottlePosition"]: random.randint(0, 100),
        SIGNALS["CoolantTemperature"]: random.randint(0, 120),
    }


async def main():
    if VSSClient is None or Datapoint is None:
        raise ImportError(
            "Failed to import kuksa-client. "
            f"Original import error: {KUKSA_IMPORT_ERROR!r}"
        )

    print(f"Starting OBD publisher: Kuksa={KUKSA_HOST}:{KUKSA_PORT}")
    print(
        "Fault injection:"
        f" enabled={FAULT_CONFIG.get('enabled', True)},"
        f" missing={FAULT_CONFIG['missing_data_probability']},"
        f" delayed={FAULT_CONFIG['delayed_signal_probability']},"
        f" incorrect={FAULT_CONFIG['incorrect_value_probability']}"
    )

    injector = FaultInjector(FAULT_CONFIG)

    while True:
        try:
            async with VSSClient(KUKSA_HOST, KUKSA_PORT) as client:
                while True:
                    values = generate_obd_values()
                    ready_values, injected_faults = injector.next_updates(values)
                    updates = {
                        signal: Datapoint(value)
                        for signal, value in ready_values.items()
                    }

                    if updates:
                        await client.set_current_values(updates)

                    print(
                        "Published:",
                        {
                            "VehicleSpeed": ready_values.get(SIGNALS["VehicleSpeed"]),
                            "EngineSpeed": ready_values.get(SIGNALS["EngineSpeed"]),
                            "FuelLevel": ready_values.get(SIGNALS["FuelLevel"]),
                            "BatteryVoltage": ready_values.get(SIGNALS["BatteryVoltage"]),
                            "ThrottlePosition": ready_values.get(SIGNALS["ThrottlePosition"]),
                            "CoolantTemperature": ready_values.get(SIGNALS["CoolantTemperature"]),
                        },
                    )
                    if injected_faults:
                        print("Injected faults:", injected_faults)
                    print("-------------------------------------------------------------------------------------------------\n")

                    await asyncio.sleep(PUBLISH_INTERVAL_SECONDS)
        except Exception as exc:
            print(f"Kuksa not ready yet: {exc}")
            await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())
