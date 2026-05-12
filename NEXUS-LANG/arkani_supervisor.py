import os
import json
import time
import datetime
import requests
from arkani_agent import correr_agente

# ============================================
# ARKANI SUPERVISOR v1.1
# Corre de noche, ejecuta tareas, genera reporte
# Tu lo revisas en la manana por AnyDesk
# Constructor: Medico Radiologo, Xalapa
# ============================================

REPORTE_PATH = os.path.expanduser(
    "~/NEXUS/NEXUS-LANG/scripts_arkani/reporte_nocturno.txt"
)
MEJORA_PATH = os.path.expanduser(
    "~/NEXUS/NEXUS-LANG/scripts_arkani/mejora_propuesta.txt"
)
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"

# ── TAREAS NOCTURNAS ──────────────────────────────────────────

TAREAS_NOCTURNAS = [
    {
        "nombre": "Verificar servicios",
        "objetivo": (
            "Ejecuta estos 2 comandos bash y reporta el resultado:\n"
            "1. 'systemctl status ollama' - verifica que Ollama este activo\n"
            "2. 'systemctl status arkani-daemon' - verifica que el daemon guardian este activo\n"
            "El daemon guardian es el servicio que vigila que Ollama no se caiga y lo reinicia si falla.\n"
            "Tambien verifica que el modelo gemma3:4b este disponible con: 'ollama list'\n"
            "Reporta si todo esta OK o si hay algun problema."
        ),
        "prioridad": 1
    },
    {
        "nombre": "Auditoria de scripts",
        "objetivo": (
            "Lista los archivos Python en ~/NEXUS/NEXUS-LANG/ "
            "y verifica la sintaxis de estos archivos clave: "
            "arkani_core.py, arkani_agent.py, arkani_tools.py, nexus_bridge.py, daemon_guardian.py. "
            "Reporta cuales tienen errores de sintaxis y cuales estan OK."
        ),
        "prioridad": 2
    },
    {
        "nombre": "Analizar memoria",
        "objetivo": (
            "Lee ~/NEXUS/NEXUS-LANG/memoria_arkani.json y reporta: "
            "cuantas conversaciones hay, cuantos pendientes, cuantos aprendizajes. "
            "Detecta si hay conversaciones con respuestas de error (que contengan 'Error' o '404'). "
            "Reporta el estado general de la memoria."
        ),
        "prioridad": 3
    },
    {
        "nombre": "Analizar logs del daemon",
        "objetivo": (
            "Lee ~/NEXUS/NEXUS-LANG/daemon_guardian.log "
            "y reporta: cuantas veces dijo 'Nucleo conectado', "
            "cuantas veces hubo error o reconexion, "
            "y si hay algun patron preocupante en las ultimas entradas."
        ),
        "prioridad": 4
    },
    {
        "nombre": "Propuesta de mejora de codigo",
        "objetivo": (
            "Lee ~/NEXUS/NEXUS-LANG/arkani_core.py completamente. "
            "Identifica UNA mejora especifica y concreta que pueda hacerse. "
            "Por ejemplo: una funcion que se puede optimizar, un bug potencial, "
            "o una funcionalidad que falta. "
            "Escribe la mejora propuesta en "
            "~/NEXUS/NEXUS-LANG/scripts_arkani/mejora_propuesta.txt "
            "con este formato exacto:\n"
            "PROBLEMA: [descripcion del problema]\n"
            "SOLUCION: [descripcion de la solucion]\n"
            "CODIGO: [el codigo Python de la mejora]\n"
            "RIESGO: [bajo/medio/alto]\n"
            "Guarda el archivo y reporta que mejora propones."
        ),
        "prioridad": 5
    },
]


def ollama_disponible() -> bool:
    try:
        r = requests.get(
            "http://127.0.0.1:11434/api/tags", timeout=5,
            proxies={'http': None, 'https': None}
        )
        return r.status_code == 200
    except Exception:
        return False


