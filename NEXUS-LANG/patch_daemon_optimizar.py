#!/usr/bin/env python3
"""
patch_daemon_optimizar.py
Ajusta el daemon para procesar archivos mas eficientemente:
  1. Timeout por archivo: 600s -> 1200s (20 min)
  2. Fragmentos mas grandes: 1500 -> 3000 chars (menos llamadas Ollama)
  3. Prioriza archivos MAS RECIENTES primero (radiologia/IA antes que decoradores viejos)
  4. Reduce pausa entre fragmentos: 1.0s -> 0.3s
"""

import os
import ast

DAEMON = "/home/arkani/NEXUS/NEXUS-LANG/arkani_daemon.py"
DIGESTOR = "/home/arkani/NEXUS/NEXUS-LANG/fractal_motor/digestion_fractal.py"

# ── 1. Patch arkani_daemon.py ──────────────────────────────────────────────
with open(DAEMON, 'r') as f:
    code = f.read()

# Aumentar timeout del subprocess por archivo
code = code.replace(
    "timeout=600  # 10 min max por archivo",
    "timeout=1200  # 20 min max por archivo (subido por archivos grandes)"
)

# Priorizar archivos mas recientes primero (orden descendente por fecha)
OLD_SORT = '''    MEMORIA_PERM.mkdir(parents=True, exist_ok=True)
    archivos = sorted(MEMORIA_PERM.iterdir()) if MEMORIA_PERM.exists() else []
    archivos_texto = [
        a for a in archivos
        if a.suffix.lower() in ('.txt', '.md', '.py', '.json')
        and str(a) not in estado.get("archivos_procesados", [])
    ]'''

NEW_SORT = '''    MEMORIA_PERM.mkdir(parents=True, exist_ok=True)
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
    archivos_texto = manuales + archivos_texto'''

if OLD_SORT in code:
    code = code.replace(OLD_SORT, NEW_SORT)
    print("✅ Priorizacion de archivos actualizada (recientes + manuales primero)")
else:
    print("⚠️  Bloque de ordenamiento no encontrado exacto")

with open(DAEMON, 'w') as f:
    f.write(code)

try:
    ast.parse(code)
    print("✅ arkani_daemon.py — sintaxis OK")
except SyntaxError as e:
    print(f"❌ Error linea {e.lineno}: {e.msg}")

# ── 2. Patch digestion_fractal.py ──────────────────────────────────────────
with open(DIGESTOR, 'r') as f:
    code2 = f.read()

code2 = code2.replace(
    "MAX_CHARS_FRAGMENTO = 1500   # chars por bloque conceptual",
    "MAX_CHARS_FRAGMENTO = 3000   # chars por bloque (subido: menos llamadas Ollama)"
)
code2 = code2.replace(
    "PAUSA_ENTRE_BLOQUES = 1.0    # segundos entre llamadas a Ollama",
    "PAUSA_ENTRE_BLOQUES = 0.3    # segundos entre llamadas (reducido)"
)
code2 = code2.replace(
    "TIMEOUT_OLLAMA      = 120    # segundos por fragmento",
    "TIMEOUT_OLLAMA      = 150    # segundos por fragmento (un poco mas margen)"
)

with open(DIGESTOR, 'w') as f:
    f.write(code2)

try:
    ast.parse(code2)
    print("✅ digestion_fractal.py — sintaxis OK")
    print("   MAX_CHARS_FRAGMENTO: 1500 -> 3000 (menos fragmentos por archivo)")
    print("   PAUSA_ENTRE_BLOQUES: 1.0 -> 0.3")
except SyntaxError as e:
    print(f"❌ Error linea {e.lineno}: {e.msg}")

print()
print("=" * 55)
print("RESUMEN DE OPTIMIZACIONES:")
print("  - Timeout por archivo: 600s -> 1200s")
print("  - Fragmentos mas grandes: menos llamadas a Ollama")
print("  - Prioridad: manuales + archivos RECIENTES primero")
print("  - Pausa reducida entre fragmentos")
print("=" * 55)
