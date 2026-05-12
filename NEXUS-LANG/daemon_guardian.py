import time
import requests
import sys
import subprocess
import os
from datetime import datetime

# ============================================
# DAEMON GUARDIAN v2.0
# Mantiene Ollama vivo y registra logs
# Constructor: Medico Radiologo, Xalapa
# ============================================

LOG_PATH     = os.path.expanduser("~/NEXUS/NEXUS-LANG/daemon_guardian.log")
OLLAMA_URL   = "http://127.0.0.1:11434/api/tags"
CHECK_EVERY  = 30   # segundos entre checks
MAX_REINTENTOS = 3  # intentos antes de reiniciar Ollama


def log(mensaje: str):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    linea = f"[{ts}] {mensaje}"
    print(linea)
    sys.stdout.flush()
    # Guardar en archivo
    with open(LOG_PATH, 'a') as f:
        f.write(linea + "\n")


def check_ollama() -> bool:
    try:
        r = requests.get(OLLAMA_URL, timeout=5,
                        proxies={'http': None, 'https': None})
        return r.status_code == 200
    except requests.exceptions.RequestException:
        return False


def reiniciar_ollama():
    log("Intentando reiniciar Ollama via systemctl...")
    try:
        resultado = subprocess.run(
            ["sudo", "systemctl", "restart", "ollama"],
            capture_output=True, text=True, timeout=30
        )
        if resultado.returncode == 0:
            log("Ollama reiniciado exitosamente.")
            time.sleep(10)  # esperar que arranque
            return True
        else:
            log(f"Error al reiniciar: {resultado.stderr[:100]}")
            return False
    except Exception as e:
        log(f"No se pudo reiniciar Ollama: {e}")
        return False


def main():
    log("=" * 50)
    log("DAEMON GUARDIAN v2.0 - INICIADO")
    log(f"Monitoreando Ollama cada {CHECK_EVERY}s")
    log(f"Logs en: {LOG_PATH}")
    log("=" * 50)

    fallos_consecutivos = 0

    while True:
        try:
            if check_ollama():
                fallos_consecutivos = 0
                log("Nucleo conectado. Ollama OK.")
            else:
                fallos_consecutivos += 1
                log(f"Sin conexion al nucleo. Fallo {fallos_consecutivos}/{MAX_REINTENTOS}")

                if fallos_consecutivos >= MAX_REINTENTOS:
                    log("Demasiados fallos. Reiniciando Ollama...")
                    if reiniciar_ollama():
                        fallos_consecutivos = 0
                    else:
                        log("No se pudo recuperar Ollama. Revisa manualmente.")

            time.sleep(CHECK_EVERY)

        except KeyboardInterrupt:
            log("Daemon detenido por el usuario.")
            break
        except Exception as e:
            log(f"Error inesperado en daemon: {e}")
            time.sleep(CHECK_EVERY)


if __name__ == "__main__":
    main()
