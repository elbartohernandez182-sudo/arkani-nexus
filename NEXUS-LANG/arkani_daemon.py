#!/usr/bin/env python3
"""
arkani_daemon.py — Modo Nocturno Automatico
============================================
Protocolo Wardenclyffe — Auto-expansion del cerebro fractal

FLUJO NOCTURNO (23:00 - 06:00):
  1. Detecta hora nocturna
  2. Pausa arkani_web.py suavemente
  3. Digiere archivos en memoria_permanente/
  4. Expande hipocampo con nuevas neuronas
  5. Entrena arkani-fractal con dataset actualizado
  6. Genera CONTEXTO_CLAUDE.md (resumen para siguiente sesion)
  7. Reactiva arkani_web.py
  8. Duerme hasta la siguiente noche

Uso:
  python3 arkani_daemon.py          # modo manual (corre ahora)
  python3 arkani_daemon.py --watch  # modo vigilante (corre en loop)
  python3 arkani_daemon.py --status # ver estado del daemon

Instalar como tarea automatica:
  crontab -e
  0 23 * * * /usr/bin/python3 /home/arkani/NEXUS/NEXUS-LANG/arkani_daemon.py >> /home/arkani/NEXUS/logs/daemon.log 2>&1
"""

import os
import sys
import json
import time
import signal
import subprocess
import threading
import datetime
from pathlib import Path

# ── Rutas ─────────────────────────────────────────────────────────────────────
NEXUS_DIR        = Path.home() / "NEXUS"
NEXUS_LANG       = NEXUS_DIR / "NEXUS-LANG"
LOGS_DIR         = NEXUS_DIR / "logs"
MEMORIA_PERM     = NEXUS_DIR / "memoria_permanente"
PAPELERA_DIR     = NEXUS_DIR / "papelera"
DATASET_PATH     = NEXUS_LANG / "arkani_fractal_dataset_v2.json"
HIPOCAMPO_PATH   = NEXUS_LANG / "hipocampo.bin"
CONTEXTO_PATH    = NEXUS_LANG / "CONTEXTO_CLAUDE.md"
ARRANCAR_SCRIPT  = NEXUS_DIR / "arrancar_arkani.sh"
DIGESTOR_PATH    = NEXUS_LANG / "fractal_motor" / "digestion_fractal.py"
ENTRENAMIENTO_PY = NEXUS_LANG / "fractal_motor" / "entrenamiento.py"
DAEMON_STATE     = NEXUS_DIR / "daemon_state.json"

# ── Configuracion ─────────────────────────────────────────────────────────────
HORA_INICIO  = 23   # 11pm
HORA_FIN     = 6    # 6am
MAX_ARCHIVOS_POR_NOCHE = 10  # para no saturar CPU

LOGS_DIR.mkdir(parents=True, exist_ok=True)


def log(msg: str):
    ts  = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    txt = f"[{ts}] {msg}"
    print(txt, flush=True)
    with open(LOGS_DIR / "daemon.log", "a") as f:
        f.write(txt + "\n")


def es_horario_nocturno() -> bool:
    hora = datetime.datetime.now().hour
    return hora >= HORA_INICIO or hora < HORA_FIN


def cargar_estado() -> dict:
    if DAEMON_STATE.exists():
        try:
            with open(DAEMON_STATE) as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "ultima_ejecucion": None,
        "total_digestiones": 0,
        "total_neuronas_agregadas": 0,
        "total_entrenamientos": 0,
        "archivos_procesados": []
    }


def guardar_estado(estado: dict):
    with open(DAEMON_STATE, 'w') as f:
        json.dump(estado, f, indent=2, ensure_ascii=False)


# ══════════════════════════════════════════════
# TAREAS NOCTURNAS
# ══════════════════════════════════════════════

