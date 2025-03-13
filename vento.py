#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import paho.mqtt.client as mqttClient
import re
import time
import socket
import signal
import sys
import logging
import argparse
import json


'''
        Dieses Programm ermöglicht es, einen Blauberg Ventilator per mqtt in eine Hausautomationsumgebung einzubinden.

        Hauptprogramm: Michael H. Bosch
        Routinen parsebytes und parse_response sind dem Modul pyEcovent entnommen, welches unter MIT Lizenz veröffentlicht wurde: https://github.com/aglehmann/pyEcovent

        Further changes: Gatis Tomsons
'''

parser = argparse.ArgumentParser(
    prog="vento",
    description="Control VENTO air unit via MQTT"
)
parser.add_argument("--vento-host", required=True, help="Host of the VENTO unit")
parser.add_argument("--mqtt-host", required=True, help="MQTT server hostname")
parser.add_argument("--mqtt-port", type=int, default=1883, help="MQTT server port")
parser.add_argument("--mqtt-user", help="MQTT server username")
parser.add_argument("--mqtt-pass", help="MQTT server password")
parser.add_argument("--mqtt-topic", default="blauberg-vento", help="MQTT topic")
parser.add_argument("--log", default=None, help="Log file path")
parser.add_argument("--debug", nargs='?', const=10, default=20, help="With debug output")
args = parser.parse_args()

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=args.debug,
    filename=args.log,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


class Ventilator:
    def parsebytes(self, bytestring, params):
        i = iter(bytestring)
        for param in i:
            value = [next(i) for _ in range(params[param][0])]
            yield (param, value)

    def parse_response(self, data):
        fan_params = {
            0x03: [1, 'state', None],
            0x04: [1, 'speed', None],
            0x05: [1, 'manual_speed', None],
            0x06: [1, 'air_flow_direction', None],
            0x08: [1, 'humidity_level', None],
            0x09: [1, 'operation_mode', None],
            0x0B: [1, 'humidity_sensor_threshold', None],
            0x0C: [1, 'alarm_status', None],
            0x0D: [1, 'relay_sensor_status', None],
            0x0E: [3, 'party_or_night_mode_countdown', None],
            0x0F: [3, 'night_mode_timer', None],
            0x10: [3, 'party_mode_timer', None],
            0x11: [3, 'deactivation_timer', None],
            0x12: [1, 'filter_eol_timer', None],
            0x13: [1, 'humidity_sensor_status', None],
            0x14: [1, 'boost_mode', None],
            0x15: [1, 'humidity_sensor', None],
            0x16: [1, 'relay_sensor', None],
            0x17: [1, '10V_sensor', None],
            0x19: [1, '10V_sensor_threshold', None],
            0x1A: [1, '10V_sensor_status', None],
            0x1B: [32, 'slave_device_search', None],
            0x1C: [4, 'response_slave_search', None],
            0x1F: [1, 'cloud_activation', None],
            0x25: [1, '10V_sensor_current_status', None]
        }

        for pair in self.parsebytes(data, fan_params):
            if pair[0] == 3:
                self.state = pair[1][0]
            elif pair[0] == 4:
                self.speed = pair[1][0]
            elif pair[0] == 5:
                self.man_speed = pair[1][0]
            elif pair[0] == 6:
                self.airflow = pair[1][0]
            elif pair[0] == 8:
                self.humidity = pair[1][0]

    def payload(self):
        return json.dumps({
            'state':     str(self.state),
            'humidity':  str(self.humidity),
            'speed':     str(self.speed),
            'airflow':   str(self.airflow),
            'man_speed': str(self.man_speed)
        })


