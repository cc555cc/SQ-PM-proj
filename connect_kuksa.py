#Task:
#1. connect to Kuksa
#2. subscribe to vehicle signals
#3. convert data into JSON structure that ditto is expecting
#4. send the update to ditto
#5. repeat steps 2-4 for each update received from Kuksa

import os
import time
import json
import requests

# get configuration from environment variables 

#kuksa env
KUKSA_HOST = os.getenv("KUKSA_HOST", "kuksa-databroker")
KUKSA_PORT = os.getenv("KUKSA_PORT", "55555")

#ditto env
DITTO_URL = os.getenv("DITTO_URL", "http://ditto:8080")
DITTO_USERNAME = os.getenv("DITTO_USERNAME", "ditto")
DITTO_THING_ID = os.getenv("DITTO_THING_ID", "org.eclipse.kuksa:vehicle1")
DITTO_PASSWORD = os.getenv("DITTO_PASSWORD", "ditto")

#get signal map
def load_signal_map():
    with open("config/signal_map.json", "r") as map:
        return json.load(map)
    
#connect to kuksa, subscribe to signal
def connect_to_kuksa():
    #create kuksa client

    #connect to databroker

    #return client
    return None

#interpret signal 
def read_signal(client, map):
    values = {}

    for signal in map.keys():
        #get value from kuksa client

        pass
    
    return values

#build payload for ditto
def build_payload(values):
    attributes = {}

    for signal, value in signal_values.items():
        key = map[signal]
        attributes[key] = value

    return {"attribute": attributes}

#send payload to ditto
def update_ditto(payload):
    url = f"{DITTO_URL}/api/2/things/{DITTO_THING_ID}/features/vehicle/signals/properties"

    #define headers and auth
    response = requests.put(url, 
        auth=(DITTO_USERNAME, DITTO_PASSWORD),
        headers={"Content-Type": "application/json"},
        json=payload
    )

    #print connection log for debugging
    print("Ditto: ", response.status_code, response.txt)

def main():
    #variables
    map = load_signal_map()
    client = connect_to_kuksa()

    #main loop
    while True:
        try:
            signal_values = read_signal(client, map)
            payload = build_payload(signal_values)
            update_ditto(payload)
            time.sleep(1) 
        except Exception as e:
            print("Error at kuksa connection: ", e)
            time.sleep(1)






    




