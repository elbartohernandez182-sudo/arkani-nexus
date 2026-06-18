#!/usr/bin/env python3
"""
arkani_internet.py — Motor de Aprendizaje Autonomo desde Internet
==================================================================
Protocolo Wardenclyffe — Expansion del IQ desde fuentes externas

FLUJO:
  SPAWN(query)          -> busca en DuckDuckGo
  LINK(urls, extractor) -> descarga y limpia texto
  FOLD(textos)          -> envia a digestion_fractal.py
  EVOLVE(dataset)       -> dataset crece, arkani-fractal aprende

Comandos en chat:
  aprende internet: python avanzado
  aprende internet: algoritmos de ordenamiento
  aprende internet: flask web development
  crea: juego de snake en python
  crea: calculadora medica de dosis

Uso directo:
  python3 arkani_internet.py --tema "python decoradores"
  python3 arkani_internet.py --tema "machine learning" --max 5
  python3 arkani_internet.py --url "https://docs.python.org/3/tutorial"
"""

import os
import sys
import re
import json
import time
import urllib.request
import urllib.parse
import urllib.error
import html
from pathlib import Path
from datetime import datetime

# ── Rutas ─────────────────────────────────────────────────────────────────────
NEXUS_DIR        = Path.home() / "NEXUS"
NEXUS_LANG       = NEXUS_DIR / "NEXUS-LANG"
MEMORIA_PERM     = NEXUS_DIR / "memoria_permanente"
DIGESTOR_PATH    = NEXUS_LANG / "fractal_motor" / "digestion_fractal.py"
OLLAMA_URL       = "http://localhost:11434/api/generate"
MODELO           = "arkani:latest"

MEMORIA_PERM.mkdir(parents=True, exist_ok=True)

# ── Fuentes confiables por tema ───────────────────────────────────────────────
FUENTES_CONFIABLES = {
    "python":      ["docs.python.org", "realpython.com", "python-guide.org"],
    "flask":       ["flask.palletsprojects.com", "realpython.com"],
    "javascript":  ["developer.mozilla.org", "javascript.info"],
    "web":         ["developer.mozilla.org", "w3schools.com"],
    "algoritmos":  ["en.wikipedia.org", "geeksforgeeks.org"],
    "machine learning": ["scikit-learn.org", "pytorch.org"],
    "sql":         ["www.w3schools.com", "sqlite.org"],
    "linux":       ["linux.die.net", "tldp.org"],
    "general":     ["en.wikipedia.org", "github.com"],
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

TIMEOUT_HTTP = 15


# ══════════════════════════════════════════════
# BUSQUEDA WEB
# ══════════════════════════════════════════════

def buscar_duckduckgo(query: str, max_resultados: int = 5) -> list:
    """
    Busca en DuckDuckGo Instant Answer API (sin API key).
    Retorna lista de {titulo, url, snippet}.
    """
    url = (f"https://api.duckduckgo.com/?"
           f"q={urllib.parse.quote(query)}&format=json&no_html=1&skip_disambig=1")
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=TIMEOUT_HTTP) as resp:
            data = json.loads(resp.read().decode('utf-8'))

        resultados = []

        # Resultado principal
        if data.get("AbstractURL"):
            resultados.append({
                "titulo":  data.get("Heading", query),
                "url":     data["AbstractURL"],
                "snippet": data.get("AbstractText", "")[:200]
            })

        # Resultados relacionados
        for item in data.get("RelatedTopics", [])[:max_resultados]:
            if isinstance(item, dict) and item.get("FirstURL"):
                resultados.append({
                    "titulo":  item.get("Text", "")[:80],
                    "url":     item["FirstURL"],
                    "snippet": item.get("Text", "")[:200]
                })

        return resultados[:max_resultados]

    except Exception as e:
        print(f"  [WARN] DuckDuckGo: {e}")
        return []


def buscar_wikipedia(tema: str) -> list:
    """Busca directamente en Wikipedia en espanol e ingles."""
    resultados = []
    for lang in ["es", "en"]:
        try:
            url = (f"https://{lang}.wikipedia.org/w/api.php?"
                   f"action=query&list=search&srsearch="
                   f"{urllib.parse.quote(tema)}&format=json&srlimit=3")
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=TIMEOUT_HTTP) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            for item in data.get("query", {}).get("search", []):
                titulo = item["title"]
                resultados.append({
                    "titulo": titulo,
                    "url": f"https://{lang}.wikipedia.org/wiki/{urllib.parse.quote(titulo)}",
                    "snippet": re.sub(r'<[^>]+>', '', item.get("snippet", ""))[:200]
                })
        except Exception:
            pass
    return resultados


