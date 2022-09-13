#!/usr/bin/sh

sudo mkdir /var/run/milter || true
sudo chown postfix: /var/run/milter
cd /var/run/milter
sudo -u postfix /usr/local/bin/milter-addmessageid.py
