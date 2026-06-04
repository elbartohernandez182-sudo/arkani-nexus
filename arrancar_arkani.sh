#!/bin/bash
echo "Arrancando Ollama..."
sudo systemctl start ollama
sleep 3

echo "Arrancando Arkani Web..."
pkill -f arkani_web.py
cd ~/NEXUS/NEXUS-LANG
nohup python3 arkani_web.py > ~/NEXUS/logs/arkani.log 2>&1 &
sleep 5

echo "Arrancando Mapper Daemon..."
pkill -f nexus_mapper_daemon.py
nohup python3 nexus_mapper_daemon.py > ~/NEXUS/logs/mapper.log 2>&1 &
sleep 2

echo "Arrancando ngrok..."
pkill ngrok
sleep 2
nohup ngrok http 8081 > ~/NEXUS/logs/ngrok.log 2>&1 &
sleep 8

echo "Tu URL ngrok:"
curl http://127.0.0.1:4040/api/tunnels 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['tunnels'][0]['public_url'])"

echo ""
echo "Arkani Web:    http://192.168.100.29:8081"
echo "Mapper Daemon: http://192.168.100.29:5010"
echo "LISTO"

# Auto-actualizar contexto para Claude
bash ~/NEXUS/scripts/update_context.sh &
