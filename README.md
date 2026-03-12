# SQ-PM-proj

This repository is currently focused on one milestone: bridging live OBD data from Kuksa Databroker into Eclipse Ditto.

## Current Scope

`connect_kuksa.py` does four things:

1. Connects to Kuksa Databroker over gRPC.
2. Subscribes to configured OBD signals.
3. Maps each Kuksa signal to a Ditto feature name.
4. Updates the matching Ditto features.

`send_obd_data_to_kuksa.py` is an optional local test producer. It publishes random OBD values into Kuksa so the bridge has live data to forward to Ditto.

The active Kuksa to Ditto mapping lives in [config/signal_map.json](/abs/path/c:/Users/Carson/OneDrive/Desktop/Proj%20Management/SQ-PM-proj/config/signal_map.json).

## Expected Signals

The bridge is currently configured for these Kuksa OBD paths:

- `Vehicle.OBD.VehicleSpeed`
- `Vehicle.OBD.EngineSpeed`
- `Vehicle.OBD.ThrottlePosition`
- `Vehicle.OBD.CoolantTemperature`

These map to Ditto feature IDs:

- `VehicleSpeed`
- `EngineSpeed`
- `ThrottlePosition`
- `CoolantTemperature`

## Requirements

- Python 3.13 recommended
- A reachable Kuksa Databroker
- A reachable Eclipse Ditto instance
- A Ditto Thing that matches the configured Thing ID and features

## Python Setup

Create and activate a Python 3.13 virtual environment:

```powershell
py -3.13 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install requests kuksa-client
```

## Environment

Default runtime values in [connect_kuksa.py](/abs/path/c:/Users/Carson/OneDrive/Desktop/Proj%20Management/SQ-PM-proj/connect_kuksa.py):

- `KUKSA_HOST=localhost`
- `KUKSA_PORT=55555`
- `DITTO_URL=http://localhost:8080`
- `DITTO_USERNAME=ditto`
- `DITTO_PASSWORD=ditto`
- `DITTO_THING_ID=org.eclipse.kuksa:vehicle1`

Override them in PowerShell when needed:

```powershell
$env:KUKSA_HOST="localhost"
$env:KUKSA_PORT="55555"
$env:DITTO_URL="http://localhost:8080"
$env:DITTO_THING_ID="org.eclipse.kuksa:vehicle1"
```

## Ditto Bootstrap

Use [config/ditto_thing.json](/abs/path/c:/Users/Carson/OneDrive/Desktop/Proj%20Management/SQ-PM-proj/config/ditto_thing.json) as the initial Thing payload for Ditto.

It defines these features:

- `VehicleSpeed`
- `EngineSpeed`
- `ThrottlePosition`
- `CoolantTemperature`

If the Thing does not already exist in Ditto, create it before running the bridge. Example:

```powershell
$body = Get-Content .\config\ditto_thing.json -Raw
Invoke-RestMethod `
  -Method Put `
  -Uri "http://localhost:8080/api/2/things/org.eclipse.kuksa:vehicle1" `
  -ContentType "application/json" `
  -Authentication Basic `
  -Credential (New-Object System.Management.Automation.PSCredential("ditto",(ConvertTo-SecureString "ditto" -AsPlainText -Force))) `
  -Body $body
```

If your Ditto policy differs, update `policyId` in [config/ditto_thing.json](/abs/path/c:/Users/Carson/OneDrive/Desktop/Proj%20Management/SQ-PM-proj/config/ditto_thing.json) and `DITTO_THING_ID` accordingly.

## Run

Start Kuksa and Ditto first.

If you want local test data, run the producer in one terminal:

```powershell
python send_obd_data_to_kuksa.py
```

Then run the bridge in another terminal:

```powershell
python connect_kuksa.py
```

On success, you should see lines like:

```text
Starting bridge: Kuksa=localhost:55555, Ditto=http://localhost:8080, Thing=org.eclipse.kuksa:vehicle1
Ditto [VehicleSpeed]: 204
```

You should also see the producer printing batches like:

```text
Starting OBD publisher: Kuksa=localhost:55555
Published: {'VehicleSpeed': 121, 'EngineSpeed': 477, 'ThrottlePosition': 55, 'CoolantTemperature': 201}
```

## Common Failures

- `Failed to import kuksa-client`
  Use Python 3.13 and install dependencies in the same interpreter that runs the script.

- `Connection refused` to Kuksa
  Kuksa Databroker is not running on the configured host and port.

- `These signals were not found in Kuksa`
  The configured paths in [config/signal_map.json](/abs/path/c:/Users/Carson/OneDrive/Desktop/Proj%20Management/SQ-PM-proj/config/signal_map.json) do not exist in the loaded Kuksa tree.

- `things:feature.notfound` or `404`
  The Ditto Thing or required features do not exist yet. Create the Thing from [config/ditto_thing.json](/abs/path/c:/Users/Carson/OneDrive/Desktop/Proj%20Management/SQ-PM-proj/config/ditto_thing.json) first.
