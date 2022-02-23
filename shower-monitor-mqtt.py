import hashlib
import json
import logging
import os
import random
import ssl
import string
import sys
import time

import paho.mqtt.client as mqtt
import requests

import settings

logging.basicConfig(
    filename=os.path.splitext(__file__)[0] + ".log",
    format='%(asctime)s %(levelname)-8s %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S')

last = {
    "status": "off",
    "power": 0,
    "level": settings.capacity,
    "timestamp": time.time(),
    "start": -1,
    "duration": 0,
    "litres": 0
}

logger = logging.getLogger(__name__)
logger.info("Starting Shower Monitor...")
client = mqtt.Client()
client.enable_logger(logger)


def rand_gen(size, chars=string.ascii_lowercase + string.digits):
    return str(''.join(random.choice(chars) for _ in range(size)))


def msg_id(unix_time):
    concat_string = '{}{}'.format(rand_gen(16), unix_time)
    final_md5 = hashlib.md5(concat_string.encode('utf-8')).hexdigest()
    return str(final_md5)


def get_unix_time():
    current_time = int(time.time())
    return current_time


def signing_key(message_id, key, uts):
    concat_string = '{}{}{}'.format(message_id, key, uts)
    final_md5 = hashlib.md5(concat_string.encode('utf-8')).hexdigest()
    return str(final_md5)


def on_connect(client, userdata, flags, rc):
    logger.info("Connected with result code " + mqtt.error_string(rc))
    client.subscribe([(settings.resend_topic, 0),
                     ("/appliance/" + settings.device_id + "/publish", 0)])


def on_disconnect(client, userdata, rc):
    logger.info("Disconnected with result code " + mqtt.error_string(rc))

def on_unsubscribe(client, userdata, mid):
    logger.info("Unsubscribed")


def process_power(power):
    global last
    status = "on" if power > settings.shower_on_power else "off"
    timestamp = time.time()
    elapsed = timestamp - last["timestamp"]
    level = last["level"] + elapsed * \
        ((settings.flow_fill - settings.flow_shower) if status == "on" else settings.flow_fill)
    msg = {
        "status": status,
        "power": power,
        "level": min(settings.capacity, level),
        "timestamp": timestamp,
        "start": last["start"],
        "duration": last["duration"],
        "litres": last["litres"]
    }
    if status == "on" and last["status"] == "off":
        msg["start"] = timestamp
        msg["duration"] = 0
        msg["litres"] = 0
    elif status == "off" and last["status"] == "on":
        msg["duration"] = timestamp - last["start"]
        msg["litres"] = settings.flow_shower * (timestamp - last["start"])
        requests.post(settings.post_url, json=msg)
    elif status == "on":
        msg["duration"] = timestamp - last["start"]
        msg["litres"] = settings.flow_shower * (timestamp - last["start"])
    client.publish(settings.resend_topic, payload=json.dumps(msg), retain=True)
    last = msg


def on_message(client, userdata, msg):
    global last
    payload = json.loads(msg.payload)
    if msg.topic == settings.resend_topic:
        logger.info("Initialising with: " + str(payload))
        last = payload
    else:
        try:
            power = payload["payload"]["electricity"]["power"]
            process_power(power)
        except:
            logger.warning("JSON was not in the expected format: " + str(payload))


def request_power():
    timestamp = get_unix_time()
    message_id = msg_id(timestamp)
    sign = signing_key(message_id, "", timestamp)
    msg = {
        "header": {
            "from": "/appliance/" + settings.device_id + "/publish",
            "messageId": message_id,
            "method": "GET",
            "namespace": "Appliance.Control.Electricity",
            "payloadVersion": 1,
            "sign": sign,
            "timestamp": str(timestamp)
        },
        "payload": {
            "channel": 0
        }
    }
    message_info = client.publish(
        "/appliance/" + settings.device_id + "/subscribe", json.dumps(msg))
    if message_info.rc != mqtt.MQTT_ERR_SUCCESS:
        logger.warn("Publish failed: " + mqtt.error_string(message_info.rc))


client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.on_message = on_message
client.on_unsubscribe = on_unsubscribe
if settings.tls:
    client.tls_set(cert_reqs=ssl.CERT_NONE)
    client.tls_insecure_set(True)

client.connect(settings.mqtt_broker, port=settings.port, keepalive=60)
client.loop_start()

# Wait for retained message
time.sleep(2)
client.unsubscribe(settings.resend_topic)

while True:
    request_power()
    time.sleep(2)
    if time.time() - last["timestamp"] > 60:
        logger.warning("No messages received for 60 seconds. Exiting. ")
        sys.exit("No response")
