# Thin FastAPI wrapper that proxies selected requests to the real OpenSOVD CDA
# service so the project can expose a stable local API without starting a
# second SOVD component.

from fastapi import FastAPI, HTTPException
import requests
import os
import json
from dotenv import load_dotenv

#load envrionement variables and threshold rule
load_dotenv()

app = FastAPI(
    title = "OpenSOVD Diagnostic API",
    version = os.getenv("SOVD_API_VERSION","0.1.0"),
    description = ("SOVD-style ditto backend API"),
)

#SOVD 
SOVD_URL = os.getenv("SOVD_URL", "http://localhost:20002")
REQUEST_TIMEOUT_SECONDS = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "5"))

#connect to SOVD
def get_sovd(path: str):
    url = f"{SOVD_URL}{path}"
    try:
        response = requests.get(url, timeout = REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        raise HTTPException(status_code = 503, detail = f"SOVD not available: {e}")

#api
@app.get("/")
def root():
    return {
        "service": "OpenSOVD proxy API",
        "implementation": "proxy over SOVD componenet",
        "upstream_sovd_url": SOVD_URL,
        "supported_endpoints": [
            "/",
            "/health/live",
            "/health/ready",
            "/vehicle/raw",
            "/vehicle/status",
        ],
    }

@app.get("/health/live")
def health_live():
    return{"status": "alive"}

@app.get("/health/ready")
def health_ready():
    try:
        get_sovd("/")
        return{
            "status": "ready",
            "sovd_url": SOVD_URL,
        }
    except HTTPException as exc:
        return{
            "status": "not ready",
            "detail": exc.detail,
            "sovd_url": SOVD_URL,
        }

@app.get("/vehicle/raw")
def vehicle_raw():
    response = get_sovd("/vehicle/raw")
    return response


@app.get("/vehicle/status")
def vehicle_status():
    response = get_sovd("/vehicle/status")
    return response.json()
