#steps:
#1. confirm Docker is running, if not, start it
#2. run each component using docker in the background
#3. wait for required services to become ready
#4. initialize Eclipse Ditto policy + thing
#5. activate venv
#6. run openDut test script first
#7. run the rest of the pipeline script if tests passed

$projectRoot = $PSScriptRoot

# =========================
# stage 1: make sure Docker is running
# =========================

$dockerDesktop = "C:\Program Files\Docker\Docker\Docker Desktop.exe"

function Test-Docker {
    docker info | Out-Null
    return ($LASTEXITCODE -eq 0)
}

#make sure docker is running
function Wait-For-Docker {
    if (Test-Docker) {
        return
    }

    if (Test-Path $dockerDesktop) {
        Start-Process $dockerDesktop | Out-Null
    } else { #drop if device does not have docker
        throw "Docker Desktop was not found at: $dockerDesktop"
    }

    #set max waiting time of waiting docker to startup
    $maxWait = (Get-Date).AddMinutes(3)

    while ((Get-Date) -lt $maxWait) {
        Start-Sleep -Seconds 5
        if (Test-Docker) {
            return
        }
    }

    throw "Docker is still not ready after 3 minutes."
}

Write-Host "Checking Docker..."
Wait-For-Docker
Write-Host "Docker is ready."

# =========================
# stage 2: run each pipeline component with Docker
# =========================
#used to start a component service
function Start-Component {
    param(
        [string]$Title,
        [string]$Workdir,
        [string]$Command
    )

    Write-Host "Starting $Title..."
    Push-Location $Workdir
    try {
        Invoke-Expression $Command
    } finally {
        Pop-Location
    }
}

function Wait-For-Component {
    param(
        [string]$Name,
        [string]$Url,
        [int]$TimeoutSeconds = 60
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)

    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing $Url -TimeoutSec 5
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                Write-Host "$Name is ready."
                return
            }
        } catch {
        }

        Start-Sleep -Seconds 2
    }

    throw "$Name is not running. Dropping pipeline."
}

function Wait-For-Port {
    param(
        [string]$Name,
        [string]$HostName,
        [int]$Port,
        [int]$TimeoutSeconds = 60
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)

    while ((Get-Date) -lt $deadline) {
        $result = Test-NetConnection -ComputerName $HostName -Port $Port -WarningAction SilentlyContinue
        if ($result.TcpTestSucceeded) {
            Write-Host "$Name is ready."
            return
        }

        Start-Sleep -Seconds 2
    }

    throw "$Name is not ready. Dropping pipeline."
}

# =========================
# Ditto helpers: create policy and Thing, essential for ditto to run properly and expose itself
# =========================

function Get-BasicAuthHeader {
    param(
        [string]$Username,
        [string]$Password
    )

    $pair = "${Username}:${Password}"
    $encoded = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes($pair))

    return @{
        Authorization = "Basic $encoded"
        "Content-Type" = "application/json"
    }
}

function Wait-For-DittoApi {
    param(
        [hashtable]$Headers,
        [int]$TimeoutSeconds = 120
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)

    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest `
                -UseBasicParsing `
                -Uri "http://localhost:8080/api/2/things" `
                -Headers $Headers `
                -TimeoutSec 5

            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                Write-Host "Ditto API is ready."
                return
            }
        } catch {
        }

        Start-Sleep -Seconds 3
    }

    throw "Ditto API did not become ready in time."
}

function Initialize-Ditto {
    param(
        [string]$ThingId = "org.eclipse.kuksa:vehicle1",
        [string]$Username = "ditto",
        [string]$Password = "ditto"
    )

    Write-Host "Initializing Ditto policy and thing..."

    $headers = Get-BasicAuthHeader -Username $Username -Password $Password

    Wait-For-DittoApi -Headers $headers -TimeoutSeconds 120

    $policyBody = @'
{
  "entries": {
    "owner": {
      "subjects": {
        "nginx:ditto": {
          "type": "nginx basic auth user"
        }
      },
      "resources": {
        "thing:/": {
          "grant": ["READ","WRITE"],
          "revoke": []
        },
        "policy:/": {
          "grant": ["READ","WRITE"],
          "revoke": []
        },
        "message:/": {
          "grant": ["READ","WRITE"],
          "revoke": []
        }
      }
    }
  }
}

function Initialize-DittoFleet {
    param(
        [string]$VehiclesConfigPath = (Join-Path $projectRoot "config\vehicles.json"),
        [string]$Username = "ditto",
        [string]$Password = "ditto"
    )

    if (-not (Test-Path $VehiclesConfigPath)) {
        Initialize-Ditto -ThingId "org.eclipse.kuksa:vehicle1" -Username $Username -Password $Password
        return
    }

    $vehicles = Get-Content $VehiclesConfigPath -Raw | ConvertFrom-Json -AsHashtable

    foreach ($vehicleId in $vehicles.Keys) {
        $thingId = $vehicles[$vehicleId]["thing_id"]
        if (-not $thingId) {
            $thingId = "org.eclipse.kuksa:$vehicleId"
        }

        Initialize-Ditto -ThingId $thingId -Username $Username -Password $Password
    }
}
'@

$thingBody = @"
{
  "policyId": "$ThingId",
  "attributes": {
    "status": "created"
  },
  "features": {
    "VehicleSpeed": {},
    "EngineSpeed": {},
    "FuelLevel": {},
    "BatteryVoltage": {},
    "ThrottlePosition": {},
    "CoolantTemperature": {}
  }
}
"@

    try {
        Invoke-RestMethod `
            -Method Put `
            -Uri "http://localhost:8080/api/2/policies/$ThingId" `
            -Headers $headers `
            -Body $policyBody | Out-Null

        Write-Host "Ditto policy created/updated: $ThingId"
    } catch {
        throw "Failed to create/update Ditto policy '$ThingId'. Error: $($_.Exception.Message)"
    }

    try {
        Invoke-RestMethod `
            -Method Put `
            -Uri "http://localhost:8080/api/2/things/$ThingId" `
            -Headers $headers `
            -Body $thingBody | Out-Null

        Write-Host "Ditto thing created/updated: $ThingId"
    } catch {
        throw "Failed to create/update Ditto thing '$ThingId'. Error: $($_.Exception.Message)"
    }
}

