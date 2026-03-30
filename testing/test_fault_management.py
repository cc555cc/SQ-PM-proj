#this script is used to test the fault mamagement logic by
#simulating different fault scenarios, verifying them by checking the quality reports

import unittest

from fault_management import (
    FaultInjector,
    build_quality_report,
    load_fault_config,
    repair_signal_value,
)


class FaultManagementTests(unittest.TestCase):
    def setUp(self):
        self.config = load_fault_config()

    #test on missing data
    def test_missing_data_becomes_missing_quality(self):
        report = build_quality_report(
            signal="Vehicle.OBD.VehicleSpeed",
            value=120,
            last_seen_cycle=1,
            current_cycle=5,
            fault_config=self.config,
        )
        self.assertEqual(report["quality"], "missing")
        self.assertIn("missing_data", report["faults"])

    #test on out of range value
    def test_out_of_range_value_becomes_invalid_quality(self):
        report = build_quality_report(
            signal="Vehicle.OBD.FuelLevel",
            value=140,
            last_seen_cycle=4,
            current_cycle=4,
            fault_config=self.config,
        )
        self.assertEqual(report["quality"], "invalid")
        self.assertIn("incorrect_value", report["faults"])

    #test on disabled injector
    def test_disabled_injector_passthroughs_values(self):
        config = load_fault_config()
        config["enabled"] = False
        injector = FaultInjector(config)
        updates, faults = injector.next_updates(
            {"Vehicle.OBD.VehicleSpeed": 100}
        )
        self.assertEqual(updates["Vehicle.OBD.VehicleSpeed"], 100)
        self.assertEqual(faults, [])

    #test on 100% faulty cycle probability
    def test_non_faulty_cycle_passthroughs_values(self):
        config = load_fault_config()
        config["faulty_cycle_probability"] = 0.0
        injector = FaultInjector(config)
        updates, faults = injector.next_updates(
            {"Vehicle.OBD.VehicleSpeed": 100}
        )
        self.assertEqual(updates["Vehicle.OBD.VehicleSpeed"], 100)
        self.assertEqual(faults, [])

    #test on 100% faulty cycle probability with out of range value
    def test_invalid_value_reuses_last_good_value(self):
        quality_report = {
            "quality": "invalid",
            "faults": ["incorrect_value"],
        }
        repaired = repair_signal_value(
            signal="Vehicle.OBD.FuelLevel",
            raw_value=140,
            quality_report=quality_report,
            last_good_value=45,
            fault_config=self.config,
        )
        self.assertEqual(repaired["effective_value"], 45)
        self.assertEqual(
            repaired["recovery_action"],
            "reused_last_good_for_invalid_value",
        )
        self.assertTrue(repaired["pipeline_safe"])

    #test on missing value with no history
    def test_missing_value_uses_default_when_no_history_exists(self):
        quality_report = {
            "quality": "missing",
            "faults": ["missing_data"],
        }
        repaired = repair_signal_value(
            signal="Vehicle.OBD.BatteryVoltage",
            raw_value=None,
            quality_report=quality_report,
            last_good_value=None,
            fault_config=self.config,
        )
        self.assertEqual(repaired["effective_value"], 12.5)
        self.assertEqual(
            repaired["recovery_action"],
            "used_default_for_missing_data",
        )
        self.assertTrue(repaired["pipeline_safe"])


if __name__ == "__main__":
    unittest.main()
