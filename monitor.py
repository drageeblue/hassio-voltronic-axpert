#!/usr/bin/env python3

import argparse
from binascii import unhexlify
import json
import os
import time

import crcmod
import paho.mqtt.client as mqtt


BATTERY_TYPES = {
    "0": "AGM",
    "1": "Flooded",
    "2": "User",
}
VOLTAGE_RANGES = {
    "0": "Appliance",
    "1": "UPS",
}
OUTPUT_SOURCES = {
    "0": "utility",
    "1": "solar",
    "2": "battery",
}
CHARGER_SOURCES = {
    "0": "utility first",
    "1": "solar first",
    "2": "solar + utility",
    "3": "solar only",
}
MACHINE_TYPES = {
    "00": "Grid tie",
    "01": "Off Grid",
    "10": "Hybrid",
}
TOPOLOGIES = {
    "0": "transformerless",
    "1": "transformer",
}
OUTPUT_MODES = {
    "0": "single machine output",
    "1": "parallel output",
    "2": "Phase 1 of 3 Phase output",
    "3": "Phase 2 of 3 Phase output",
    "4": "Phase 3 of 3 Phase output",
}
PV_OK_CONDITIONS = {
    "0": "As long as one unit of inverters has connect PV, parallel system will consider PV OK",
    "1": "Only All of inverters have connect PV, parallel system will consider PV OK",
}
PV_POWER_BALANCE = {
    "0": "PV input max current will be the max charged current",
    "1": "PV input max power will be the sum of the max charged power and loads power",
}


def mqtt_connect(*, server, username, password, client_id):
    client = mqtt.Client(client_id=client_id)
    client.username_pw_set(username, password)
    client.connect(server)
    return client


def serial_command(device, command, *, retries=1):
    print(f"Sending command {command}")
    command_bytes = command.encode()
    xmodem_crc_func = crcmod.predefined.mkCrcFun("xmodem")
    crc_bytes = unhexlify(hex(xmodem_crc_func(command_bytes))[2:])
    try:
        try:
            file = os.open(device, os.O_RDWR | os.O_NONBLOCK)
        except Exception as e:
            raise RuntimeError(f"Error opening device {device}") from e

        os.write(file, command_bytes + crc_bytes + b"\x0d")

        response = b""
        timeout_counter = 0
        while b"\r" not in response:
            if timeout_counter > 1000:
                raise RuntimeError("Read operation timed out")
            timeout_counter += 1
            try:
                response += os.read(file, 256)
            except Exception:
                time.sleep(0.02)
            if len(response) > 0 and response[0] != ord("("):
                raise RuntimeError(f"Corrupt response {response}")

        return response.split(b"\r")[0][1:-2].decode()
    except Exception as e:
        if retries:
            print(f"Error sending command {command}, {retries} retries remaining")
            time.sleep(0.1)
            return serial_command(device, command, retries=retries-1)
        raise RuntimeError(f"Error sending command {command}")
    finally:
        try:
            os.close(file)
        except Exception:
            pass


def get_serial_number(device):
    return serial_command(device, "QID")


def get_parallel_data(device):
    response = serial_command(device, "QPGS0")
    try:
        terms = response.split(" ")
        if len(terms) >= 27:
#            raise RuntimeError("Received fewer than 27 terms")

            return {
                "SerialNumber": int(terms[1]),
                "Mode": "grid" if terms[2] == "L" else "solar" if terms[2] == "B" else None,
                "GridVoltage": float(terms[4]),
                "GridFrequency": float(terms[5]),
                "OutputVoltage": float(terms[6]),
                "OutputFrequency": float(terms[7]),
                "OutputAparentPower": int(terms[8]),
                "OutputActivePower": int(terms[9]),
                "LoadPercentage": int(terms[10]),
                "BatteryVoltage": float(terms[11]),
                "BatteryChargingCurrent": int(terms[12]),
                "BatteryCapacity": float(terms[13]),
                "PvInputVoltage": float(terms[14]),
                "TotalChargingCurrent": int(terms[15]),
                "TotalAcOutputApparentPower": int(terms[16]),
                "TotalAcOutputActivePower": int(terms[17]),
                "TotalAcOutputPercentage": int(terms[18]),
                "InverterStatus": terms[19],
                "OutputMode": int(terms[20]),
                "ChargerSourcePriority": int(terms[21]),
                "MaxChargeCurrent": int(terms[22]),
                "MaxChargerRange": int(terms[23]),
                "MaxAcChargerCurrent": int(terms[24]),
                "PvInputCurrentForBattery": int(terms[25]),
                "BatteryDischargeCurrent": int(terms[26]),
            }
    except Exception as e:
        raise RuntimeError(f"Error parsing parallel_data ({response})") from e