def esperar_ollama(max_espera: int = 120) -> bool:
    print("Verificando Ollama...")
    for i in range(max_espera // 10):
        if ollama_disponible():
            print("Ollama OK")
            return True
        print(f"Esperando Ollama... ({(i+1)*10}s)")
        time.sleep(10)
    return False


def generar_resumen_ejecutivo(resultados: list) -> str:
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    resumen  = "=" * 60 + "\n"
    resumen += "  REPORTE NOCTURNO ARKANI\n"
    resumen += f"  Fecha: {ts}\n"
    resumen += "=" * 60 + "\n\n"

    exitosas = sum(1 for r in resultados if r["estado"] == "OK")
    fallidas  = sum(1 for r in resultados if r["estado"] == "ERROR")

    resumen += f"RESUMEN EJECUTIVO:\n"
    resumen += f"  Tareas completadas : {exitosas}/{len(resultados)}\n"
    resumen += f"  Tareas con error   : {fallidas}/{len(resultados)}\n\n"

    for i, r in enumerate(resultados, 1):
        icono = "✅" if r["estado"] == "OK" else "❌"
        resumen += f"{icono} TAREA {i}: {r['nombre']}\n"
        resumen += f"   Duracion : {r['duracion']}s\n"
        resumen += f"   Resultado: {r['resultado'][:400]}\n"
        resumen += "-" * 50 + "\n\n"

    resumen += "\n" + "=" * 60 + "\n"
    resumen += "ACCIONES REQUERIDAS DEL CONSTRUCTOR:\n"
    resumen += "=" * 60 + "\n"
    resumen += "1. Revisa mejora_propuesta.txt en scripts_arkani/\n"
    resumen += "2. Si apruebas la mejora, aplícala manualmente o dile a Claude\n"
    resumen += "3. Si hay errores en servicios, reinicia manualmente\n"
    resumen += "4. Si hay conversaciones con errores en memoria, ejecuta /limpiar\n\n"
    resumen += "Arkani propone. Tu decides. Juntos mejoramos.\n"

    return resumen


def ejecutar_tarea(tarea: dict) -> dict:
    print(f"\n{'='*40}")
    print(f"Iniciando: {tarea['nombre']}")
    print(f"{'='*40}")

    inicio = time.time()
    estado = "OK"
    resultado = ""

    try:
        resultado = correr_agente(tarea["objetivo"], verbose=True)
    except Exception as e:
        resultado = f"ERROR: {e}"
        estado = "ERROR"

    duracion = int(time.time() - inicio)
    return {
        "nombre": tarea["nombre"],
        "estado": estado,
        "resultado": resultado,
        "duracion": duracion,
        "timestamp": datetime.datetime.now().isoformat()
    }


def main():
    print("\n" + "=" * 60)
    print("  ARKANI SUPERVISOR v1.1 - SESION NOCTURNA")
    print("=" * 60)
    print(f"  Inicio: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Tareas: {len(TAREAS_NOCTURNAS)}")
    print("=" * 60 + "\n")

    if not esperar_ollama():
        print("ERROR: Ollama no responde. Abortando.")
        return

    tareas_ordenadas = sorted(TAREAS_NOCTURNAS, key=lambda x: x["prioridad"])
    resultados = []

    for tarea in tareas_ordenadas:
        resultado = ejecutar_tarea(tarea)
        resultados.append(resultado)
        print(f"\nPausa 30s antes de siguiente tarea...")
        time.sleep(30)

    # Generar y guardar reporte
    print("\nGenerando reporte final...")
    resumen = generar_resumen_ejecutivo(resultados)
    os.makedirs(os.path.dirname(REPORTE_PATH), exist_ok=True)
    with open(REPORTE_PATH, 'w') as f:
        f.write(resumen)

    print(f"\nReporte guardado: {REPORTE_PATH}")
    print("\n" + "="*60)
    print(resumen[:800])
    print("\nSesion nocturna completada.")
    print("Revisa por AnyDesk manana.")


if __name__ == "__main__":
    main()
