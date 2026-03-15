#This script sends simulated OBD data to Kuksa for testing purposes.
import asyncio
import os
import random

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
PUBLISH_INTERVAL_SECONDS = float(os.getenv("PUBLISH_INTERVAL_SECONDS", "1"))

SIGNALS = {
    "VehicleSpeed": "Vehicle.OBD.VehicleSpeed",
    "EngineSpeed": "Vehicle.OBD.EngineSpeed",
    "ThrottlePosition": "Vehicle.OBD.ThrottlePosition",
    "CoolantTemperature": "Vehicle.OBD.CoolantTemperature",
}


def generate_obd_values():
    return {
        SIGNALS["VehicleSpeed"]: random.randint(0, 255),
        SIGNALS["EngineSpeed"]: random.randint(0, 1000),
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

    while True:
        try:
            async with VSSClient(KUKSA_HOST, KUKSA_PORT) as client:
                while True:
                    values = generate_obd_values()
                    updates = {
                        signal: Datapoint(value)
                        for signal, value in values.items()
                    }

                    await client.set_current_values(updates)

                    print(
                        "Published:",
                        {
                            "VehicleSpeed": values[SIGNALS["VehicleSpeed"]],
                            "EngineSpeed": values[SIGNALS["EngineSpeed"]],
                            "ThrottlePosition": values[SIGNALS["ThrottlePosition"]],
                            "CoolantTemperature": values[SIGNALS["CoolantTemperature"]],
                        },
                    )
                    print("-------------------------------------------------------------------------------------------------\n")

                    await asyncio.sleep(PUBLISH_INTERVAL_SECONDS)
        except Exception as exc:
            print(f"Kuksa not ready yet: {exc}")
            await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())