def get_data(device):
    response = serial_command(device, "QPIGS")
    try:
        terms = response.split(" ")
        if len(terms) < 20:
            raise RuntimeError("Received fewer than 20 terms")

        return {
            "GridVoltage": float(terms[0]),
            "GridFrequency": float(terms[1]),		
            "ACOutputVoltage": float(terms[2]),	
            "ACOutputFrequency": float(terms[3]),	
            "ACOutputApparentPower": int(terms[4]),		
            "ACOutputActivePower": int(terms[5]),
            "OutputLoadPercent":int(terms[6]),
            "BusVoltage": float(terms[7]),
            "BatteryVoltage": float(terms[8]),            
            "BatteryChargingCurrent": int(terms[9]),
            "BatteryCapacity": int(terms[10]),
            "InverterHeatsinkTemperature": float(terms[11]),
            "PvInputCurrent": float(terms[12]),
            "PvInputVoltage": float(terms[13]),
            "BatteryVoltageFromScc": float(terms[14]),
            "BatteryDischargeCurrent": int(terms[15]),
            "DeviceStatus": terms[16],
            "BatteryVoltageOffsetForFansOn": int(terms[17]),
	    "EEPROMVersion": terms[18], 
            "PvInputPower": int(terms[19]),
            "DeviceStatus2": terms[20],	
        }
    except Exception as e:
        raise RuntimeError(f"Error parsing data ({response})") from e
        
