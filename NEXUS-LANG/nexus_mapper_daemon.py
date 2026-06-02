#!/usr/bin/env python3
import os
import json
import hashlib
import subprocess
import importlib.util
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify
from flask_cors import CORS

BASE_PATH  = os.path.expanduser("~/NEXUS/NEXUS-LANG")
NEXUS_ROOT = os.path.expanduser("~/NEXUS")
CLAVE      = "arkani"
PORT       = 5010

app = Flask(__name__)
CORS(app)

def check_clave(data):
    return str(data.get("clave","")).lower() == CLAVE

def sha256_file(path):
    try:
        h = hashlib.sha256()
        with open(path,"rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()[:12]
    except:
        return "ERROR"

def file_info(path):
    try:
        stat  = os.stat(path)
        size  = stat.st_size
        sha   = sha256_file(path)
        ext   = Path(path).suffix
        lines = 0
        errors = []
        classes = []
        functions = []
        if ext == ".py":
            try:
                with open(path,"r",errors="replace") as f:
                    src = f.read()
                lines = src.count("\n") + 1
                for line in src.splitlines():
                    s = line.strip()
                    if s.startswith("class "):
                        classes.append(s.split("(")[0].replace("class ","").strip().rstrip(":"))
                    elif s.startswith("def "):
                        functions.append(s.split("(")[0].replace("def ","").strip())
                try:
                    spec = importlib.util.spec_from_file_location("_test", path)
                    mod  = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                except SyntaxError as e:
                    errors.append(f"SyntaxError: {e}")
                except Exception as e:
                    errors.append(f"ImportError: {type(e).__name__}: {e}")
            except Exception as e:
                errors.append(str(e))
        else:
            try:
                with open(path,"r",errors="replace") as f:
                    lines = f.read().count("\n") + 1
            except:
                lines = -1
        return {"size_bytes":size,"lines":lines,"sha":sha,
                "classes":classes,"functions":functions,"errors":errors}
    except Exception as e:
        return {"error": str(e)}

@app.route("/ping", methods=["GET"])
def ping():
    return jsonify({"status":"NEXUS MAPPER ONLINE",
                    "base_path":BASE_PATH,
                    "time":datetime.now().isoformat()})

@app.route("/nexus/map", methods=["POST"])
def mapa_completo():
    if not check_clave(request.json or {}):
        return jsonify({"status":"ACCESO DENEGADO"}), 403
    mapa = {}
    for root, dirs, files in os.walk(BASE_PATH):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for fname in sorted(files):
            full = os.path.join(root, fname)
            rel  = os.path.relpath(full, BASE_PATH)
            mapa[rel] = file_info(full)
    py_files   = [k for k in mapa if k.endswith(".py")]
    json_files = [k for k in mapa if k.endswith(".json")]
    bin_files  = [k for k in mapa if k.endswith(".bin")]
    errores    = {k:v["errors"] for k,v in mapa.items()
                  if isinstance(v.get("errors"),list) and v["errors"]}
    return jsonify({"resumen":{"total_archivos":len(mapa),
                               "python":len(py_files),
                               "json":len(json_files),
                               "binarios":len(bin_files),
                               "con_errores":len(errores)},
                    "errores_criticos":errores,
                    "archivos":mapa,
                    "timestamp":datetime.now().isoformat()})

@app.route("/nexus/read", methods=["POST"])
def leer_archivo():
    data = request.json or {}
    if not check_clave(data):
        return jsonify({"status":"ACCESO DENEGADO"}), 403
    nombre = data.get("archivo","").strip()
    if not nombre or ".." in nombre:
        return jsonify({"error":"Nombre invalido"}), 400
    full = os.path.join(BASE_PATH, nombre)
    if not os.path.exists(full):
        return jsonify({"error":f"No existe: {nombre}"}), 404
    with open(full,"r",errors="replace") as f:
        contenido = f.read()
    return jsonify({"archivo":nombre,"contenido":contenido,
                    "lineas":contenido.count("\n")+1,"sha":sha256_file(full)})

@app.route("/nexus/write", methods=["POST"])
def escribir_archivo():
    data = request.json or {}
    if not check_clave(data):
        return jsonify({"status":"ACCESO DENEGADO"}), 403
    nombre    = data.get("archivo","").strip()
    contenido = data.get("contenido","")
    if not nombre or ".." in nombre or nombre.startswith("/"):
        return jsonify({"error":"Nombre invalido"}), 400
    full = os.path.join(BASE_PATH, nombre)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    backup = None
    if os.path.exists(full):
        backup = full + f".bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        os.rename(full, backup)
    with open(full,"w") as f:
        f.write(contenido)
    return jsonify({"status":"ESCRITO","archivo":nombre,
                    "bytes":len(contenido.encode()),
                    "backup":os.path.basename(backup) if backup else None,
                    "sha":sha256_file(full)})

@app.route("/nexus/run", methods=["POST"])
def ejecutar_script():
    data = request.json or {}
    if not check_clave(data):
        return jsonify({"status":"ACCESO DENEGADO"}), 403
    script  = data.get("script","").strip()
    timeout = min(int(data.get("timeout",15)), 30)
    bloqueados = ["os.system","rm -rf","shutil.rmtree","chmod 777"]
    for blq in bloqueados:
        if blq in script:
            return jsonify({"error":f"Bloqueado: {blq}"}), 403
    result = subprocess.run(["python3","-c",script],
                            capture_output=True, text=True,
                            timeout=timeout, cwd=BASE_PATH)
    return jsonify({"stdout":result.stdout,"stderr":result.stderr,
                    "returncode":result.returncode,"exito":result.returncode==0})

@app.route("/nexus/git", methods=["POST"])
def git_status():
    data = request.json or {}
    if not check_clave(data):
        return jsonify({"status":"ACCESO DENEGADO"}), 403
    def rg(cmd):
        try:
            r = subprocess.run(cmd,capture_output=True,text=True,
                               timeout=10,cwd=NEXUS_ROOT)
            return r.stdout.strip()
        except:
            return "error"
    return jsonify({"log_10":rg(["git","log","--oneline","-10"]),
                    "status":rg(["git","status","--short"]),
                    "branch":rg(["git","branch","--show-current"]),
                    "ultimo":rg(["git","log","-1","--format=%ai %s"])})

@app.route("/nexus/hipocampo", methods=["POST"])
def estado_hipocampo():
    data = request.json or {}
    if not check_clave(data):
        return jsonify({"status":"ACCESO DENEGADO"}), 403
    bin_path = os.path.join(BASE_PATH,"hipocampo.bin")
    if not os.path.exists(bin_path):
        return jsonify({"error":"hipocampo.bin no existe"}), 404
    OP_NAMES = {0xA0:"SUM",0xA1:"IF",0xA3:"LOOP",
                0xA5:"SPAWN",0xA7:"FOLD",0xA9:"LINK",0xF1:"EVOLVE"}
    instrucciones = []
    conteo = {}
    with open(bin_path,"rb") as f:
        data_bin = f.read()
    for i in range(0, len(data_bin), 16):
        chunk = data_bin[i:i+16]
        if len(chunk) != 16 or chunk[0] != 0x7C:
            continue
        op_name = OP_NAMES.get(chunk[1], f"0x{chunk[1]:02X}")
        conteo[op_name] = conteo.get(op_name,0) + 1
        instrucciones.append({"dir":i//16,"op":op_name,
                               "scale":chunk[2],"hex":chunk.hex()})
    total = len(instrucciones)
    return jsonify({"total":total,"bytes":total*16,
                    "conteo_por_op":conteo,
                    "primeras_5":instrucciones[:5],
                    "ultimas_5":instrucciones[-5:] if total>5 else []})

@app.route("/nexus/diagnose", methods=["POST"])
def diagnostico():
    data = request.json or {}
    if not check_clave(data):
        return jsonify({"status":"ACCESO DENEGADO"}), 403
    esperados = {
        "nexus_fractal_compiler.py":"Compilador .nl -> binario 16 bytes",
        "nexus_fractal_os.py":      "OS fractal API REST port 5005",
        "nexus_fractal_vm.py":      "VM ejecuta bytecode <- FALTA",
        "arkani_engine.py":         "Motor conversacional",
        "arkani_web.py":            "Interfaz web port 8081",
        "daemon_guardian.py":       "Guardian 24/7",
        "arrancar_arkani.sh":       "Script de arranque",
        "hipocampo.bin":            "Memoria binaria de Arkani",
        "INSTRUCCIONES.md":         "Tareas para Claude <- FALTA",
    }
    presentes = {}
    faltantes = {}
    con_errores = {}
    for arch, desc in esperados.items():
        ruta = os.path.join(BASE_PATH, arch)
        if os.path.exists(ruta):
            info = file_info(ruta)
            presentes[arch] = {"descripcion":desc, **info}
            if info.get("errors"):
                con_errores[arch] = info["errors"]
        else:
            faltantes[arch] = desc
    todos_py = [
        os.path.relpath(os.path.join(r,f), BASE_PATH)
        for r,_,files in os.walk(BASE_PATH)
        for f in files if f.endswith(".py") and "__pycache__" not in r
    ]
    extras = [f for f in todos_py if os.path.basename(f) not in esperados]
    return jsonify({
        "presentes":presentes,
        "faltantes":faltantes,
        "con_errores":con_errores,
        "extras":extras,
        "resumen":{"presentes":len(presentes),"faltantes":len(faltantes),
                   "con_errores":len(con_errores),"extras":len(extras)},
        "proximos_pasos":[
            "Crear nexus_fractal_vm.py - Maquina Virtual",
            "Crear INSTRUCCIONES.md - guia entre sesiones",
            "Conectar compilador + VM + arkani_web.py",
        ],
        "timestamp":datetime.now().isoformat()
    })

if __name__ == "__main__":
    print("="*55)
    print("NEXUS MAPPER DAEMON v1.0")
    print(f"Base: {BASE_PATH}")
    print(f"Puerto: {PORT}  |  Clave: {CLAVE}")
    print("Endpoints: /ping /nexus/map /nexus/read")
    print("           /nexus/write /nexus/run /nexus/git")
    print("           /nexus/hipocampo /nexus/diagnose")
    print(f"ngrok: ngrok http {PORT}")
    print("="*55)
    app.run(host="0.0.0.0", port=PORT, debug=False)
