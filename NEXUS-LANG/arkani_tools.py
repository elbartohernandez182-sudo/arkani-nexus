import os
import subprocess
import requests
import json
import datetime
from pathlib import Path

# ============================================
# ARKANI TOOLS v1.0
# Herramientas seguras para el agente
# Constructor: Medico Radiologo, Xalapa
# ============================================

NEXUS_DIR  = os.path.expanduser("~/NEXUS/")
LOG_PATH   = os.path.expanduser("~/NEXUS/NEXUS-LANG/agent_tools.log")
SCRIPTS_DIR = os.path.expanduser("~/NEXUS/NEXUS-LANG/scripts_arkani/")

# Directorios permitidos para escritura
RUTAS_PERMITIDAS = [
    os.path.expanduser("~/NEXUS/NEXUS-LANG/scripts_arkani/"),
    os.path.expanduser("~/NEXUS/NEXUS-LANG/"),
    os.path.expanduser("~/NEXUS/data/"),
    os.path.expanduser("~/NEXUS/NEXUS-LANG/autogen/"),
]

# Comandos peligrosos bloqueados
COMANDOS_BLOQUEADOS = [
    "rm -rf", "mkfs", "dd if=", "chmod 777",
    "sudo rm", "> /dev/", "format", "fdisk",
    "shutdown", "reboot", "halt", "init 0"
]


def log_accion(herramienta: str, entrada: str, resultado: str):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    linea = f"[{ts}] {herramienta}: {entrada[:50]} -> {resultado[:100]}\n"
    with open(LOG_PATH, 'a') as f:
        f.write(linea)


def es_ruta_permitida(ruta: str) -> bool:
    ruta_abs = os.path.abspath(os.path.expanduser(ruta))
    for permitida in RUTAS_PERMITIDAS:
        if ruta_abs.startswith(os.path.abspath(permitida)):
            return True
    return False


def es_comando_seguro(comando: str) -> bool:
    comando_lower = comando.lower()
    for bloqueado in COMANDOS_BLOQUEADOS:
        if bloqueado in comando_lower:
            return False
    return True


# ── HERRAMIENTAS ──────────────────────────────────────────────

def leer_archivo(ruta: str) -> str:
    """Lee el contenido de un archivo del NEXUS."""
    try:
        ruta_completa = os.path.expanduser(ruta)
        if not os.path.exists(ruta_completa):
            return f"ERROR: No existe {ruta}"
        with open(ruta_completa, 'r', errors='ignore') as f:
            contenido = f.read()
        resultado = contenido[:2000]  # max 2000 chars
        log_accion("leer_archivo", ruta, f"OK ({len(contenido)} chars)")
        return resultado
    except Exception as e:
        return f"ERROR al leer: {e}"


def escribir_archivo(ruta: str, contenido: str) -> str:
    """Escribe un archivo en rutas permitidas del NEXUS."""
    try:
        if not es_ruta_permitida(ruta):
            return f"ERROR: Ruta no permitida: {ruta}"
        ruta_completa = os.path.expanduser(ruta)
        os.makedirs(os.path.dirname(ruta_completa), exist_ok=True)
        with open(ruta_completa, 'w') as f:
            f.write(contenido)
        log_accion("escribir_archivo", ruta, "OK")
        return f"OK: Archivo escrito en {ruta}"
    except Exception as e:
        return f"ERROR al escribir: {e}"


def ejecutar_bash(comando: str) -> str:
    """Ejecuta un comando bash seguro y retorna la salida."""
    try:
        if not es_comando_seguro(comando):
            return f"ERROR: Comando bloqueado por seguridad: {comando}"
        resultado = subprocess.run(
            comando, shell=True,
            capture_output=True, text=True, timeout=30
        )
        salida = resultado.stdout[:1000] if resultado.stdout else ""
        error  = resultado.stderr[:500]  if resultado.stderr else ""
        out = salida if salida else error if error else "(sin salida)"
        log_accion("ejecutar_bash", comando, out[:100])
        return out
    except subprocess.TimeoutExpired:
        return "ERROR: Comando tardó más de 30s"
    except Exception as e:
        return f"ERROR: {e}"