def get_config_data(device):

    device_json = {
        "identifiers": [
          "AxpertVMIII"
        ],
        "manufacturer": "Voltronic",
        "name": "Axpert3",
        "model": "3Kw",
    }
    busvoltage_json = {
        "unique_id": "axpert3_busvoltage",
        "name": "BusVoltage",
        "device_class": "voltage",
        "state_class": "measurement",
        "unit_of_measurement": "V",
        "state_topic": "inverter/axpert3/BusVoltage",
        "expire_after": 200,
        "icon": "mdi:meter-electric",
        "device": device_json,
    }
    batteryvoltage_json = {
        "unique_id": "axpert3_batteryvoltage",
        "name": "BatteryVoltage",
        "device_class": "voltage",
        "state_class": "measurement",
        "unit_of_measurement": "V",
        "state_topic": "inverter/axpert3/BatteryVoltage",
        "expire_after": 200,
        "icon": "mdi:meter-electric",
        "device": device_json,
    }
    batterychargingcurrent_json = {
        "unique_id": "axpert3_batterychargingcurrent",
        "name": "BatteryChargingCurrent",
        "device_class": "current",
        "state_class": "measurement",
        "unit_of_measurement": "A",
        "state_topic": "inverter/axpert3/BatteryChargingCurrent",
        "expire_after": 200,
        "icon": "mdi:current-dc",
        "device": device_json,
    }
    batterycapacity_json = {
        "unique_id": "axpert3_batterycapacity",
        "name": "BatteryCapacity",
        "state_class": "measurement",
        "unit_of_measurement": "Ah",
        "state_topic": "inverter/axpert3/BatteryCapacity",
        "expire_after": 200,
        "icon": "mdi:home-battery",
        "device": device_json,
    }	
    inverterheatsinktemperature_json = {
        "unique_id": "axpert3_inverterheatsinktemperature",
        "name": "InverterHeatsinkTemperature",
        "device_class": "temperature",	    
        "state_class": "measurement",
        "unit_of_measurement": "°C",
        "state_topic": "inverter/axpert3/InverterHeatsinkTemperature",
        "expire_after": 200,
        "icon": "mdi:temperature-celsius",
        "device": device_json,
    }		
    pvinputcurrent_json = {
        "unique_id": "axpert3_pvinputcurrent",
        "name": "PvInputCurrent",
        "device_class": "current",	    
        "state_class": "measurement",
        "unit_of_measurement": "A",
        "state_topic": "inverter/axpert3/PvInputCurrent",
        "expire_after": 200,
        "icon": "mdi:current-dc",
        "device": device_json,
    }		
    pvinputvoltage_json = {
        "unique_id": "axpert3_pvinputvoltage",
        "name": "PvInputVoltage",
        "device_class": "voltage",
        "state_class": "measurement",
        "unit_of_measurement": "V",
        "state_topic": "inverter/axpert3/PvInputVoltage",
        "expire_after": 200,
        "icon": "mdi:meter-electric",
        "device": device_json,
    }
	
    gridvoltage_json = {
        "unique_id": "axpert3_gridvoltage",
        "name": "GridVoltage",
        "device_class": "voltage",
        "state_class": "measurement",
        "unit_of_measurement": "V",
        "state_topic": "inverter/axpert3/GridVoltage",
        "expire_after": 200,
        "icon": "mdi:meter-electric",
        "device": device_json,
    }
	
    batteryvoltagefromscc_json = {
        "unique_id": "axpert3_batteryvoltagefromscc",
        "name": "BatteryVoltageFromScc",
        "device_class": "voltage",
        "state_class": "measurement",
        "unit_of_measurement": "V",
        "state_topic": "inverter/axpert3/BatteryVoltageFromScc",
        "expire_after": 200,
        "icon": "mdi:meter-electric",
        "device": device_json,
    }
    batterydischargecurrent_json = {
        "unique_id": "axpert3_batterydischargecurrent",
        "name": "BatteryDischargeCurrent",
        "device_class": "current",	    
        "state_class": "measurement",
        "unit_of_measurement": "A",
        "state_topic": "inverter/axpert3/BatteryDischargeCurrent",
        "expire_after": 200,
        "icon": "mdi:current-dc",
        "device": device_json,
    }	

	
    pvinputpower_json = {
        "unique_id": "axpert3_pvinputpower",
        "name": "PvInputPower",
        "device_class": "power",
        "state_class": "measurement",
        "unit_of_measurement": "W",
        "state_topic": "inverter/axpert3/PvInputPower",
        "expire_after": 200,
        "icon": "mdi:solar-power",
        "device": device_json,
    }
	
    acoutputactivepower_json = {
        "unique_id": "axpert3_acoutputactivepower",
        "name": "ACOutputActivePower",
        "device_class": "power",
        "state_class": "measurement",
        "unit_of_measurement": "W",
        "state_topic": "inverter/axpert3/ACOutputActivePower",
        "expire_after": 200,
        "icon": "mdi:power-socket-de",
        "device": device_json,
    }	

    acoutputapparentpower_json = {
        "unique_id": "axpert3_acoutputapparentpower",
        "name": "ACOutputApparentPower",
        "device_class": "apparent_power",
        "state_class": "measurement",
        "unit_of_measurement": "W",
        "state_topic": "inverter/axpert3/ACOutputApparentPower",
        "expire_after": 200,
        "icon": "mdi:meter-electric",
        "device": device_json,
    }	
	
    outputloadpercent_json = {
        "unique_id": "axpert3_outputloadpercent",
        "name": "OutputLoadPercent",
        "device_class": "power",
        "state_class": "measurement",
        "unit_of_measurement": "%",
        "state_topic": "inverter/axpert3/OutputLoadPercent",
        "expire_after": 200,
        "icon": "mdi:percent",
        "device": device_json,
    }	
	
    try:
        return {
            "busvoltage": busvoltage_json,
            "batteryvoltage": batteryvoltage_json,		
	    "batterychargingcurrent_": batterychargingcurrent_json,
	    "batterycapacity": batterycapacity_json,
	    "inverterheatsinktemperature": inverterheatsinktemperature_json,
            "pvinputcurrent": pvinputcurrent_json,		
            "pvinputvoltage": pvinputvoltage_json,
            "gridvoltage": gridvoltage_json,		
            "batteryvoltagefromscc": batteryvoltagefromscc_json,
            "batterydischargecurrent": batterydischargecurrent_json,
	    "pvinputpower": pvinputpower_json,
	    "acoutputactivepower": acoutputactivepower_json,
	    "acoutputapparentpower": acoutputapparentpower_json,	
	    "outputloadpercent": outputloadpercent_json,			
	}
    except Exception as e:
        raise RuntimeError(f"Error parsing data ({response})") from e

def get_settings(device):
    response = serial_command(device, "QPIRI")
    try:
        terms = response.split(" ")
        if len(terms) < 25:
            raise RuntimeError("Received fewer than 25 terms")

        return {     
            "AcInputVoltage": float(terms[0]),
            "AcInputCurrent": float(terms[1]),
            "AcOutputVoltage": float(terms[2]),
            "AcOutputFrequency": float(terms[3]),
            "AcOutputCurrent": float(terms[4]),
            "AcOutputApparentPower": int(terms[5]),
            "AcOutputActivePower": int(terms[6]),
            "BatteryVoltage": float(terms[7]),
            "BatteryRechargeVoltage": float(terms[8]),
            "BatteryUnderVoltage": float(terms[9]),
            "BatteryBulkVoltage": float(terms[10]),
            "BatteryFloatVoltage": float(terms[11]),
            "BatteryType": BATTERY_TYPES[terms[12]],
            "MaxAcChargingCurrent": int(terms[13]),
            "MaxChargingCurrent": int(terms[14]),
            "InputVoltageRange": VOLTAGE_RANGES[terms[15]],
            "OutputSourcePriority": OUTPUT_SOURCES[terms[16]],
            "ChargerSourcePriority": CHARGER_SOURCES[terms[17]],
            "MaxParallelUnits": int(terms[18]),
            "MachineType": MACHINE_TYPES[terms[19]],
            "Topology": TOPOLOGIES[terms[20]],
            "OutputMode": OUTPUT_MODES[terms[21]],
            "BatteryRedischargeVoltage": float(terms[22]),
            "PvOkCondition": PV_OK_CONDITIONS[terms[23]],
            "PvPowerBalance": PV_POWER_BALANCE[terms[24]],
        }
    except Exception as e:
        raise RuntimeError(f"Error parsing settings ({response})") from e


