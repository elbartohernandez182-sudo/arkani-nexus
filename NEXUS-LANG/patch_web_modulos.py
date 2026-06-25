#!/usr/bin/env python3
"""
patch_web_modulos.py — Agrega rutas backend para:
  /pack/comprimir, /pack/extraer, /pack/info
  /rad/subir, /rad/analizar
  /sam/generar, /nexus/listar_autogen
  /office/generar
  /frachat/  (base)
  /subir_archivo, /archivos_memoria (si no existen)
Aplica sobre arkani_web.py existente.
"""
import os, ast

WEB = "/home/arkani/NEXUS/NEXUS-LANG/arkani_web.py"

with open(WEB, 'r') as f:
    code = f.read()

NUEVAS_RUTAS = '''
# ═══════════════════════════════════════════════════════════
# NEXUS-PACK — Compresor/Descompresor .nxf
# ═══════════════════════════════════════════════════════════

@app.route('/pack/comprimir', methods=['POST'])
def pack_comprimir():
    """Comprime archivos subidos a formato .nxf"""
    try:
        archivos = request.files.getlist('archivos')
        nombre   = request.form.get('nombre', 'paquete_nexus')
        if not archivos:
            return jsonify({"ok": False, "error": "Sin archivos"})

        import tempfile, shutil
        tmp_dir = tempfile.mkdtemp()
        rutas = []
        size_orig = 0
        for f in archivos:
            ruta = os.path.join(tmp_dir, f.filename)
            f.save(ruta)
            rutas.append(ruta)
            size_orig += os.path.getsize(ruta)

        salida = os.path.join(os.path.expanduser("~/NEXUS"), nombre + ".nxf")
        origen = tmp_dir if len(rutas) > 1 else rutas[0]

        import subprocess
        r = subprocess.run(
            ["python3", os.path.join(BASE_DIR, "nexus_fractal_packager.py"),
             "--comprimir", origen, salida],
            capture_output=True, text=True, timeout=60
        )
        shutil.rmtree(tmp_dir, ignore_errors=True)

        if os.path.exists(salida):
            size_comp = os.path.getsize(salida)
            ratio = round((1 - size_comp/max(size_orig,1)) * 100, 1)
            return jsonify({
                "ok": True,
                "archivo": nombre + ".nxf",
                "size_orig": size_orig,
                "size_comp": size_comp,
                "ratio": ratio
            })
        return jsonify({"ok": False, "error": r.stderr[:200] or "Error empaquetando"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route('/pack/extraer', methods=['POST'])
def pack_extraer():
    """Extrae un .nxf a directorio"""
    try:
        archivo = request.files.get('archivo')
        if not archivo:
            return jsonify({"ok": False, "error": "Sin archivo"})

        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix='.nxf', delete=False)
        archivo.save(tmp.name)

        destino = os.path.expanduser("~/NEXUS/recibidos/" + archivo.filename.replace('.nxf',''))
        os.makedirs(destino, exist_ok=True)

        import subprocess
        r = subprocess.run(
            ["python3", os.path.join(BASE_DIR, "nexus_fractal_packager.py"),
             "--extraer", tmp.name, destino],
            capture_output=True, text=True, timeout=60
        )
        os.unlink(tmp.name)

        archivos = len(os.listdir(destino)) if os.path.exists(destino) else 0
        return jsonify({"ok": True, "destino": destino, "archivos": archivos})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route('/pack/info', methods=['POST'])
def pack_info():
    """Devuelve info de un .nxf sin extraer"""
    try:
        archivo = request.files.get('archivo')
        if not archivo:
            return jsonify({"ok": False, "error": "Sin archivo"})

        import tempfile, subprocess, struct
        tmp = tempfile.NamedTemporaryFile(suffix='.nxf', delete=False)
        archivo.save(tmp.name)

        r = subprocess.run(
            ["python3", os.path.join(BASE_DIR, "nexus_fractal_packager.py"),
             "--info", tmp.name],
            capture_output=True, text=True, timeout=30
        )
        os.unlink(tmp.name)

        # Parsear output del packager
        lines = r.stdout.strip().split('\\n')
        info = {}
        for l in lines:
            if ':' in l:
                k, v = l.split(':', 1)
                info[k.strip()] = v.strip()

        return jsonify({
            "ok": True,
            "nombre": archivo.filename,
            "archivos": info.get('Archivos', '?'),
            "size_orig": int(info.get('Original', '0 bytes').replace(',','').split()[0]) if 'Original' in info else 0,
            "size_comp": int(info.get('Comprimido', '0 bytes').replace(',','').split()[0]) if 'Comprimido' in info else 0,
            "ratio": info.get('Ratio', '?'),
            "fecha": info.get('Fecha', '?'),
            "raw": r.stdout[:500]
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


# ═══════════════════════════════════════════════════════════
# NEXUS-RAD — Radiología
# ═══════════════════════════════════════════════════════════

@app.route('/rad/subir', methods=['POST'])
def rad_subir():
    """Recibe archivo DICOM y lo procesa"""
    try:
        archivo = request.files.get('dicom')
        if not archivo:
            return jsonify({"ok": False, "error": "Sin archivo DICOM"})

        rad_dir = os.path.expanduser("~/NEXUS/nexus-rad/estudios/")
        os.makedirs(rad_dir, exist_ok=True)
        ruta = os.path.join(rad_dir, archivo.filename)
        archivo.save(ruta)

        info = {"nombre": archivo.filename, "size": os.path.getsize(ruta), "ruta": ruta}

        # Intentar leer metadatos con pydicom si está disponible
        try:
            import pydicom
            ds = pydicom.dcmread(ruta)
            info["paciente"] = str(getattr(ds, 'PatientName', 'Desconocido'))
            info["modalidad"] = str(getattr(ds, 'Modality', '?'))
            info["fecha"] = str(getattr(ds, 'StudyDate', '?'))
            info["descripcion"] = str(getattr(ds, 'StudyDescription', '?'))
            info["pydicom"] = True
        except ImportError:
            info["pydicom"] = False
            info["nota"] = "pydicom no instalado — instalar con: pip install pydicom"
        except Exception as e:
            info["pydicom"] = False
            info["nota"] = str(e)

        return jsonify({"ok": True, **info})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route('/rad/analizar', methods=['POST'])
def rad_analizar():
    """Analiza imagen DICOM con Arkani (texto por ahora, LLaVA con GPU)"""
    try:
        data = request.json or {}
        descripcion = data.get('descripcion', '')
        modalidad = data.get('modalidad', 'TC')

        if arkani:
            prompt = f"Como radiólogo, analiza este estudio de {modalidad}: {descripcion}"
            respuesta = arkani.chat(prompt)
            return jsonify({"ok": True, "analisis": respuesta})
        return jsonify({"ok": False, "error": "Arkani no disponible"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route('/rad/comprimir_dicom', methods=['POST'])
def rad_comprimir_dicom():
    """Convierte DICOM a .nxf fractal"""
    try:
        data = request.json or {}
        ruta_dicom = data.get('ruta', '')
        if not ruta_dicom or not os.path.exists(ruta_dicom):
            return jsonify({"ok": False, "error": "Ruta DICOM no válida"})

        nombre = os.path.basename(ruta_dicom).replace('.dcm', '')
        salida = os.path.expanduser(f"~/NEXUS/nexus-rad/fractal/{nombre}.nxf")
        os.makedirs(os.path.dirname(salida), exist_ok=True)

        import subprocess
        r = subprocess.run(
            ["python3", os.path.join(BASE_DIR, "nexus_fractal_packager.py"),
             "--comprimir", ruta_dicom, salida],
            capture_output=True, text=True, timeout=120
        )

        if os.path.exists(salida):
            size_orig = os.path.getsize(ruta_dicom)
            size_nxf  = os.path.getsize(salida)
            ratio = round((1 - size_nxf/max(size_orig,1)) * 100, 1)
            return jsonify({
                "ok": True, "salida": salida,
                "size_orig_mb": round(size_orig/1048576, 2),
                "size_nxf_mb":  round(size_nxf/1048576, 2),
                "reduccion": f"{ratio}%"
            })
        return jsonify({"ok": False, "error": r.stderr[:200]})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


# ═══════════════════════════════════════════════════════════
# SAM — System Auto-coder Module
# ═══════════════════════════════════════════════════════════

@app.route('/nexus/listar_autogen')
def nexus_listar_autogen():
    """Lista módulos en autogen/"""
    try:
        autogen_dir = os.path.join(BASE_DIR, "autogen")
        if not os.path.exists(autogen_dir):
            return jsonify({"archivos": [], "total": 0})
        archivos = sorted([
            f for f in os.listdir(autogen_dir)
            if f.endswith('.py')
        ])
        return jsonify({"archivos": archivos, "total": len(archivos)})
    except Exception as e:
        return jsonify({"archivos": [], "error": str(e)})


@app.route('/sam/generar', methods=['POST'])
def sam_generar():
    """Genera código usando Arkani"""
    try:
        data = request.json or {}
        descripcion = data.get('descripcion', '').strip()
        lenguaje    = data.get('lenguaje', 'Python')
        if not descripcion:
            return jsonify({"ok": False, "error": "Sin descripción"})

        if arkani:
            prompt = f"crea: {descripcion} en {lenguaje}"
            codigo = arkani.chat(prompt)
            return jsonify({"ok": True, "codigo": codigo})
        return jsonify({"ok": False, "error": "Arkani no disponible"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route('/sam/ejecutar', methods=['POST'])
def sam_ejecutar():
    """Ejecuta un módulo de autogen/"""
    try:
        data = request.json or {}
        nombre = data.get('nombre', '').strip()
        if not nombre or '..' in nombre:
            return jsonify({"ok": False, "error": "Nombre inválido"})

        ruta = os.path.join(BASE_DIR, "autogen", nombre)
        if not os.path.exists(ruta):
            return jsonify({"ok": False, "error": f"No existe: {nombre}"})

        import subprocess
        r = subprocess.run(
            ["python3", ruta],
            capture_output=True, text=True, timeout=30,
            cwd=BASE_DIR
        )
        return jsonify({
            "ok": r.returncode == 0,
            "stdout": r.stdout[:1000],
            "stderr": r.stderr[:500],
            "returncode": r.returncode
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


# ═══════════════════════════════════════════════════════════
# NEXUS-OFFICE — Documentos
# ═══════════════════════════════════════════════════════════

@app.route('/office/generar', methods=['POST'])
def office_generar():
    """Genera documento con Arkani"""
    try:
        data = request.json or {}
        tipo        = data.get('tipo', 'word')
        descripcion = data.get('descripcion', '').strip()
        if not descripcion:
            return jsonify({"ok": False, "error": "Sin descripción"})

        if arkani:
            prompt = f"crea: documento {tipo} — {descripcion}"
            resultado = arkani.chat(prompt)
            return jsonify({"ok": True, "resultado": resultado,
                           "nota": "Integración python-docx/pptx/xlsx en desarrollo"})
        return jsonify({"ok": False, "error": "Arkani no disponible"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


# ═══════════════════════════════════════════════════════════
# FRACHAT — Mensajería Fractal (base)
# ═══════════════════════════════════════════════════════════
_frachat_mensajes = []  # En memoria por ahora

@app.route('/frachat/mensajes')
def frachat_mensajes():
    return jsonify({"mensajes": _frachat_mensajes[-50:], "total": len(_frachat_mensajes)})


@app.route('/frachat/enviar', methods=['POST'])
def frachat_enviar():
    try:
        data = request.json or {}
        msg = {
            "de":       data.get('de', 'Anon'),
            "para":     data.get('para', 'todos'),
            "texto":    data.get('texto', ''),
            "tipo":     data.get('tipo', 'texto'),  # texto, voz, nxf
            "timestamp": __import__('datetime').datetime.now().isoformat(),
            "nodo":     data.get('nodo', 'local')
        }
        _frachat_mensajes.append(msg)
        # Emitir por SocketIO a todos
        socketio.emit('frachat_mensaje', msg)
        return jsonify({"ok": True, "id": len(_frachat_mensajes)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route('/frachat/estado')
def frachat_estado():
    return jsonify({
        "online": True,
        "mensajes": len(_frachat_mensajes),
        "nodo_id": "local",
        "protocolo": "FraChat v1.0 — Fractal"
    })


# ═══════════════════════════════════════════════════════════
# SUBIR ARCHIVO a memoria permanente (si no existe)
# ═══════════════════════════════════════════════════════════

@app.route('/subir_archivo', methods=['POST'])
def subir_archivo():
    try:
        archivo = request.files.get('archivo')
        aprende  = request.form.get('aprende', 'false').lower() == 'true'
        if not archivo:
            return jsonify({"ok": False, "error": "Sin archivo"})

        if aprende:
            destino_dir = os.path.expanduser("~/NEXUS/memoria_permanente/")
        else:
            destino_dir = os.path.expanduser("~/NEXUS/papelera/")

        os.makedirs(destino_dir, exist_ok=True)
        ruta = os.path.join(destino_dir, archivo.filename)
        archivo.save(ruta)

        preview = ""
        try:
            with open(ruta, 'r', errors='replace') as f:
                preview = f.read(300)
        except:
            preview = "(archivo binario)"

        return jsonify({
            "ok": True,
            "nombre": archivo.filename,
            "ruta": ruta,
            "modo": "permanente" if aprende else "temporal",
            "preview": preview
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route('/archivos_memoria')
def archivos_memoria():
    try:
        mp = os.path.expanduser("~/NEXUS/memoria_permanente/")
        archivos = []
        if os.path.exists(mp):
            for f in sorted(os.listdir(mp)):
                ruta = os.path.join(mp, f)
                archivos.append({
                    "nombre": f,
                    "size": os.path.getsize(ruta),
                    "fecha": __import__('datetime').datetime.fromtimestamp(
                        os.path.getmtime(ruta)).strftime('%Y-%m-%d %H:%M')
                })
        return jsonify({"archivos": archivos, "total": len(archivos)})
    except Exception as e:
        return jsonify({"archivos": [], "error": str(e)})

'''

# Insertar antes del if __name__ == '__main__'
OLD_MAIN = "if __name__ == '__main__':"
if OLD_MAIN in code:
    # Evitar duplicados
    if '/pack/comprimir' not in code:
        code = code.replace(OLD_MAIN, NUEVAS_RUTAS + OLD_MAIN)
        print("✅ Rutas nuevas agregadas")
    else:
        print("⚠️  Rutas ya existen — no modificado")
else:
    print("❌ No encontré if __name__")

# Verificar sintaxis
try:
    ast.parse(code)
    with open(WEB, 'w') as f:
        f.write(code)
    print("✅ Sintaxis OK — arkani_web.py actualizado")
    print(f"   Líneas: {code.count(chr(10))}")
except SyntaxError as e:
    print(f"❌ SyntaxError línea {e.lineno}: {e.msg}")
