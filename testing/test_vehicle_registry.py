import unittest

from vehicle_registry import apply_vehicle_profile, load_vehicle_registry


class VehicleRegistryTests(unittest.TestCase):
    def test_registry_contains_multiple_vehicles(self):
        registry = load_vehicle_registry()
        self.assertGreaterEqual(len(registry), 3)
        self.assertIn("vehicle1", registry)
        self.assertIn("vehicle2", registry)
        self.assertIn("vehicle3", registry)

    def test_vehicle_profile_adjusts_values(self):
        registry = load_vehicle_registry()
        adjusted = apply_vehicle_profile(
            "Vehicle.OBD.VehicleSpeed",
            100,
            registry["vehicle2"],
        )
        self.assertEqual(adjusted, 104)


if __name__ == "__main__":
    unittest.main(verbosity=2)
