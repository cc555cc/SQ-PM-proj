import argparse
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
PYTHON = sys.executable


def build_commands(include_producer: bool, include_api: bool) -> list[tuple[str, list[str]]]:
    commands: list[tuple[str, list[str]]] = [
        ("kuksa->zenoh", [PYTHON, "connect_kuksa_zenoh.py"]),
        ("zenoh->ditto", [PYTHON, "subscribe_ditto_zenoh.py"]),
    ]

    if include_producer:
        commands.insert(0, ("obd-producer", [PYTHON, "send_obd_data_to_kuksa.py"]))

    if include_api:
        commands.append(
            (
                "sovd-api",
                [
                    PYTHON,
                    "-m",
                    "uvicorn",
                    "diagnostics.sovd_api_server:app",
                    "--host",
                    os.getenv("SOVD_HOST", "127.0.0.1"),
                    "--port",
                    os.getenv("SOVD_PORT", "8000"),
                ],
            )
        )

    return commands


def stream_output(name: str, process: subprocess.Popen[str]) -> None:
    assert process.stdout is not None

    for line in process.stdout:
        print(f"[{name}] {line}", end="")


def terminate_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return

    process.terminate()

    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the local SQ-PM pipeline from one terminal."
    )
    parser.add_argument(
        "--no-producer",
        action="store_true",
        help="Skip the local OBD test data producer.",
    )
    parser.add_argument(
        "--with-api",
        action="store_true",
        help="Also run the OpenSOVD API with uvicorn.",
    )
    args = parser.parse_args()

    commands = build_commands(
        include_producer=not args.no_producer,
        include_api=args.with_api,
    )

    processes: list[tuple[str, subprocess.Popen[str]]] = []
    output_threads: list[threading.Thread] = []

    print("Starting pipeline:")
    for name, command in commands:
        print(f"  - {name}: {' '.join(command)}")

    try:
        for name, command in commands:
            process = subprocess.Popen(
                command,
                cwd=ROOT_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            processes.append((name, process))

            thread = threading.Thread(
                target=stream_output,
                args=(name, process),
                daemon=True,
            )
            thread.start()
            output_threads.append(thread)

        print("Pipeline is running. Press Ctrl+C to stop everything.")

        while True:
            for name, process in processes:
                exit_code = process.poll()
                if exit_code is not None:
                    print(f"\n{name} exited with code {exit_code}. Stopping pipeline.")
                    return exit_code

            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping pipeline...")
        return 0
    finally:
        for _, process in processes:
            terminate_process(process)

        for thread in output_threads:
            thread.join(timeout=1)


if __name__ == "__main__":
    raise SystemExit(main())
