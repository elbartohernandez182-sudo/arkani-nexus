#!/bin/bash
echo "Arrancando Ollama..."
sudo systemctl start ollama
sleep 3

echo "Arrancando Arkani..."
pkill -f arkani_web.py
cd ~/NEXUS/NEXUS-LANG
nohup python3 arkani_web.py > arkani.log 2>&1 &
sleep 5

echo "Arrancando ngrok..."
pkill ngrok
sleep 2
nohup ngrok http 8081 > ngrok.log 2>&1 &
sleep 8

echo "Tu URL:"
curl http://127.0.0.1:4040/api/tunnels 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['tunnels'][0]['public_url'])"
