from fastapi import FastAPI, HTTPException
import requests
import os
import json
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

DITTO_URL = os.getenv("DITTO_URL", "http://localhost:8080")
DITTO_USERNAME = os.getenv("DITTO_USERNAME", "ditto")
DITTO_PASSWORD = os.getenv("DITTO_PASSWORD", "ditto")
THING_ID = os.getenv("DITTO_THING_ID", "org.eclipse.kuksa:vehicle1")
REQUEST_TIMEOUT_SECONDS = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "5"))

with open("config/thresholds.json", "r", encoding="utf-8") as f:
    thresholds = json.load(f)


def get_ditto_thing():
    url = f"{DITTO_URL}/api/2/things/{THING_ID}"
    try:
        response = requests.get(
            url,
            auth=(DITTO_USERNAME, DITTO_PASSWORD),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        raise HTTPException(status_code=503, detail=f"Ditto unavailable: {e}")


def extract_feature_values(thing):
    features = thing.get("features", {})
    values = {}

    for feature_name, feature_body in features.items():
        values[feature_name] = (
            feature_body.get("properties", {}).get("value")
        )

    return values


@app.get("/")
def root():
    return {"message": "OpenSOVD Diagnostic API running"}


@app.get("/vehicle/raw")
def vehicle_raw():
    thing = get_ditto_thing()
    return extract_feature_values(thing)


@app.get("/vehicle/status")
def vehicle_status():
    thing = get_ditto_thing()
    values = extract_feature_values(thing)

    alerts = []
    signals = {}
    overall_status = "normal"

    for signal, value in values.items():
        rule = thresholds.get(signal, {})
        min_v = rule.get("min")
        max_v = rule.get("max")
        unit = rule.get("unit", "")

        status = "normal"

        if isinstance(value, (int, float)):
            if min_v is not None and value < min_v:
                status = "warning"
            if max_v is not None and value > max_v:
                status = "warning"

        if status != "normal":
            alerts.append(signal)
            overall_status = "warning"

        signals[signal] = {
            "value": value,
            "unit": unit,
            "status": status
        }

    return {
        "signals": signals,
        "alerts": alerts,
        "overall_status": overall_status
    }