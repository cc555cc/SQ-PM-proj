import json
import unittest

from subscribe_ditto_zenoh import build_feature_updates


class FakePayloadBytes:
    def __init__(self, content):
        self._content = content

    def to_bytes(self):
        return self._content


class FakeZenohPayload:
    def __init__(self, body):
        self.payload = FakePayloadBytes(body)


class SubscribeDittoZenohTests(unittest.TestCase):
    def test_build_feature_updates_keeps_fault_and_twin_metadata(self):
        payload = {
            "vehicleId": "vehicle2",
            "thingId": "org.eclipse.kuksa:vehicle2",
            "feature": "CoolantTemperature",
            "value": 90,
            "rawValue": 170,
            "quality": "invalid",
            "faults": ["incorrect_value"],
            "recoveryAction": "reused_last_good_for_invalid_value",
            "pipelineSafe": True,
            "timestamp": 123.45,
            "cycle": 7,
        }

        result = build_feature_updates(
            FakeZenohPayload(json.dumps(payload).encode("utf-8"))
        )

        properties = result["feature_updates"]["CoolantTemperature"]["properties"]
        self.assertEqual(result["thing_id"], "org.eclipse.kuksa:vehicle2")
        self.assertEqual(properties["vehicleId"], "vehicle2")
        self.assertEqual(properties["value"], 90)
        self.assertEqual(properties["rawValue"], 170)
        self.assertEqual(properties["quality"], "invalid")
        self.assertEqual(properties["faults"], ["incorrect_value"])
        self.assertEqual(
            properties["recoveryAction"],
            "reused_last_good_for_invalid_value",
        )
        self.assertTrue(properties["pipelineSafe"])
        self.assertEqual(properties["cycle"], 7)
        self.assertEqual(properties["sourceTimestamp"], 123.45)
        self.assertFalse(properties["isHealthy"])


if __name__ == "__main__":
    unittest.main()