def probar_script(ruta: str) -> str:
    """Ejecuta un script Python y reporta si funciona."""
    try:
        ruta_completa = os.path.expanduser(ruta)
        if not os.path.exists(ruta_completa):
            return f"ERROR: No existe {ruta}"
        resultado = subprocess.run(
            ["python3", "-c", f"import py_compile; py_compile.compile('{ruta_completa}')"],
            capture_output=True, text=True, timeout=10
        )
        if resultado.returncode == 0:
            log_accion("probar_script", ruta, "Sintaxis OK")
            return f"OK: Sintaxis correcta en {ruta}"
        else:
            error = resultado.stderr[:500]
            log_accion("probar_script", ruta, f"ERROR: {error}")
            return f"ERROR de sintaxis: {error}"
    except Exception as e:
        return f"ERROR: {e}"


def listar_archivos(directorio: str) -> str:
    """Lista archivos en un directorio del NEXUS."""
    try:
        ruta = os.path.expanduser(directorio)
        if not os.path.exists(ruta):
            return f"ERROR: No existe {directorio}"
        archivos = []
        for f in os.listdir(ruta):
            ruta_f = os.path.join(ruta, f)
            tipo = "DIR" if os.path.isdir(ruta_f) else "FILE"
            archivos.append(f"{tipo}: {f}")
        resultado = "\n".join(archivos[:30])
        log_accion("listar_archivos", directorio, f"{len(archivos)} items")
        return resultado
    except Exception as e:
        return f"ERROR: {e}"


def buscar_en_nexus(termino: str = "*.py") -> str:
    """Busca un término en archivos del NEXUS."""
    try:
        resultado = subprocess.run(
            ["grep", "-r", "--include=*.py", "--include=*.txt",
             "--include=*.json", "-l", termino, NEXUS_DIR],
            capture_output=True, text=True, timeout=15
        )
        archivos = resultado.stdout.strip().split('\n')
        archivos = [a for a in archivos if a]
        if not archivos:
            return f"No encontrado: '{termino}'"
        log_accion("buscar_en_nexus", termino, f"{len(archivos)} archivos")
        return "\n".join(archivos[:10])
    except Exception as e:
        return f"ERROR: {e}"


def guardar_reporte(titulo: str, contenido: str) -> str:
    """Guarda un reporte de actividad del agente."""
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    ruta = os.path.expanduser(
        f"~/NEXUS/NEXUS-LANG/scripts_arkani/reporte_{ts}.txt"
    )
    texto = f"REPORTE: {titulo}\n"
    texto += f"Fecha: {datetime.datetime.now().isoformat()}\n"
    texto += "=" * 50 + "\n"
    texto += contenido
    try:
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        with open(ruta, 'w') as f:
            f.write(texto)
        return f"OK: Reporte guardado en {ruta}"
    except Exception as e:
        return f"ERROR: {e}"


# Registro de herramientas disponibles
HERRAMIENTAS = {
    "leer_archivo": {
        "fn": leer_archivo,
        "desc": "Lee el contenido de un archivo. Param: ruta"
    },
    "escribir_archivo": {
        "fn": escribir_archivo,
        "desc": "Escribe contenido en un archivo. Params: ruta, contenido"
    },
    "ejecutar_bash": {
        "fn": ejecutar_bash,
        "desc": "Ejecuta comando bash seguro. Param: comando"
    },
    "probar_script": {
        "fn": probar_script,
        "desc": "Verifica sintaxis de un script Python. Param: ruta"
    },
    "listar_archivos": {
        "fn": listar_archivos,
        "desc": "Lista archivos en un directorio. Param: directorio"
    },
    "buscar_en_nexus": {
        "fn": buscar_en_nexus,
        "desc": "Busca un término en archivos del NEXUS. Param: termino"
    },
    "guardar_reporte": {
        "fn": guardar_reporte,
        "desc": "Guarda reporte de actividad. Params: titulo, contenido"
    },
}


if __name__ == "__main__":
    print("ARKANI TOOLS v1.0 - Test")
    print(listar_archivos("~/NEXUS/NEXUS-LANG/"))

