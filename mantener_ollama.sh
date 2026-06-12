#!/bin/bash
# Guardian: mantiene arkani:latest cargado en RAM permanentemente
while true; do
    STATUS=$(ollama ps | grep "arkani")
    if [ -z "$STATUS" ]; then
        echo "$(date): Modelo descargado — recargando..."
        curl -s http://localhost:11434/api/generate \
          -d '{"model":"arkani:latest","prompt":"ping","stream":false,"keep_alive":-1}' \
          > /dev/null 2>&1 &
    fi
    sleep 30
done
