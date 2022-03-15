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
import requests as req

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


def rgb_to_int(r, g, b):
    return 65536 * r + 256 * g + b


WHITE = rgb_to_int(255, 255, 255)
BLUE = rgb_to_int(0, 0, 255)
GREEN = rgb_to_int(0, 255, 0)
ORANGE = rgb_to_int(255, 127, 0)
RED = rgb_to_int(255, 0, 0)

colour = -1

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
    client.subscribe([(settings.resend_topic, 0)])


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
        ((settings.flow_fill - settings.flow_shower)
         if status == "on" else settings.flow_fill)
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
        req.post(settings.post_url, json=msg)
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


def set_light(rgb):
    timestamp = get_unix_time()
    message_id = msg_id(timestamp)
    sign = signing_key(message_id, settings.key, timestamp)
    payload = {
        "light": {
            "capacity": 6 if rgb == WHITE else 5,
            "channel": 0,
            "rgb": rgb,
            "temperature": 100,
            "luminance": 100,
            "transform": -1
        }
    }
    try:
        meross_request(
            settings.light_address, "SET", "Appliance.Control.Light", payload)
    except Exception as ex:
        logger.warning("Setting light failed: {}".format(ex))


def get_colour(litres, level, status):
    if status == "off":
        return WHITE
    elif level < 25 or litres > 75:
        return RED
    elif litres > 50:
        return ORANGE
    else:
        return BLUE


def meross_request(address, method, namespace, payload):
    timestamp = get_unix_time()
    message_id = msg_id(timestamp)
    sign = signing_key(message_id, settings.key, timestamp)
    msg = {
        "header": {
            "from": "http://" + address + "/config",
            "messageId": message_id,
            "method": method,
            "namespace": namespace,
            "payloadVersion": 1,
            "sign": sign,
            "timestamp": str(timestamp)
        },
        "payload": payload
    }
    resp = req.post("http://" + address +
                    "/config", json=msg)
    json = resp.json()
    return json


def request_power():
    try:
        payload = meross_request(
            settings.device_address, "GET", "Appliance.Control.Electricity", {})
        power = payload["payload"]["electricity"]["power"]
        process_power(power)
    except Exception as ex:
        logger.warning("Power request failed: {}".format(ex))


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
    rgb = get_colour(last["litres"], last["level"], last["status"])
    if rgb != colour:
        set_light(rgb)
        colour = rgb
    time.sleep(2)
    if time.time() - last["timestamp"] > 60:
        logger.warning("No messages received for 60 seconds. Exiting. ")
        sys.exit("No response")