def construir_urls_directas(tema: str) -> list:
    """
    Construye URLs directas a documentacion oficial segun el tema.
    Mas confiables que busquedas genericas.
    """
    t = tema.lower()
    urls = []

    if any(p in t for p in ["python", "pip", "pep"]):
        termino = urllib.parse.quote(tema)
        urls += [
            {"titulo": f"Python docs: {tema}",
             "url": f"https://docs.python.org/3/search.html?q={termino}",
             "snippet": "Documentacion oficial Python"},
            {"titulo": f"Real Python: {tema}",
             "url": f"https://realpython.com/search/?q={termino}",
             "snippet": "Tutoriales Python de alta calidad"},
        ]
    if any(p in t for p in ["flask", "web", "http", "api", "rest"]):
        urls.append({
            "titulo": "Flask docs",
            "url": "https://flask.palletsprojects.com/en/3.0.x/",
            "snippet": "Documentacion oficial Flask"
        })
    if any(p in t for p in ["javascript", "js", "html", "css", "dom"]):
        urls.append({
            "titulo": f"MDN: {tema}",
            "url": f"https://developer.mozilla.org/en-US/search?q={urllib.parse.quote(tema)}",
            "snippet": "Mozilla Developer Network"
        })
    if any(p in t for p in ["sql", "database", "sqlite"]):
        urls.append({
            "titulo": "SQLite docs",
            "url": "https://www.sqlite.org/lang.html",
            "snippet": "Documentacion SQLite"
        })

    return urls


# ══════════════════════════════════════════════
# EXTRACTOR DE TEXTO
# ══════════════════════════════════════════════

def limpiar_html(texto_html: str) -> str:
    """Extrae texto limpio de HTML."""
    # Quitar scripts y styles completos
    texto = re.sub(r'<script[^>]*>.*?</script>', '', texto_html,
                   flags=re.DOTALL | re.IGNORECASE)
    texto = re.sub(r'<style[^>]*>.*?</style>', '', texto,
                   flags=re.DOTALL | re.IGNORECASE)
    # Quitar nav, header, footer, ads
    texto = re.sub(r'<(nav|header|footer|aside)[^>]*>.*?</\1>', '', texto,
                   flags=re.DOTALL | re.IGNORECASE)
    # Convertir listas y parrafos a texto
    texto = re.sub(r'<li[^>]*>', '\n• ', texto, flags=re.IGNORECASE)
    texto = re.sub(r'<p[^>]*>|<br[^>]*>|<h[1-6][^>]*>', '\n', texto,
                   flags=re.IGNORECASE)
    # Quitar todas las etiquetas restantes
    texto = re.sub(r'<[^>]+>', '', texto)
    # Decodificar entidades HTML
    texto = html.unescape(texto)
    # Limpiar espacios multiples
    texto = re.sub(r'\n{3,}', '\n\n', texto)
    texto = re.sub(r' {2,}', ' ', texto)
    return texto.strip()


def descargar_url(url: str, max_chars: int = 15000) -> str:
    """Descarga y extrae texto limpio de una URL."""
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=TIMEOUT_HTTP) as resp:
            # Solo procesar HTML y texto
            content_type = resp.headers.get('Content-Type', '')
            if 'pdf' in content_type or 'binary' in content_type:
                return f"[Archivo binario no procesable: {url}]"
            raw = resp.read(200_000)  # max 200KB
            try:
                texto_html = raw.decode('utf-8')
            except UnicodeDecodeError:
                texto_html = raw.decode('latin-1', errors='ignore')

        if '<html' in texto_html.lower():
            texto = limpiar_html(texto_html)
        else:
            texto = texto_html

        # Retornar los primeros max_chars caracteres significativos
        return texto[:max_chars]

    except urllib.error.HTTPError as e:
        return f"[HTTP {e.code}: {url}]"
    except Exception as e:
        return f"[Error descargando {url}: {e}]"


# ══════════════════════════════════════════════
# PIPELINE PRINCIPAL
# ══════════════════════════════════════════════

