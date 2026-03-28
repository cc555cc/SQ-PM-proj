import json
import random
from dataclasses import dataclass
from pathlib import Path


DEFAULT_FAULT_CONFIG = {
    "enabled": True,
    "cycle_interval_seconds": 1.0,
    "faulty_cycle_probability": 0.3,
    "missing_data_probability": 0.1,
    "delayed_signal_probability": 0.15,
    "incorrect_value_probability": 0.1,
    "missing_after_cycles": 3,
    "max_delay_cycles": 3,
    "max_stale_cycles": 2,
    "fallback_defaults": {
        "Vehicle.OBD.VehicleSpeed": 0,
        "Vehicle.OBD.EngineSpeed": 0,
        "Vehicle.OBD.FuelLevel": 0,
        "Vehicle.OBD.BatteryVoltage": 12.5,
        "Vehicle.OBD.ThrottlePosition": 0,
        "Vehicle.OBD.CoolantTemperature": 90,
    },
    "signals": {
        "Vehicle.OBD.VehicleSpeed": {"min": 0, "max": 255},
        "Vehicle.OBD.EngineSpeed": {"min": 0, "max": 8000},
        "Vehicle.OBD.FuelLevel": {"min": 0, "max": 100},
        "Vehicle.OBD.BatteryVoltage": {"min": 11.0, "max": 15.0},
        "Vehicle.OBD.ThrottlePosition": {"min": 0, "max": 100},
        "Vehicle.OBD.CoolantTemperature": {"min": -40, "max": 130},
    },
}


BASE_DIR = Path(__file__).resolve().parent
FAULT_CONFIG_PATH = BASE_DIR / "config" / "fault_config.json"


def load_fault_config(path=FAULT_CONFIG_PATH):
    if not Path(path).exists():
        return DEFAULT_FAULT_CONFIG

    with Path(path).open("r", encoding="utf-8") as config_file:
        loaded = json.load(config_file)

    merged = json.loads(json.dumps(DEFAULT_FAULT_CONFIG))
    merged.update({k: v for k, v in loaded.items() if k != "signals"})
    merged["signals"].update(loaded.get("signals", {}))
    return merged


def is_value_out_of_range(signal, value, fault_config):
    bounds = fault_config.get("signals", {}).get(signal)
    if bounds is None or value is None:
        return False

    minimum = bounds.get("min")
    maximum = bounds.get("max")

    if minimum is not None and value < minimum:
        return True
    if maximum is not None and value > maximum:
        return True
    return False


def build_quality_report(signal, value, last_seen_cycle, current_cycle, fault_config):
    faults = []

    if last_seen_cycle is None:
        faults.append("missing_data")
    else:
        age = current_cycle - last_seen_cycle
        if age >= fault_config["missing_after_cycles"]:
            faults.append("missing_data")
        elif age > 1:
            faults.append("delayed_signal")

    if is_value_out_of_range(signal, value, fault_config):
        faults.append("incorrect_value")

    if "missing_data" in faults:
        quality = "missing"
    elif "incorrect_value" in faults:
        quality = "invalid"
    elif "delayed_signal" in faults:
        quality = "degraded"
    else:
        quality = "good"

    return {"quality": quality, "faults": faults}


def get_fallback_value(signal, fault_config):
    return fault_config.get("fallback_defaults", {}).get(signal)


def repair_signal_value(
    signal,
    raw_value,
    quality_report,
    last_good_value,
    fault_config,
):
    faults = quality_report["faults"]
    recovery_action = "pass_through"
    effective_value = raw_value

    if "incorrect_value" in faults:
        if last_good_value is not None:
            effective_value = last_good_value
            recovery_action = "reused_last_good_for_invalid_value"
        else:
            effective_value = get_fallback_value(signal, fault_config)
            recovery_action = "used_default_for_invalid_value"
    elif "missing_data" in faults:
        if last_good_value is not None:
            effective_value = last_good_value
            recovery_action = "reused_last_good_for_missing_data"
        else:
            effective_value = get_fallback_value(signal, fault_config)
            recovery_action = "used_default_for_missing_data"
    elif "delayed_signal" in faults:
        if last_good_value is not None:
            effective_value = last_good_value
            recovery_action = "held_last_good_while_signal_delayed"
        else:
            effective_value = raw_value
            recovery_action = "accepted_delayed_value"

    pipeline_safe = effective_value is not None

    return {
        "raw_value": raw_value,
        "effective_value": effective_value,
        "recovery_action": recovery_action,
        "pipeline_safe": pipeline_safe,
    }


@dataclass
class PendingUpdate:
    signal: str
    value: float
    release_cycle: int


class FaultInjector:
    def __init__(self, fault_config):
        self.fault_config = fault_config
        self.current_cycle = 0
        self.pending_updates = []

    def _mutate_value(self, signal, value):
        bounds = self.fault_config.get("signals", {}).get(signal, {})
        minimum = bounds.get("min")
        maximum = bounds.get("max")

        if minimum is None or maximum is None:
            return value * 3 if isinstance(value, (int, float)) else value

        span = max(maximum - minimum, 1)
        overshoot = max(1, round(span * 0.25, 2))

        if random.choice([True, False]):
            mutated = maximum + overshoot
        else:
            mutated = minimum - overshoot

        if isinstance(value, int):
            return int(round(mutated))
        return round(float(mutated), 2)

    def next_updates(self, generated_values):
        self.current_cycle += 1
        ready_updates = {}
        injected_faults = []

        remaining_pending = []
        for pending in self.pending_updates:
            if pending.release_cycle <= self.current_cycle:
                ready_updates[pending.signal] = pending.value
            else:
                remaining_pending.append(pending)
        self.pending_updates = remaining_pending

        if not self.fault_config.get("enabled", True):
            ready_updates.update(generated_values)
            return ready_updates, injected_faults

        faulty_cycle_probability = self.fault_config.get("faulty_cycle_probability", 1.0)
        if random.random() >= faulty_cycle_probability:
            ready_updates.update(generated_values)
            return ready_updates, injected_faults

        for signal, value in generated_values.items():
            if random.random() < self.fault_config["missing_data_probability"]:
                injected_faults.append({"signal": signal, "fault": "missing_data"})
                continue

            next_value = value
            if random.random() < self.fault_config["incorrect_value_probability"]:
                next_value = self._mutate_value(signal, value)
                injected_faults.append(
                    {
                        "signal": signal,
                        "fault": "incorrect_value",
                        "original_value": value,
                        "faulty_value": next_value,
                    }
                )

            if random.random() < self.fault_config["delayed_signal_probability"]:
                delay_cycles = random.randint(2, self.fault_config["max_delay_cycles"] + 1)
                self.pending_updates.append(
                    PendingUpdate(
                        signal=signal,
                        value=next_value,
                        release_cycle=self.current_cycle + delay_cycles,
                    )
                )
                injected_faults.append(
                    {
                        "signal": signal,
                        "fault": "delayed_signal",
                        "release_cycle": self.current_cycle + delay_cycles,
                    }
                )
                continue

            ready_updates[signal] = next_value

        return ready_updates, injected_faults