def tarea_pausar_web() -> bool:
    """Pausa arkani_web.py suavemente."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "arkani_web.py"],
            capture_output=True, text=True
        )
        if result.stdout.strip():
            subprocess.run(["pkill", "-f", "arkani_web.py"])
            time.sleep(3)
            log("🌙 Web pausada para modo nocturno")
            return True
        log("ℹ️  Web ya estaba inactiva")
        return True
    except Exception as e:
        log(f"⚠️  Error pausando web: {e}")
        return False


def tarea_digerir_archivos(estado: dict) -> int:
    """Digiere archivos nuevos en memoria_permanente/ que no han sido procesados."""
    if not DIGESTOR_PATH.exists():
        log("⚠️  digestion_fractal.py no encontrado")
        return 0

    MEMORIA_PERM.mkdir(parents=True, exist_ok=True)
    # Ordenar por fecha de modificacion DESCENDENTE (mas recientes primero)
    archivos = sorted(MEMORIA_PERM.iterdir(),
                      key=lambda p: p.stat().st_mtime if p.exists() else 0,
                      reverse=True) if MEMORIA_PERM.exists() else []
    archivos_texto = [
        a for a in archivos
        if a.suffix.lower() in ('.txt', '.md', '.py', '.json')
        and str(a) not in estado.get("archivos_procesados", [])
        and 'manual_' not in a.name.lower()  # manuales se procesan aparte, siempre
    ]
    # Los manuales (instrucciones base) van primero siempre, sin importar fecha
    manuales = [
        a for a in archivos
        if a.suffix.lower() == '.txt' and 'manual_' in a.name.lower()
        and str(a) not in estado.get("archivos_procesados", [])
    ]
    archivos_texto = manuales + archivos_texto

    if not archivos_texto:
        log("ℹ️  Sin archivos nuevos para digerir")
        return 0

    log(f"📚 Archivos a digerir: {len(archivos_texto)}")
    total = 0

    for i, archivo in enumerate(archivos_texto[:MAX_ARCHIVOS_POR_NOCHE]):
        log(f"   SPAWN → {archivo.name}")
        if i > 0 and i % 2 == 0:
            log("   🔄 Reiniciando Ollama...")
            import subprocess as sp
            sp.run(["sudo", "systemctl", "restart", "ollama"], capture_output=True)
            import time as t
            t.sleep(15)
        try:
            result = subprocess.run(
                [sys.executable, str(DIGESTOR_PATH),
                 "--libro", str(archivo),
                 "--silencioso"],
                capture_output=True, text=True,
                timeout=1200  # 20 min max por archivo (subido por archivos grandes)
            )
            if result.returncode == 0:
                # Extraer numero de ejemplos del output
                for linea in result.stdout.split('\n'):
                    if 'ejemplos nuevos' in linea.lower():
                        try:
                            n = int(''.join(filter(str.isdigit, linea.split('—')[1])))
                            total += n
                        except Exception:
                            total += 1
                estado.setdefault("archivos_procesados", []).append(str(archivo))
                log(f"   ✅ {archivo.name} digerido")
            else:
                log(f"   ⚠️  Error en {archivo.name}: {result.stderr[:100]}")
        except subprocess.TimeoutExpired:
            log(f"   ⚠️  Timeout en {archivo.name}")
        except Exception as e:
            log(f"   ❌ {archivo.name}: {e}")

    estado["total_digestiones"] = estado.get("total_digestiones", 0) + total
    return total


def tarea_expandir_hipocampo(nuevos_ejemplos: int) -> int:
    """
    Agrega nuevas neuronas al hipocampo basado en cuanto aprendio esta noche.
    Usa arkani_engine directamente.
    """
    if nuevos_ejemplos == 0:
        return 0

    try:
        sys.path.insert(0, str(NEXUS_LANG))
        from arkani_engine import FractalInstruction, FractalOp, Hipocampo

        hipocampo = Hipocampo()
        antes     = len(hipocampo.instructions)

        # Agregar neurona EVOLVE por cada 5 ejemplos nuevos
        nuevas_neuronas = max(1, nuevos_ejemplos // 5)
        for i in range(nuevas_neuronas):
            inst = FractalInstruction(
                FractalOp.EVOLVE,
                scale=min(antes + i + 1, 31),
                fold_target="self"
            )
            hipocampo.agregar(inst)

        # Agregar neurona SPAWN (nuevo conocimiento listo para expandirse)
        spawn = FractalInstruction(FractalOp.SPAWN, scale=5, link_to=0)
        hipocampo.agregar(spawn)

        agregadas = len(hipocampo.instructions) - antes
        log(f"🧬 Hipocampo: +{agregadas} neuronas "
            f"({antes} → {len(hipocampo.instructions)})")
        return agregadas

    except Exception as e:
        log(f"⚠️  Error expandiendo hipocampo: {e}")
        return 0


def tarea_entrenar(estado: dict) -> bool:
    """Corre entrenamiento.py si existe y hay dataset suficiente."""
    if not ENTRENAMIENTO_PY.exists():
        log("ℹ️  entrenamiento.py no encontrado — saltando")
        return False

    # Verificar que hay suficientes ejemplos nuevos
    try:
        with open(DATASET_PATH) as f:
            dataset = json.load(f)
        if len(dataset) < 50:
            log(f"ℹ️  Dataset pequeño ({len(dataset)} ejemplos) — esperando más")
            return False
    except Exception:
        return False

    log(f"🎯 Iniciando entrenamiento nocturno ({len(dataset)} ejemplos)...")
    try:
        result = subprocess.run(
            [sys.executable, str(ENTRENAMIENTO_PY),
             "--epochs", "1"],   # solo 1 epoca por noche en CPU
            capture_output=True, text=True,
            timeout=7200  # max 2 horas
        )
        if result.returncode == 0:
            estado["total_entrenamientos"] = \
                estado.get("total_entrenamientos", 0) + 1
            log("✅ Entrenamiento completado")
            return True
        else:
            log(f"⚠️  Entrenamiento con errores: {result.stderr[:200]}")
            return False
    except subprocess.TimeoutExpired:
        log("⚠️  Entrenamiento cancelado por timeout (2h)")
        return False
    except Exception as e:
        log(f"⚠️  Error en entrenamiento: {e}")
        return False


def tarea_vaciar_papelera():
    """Limpia archivos de papelera vencidos (>30 dias)."""
    if not PAPELERA_DIR.exists():
        return

    ahora   = datetime.datetime.now()
    limite  = ahora - datetime.timedelta(days=30)
    borrados = 0

    for archivo in PAPELERA_DIR.iterdir():
        try:
            mtime = datetime.datetime.fromtimestamp(archivo.stat().st_mtime)
            if mtime < limite:
                archivo.unlink()
                borrados += 1
        except Exception:
            pass

    if borrados:
        log(f"🗑️  Papelera: {borrados} archivos borrados")


def tarea_generar_contexto(estado: dict, neuronas_agregadas: int,
                            ejemplos_digeridos: int, entrenado: bool):
    """
    Genera CONTEXTO_CLAUDE.md — resumen de sesion para el siguiente chat.
    Arkani escribe su propio estado para que Claude lo lea al inicio.
    """
    try:
        # Leer memoria
        mem_path = NEXUS_LANG / "memoria_arkani.json"
        memoria  = {}
        if mem_path.exists():
            with open(mem_path) as f:
                memoria = json.load(f)

        # Contar dataset
        dataset_total = 0
        if DATASET_PATH.exists():
            try:
                with open(DATASET_PATH) as f:
                    dataset_total = len(json.load(f))
            except Exception:
                pass

        # Contar hipocampo
        hipocampo_total = 0
        if HIPOCAMPO_PATH.exists():
            hipocampo_total = os.path.getsize(HIPOCAMPO_PATH) // 16

        ahora = datetime.datetime.now()

        contexto = f"""# CONTEXTO_CLAUDE.md — Estado de ARKANI NEXUS
