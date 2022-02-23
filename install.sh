#!/bin/sh

sudo cp ./shower-monitor.service /lib/systemd/system
sudo chmod 644 /lib/systemd/system/shower-monitor.service
sudo systemctl daemon-reload
sudo systemctl enable shower-monitor.service
sudo systemctl start shower-monitor.service