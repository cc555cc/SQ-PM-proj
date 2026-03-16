# Thin FastAPI wrapper that proxies selected requests to the real OpenSOVD CDA
# service so the project can expose a stable local API without starting a
# second SOVD component.

from fastapi import FastAPI, HTTPException, Response
import requests
import os
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
def request_sovd(path: str) -> requests.Response:
    url = f"{SOVD_URL}{path}"
    try:
        response = requests.get(url, timeout = REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response
    except requests.RequestException as e:
        raise HTTPException(status_code = 503, detail = f"SOVD not available: {e}")


def get_sovd_json(path: str):
    return request_sovd(path).json()

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
        "upstream_mappings": {
            "/health/ready": "/health",
            "/vehicle/raw": "/vehicle/v15/components",
            "/vehicle/status": "/health",
        },
    }

@app.get("/health/live")
def health_live():
    return{"status": "alive"}

@app.get("/health/ready")
def health_ready():
    try:
        request_sovd("/health")
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
    return get_sovd_json("/vehicle/v15/components")


@app.get("/vehicle/status")
def vehicle_status():
    upstream_response = request_sovd("/health")
    return Response(
        content=upstream_response.text,
        status_code=upstream_response.status_code,
        media_type=upstream_response.headers.get("content-type", "application/json"),
    )
