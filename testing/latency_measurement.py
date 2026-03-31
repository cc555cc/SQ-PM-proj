# This script measures end-to-end latency from Kuksa to Ditto by sending a
# test value to a Kuksa signal and timing how long it takes for the matching
# Ditto feature to reflect the same update.
import argparse
import asyncio
import os
import statistics
import time

import requests
from dotenv import load_dotenv

load_dotenv()

from kuksa_client.grpc import Datapoint
from kuksa_client.grpc.aio import VSSClient

KUKSA_HOST = os.getenv("KUKSA_HOST", "localhost")
KUKSA_PORT = int(os.getenv("KUKSA_PORT", "55555"))

DITTO_URL = os.getenv("DITTO_URL", "http://localhost:8080")
DITTO_USERNAME = os.getenv("DITTO_USERNAME", "ditto")
DITTO_PASSWORD = os.getenv("DITTO_PASSWORD", "ditto")
DITTO_THING_ID = os.getenv("DITTO_THING_ID", "org.eclipse.kuksa:vehicle1")

KUKSA_TEST_SIGNAL = "Vehicle.OBD.VehicleSpeed"
DITTO_TEST_FEATURE = "VehicleSpeed"
SAMPLE_VALUE_GAP = 10


def get_ditto_feature_properties():
    url = f"{DITTO_URL}/api/2/things/{DITTO_THING_ID}"
    response = requests.get(
        url,
        auth=(DITTO_USERNAME, DITTO_PASSWORD),
        timeout=5,
    )
    response.raise_for_status()

    thing = response.json()
    return (
        thing.get("features", {})
        .get(DITTO_TEST_FEATURE, {})
        .get("properties", {})
    )

#choose test values that are different from the current value in Ditto
def choose_test_values(sample_count):
    current_value = get_ditto_feature_properties().get("value")
    base_value = 220

    if current_value is not None and current_value >= base_value:
        base_value = int(current_value) + SAMPLE_VALUE_GAP

    return [base_value + (index * SAMPLE_VALUE_GAP) for index in range(sample_count)]


def next_retry_value(base_value, attempt_index):
    return base_value + attempt_index

#sends a test value to Kuksa and polls Ditto until it sees the update
async def measure_single_latency(client, test_value, timeout_seconds, poll_interval):
    print(f"Sending test value {test_value} to Kuksa signal {KUKSA_TEST_SIGNAL}")
    start = time.perf_counter()
    last_reassertion = 0.0
    last_observed_value = None

    #poll Ditto until it sees the update
    while True:
        elapsed_seconds = time.perf_counter() - start

        # Reassert the probe value so the background publisher does not immediately
        # overwrite the signal before the bridge can propagate it to Ditto.
        if elapsed_seconds == 0.0 or (elapsed_seconds - last_reassertion) >= poll_interval:
            await client.set_current_values({KUKSA_TEST_SIGNAL: Datapoint(test_value)})
            last_reassertion = elapsed_seconds

        observed_properties = get_ditto_feature_properties()
        observed_value = observed_properties.get("value")
        last_observed_value = observed_value

        if observed_value == test_value:
            elapsed_ms = (time.perf_counter() - start) * 1000
            print(
                f"Observed {DITTO_TEST_FEATURE}={observed_value} in Ditto "
                f"after {elapsed_ms:.2f} ms"
            )
            return elapsed_ms

        if elapsed_seconds > timeout_seconds:
            raise TimeoutError(
                "Ditto did not reflect the Kuksa update within the timeout. "
                f"Last observed {DITTO_TEST_FEATURE} value was {last_observed_value!r}."
            )

        await asyncio.sleep(poll_interval)

#calculates and prints statistics 
def print_summary(results_ms):
    average_ms = statistics.mean(results_ms)
    median_ms = statistics.median(results_ms)
    minimum_ms = min(results_ms)
    maximum_ms = max(results_ms)

    if len(results_ms) > 1:
        stdev_ms = statistics.stdev(results_ms)
    else:
        stdev_ms = 0.0

    print("\nLatency summary")
    print(f"Samples: {len(results_ms)}")
    print(f"Average: {average_ms:.2f} ms")
    print(f"Median: {median_ms:.2f} ms")
    print(f"Min: {minimum_ms:.2f} ms")
    print(f"Max: {maximum_ms:.2f} ms")
    print(f"Std Dev: {stdev_ms:.2f} ms")


async def main():
    parser = argparse.ArgumentParser(
        description="Measure end-to-end Kuksa to Ditto latency."
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=5,
        help="Number of latency samples to collect.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="Seconds to wait for each Ditto update before failing.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=0.1,
        help="Seconds between Ditto polls.",
    )
    parser.add_argument(
        "--retries-per-sample",
        type=int,
        default=3,
        help="How many fresh values to try before marking a sample as failed.",
    )
    parser.add_argument(
        "--settle-seconds",
        type=float,
        default=1.0,
        help="Seconds to wait between samples so late updates can drain through Ditto.",
    )
    parser.add_argument(
        "--minimum-successful-samples",
        type=int,
        default=3,
        help="Minimum successful samples required for the latency run to pass.",
    )
    args = parser.parse_args()

    if args.samples < 1:
        raise ValueError("--samples must be at least 1.")
    if args.retries_per_sample < 1:
        raise ValueError("--retries-per-sample must be at least 1.")
    if args.minimum_successful_samples < 1:
        raise ValueError("--minimum-successful-samples must be at least 1.")
    if args.minimum_successful_samples > args.samples:
        raise ValueError("--minimum-successful-samples cannot exceed --samples.")

    results_ms = []
    test_values = choose_test_values(args.samples)
    failed_samples = []

    async with VSSClient(KUKSA_HOST, KUKSA_PORT) as client:
        for index, base_test_value in enumerate(test_values, start=1):
            print(f"\nSample {index}/{args.samples}")
            sample_succeeded = False

            for attempt_index in range(args.retries_per_sample):
                test_value = next_retry_value(base_test_value, attempt_index)
                if attempt_index > 0:
                    print(
                        f"Retry {attempt_index}/{args.retries_per_sample - 1} "
                        f"with test value {test_value}"
                    )

                try:
                    elapsed_ms = await measure_single_latency(
                        client=client,
                        test_value=test_value,
                        timeout_seconds=args.timeout,
                        poll_interval=args.poll_interval,
                    )
                    results_ms.append(elapsed_ms)
                    sample_succeeded = True
                    break
                except TimeoutError as exc:
                    print(f"Sample {index} attempt {attempt_index + 1} timed out: {exc}")

            if not sample_succeeded:
                failed_samples.append(index)

            if index < args.samples:
                await asyncio.sleep(args.settle_seconds)

    if results_ms:
        print_summary(results_ms)

    successful_samples = len(results_ms)
    print(
        f"Successful samples: {successful_samples}/{args.samples} "
        f"(minimum required: {args.minimum_successful_samples})"
    )

    if successful_samples < args.minimum_successful_samples:
        raise TimeoutError(
            "Latency measurement did not reach the minimum successful sample count. "
            f"Failed sample(s): {', '.join(str(sample) for sample in failed_samples)}"
        )


if __name__ == "__main__":
    asyncio.run(main())
