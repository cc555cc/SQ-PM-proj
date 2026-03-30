#this script is used to test connection to kuksa zenoh bridge
#on port 7447 by sending a test value and checking for the expected output

import unittest
from unittest.mock import patch

from connect_kuksa_zenoh import publish_quality_updates


class ConnectKuksaZenohTests(unittest.TestCase):
    def test_publish_quality_updates_only_emits_healthy_changed_signals(self):
        signal_map = {
            "Vehicle.OBD.VehicleSpeed": "VehicleSpeed",
            "Vehicle.OBD.EngineSpeed": "EngineSpeed",
        }
        vehicle_registry = {
            "vehicle1": {
                "vehicle_id": "vehicle1",
                "thing_id": "org.eclipse.kuksa:vehicle1",
                "zenoh_prefix": "vehicle/vehicle1/vss",
                "signal_offsets": {},
            }
        }
        current_values = {
            "Vehicle.OBD.VehicleSpeed": 88,
            "Vehicle.OBD.EngineSpeed": 1500,
        }
        last_seen_cycles = {
            "Vehicle.OBD.VehicleSpeed": 4,
            "Vehicle.OBD.EngineSpeed": 4,
        }
        last_good_values = {}

        with patch("connect_kuksa_zenoh.log_bridge_event"), patch(
            "connect_kuksa_zenoh.build_and_ship_feature"
        ) as build_and_ship_feature:
            publish_quality_updates(
                zenoh_session=object(),
                signal_map=signal_map,
                vehicle_registry=vehicle_registry,
                current_values=current_values,
                updated_signals={"Vehicle.OBD.VehicleSpeed"},
                last_seen_cycles=last_seen_cycles,
                last_good_values=last_good_values,
                cycle_index=4,
            )

        self.assertEqual(build_and_ship_feature.call_count, 1)
        published_signal = build_and_ship_feature.call_args.kwargs["signal"]
        self.assertEqual(published_signal, "Vehicle.OBD.VehicleSpeed")


if __name__ == "__main__":
    unittest.main()