def aprender_tema(tema: str, max_fuentes: int = 4,
                  usar_digestor: bool = False) -> dict:  # False = no llama Ollama en tiempo real
    """
    Pipeline completo: buscar → descargar → guardar → digerir.
    Retorna resumen de lo aprendido.
    """
    print(f"\n{'='*55}")
    print(f"  ARKANI APRENDE: {tema}")
    print(f"  {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*55}")

    # 1. Buscar fuentes
    print(f"\n[SPAWN] Buscando fuentes para: {tema}")
    resultados = []
    resultados += construir_urls_directas(tema)
    resultados += buscar_wikipedia(tema)
    resultados += buscar_duckduckgo(tema, max_resultados=3)

    # Deduplicar por URL
    vistas = set()
    unicas = []
    for r in resultados:
        if r["url"] not in vistas:
            vistas.add(r["url"])
            unicas.append(r)
    resultados = unicas[:max_fuentes]

    if not resultados:
        print("  [WARN] Sin resultados encontrados")
        return {"ok": False, "tema": tema, "fuentes": 0}

    print(f"  Fuentes encontradas: {len(resultados)}")

    # 2. Descargar y guardar
    textos_descargados = []
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    for i, fuente in enumerate(resultados, 1):
        print(f"\n[LINK {i}/{len(resultados)}] {fuente['titulo'][:50]}")
        print(f"  URL: {fuente['url'][:70]}")

        texto = descargar_url(fuente['url'])

        if texto and not texto.startswith('['):
            chars = len(texto)
            print(f"  ✅ {chars:,} chars extraidos")

            # Guardar en memoria_permanente para procesamiento nocturno
            nombre = re.sub(r'[^a-z0-9_]', '_',
                           (tema + "_" + fuente['titulo'])
                           .lower().replace(' ', '_'))[:50]
            ruta = MEMORIA_PERM / f"{timestamp}_{nombre}.txt"
            encabezado = (f"FUENTE: {fuente['url']}\n"
                         f"TEMA: {tema}\n"
                         f"FECHA: {datetime.now().isoformat()}\n"
                         f"{'='*60}\n\n")
            with open(ruta, 'w', encoding='utf-8', errors='ignore') as f:
                f.write(encabezado + texto)

            textos_descargados.append({
                "titulo": fuente["titulo"],
                "url":    fuente["url"],
                "chars":  chars,
                "ruta":   str(ruta)
            })
        else:
            print(f"  ⚠️  Sin contenido util")

        time.sleep(1)  # cortesia al servidor

    total_chars = sum(t["chars"] for t in textos_descargados)
    print(f"\n[FOLD] Total descargado: {len(textos_descargados)} fuentes, "
          f"{total_chars:,} chars")

    # 3. Digerir inmediatamente si hay digestor y tiempo
    digestados = 0
    if usar_digestor and DIGESTOR_PATH.exists() and textos_descargados:
        print(f"\n[EVOLVE] Iniciando digestión fractal...")
        import subprocess
        for t in textos_descargados[:2]:  # max 2 para no saturar CPU
            print(f"  Digiriendo: {Path(t['ruta']).name}")
            try:
                result = subprocess.run(
                    [sys.executable, str(DIGESTOR_PATH),
                     "--libro", t["ruta"],
                     "--hasta", "8",          # max 8 fragmentos
                     "--silencioso"],
                    capture_output=True, text=True,
                    timeout=300
                )
                if result.returncode == 0:
                    digestados += 1
                    print(f"  ✅ Digerido")
                else:
                    print(f"  ⚠️  Error: {result.stderr[:80]}")
            except subprocess.TimeoutExpired:
                print(f"  ⚠️  Timeout — se procesara de noche")
            except Exception as e:
                print(f"  ⚠️  {e}")

    resumen = {
        "ok":        len(textos_descargados) > 0,
        "tema":      tema,
        "fuentes":   len(textos_descargados),
        "chars":     total_chars,
        "digestados": digestados,
        "archivos":  [t["ruta"] for t in textos_descargados],
        "mensaje": (
            f"Aprendi sobre '{tema}': {len(textos_descargados)} fuentes, "
            f"{total_chars:,} chars. "
            f"{'Digestado ahora.' if digestados else 'Se digerira esta noche.'}"
        )
    }

    print(f"\n{'='*55}")
    print(f"✅ {resumen['mensaje']}")
    print(f"{'='*55}\n")

    return resumen


def aprender_url(url: str, tema: str = "") -> dict:
    """Aprende de una URL especifica."""
    print(f"\n[SPAWN] Descargando: {url}")
    texto = descargar_url(url)
    if not texto or texto.startswith('['):
        return {"ok": False, "error": texto}

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    nombre    = urllib.parse.urlparse(url).netloc.replace('.', '_')
    ruta      = MEMORIA_PERM / f"{timestamp}_{nombre}.txt"

    with open(ruta, 'w', encoding='utf-8', errors='ignore') as f:
        f.write(f"FUENTE: {url}\nTEMA: {tema}\n{'='*60}\n\n{texto}")

    print(f"✅ {len(texto):,} chars guardados en {ruta.name}")
    return {"ok": True, "chars": len(texto), "ruta": str(ruta)}


# ══════════════════════════════════════════════
# CREADOR DE PROGRAMAS (para "crea: juego de snake")
# ══════════════════════════════════════════════