Generado automaticamente: {ahora.strftime('%Y-%m-%d %H:%M')}

## Estado del Sistema
- Modelo principal  : arkani:latest (qwen2.5:7b + Protocolo Wardenclyffe)
- Motor fractal     : FractalVM ONLINE
- Hipocampo         : {hipocampo_total} instrucciones
- Dataset fractal   : {dataset_total} ejemplos
- Conversaciones    : {len(memoria.get('conversaciones', []))}
- Aprendizajes      : {len(memoria.get('conocimiento_arkani', {}).get('hechos', {}) if False else {})}
- Evoluciones       : {len(memoria.get('evoluciones', []))}

## Sesion Nocturna — {ahora.strftime('%Y-%m-%d')}
- Ejemplos digeridos   : {ejemplos_digeridos}
- Neuronas agregadas   : {neuronas_agregadas}
- Entrenamiento        : {'✅ completado' if entrenado else '⏭️ saltado'}
- Total digestiones    : {estado.get('total_digestiones', 0)}
- Total entrenamientos : {estado.get('total_entrenamientos', 0)}

## GitHub
- Repo: https://github.com/elbartohernandez182-sudo/arkani-nexus
- Branch: master

## Proximas Prioridades
1. Servidor GPU (Radeon 12GB) — LLaVA para radiografias
2. Instalador Windows para primos
3. M2M entre dos PCs reales
4. Expandir dataset fractal (target: 1000 ejemplos)

