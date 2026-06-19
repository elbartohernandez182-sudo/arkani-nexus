#!/usr/bin/env python3
"""
digestion_fractal.py — Tuberia de Digestion Semantica
======================================================
Protocolo Wardenclyffe — Expansion del IQ de ARKANI

Toma un libro o manual tecnico, lo fragmenta en bloques conceptuales
y usa arkani:latest (7B maestro) para traducir cada concepto al
lenguaje fractal nativo, inyectandolo en el dataset de entrenamiento.

OPERACIONES:
  SPAWN(fragmento)         -> extrae bloque del libro
  LINK(fragmento, 7B)      -> traduce al protocolo fractal
  FOLD(ejemplos, dataset)  -> inyecta en arkani_fractal_dataset_v2.json

Uso:
  python3 digestion_fractal.py --libro ~/NEXUS/manual.txt
  python3 digestion_fractal.py --libro ~/NEXUS/manual.txt --max-chars 2000
  python3 digestion_fractal.py --libro ~/NEXUS/manual.txt --desde 10
"""

import os
import sys
import json
import time
import argparse
import urllib.request
from pathlib import Path
from datetime import datetime

# ── Rutas ────────────────────────────────────────────────────────────────────
NEXUS_DIR    = Path.home() / "NEXUS"
DATASET_PATH = NEXUS_DIR / "NEXUS-LANG" / "arkani_fractal_dataset_v2.json"
OLLAMA_URL   = "http://localhost:11434/api/generate"
MODELO       = "arkani:latest"   # 7B maestro con Protocolo Wardenclyffe

# ── Configuracion ─────────────────────────────────────────────────────────────
MAX_CHARS_FRAGMENTO = 3000   # chars por bloque (subido: menos llamadas Ollama)
PAUSA_ENTRE_BLOQUES = 0.3    # segundos entre llamadas (reducido)
TIMEOUT_OLLAMA      = 150    # segundos por fragmento (un poco mas margen)


