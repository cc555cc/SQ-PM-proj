# This script uses FastAPI to expose simple Eclipse SOVD-style diagnostic
# endpoints for the project pipeline. It reads the latest vehicle features
# from the Ditto twin and returns either raw values or threshold-based status
# summaries.
#
#steps:
#1. Load environment variables and threshold rules from configuration.
#2. Request the latest vehicle Thing data from Eclipse Ditto.
#3. Extract the current feature values from the Ditto response.
#4. Return raw signal values through the `/vehicle/raw` endpoint.
#5. Return warning status summaries through the `/vehicle/status` endpoint.

from fastapi import FastAPI, HTTPException
import requests
import os
import json
from dotenv import load_dotenv

#load envrionement variables and threshold rule
load_dotenv()

app = FastAPI()

#ditto
DITTO_URL = os.getenv("DITTO_URL", "http://localhost:8080")
DITTO_USERNAME = os.getenv("DITTO_USERNAME", "ditto")
DITTO_PASSWORD = os.getenv("DITTO_PASSWORD", "ditto")
THING_ID = os.getenv("DITTO_THING_ID", "org.eclipse.kuksa:vehicle1")
REQUEST_TIMEOUT_SECONDS = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "5"))

#read diagnostic threshold rules, load to python
with open("config/thresholds.json", "r", encoding="utf-8") as f:
    thresholds = json.load(f)

#request the current vehicle Thing from Eclipse Ditto so the SOVD API can
#use the latest twin data to build diagnostic responses
def get_ditto_thing():
    url = f"{DITTO_URL}/api/2/things/{THING_ID}"
    try:
        response = requests.get(
            url,
            auth=(DITTO_USERNAME, DITTO_PASSWORD),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json() #return response from ditto as parsed JSON data
    except requests.RequestException as e:
        raise HTTPException(status_code=503, detail=f"Ditto unavailable: {e}")


#extract only the feature property values from the Ditto Thing response and
#store them in a simpler dictionary keyed by feature name
def extract_feature_values(thing):
    features = thing.get("features", {})
    values = {}

    #for each features, extra their value
    for feature_name, feature_body in features.items():
        values[feature_name] = (
            feature_body.get("properties", {}).get("value")
        )

    return values

#api
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