## Componentes Activos
- arkani_web.py       : Flask + SocketIO, puerto 8081
- arkani_engine.py    : Motor unificado v2.0 con FractalVM
- nexus_fractal_vm.py : VM fractal (ejecutar_todo, ejecutar_una, estado)
- digestion_fractal.py: Tuberia de digestion semantica
- arkani_daemon.py    : Modo nocturno automatico

## Comandos Utiles
```
vm: estado              # estado de FractalVM
vm: ejecutar            # ejecutar todas las instrucciones
vm: listar              # listar neuronas del hipocampo
evoluciona: [desc]      # auto-evolucion con nuevo modulo
autoprograma: [tarea]   # agente ReAct autonomo
aprender: [archivo]     # mover archivo a memoria permanente
```

## Notas del Daemon
{estado.get('ultima_ejecucion', 'Primera ejecucion')}
Archivos procesados: {len(estado.get('archivos_procesados', []))}
"""

        with open(CONTEXTO_PATH, 'w') as f:
            f.write(contexto)
        log(f"📋 CONTEXTO_CLAUDE.md actualizado ({len(contexto)} chars)")

    except Exception as e:
        log(f"⚠️  Error generando contexto: {e}")


def tarea_reactivar_web():
    """Reactiva arkani_web.py."""
    try:
        if ARRANCAR_SCRIPT.exists():
            subprocess.Popen(
                ["bash", str(ARRANCAR_SCRIPT)],
                cwd=str(NEXUS_DIR),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            log("🌅 Web reactivada — arkani_web.py arrancando")
        else:
            # Arranque directo
            subprocess.Popen(
                [sys.executable,
                 str(NEXUS_LANG / "arkani_web.py")],
                cwd=str(NEXUS_LANG),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            log("🌅 Web reactivada directamente")
    except Exception as e:
        log(f"⚠️  Error reactivando web: {e}")


# ══════════════════════════════════════════════
# CICLO PRINCIPAL
# ══════════════════════════════════════════════

def ejecutar_ciclo_nocturno():
    """Ejecuta el ciclo completo de tareas nocturnas."""
    log("=" * 55)
    log("🌙 ARKANI DAEMON — CICLO NOCTURNO INICIADO")
    log("=" * 55)

    estado = cargar_estado()
    t0     = time.time()

    # 1. Pausar web
    tarea_pausar_web()
    time.sleep(5)

    # 2. Digerir archivos nuevos
    log("\n📚 FASE 1: Digestión de archivos")
    ejemplos = tarea_digerir_archivos(estado)

    # 3. Expandir hipocampo
    log("\n🧬 FASE 2: Expansión del hipocampo")
    neuronas = tarea_expandir_hipocampo(ejemplos)
    estado["total_neuronas_agregadas"] = \
        estado.get("total_neuronas_agregadas", 0) + neuronas

    # 4. Entrenar
    log("\n🎯 FASE 3: Entrenamiento nocturno")
    entrenado = tarea_entrenar(estado)

    # 5. Limpiar papelera
    log("\n🗑️  FASE 4: Limpieza de papelera")
    tarea_vaciar_papelera()

    # 6. Generar contexto
    log("\n📋 FASE 5: Generando CONTEXTO_CLAUDE.md")
    tarea_generar_contexto(estado, neuronas, ejemplos, entrenado)

    # 7. Actualizar estado
    estado["ultima_ejecucion"] = datetime.datetime.now().isoformat()
    guardar_estado(estado)

    elapsed = time.time() - t0
    log(f"\n{'='*55}")
    log(f"✅ CICLO COMPLETADO en {elapsed/60:.1f} minutos")
    log(f"   Ejemplos digeridos : {ejemplos}")
    log(f"   Neuronas agregadas : {neuronas}")
    log(f"   Entrenamiento      : {'SI' if entrenado else 'NO'}")
    log(f"{'='*55}\n")

    # 8. Reactivar web
    time.sleep(5)
    tarea_reactivar_web()


def modo_vigilante():
    """
    Loop que espera la hora nocturna y ejecuta el ciclo automaticamente.
    Corre indefinidamente — ideal para dejarlo como proceso en background.
    """
    log("👁️  ARKANI DAEMON en modo vigilante")
    log(f"   Horario nocturno: {HORA_INICIO}:00 — {HORA_FIN}:00")
    log("   Presiona Ctrl+C para detener\n")

    ya_ejecuto_hoy = False

    while True:
        ahora = datetime.datetime.now()

        if es_horario_nocturno():
            if not ya_ejecuto_hoy:
                ejecutar_ciclo_nocturno()
                ya_ejecuto_hoy = True
        else:
            # Es de dia — resetear flag
            if ya_ejecuto_hoy:
                log(f"🌅 Nuevo dia — esperando siguiente noche")
                ya_ejecuto_hoy = False

        # Revisar cada 30 minutos
        time.sleep(1800)


def mostrar_estado():
    """Muestra el estado actual del daemon."""
    estado = cargar_estado()
    print("\n" + "="*55)
    print("  ARKANI DAEMON — ESTADO")
    print("="*55)
    print(f"  Ultima ejecucion    : {estado.get('ultima_ejecucion', 'nunca')}")
    print(f"  Total digestiones   : {estado.get('total_digestiones', 0)}")
    print(f"  Neuronas agregadas  : {estado.get('total_neuronas_agregadas', 0)}")
    print(f"  Total entrenamientos: {estado.get('total_entrenamientos', 0)}")
    print(f"  Archivos procesados : {len(estado.get('archivos_procesados', []))}")

    # Contar archivos pendientes
    pendientes = 0
    if MEMORIA_PERM.exists():
        procesados = set(estado.get("archivos_procesados", []))
        pendientes = sum(
            1 for a in MEMORIA_PERM.iterdir()
            if a.suffix.lower() in ('.txt', '.md', '.py', '.json')
            and str(a) not in procesados
        )
    print(f"  Archivos pendientes : {pendientes}")
    print(f"  Horario nocturno    : {HORA_INICIO}:00 — {HORA_FIN}:00")
    print(f"  Es horario nocturno : {'SI' if es_horario_nocturno() else 'NO'}")
    print("="*55 + "\n")


# ══════════════════════════════════════════════
# INTEGRACION CON ARKANI_ENGINE
# ══════════════════════════════════════════════

def iniciar_daemon_background():
    """
    Inicia el daemon en un hilo background desde arkani_engine.py o arkani_web.py.

    Uso en arkani_web.py:
      from arkani_daemon import iniciar_daemon_background
      iniciar_daemon_background()
    """
    def _run():
        try:
            modo_vigilante()
        except Exception as e:
            log(f"Error en daemon background: {e}")

    t = threading.Thread(target=_run, daemon=True, name="ArkaniDaemon")
    t.start()
    log("🌙 Daemon nocturno iniciado en background")
    return t


# ══════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="ARKANI Daemon — Auto-expansion nocturna del cerebro fractal"
    )
    parser.add_argument('--watch',  action='store_true',
                        help="Modo vigilante: espera horario nocturno y ejecuta automaticamente")
    parser.add_argument('--status', action='store_true',
                        help="Mostrar estado del daemon")
    parser.add_argument('--forzar', action='store_true',
                        help="Forzar ciclo nocturno ahora (sin esperar hora)")
    args = parser.parse_args()

    if args.status:
        mostrar_estado()
    elif args.watch:
        modo_vigilante()
    elif args.forzar:
        log("⚡ Ciclo forzado manualmente")
        ejecutar_ciclo_nocturno()
    else:
        # Por defecto: ejecutar ciclo ahora
        ejecutar_ciclo_nocturno()