def send_data(client, topic, data):
    try:
        client.publish(topic, data, 0, True)
    except Exception as e:
        raise RuntimeError("Error sending data to mqtt server") from e


def main(
    *,
    device,
    mqtt_server,
    mqtt_user,
    mqtt_pass,
    mqtt_client_id,
    mqtt_topic_settings,
    mqtt_topic_parallel,
    mqtt_topic,
    sleep_query=0,
    sleep_iteration=0,
):
    client = mqtt_connect(
        server=mqtt_server,
        username=mqtt_user,
        password=mqtt_pass,
        client_id=mqtt_client_id,
    )

    print("Querying inverter serial number...")
    serial_number = get_serial_number(device)
    print(f"Reading from inverter {serial_number}\n")
    mqtt_topic = mqtt_topic.replace("{sn}", serial_number)

    while True:
        start = time.time()

 #       data = json.dumps(get_parallel_data(device))
 #       print("parallel_data", data, "\n")
 #       send_data(client, mqtt_topic_parallel, data)
 #       time.sleep(sleep_query)


        data = get_data(device)	    
        for topicin, datain in data.items():
           j = json.dumps(datain)	    
#           print("data", j, "\n")
           send_data(client, mqtt_topic+"/"+topicin , j)
        time.sleep(sleep_query)

        data = json.dumps(get_settings(device))
#        print("settings", data, "\n")
        send_data(client, mqtt_topic_settings, data)
        time.sleep(sleep_query)

        data = get_config_data(device)
        for topicin, datain in data.items():
           j = json.dumps(datain)	    
#           print("data", j, "\n")
           send_data(client, "homeassistant/sensor/axpert3/"+topicin+"/config", j)
        time.sleep(sleep_query)
        
        time.sleep(max(0, sleep_iteration - (time.time() - start)))


if __name__ == "__main__":
    def env(var, val=None):
        return {"default": os.environ.get(var)} if os.environ.get(var) else \
               {"default": val} if val is not None else \
               {"required": True}
    parser = argparse.ArgumentParser(description="""
        Monitor inverter parameters and send them to an MQTT server.
        Arguments can also be set using their corresponding environment variables.
    """)
    parser.add_argument("--device", **env("DEVICE"), help="Inverter IO device")
    parser.add_argument("--mqtt-server", **env("MQTT_SERVER"), help="MQTT server address")
    parser.add_argument("--mqtt-user", **env("MQTT_USER"), help="MQTT username")
    parser.add_argument("--mqtt-pass", **env("MQTT_PASS"), help="MQTT password")
    parser.add_argument("--mqtt-client-id", **env("MQTT_CLIENT_ID"), help="MQTT client id")
    parser.add_argument("--mqtt-topic-settings", **env("MQTT_TOPIC_SETTINGS"), help="MQTT topic for settings")
    parser.add_argument("--mqtt-topic-parallel", **env("MQTT_TOPIC_PARALLEL"), help="MQTT topic for parallel data")
    parser.add_argument("--mqtt-topic", **env("MQTT_TOPIC"), help="MQTT topic for data")
    parser.add_argument("--sleep-query", type=float, **env("SLEEP_QUERY", 1), help="Seconds between queries")
    parser.add_argument("--sleep-iteration", type=float, **env("SLEEP_ITERATION", 5), help="Seconds between iteration starts")
    args = parser.parse_args()

    main(
        device=args.device,
        mqtt_server=args.mqtt_server,
        mqtt_user=args.mqtt_user,
        mqtt_pass=args.mqtt_pass,
        mqtt_client_id=args.mqtt_client_id,
        mqtt_topic_settings=args.mqtt_topic_settings,
        mqtt_topic_parallel=args.mqtt_topic_parallel,
        mqtt_topic=args.mqtt_topic,
        sleep_query=args.sleep_query,
        sleep_iteration=args.sleep_iteration,
    )
