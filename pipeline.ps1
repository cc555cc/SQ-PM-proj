#this pipeline script open a terminal window for each script

#confirm venv activate script exist & define relative path to venv in the project file
$venvDir = if (Test-Path (Join-Path $PSScriptRoot "venv\Scripts\Activate.ps1")) {
    "venv" #set venvDir to venv
} elseif (Test-Path (Join-Path $PSScriptRoot ".venv\Scripts\Activate.ps1")) { #also check for .venv
    ".venv"
} else {
    throw "No virtual environment found. Expected 'venv' or '.venv' in $PSScriptRoot."
}

#build relative path to powershell activation script
$activate = ".\$venvDir\Scripts\Activate.ps1"

#window instances that run the scripts
function Start-ComponentWindow {
    param(
        [string]$Title,
        [string]$Command
    )

    Start-Process powershell -ArgumentList @(
        "-NoExit",
        "-Command",
        "cd '$PSScriptRoot'; `$Host.UI.RawUI.WindowTitle = '$Title'; $activate; $Command"
    )
}

#list of script and theire value(Title, Command)
$components = @(
    @{
        Title = "OBD Publisher"
        Command = "python send_obd_data_to_kuksa.py"
    },
    @{
        Title = "Kuksa to Zenoh"
        Command = "python connect_kuksa_zenoh.py"
    },
    @{
        Title = "Zenoh to Ditto"
        Command = "python subscribe_ditto_zenoh.py"
    },
    @{
        Title = "SOVD API"
        Command = "python -m uvicorn diagnostics.sovd_api_server:app --host 0.0.0.0 --port 9000"
    },
    @{
        Title = "OpenDuT CARL"
        Command = "docker compose -f .\opendut-docker\docker-compose.yml up"
    }
)

#loop through components list and assign a terminal window
foreach ($component in $components) {
    Start-ComponentWindow -Title $component.Title -Command $component.Command
    Start-Sleep -Milliseconds 400
}