class Vento:
    def __init__(self):
        self.ventilator_host = args.vento_host
        self.broker_address = args.mqtt_host
        self.mqtt_port = args.mqtt_port
        self.mqtt_user = args.mqtt_user
        self.mqtt_password = args.mqtt_pass
        self.mqtt_topic = args.mqtt_topic

        self.connected = False
        self.ventilator = Ventilator()
        self.sleeptime = 5  # Socket sleep time
        self.ventilator_state = False
        self.ventilator_speed = False
        self.ventilator_airflow = False
        self.change_onoff = False
        self.change_speed = False
        self.change_airflow = False

        self.client = mqttClient.Client(mqttClient.CallbackAPIVersion.VERSION2)
        self.client.username_pw_set(self.mqtt_user, password=self.mqtt_password)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_subscribe = self.on_subscribe
        self.client.on_unsubscribe = self.on_unsubscribe
        self.client.on_disconnect = self.on_disconnect

    def start(self):
        try:
            signal.signal(signal.SIGTERM, self.exit_gracefully)
            self.connect_to_mqtt()
            while True:
                self.main_loop()
        except (KeyboardInterrupt, SystemExit):
            self.client.publish(self.mqtt_topic + "/service", "Service Down")
            logger.info("Start cleanup")
            self.client.loop_stop()
            time.sleep(2)
            self.client.disconnect()
            logger.info("Bye")
            sys.exit(0)

    def connect_to_mqtt(self):
        try:
            self.client.connect(self.broker_address, port=self.mqtt_port)
            self.client.loop_start()
        except socket.error as error:
            logger.error("MQTT connection: %s" % error)
            time.sleep(2)
            self.connect_to_mqtt()

    def subscribe_to_topics(self):
        self.client.subscribe([
            (self.mqtt_topic + "/command/state", 0),
            (self.mqtt_topic + "/command/speed", 0),
            (self.mqtt_topic + "/command/airflow", 0)
        ])

    def on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            logger.info("Connected to a MQTT broker")
            self.connected = True
            self.subscribe_to_topics()
        elif reason_code == 1:
            logger.error("Wrong protocol version")
        elif reason_code == 2:
            logger.error("Identification failed")
        elif reason_code == 3:
            logger.error("Server not reachable")
        elif reason_code == 4:
            logger.error("Wrong username or password")
        elif reason_code == 5:
            logger.error("Unauthorized")
        else:
            logger.error("Failed with unknown error code: " + str(reason_code))

    def on_disconnect(self, client, userdata, flags, reason_code, properties):
        if reason_code != 0:
            logger.info("A disconnect was received, try reconnecting...")
            client.reconnect()

    def on_message(self, client, userdata, message):
        logger.debug("Messagetopic=" + message.topic + " Message=" + str(message.payload))
        data = str(message.payload)
        data = data[2:len(data)-1]
        logger.debug("Message="+data)

        if str(message.topic) == self.mqtt_topic + "/command/state" and re.match(r"[0-1]", data):
            self.ventilator_state = data
            self.change_onoff = True

        if str(message.topic) == self.mqtt_topic + "/command/speed" and re.match(r"[0-3]", data):
            self.ventilator_speed = data
            self.change_speed = True

        if str(message.topic) == self.mqtt_topic + "/command/airflow" and re.match(r"[0-2]", data):
            self.ventilator_airflow = data
            self.change_airflow = True

    def on_subscribe(self, client, userdata, mid, reason_code_list, properties):
        logger.debug("On subscribe: " + str(mid))

    def on_unsubscribe(self, client, userdata, mid, reason_code_list, properties):
        logger.debug("On unsubscribe: " + str(mid))

    def send_mqtt(self, msg):
        self.client.publish(self.mqtt_topic + "/status", msg)
        self.client.publish(self.mqtt_topic + "/service", "Online")

    def main_loop(self):
        retry = 1
        alt_status = ""

        HEADER = bytes.fromhex('6D6F62696C65')
        FOOTER = bytes.fromhex('0D0A')

        # Data request for the control page
        data = bytes.fromhex('6D6F62696C6501000D0A')

        # UDP Socket
        addr = (self.ventilator_host, 4000)
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.settimeout(10)
        while True:
            try:
                udp_socket.sendto(data, addr)
                response = udp_socket.recv(98)
                logger.debug("Raw response: " + str(response))
                self.ventilator.parse_response(response[6:])
                status = str(self.ventilator.state) + "-" + str(self.ventilator.speed) + "-" + str(self.ventilator.man_speed) + "-" + str(self.ventilator.humidity) + "-" + str(self.ventilator.airflow)
                if self.ventilator_state is False:
                    self.ventilator_state = self.ventilator.state
                if self.ventilator_speed is False:
                    self.ventilator_speed = self.ventilator.speed
                if self.ventilator_airflow is False:
                    self.ventilator_airflow = self.ventilator.airflow

                if int(self.ventilator_state) != int(self.ventilator.state):
                    if self.change_onoff is True:
                        logger.info("Change status: " + str(self.ventilator_state))
                        udp_socket.sendto(bytes.fromhex('6D6F62696C6503000D0A'), addr)
                    else:
                        self.ventilator_state = self.ventilator.state
                else:
                    self.change_onoff = False
                if int(self.ventilator_speed) != int(self.ventilator.speed):
                    if self.change_speed is True:
                        logger.info("Change speed: " + str(self.ventilator_speed))
                        cmd = '04' + '{0:0{1}x}'.format(int(self.ventilator_speed), 2)
                        udp_socket.sendto((HEADER + bytes.fromhex(cmd) + FOOTER), addr)
                    else:
                        self.ventilator_speed = self.ventilator.speed
                else:
                    self.change_speed = False
                if int(self.ventilator_airflow) != int(self.ventilator.airflow):
                    if self.change_airflow is True:
                        logger.info("Change airflow: " + str(self.ventilator_airflow))
                        cmd = '06' + '{0:0{1}x}'.format(int(self.ventilator_airflow), 2)
                        udp_socket.sendto((HEADER + bytes.fromhex(cmd) + FOOTER), addr)
                    else:
                        self.ventilator_airflow = self.ventilator.airflow
                else:
                    self.change_airflow = False
                logger.debug(self.ventilator.payload())
                if alt_status != status:
                    self.send_mqtt(self.ventilator.payload())
                alt_status = status
                self.client.publish(self.mqtt_topic + "/service", "Online")
                retry = 1
                signal.signal(signal.SIGTERM, self.exit_gracefully)
                time.sleep(self.sleeptime)
            except socket.timeout as error:
                logger.error("Socket Error: %s" % error)
                self.client.publish(self.mqtt_topic + "/service", "TimeOut")
                time.sleep(self.sleeptime)
                logger.info("Waiting for a response from the ventilation system #" + str(retry))
                retry += 1
                pass
            except socket.error as error:
                logger.error("Unhandled Socket Error: %s" % error)
                udp_socket.close()
                time.sleep(5)
                pass
            except (KeyboardInterrupt, SystemExit):
                logger.info("Exiting")
                udp_socket.close()
                sys.exit(0)

    def exit_gracefully(self, signum, frame):
        self.client.publish(self.mqtt_topic + "/service", "Service Down")
        logger.info("Terminate service due to TERM signal")
        self.client.disconnect()
        time.sleep(1)
        sys.exit(0)


Vento().start()