def crear_programa(descripcion: str) -> dict:
    """
    Genera un programa completo usando arkani:latest.
    El resultado se guarda en autogen/ y se ejecuta en sandbox.
    """
    AUTOGEN_DIR = NEXUS_LANG / "autogen"
    AUTOGEN_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n[SPAWN] Creando: {descripcion}")

    prompt = f"""[SISTEMA ARKANI — MODO CREACION]
Eres ARKANI, arquitecto de software del Protocolo Wardenclyffe.
Crea un programa Python COMPLETO y FUNCIONAL para:

"{descripcion}"

REGLAS:
1. El codigo debe ser Python puro, ejecutable directamente
2. Comentarios en espanol
3. Sin dependencias externas raras (usa stdlib o pygame si es juego)
4. El programa debe ser autocontenido
5. Maximo 150 lineas
6. Al final incluye if __name__ == '__main__':

Devuelve SOLO el codigo Python, sin explicaciones ni markdown:
"""

    try:
        payload = {
            "model":   MODELO,
            "prompt":  prompt,
            "stream":  False,
            "options": {"temperature": 0.3, "num_predict": 800}
        }
        req = urllib.request.Request(
            OLLAMA_URL,
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            respuesta = json.loads(resp.read().decode('utf-8'))
            codigo = respuesta.get("response", "").strip()

        # Limpiar markdown si viene
        if "```python" in codigo:
            codigo = codigo.split("```python")[1].split("```")[0].strip()
        elif "```" in codigo:
            codigo = codigo.split("```")[1].split("```")[0].strip()

        # Guardar
        nombre = re.sub(r'[^a-z0-9_]', '_',
                       descripcion.lower().replace(' ', '_'))[:40]
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        ruta = AUTOGEN_DIR / f"crea_{timestamp}_{nombre}.py"

        with open(ruta, 'w') as f:
            f.write(f"# ARKANI CREA: {descripcion}\n"
                   f"# Generado: {datetime.now().isoformat()}\n\n"
                   f"{codigo}")

        print(f"✅ Programa creado: {ruta.name}")
        print(f"   Lineas: {len(codigo.splitlines())}")

        return {
            "ok":      True,
            "ruta":    str(ruta),
            "nombre":  ruta.name,
            "codigo":  codigo[:500],
            "lineas":  len(codigo.splitlines()),
            "mensaje": f"Programa creado: {ruta.name}\nPara ejecutar: python3 {ruta}"
        }

    except Exception as e:
        return {"ok": False, "error": str(e)}


# ══════════════════════════════════════════════
# INTEGRACION CON ARKANI_ENGINE
# ══════════════════════════════════════════════
# Agregar en _decidir_modo() de ArkaniEngine:
#
#   if texto.startswith("aprende internet:"):  return "INTERNET"
#   if texto.startswith("crea:"):              return "CREAR"
#
# Agregar en chat():
#
#   if modo == "INTERNET":
#       from arkani_internet import aprender_tema
#       tema = pregunta[17:].strip()
#       r = aprender_tema(tema, usar_digestor=False)
#       return r["mensaje"]
#
#   if modo == "CREAR":
#       from arkani_internet import crear_programa
#       desc = pregunta[5:].strip()
#       r = crear_programa(desc)
#       return r.get("mensaje", r.get("error", "Error"))


# ══════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="ARKANI Internet — Aprendizaje autonomo desde la web"
    )
    parser.add_argument('--tema',  help="Tema a aprender (ej: 'python decoradores')")
    parser.add_argument('--url',   help="URL especifica a descargar")
    parser.add_argument('--crea',  help="Crear programa (ej: 'juego de snake')")
    parser.add_argument('--max',   type=int, default=4,
                        help="Maximo de fuentes (default: 4)")
    parser.add_argument('--sin-digestor', action='store_true',
                        help="Solo descargar, sin digerir ahora")
    args = parser.parse_args()

    if args.tema:
        aprender_tema(args.tema, max_fuentes=args.max,
                     usar_digestor=not args.sin_digestor)
    elif args.url:
        aprender_url(args.url)
    elif args.crea:
        r = crear_programa(args.crea)
        if r["ok"]:
            print(f"\nCodigo generado:\n{r['codigo']}")
    else:
        parser.print_help()
        print("\nEjemplos:")
        print("  python3 arkani_internet.py --tema 'python decoradores'")
        print("  python3 arkani_internet.py --tema 'algoritmos sorting' --max 3")
        print("  python3 arkani_internet.py --url 'https://docs.python.org/3/tutorial/'")
        print("  python3 arkani_internet.py --crea 'juego de snake'")