def leer_archivo(ruta: Path) -> str:
    """Lee txt, py, md. Para PDF usa pdftotext si esta disponible."""
    ext = ruta.suffix.lower()
    if ext == '.pdf':
        try:
            import subprocess
            r = subprocess.run(['pdftotext', str(ruta), '-'],
                               capture_output=True, text=True, timeout=30)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout
            print("  [WARN] PDF sin texto extraible, intenta convertir a .txt primero")
            return ""
        except Exception as e:
            print(f"  [WARN] pdftotext no disponible: {e}")
            return ""
    # txt, py, md, etc.
    try:
        with open(ruta, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
    except Exception as e:
        print(f"  [ERROR] No se pudo leer {ruta}: {e}")
        return ""


def fragmentar(texto: str, max_chars: int = MAX_CHARS_FRAGMENTO) -> list:
    """
    SPAWN: Divide el texto en bloques conceptuales.
    Respeta saltos de linea dobles (parrafos) cuando es posible.
    """
    if not texto.strip():
        return []

    fragmentos = []
    inicio = 0
    total  = len(texto)

    while inicio < total:
        fin = min(inicio + max_chars, total)

        if fin < total:
            # Intentar cortar en parrafo (doble salto)
            corte = texto.rfind('\n\n', inicio, fin)
            if corte == -1 or corte <= inicio:
                # Cortar en espacio
                corte = texto.rfind(' ', inicio, fin)
            if corte > inicio:
                fin = corte

        fragmento = texto[inicio:fin].strip()
        if len(fragmento) > 80:   # ignorar fragmentos muy cortos
            fragmentos.append(fragmento)
        inicio = fin

    return fragmentos


def traducir_a_fractal(fragmento: str, indice: int, total: int) -> dict:
    """
    LINK: Envia el fragmento al modelo maestro (7B) para que lo
    traduzca al Protocolo Wardenclyffe en formato instruccion/output.
    """
    prompt = f"""[SISTEMA PROTOCOLO WARDENCLYFFE — INGENIERIA DE DATASET]
Eres el Ingeniero Core de ARKANI NEXUS. Tu tarea es digerir el siguiente
fragmento tecnico y convertirlo en un par de entrenamiento estructurado.

Fragmento [{indice}/{total}]:
\"\"\"
{fragmento[:1200]}
\"\"\"

INSTRUCCIONES:
1. Extrae el concepto central del fragmento como pregunta clara en "instruction".
2. Responde en "output" USANDO las 7 operaciones fractales: SUM, IF, LOOP, SPAWN, FOLD, LINK, EVOLVE.
3. El output debe ser codigo fractal explicativo, no texto plano.

Devuelve UNICAMENTE un objeto JSON sin markdown extra, con este formato:
{{"instruction": "Pregunta concisa sobre el concepto", "output": "Respuesta en operaciones fractales"}}
"""
    payload = {
        "model":   MODELO,
        "prompt":  prompt,
        "stream":  False,
        "format":  "json",
        "options": {"temperature": 0.2, "num_predict": 400}
    }

    try:
        req = urllib.request.Request(
            OLLAMA_URL,
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT_OLLAMA) as resp:
            res = json.loads(resp.read().decode('utf-8'))
            raw = res.get("response", "{}").strip()
            # Limpiar posible markdown
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            par = json.loads(raw)
            if "instruction" in par and "output" in par:
                return par
            return None
    except json.JSONDecodeError as e:
        print(f"  [WARN] JSON malformado del modelo: {e}")
        return None
    except Exception as e:
        print(f"  [ERROR] Ollama: {e}")
        return None


def cargar_dataset() -> list:
    """Carga el dataset existente o retorna lista vacia."""
    if DATASET_PATH.exists():
        try:
            with open(DATASET_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            print(f"  [WARN] Dataset corrupto, iniciando nuevo")
    return []


def guardar_dataset(ejemplos: list):
    """FOLD: Integra los nuevos pares al dataset historico."""
    DATASET_PATH.parent.mkdir(parents=True, exist_ok=True)
    dataset = cargar_dataset()
    antes   = len(dataset)
    dataset.extend(ejemplos)
    with open(DATASET_PATH, 'w', encoding='utf-8') as f:
        json.dump(dataset, f, indent=2, ensure_ascii=False)
    print(f"\n✅ [FOLD] Dataset actualizado:")
    print(f"   Ejemplos anteriores : {antes}")
    print(f"   Nuevos inyectados   : {len(ejemplos)}")
    print(f"   Total en dataset    : {len(dataset)}")
    print(f"   Ruta                : {DATASET_PATH}")


def procesar(ruta_libro: str, max_chars: int = MAX_CHARS_FRAGMENTO,
             desde: int = 0, hasta: int = None, verbose: bool = True):
    """
    Pipeline completo: leer → fragmentar → traducir → guardar.
    """
    ruta = Path(ruta_libro).expanduser()
    if not ruta.exists():
        print(f"[ERROR] Archivo no encontrado: {ruta}")
        sys.exit(1)

    print("=" * 60)
    print(f"  DIGESTION FRACTAL — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Libro  : {ruta.name}")
    print(f"  Modelo : {MODELO}")
    print("=" * 60)

    # 1. Leer
    texto = leer_archivo(ruta)
    if not texto:
        print("[ERROR] Archivo vacio o no legible")
        sys.exit(1)
    print(f"\n[SPAWN] Texto leido: {len(texto):,} caracteres")

    # 2. Fragmentar
    fragmentos = fragmentar(texto, max_chars)
    print(f"[SPAWN] Fragmentos: {len(fragmentos)}")

    # Aplicar rango
    if hasta:
        fragmentos = fragmentos[desde:hasta]
    elif desde:
        fragmentos = fragmentos[desde:]
    print(f"[SPAWN] Procesando: {len(fragmentos)} fragmentos (desde {desde})")

    # 3. Traducir
    ejemplos    = []
    errores     = 0
    total       = len(fragmentos)
    t_inicio    = time.time()

    for idx, frag in enumerate(fragmentos, start=1):
        print(f"\n[{idx:3d}/{total}] LINK → {MODELO}...", end=' ', flush=True)

        par = traducir_a_fractal(frag, idx, total)

        if par:
            ejemplos.append(par)
            if verbose:
                print(f"✅  instruction: {par['instruction'][:60]}...")
            else:
                print("✅")
        else:
            errores += 1
            print(f"⚠️  (error {errores})")

        # Pausa para no saturar CPU
        if idx < total:
            time.sleep(PAUSA_ENTRE_BLOQUES)

    # 4. Guardar
    elapsed = time.time() - t_inicio
    print(f"\n[STATS] Tiempo: {elapsed:.1f}s | OK: {len(ejemplos)} | Errores: {errores}")

    if ejemplos:
        guardar_dataset(ejemplos)
    else:
        print("[WARN] Sin ejemplos generados — dataset no modificado")

    return len(ejemplos)


# ── Uso desde arkani_web.py (import) ─────────────────────────────────────────

def digerir_texto(nombre: str, contenido: str, max_fragmentos: int = 20) -> dict:
    """
    Punto de entrada para llamar desde arkani_web.py en background.

    from digestion_fractal import digerir_texto
    digerir_texto("manual.txt", contenido_del_archivo, max_fragmentos=30)
    """
    import tempfile
    # Guardar temporalmente
    tmp = NEXUS_DIR / f"tmp_digestion_{nombre.replace(' ','_')}"
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(contenido)

    total_ok = procesar(
        str(tmp),
        max_chars=MAX_CHARS_FRAGMENTO,
        hasta=max_fragmentos,
        verbose=False
    )

    # Limpiar temporal
    try:
        tmp.unlink()
    except Exception:
        pass

    return {
        "ok":       total_ok > 0,
        "ejemplos": total_ok,
        "dataset":  str(DATASET_PATH)
    }


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Digestor Fractal — convierte libros en dataset de entrenamiento ARKANI"
    )
    parser.add_argument('--libro',     required=True,  help="Ruta al archivo (txt, pdf, md, py)")
    parser.add_argument('--max-chars', type=int, default=MAX_CHARS_FRAGMENTO,
                        help=f"Chars por fragmento (default: {MAX_CHARS_FRAGMENTO})")
    parser.add_argument('--desde',     type=int, default=0,
                        help="Fragmento inicial (para reanudar)")
    parser.add_argument('--hasta',     type=int, default=None,
                        help="Fragmento final (para procesar en partes)")
    parser.add_argument('--silencioso', action='store_true',
                        help="Menos output en pantalla")
    args = parser.parse_args()

    n = procesar(
        args.libro,
        max_chars=args.max_chars,
        desde=args.desde,
        hasta=args.hasta,
        verbose=not args.silencioso
    )
    print(f"\n🔥 Digestion completa — {n} ejemplos nuevos en el dataset")
