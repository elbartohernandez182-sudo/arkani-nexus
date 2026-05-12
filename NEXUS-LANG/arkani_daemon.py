import subprocess
import time
import requests
import json
import os
from datetime import datetime

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
LOG_PATH = os.path.expanduser("~/NEXUS/NEXUS-LANG/daemon_log.txt")

def log(mensaje):
    hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    linea = f"[{hora}] {mensaje}"
    print(linea)
    with open(LOG_PATH, "a") as f:
        f.write(linea + "\n")

def mantener_ollama_caliente():
    try:
        requests.post(OLLAMA_URL, json={
            "model": "tinyllama",
            "prompt": "di solo: listo",
            "stream": False,
            "options": {"num_predict": 5}
        }, timeout=60)
        log("✅ Ollama caliente")
    except Exception as e:
        log(f"⚠️ Error: {e}")

def main():
    log("🔴 Daemon Arkani iniciando...")
    while True:
        mantener_ollama_caliente()
        time.sleep(300)  # cada 5 minutos

if __name__ == "__main__":
    main()
