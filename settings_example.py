# Copy to settings.py
mqtt_broker = "192.168.1.2"
device_address = "192.168.1.3"
light_address = "192.168.1.4"
key = "002debbf74504093a8864093dc086c87"
resend_topic = "home/shower"
tls = True
port = 8883
post_url = "https://prod-45.northeurope.logic.azure.com:443/workflows/e4fa3a9b4abd417380abae1a9a8c349a/triggers/manual/paths/invoke?api-version=2016-10-01&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=bb5518d7-0cc9-4d16-a5f4-1586f84b50cb"
device_id = "ce39eced77084c99bfe727d55192fc74" # Only used for local mqtt

shower_on_power = 100000  # reading - presumably mW
flow_shower = 0.125  # l/s
flow_fill = 0.025  # l/s
capacity = 100  # litres