# =========================
# Start infrastructure
# =========================

# kuksa
Start-Component `
    -Title "Kuksa" `
    -Workdir "~\kuksa-databroker" `
    -Command "docker run -d -p 55555:55555 -v `"${projectRoot}\vss\OBD.json:/OBD.json`" ghcr.io/eclipse-kuksa/kuksa-databroker:main --insecure --vss /OBD.json"

# zenoh
Start-Component `
    -Title "Zenoh" `
    -Workdir $projectRoot `
    -Command "docker run --name zenoh-router -p 7447:7447 -d eclipse/zenoh:latest"


# ditto
Start-Component `
    -Title "Ditto" `
    -Workdir "~\ditto" `
    -Command "docker compose -f .\deployment\docker\docker-compose.yml up -d"


# IMPORTANT: initialize Ditto before subscriber/bridge starts
Initialize-DittoFleet

# zovd
Start-Component `
    -Title "ZOVD" `
    -Workdir "~\classic-diagnostic-adapter" `
    -Command "docker compose -f .\testcontainer\docker-compose.yml up -d --build"


# openDUT
Start-Component `
    -Title "openDut" `
    -Workdir $projectRoot `
    -Command "docker compose -f .\opendut-docker\docker-compose.yml up -d"

# =========================
# stage 3: run scripts in venv
# =========================

#activate virtual environment before running any pipeline script
$venvDir = if (Test-Path (Join-Path $projectRoot "venv\Scripts\Activate.ps1")) {
    "venv"
} elseif (Test-Path (Join-Path $projectRoot ".venv\Scripts\Activate.ps1")) {
    ".venv"
} else {
    throw "There is no virtual environment installed in this directory."
}

$activateScript = ".\$venvDir\Scripts\Activate.ps1"
$activateScriptPath = Join-Path $projectRoot "$venvDir\Scripts\Activate.ps1"

function Run-ProjectScript {
    param(
        [string]$Title,
        [string]$ProjectRoot,
        [string]$ActivateScript,
        [string]$Command
    )

    Start-Process powershell -ArgumentList @(
        "-NoExit",
        "-Command",
        "cd '$ProjectRoot'; `$Host.UI.RawUI.WindowTitle = '$Title'; & '$ActivateScript'; $Command"
    )
}

#wait for all service to run, then start the test
Wait-For-Port -Name "Kuksa" -HostName "localhost" -Port 55555
Wait-For-Port -Name "Zenoh" -HostName "localhost" -Port 7447
Wait-For-Component -Name "Ditto" -Url "http://localhost:8080"
Wait-For-Component -Name "ZOVD" -Url "http://localhost:20002/health"
Wait-For-Component -Name "openDut" -Url "http://localhost:8085"

#run test with openDUT first and stop the pipeline if it fails
Set-Location $projectRoot
& $activateScriptPath
python .\testing\open_dut_test_cases.py
if ($LASTEXITCODE -ne 0) {
    throw "openDut integration test failed. Stopping pipeline before launching project scripts."
}

#generate OBD data to Kuksa
Run-ProjectScript `
    -Title "OBD Publisher" `
    -ProjectRoot $projectRoot `
    -ActivateScript $activateScript `
    -Command "python .\send_obd_data_to_kuksa.py"

#connect Kuksa to Zenoh
Run-ProjectScript `
    -Title "Send Data to Zenoh" `
    -ProjectRoot $projectRoot `
    -ActivateScript $activateScript `
    -Command "python .\connect_kuksa_zenoh.py"

#subscribe Ditto to Zenoh
Run-ProjectScript `
    -Title "Get Feature Update from Zenoh" `
    -ProjectRoot $projectRoot `
    -ActivateScript $activateScript `
    -Command "python .\subscribe_ditto_zenoh.py"

#start SOVD API service
Run-ProjectScript `
    -Title "SOVD API" `
    -ProjectRoot $projectRoot `
    -ActivateScript $activateScript `
    -Command "python -m uvicorn diagnostics.sovd_api_server:app --host 0.0.0.0 --port 9001"
