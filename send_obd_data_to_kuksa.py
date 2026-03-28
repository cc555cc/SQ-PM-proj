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
VERBOSE_LOGGING = os.getenv("VERBOSE_LOGGING", "false").lower() == "true"
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

RED_TEXT = "\033[31m"
RESET_TEXT = "\033[0m"


def colorize_red(message):
    return f"{RED_TEXT}{message}{RESET_TEXT}"


def generate_obd_values():
    return {
        SIGNALS["VehicleSpeed"]: random.randint(0, 255),
        SIGNALS["EngineSpeed"]: random.randint(0, 1000),
        SIGNALS["FuelLevel"]: random.randint(0, 100),
        SIGNALS["BatteryVoltage"]: round(random.uniform(11.5, 14.8), 2),
        SIGNALS["ThrottlePosition"]: random.randint(0, 100),
        SIGNALS["CoolantTemperature"]: random.randint(0, 120),
    }


def summarize_published_values(ready_values):
    published = [signal.split(".")[-1] for signal in ready_values.keys()]
    return ", ".join(published) if published else "none"


def summarize_faults(injected_faults):
    if not injected_faults:
        return "none"

    counts = {}
    for item in injected_faults:
        fault_name = item["fault"]
        counts[fault_name] = counts.get(fault_name, 0) + 1

    return ", ".join(f"{name}={count}" for name, count in sorted(counts.items()))


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
    cycle_index = 0

    while True:
        try:
            async with VSSClient(KUKSA_HOST, KUKSA_PORT) as client:
                while True:
                    cycle_index += 1
                    values = generate_obd_values()
                    ready_values, injected_faults = injector.next_updates(values)
                    updates = {
                        signal: Datapoint(value)
                        for signal, value in ready_values.items()
                    }

                    if updates:
                        await client.set_current_values(updates)

                    cycle_summary = (
                        f"[cycle {cycle_index}] published={summarize_published_values(ready_values)} "
                        f"faults={summarize_faults(injected_faults)}"
                    )
                    print(
                        colorize_red(cycle_summary)
                        if injected_faults
                        else cycle_summary
                    )
                    if injected_faults:
                        print(
                            colorize_red(
                                f"[cycle {cycle_index}] fault details: {injected_faults}"
                            )
                        )
                    elif VERBOSE_LOGGING:
                        print(f"[cycle {cycle_index}] values: {ready_values}")

                    await asyncio.sleep(PUBLISH_INTERVAL_SECONDS)
        except Exception as exc:
            print(f"Kuksa not ready yet: {exc}")
            await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())
