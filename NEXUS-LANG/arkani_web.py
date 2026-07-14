import os, sys, json, ast, datetime, base64
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['SECRET_KEY'] = 'arkani1979nexus'
socketio = SocketIO(app, cors_allowed_origins="*")
BASE_DIR = os.path.expanduser("~/NEXUS/NEXUS-LANG")
AUTOGEN_DIR = os.path.join(BASE_DIR, "autogen")
sys.path.insert(0, BASE_DIR)
from nexus_commander import commander
from nexus_evolve_v2 import evolve_engine

try:
    from arkani_engine import ArkaniEngine, verificar_codigo_seguro, exec_seguro
    arkani = ArkaniEngine()
    ARKANI_OK = True
except Exception as e:
    ARKANI_OK = False
    arkani = None
    print(f"warning: {e}")

# UPDATER
try:
    from nexus_updater import registrar_rutas as updater_rutas
    UPDATER_OK = True
except Exception as e:
    UPDATER_OK = False

def cargar_rag():
    frags = []
    for f in ["arkani_engine.py", "arkani_tools.py"]:
        try:
            with open(os.path.join(BASE_DIR, f)) as fh:
                frags.append(f"### {f}\n{fh.read(800)}")
        except:
            pass
    try:
        nodos = sorted([f for f in os.listdir(AUTOGEN_DIR) if f.endswith('.py')])
        frags.append("### CAPACIDADES\n" + "\n".join(nodos))
    except:
        pass
    ctx = "\n\n".join(frags)
    if arkani:
        arkani.set_contexto_propio(ctx)
    print(f"RAG: {len(frags)} archivos, {len(ctx)} chars")
    return ctx


# ── Directorios de memoria por archivo ────────────────────────────────────
MEMORIA_PERM_DIR = os.path.expanduser("~/NEXUS/memoria_permanente/")
PAPELERA_DIR     = os.path.expanduser("~/NEXUS/papelera/")
INDICE_PATH      = os.path.expanduser("~/NEXUS/indice_archivos.json")
for _d in [MEMORIA_PERM_DIR, PAPELERA_DIR]:
    os.makedirs(_d, exist_ok=True)

def _cargar_indice():
    try:
        with open(INDICE_PATH) as f: return json.load(f)
    except Exception: return {"permanentes": [], "papelera": []}

def _guardar_indice(idx):
    with open(INDICE_PATH, 'w') as f:
        json.dump(idx, f, indent=2, ensure_ascii=False)

def _leer_contenido(ruta: str, nombre: str) -> str:
    ext = os.path.splitext(nombre)[1].lower()
    if ext in ('.txt', '.py', '.md', '.json', '.nl'):
        try:
            with open(ruta, 'r', errors='ignore') as f: return f.read(50000)
        except Exception as e: return f"[Error: {e}]"
    if ext == '.pdf':
        try:
            import subprocess
            r = subprocess.run(['pdftotext', ruta, '-'],
                               capture_output=True, text=True, timeout=15)
            if r.returncode == 0 and r.stdout.strip(): return r.stdout[:50000]
            return "[PDF sin texto extraible]"
        except Exception as e: return f"[Error PDF: {e}]"
    if ext in ('.png', '.jpg', '.jpeg', '.webp', '.gif'):
        try:
            size_kb = round(os.path.getsize(ruta) / 1024, 1)
            return (f'[Imagen: {nombre} — {size_kb} KB]\n'
                    f'Archivo guardado. Para analisis visual: ollama pull llava\n'
                    f'Ruta: {ruta}')
        except Exception as e: return f'[Error imagen: {e}]'
    if ext == '.docx':
        try:
            from docx import Document
            d = Document(ruta)
            return '\n'.join(p.text for p in d.paragraphs)[:50000]
        except Exception as e: return f"[DOCX error: {e}]"
    return f"[Tipo {ext} no soportado]"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/status')
def status():
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=1)
        ram = psutil.virtual_memory().percent
    except:
        cpu = ram = 0
    info = arkani.resumen() if arkani else {}
    ultimas = []
    if arkani:
        convs = arkani.mem.memoria.get('conversaciones', [])[-5:]
        ultimas = [{'pregunta': c.get('pregunta','')[:40],
                    'fecha': c.get('fecha','')} for c in reversed(convs)]
    return jsonify({'cpu': cpu, 'ram': ram, 'arkani_ok': ARKANI_OK,
                    'ultimas_conversaciones': ultimas, **info,
                    'timestamp': datetime.datetime.now().strftime('%H:%M:%S')})

@app.route('/hipocampo')
def hipocampo():
    if not arkani:
        return jsonify({"total": 0, "instrucciones": [], "resumen": ""})
    instr = arkani.motor.hipocampo.instructions
    return jsonify({
        "total": len(instr),
        "bytes": len(instr) * 16,
        "resumen": arkani.motor.hipocampo.resumen(),
        "instrucciones": [str(i) for i in instr]
    })

@app.route('/archivos')
def archivos():
    try:
        arch = sorted([f for f in os.listdir(AUTOGEN_DIR) if f.endswith('.py')])
        return jsonify({"archivos": arch})
    except Exception as e:
        return jsonify({"archivos": []})

@app.route('/archivo')
def leer_archivo():
    nombre = request.args.get('nombre', '')
    if not nombre or '..' in nombre or '/' in nombre:
        return jsonify({"error": "invalido"}), 400
    try:
        with open(os.path.join(AUTOGEN_DIR, nombre)) as f:
            return jsonify({"contenido": f.read(), "nombre": nombre})
    except Exception as e:
        return jsonify({"error": str(e)}), 404

@app.route('/guardar_codigo', methods=['POST'])
def guardar_codigo():
    data = request.json
    nombre = data.get('nombre', '').strip()
    codigo = data.get('codigo', '').strip()
    if not nombre or not codigo:
        return jsonify({"ok": False, "error": "Vacio"})
    nombre_limpio = ''.join(c for c in nombre.replace('fn_', '').replace('.py', '')
                            if c.isalnum() or c == '_')
    nombre_final = f"fn_{nombre_limpio}.py"
    seguro, motivo = verificar_codigo_seguro(codigo)
    if not seguro:
        return jsonify({"ok": False, "error": motivo})
    try:
        ast.parse(codigo)
    except SyntaxError as e:
        return jsonify({"ok": False, "error": str(e)})
    with open(os.path.join(AUTOGEN_DIR, nombre_final), 'w') as f:
        f.write(f"# GUARDADO POR CONSTRUCTOR\n# {datetime.datetime.now().isoformat()}\n\n{codigo}")
    cargar_rag()
    return jsonify({"ok": True, "ruta": nombre_final, "mensaje": f"Guardado: {nombre_final}"})

@app.route('/probar_codigo', methods=['POST'])
def probar_codigo():
    codigo = request.json.get('codigo', '').strip()
    if not codigo:
        return jsonify({"ok": False, "error": "Vacio"})
    seguro, motivo = verificar_codigo_seguro(codigo)
    if not seguro:
        return jsonify({"ok": False, "error": motivo})
    try:
        ast.parse(codigo)
    except SyntaxError as e:
        return jsonify({"ok": False, "error": str(e)})
    ok, msg = exec_seguro(codigo)
    return jsonify({"ok": ok, "mensaje": msg, "error": msg if not ok else ""})

@app.route('/escanear_errores')
def escanear_errores():
    errores = []
    try:
        lista = [f for f in os.listdir(AUTOGEN_DIR) if f.endswith('.py')]
        for archivo in sorted(lista):
            try:
                with open(os.path.join(AUTOGEN_DIR, archivo)) as f:
                    codigo = f.read()
                try:
                    tree = ast.parse(codigo)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.FunctionDef):
                            if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                                errores.append({
                                    "tipo": "warning",
                                    "archivo": archivo,
                                    "titulo": f"Funcion vacia: {node.name}()",
                                    "descripcion": "Solo tiene pass",
                                    "codigo_fix": f"def {node.name}():\n    return None"
                                })
                except SyntaxError as e:
                    errores.append({
                        "tipo": "error",
                        "archivo": archivo,
                        "titulo": f"Sintaxis linea {e.lineno}",
                        "descripcion": str(e),
                        "codigo_fix": None
                    })
                lineas = [l for l in codigo.split('\n') if l.strip() and not l.startswith('#')]
                if len(lineas) < 2:
                    errores.append({
                        "tipo": "warning",
                        "archivo": archivo,
                        "titulo": "Modulo casi vacio",
                        "descripcion": f"Solo {len(lineas)} lineas",
                        "codigo_fix": None
                    })
            except Exception as e:
                errores.append({
                    "tipo": "error",
                    "archivo": archivo,
                    "titulo": "No se pudo leer",
                    "descripcion": str(e),
                    "codigo_fix": None
                })
    except Exception as e:
        return jsonify({"errores": [], "error": str(e)})
    return jsonify({"errores": errores, "total": len(errores)})

@app.route('/aplicar_fix', methods=['POST'])
def aplicar_fix():
    data = request.json
    archivo = data.get('archivo', '')
    codigo_fix = data.get('codigo_fix', '')
    if not archivo or not codigo_fix or '..' in archivo:
        return jsonify({"ok": False, "error": "Invalido"})
    seguro, motivo = verificar_codigo_seguro(codigo_fix)
    if not seguro:
        return jsonify({"ok": False, "error": motivo})
    try:
        ast.parse(codigo_fix)
    except SyntaxError as e:
        return jsonify({"ok": False, "error": str(e)})
    ok, msg = exec_seguro(codigo_fix)
    if not ok:
        return jsonify({"ok": False, "error": msg})
    with open(os.path.join(AUTOGEN_DIR, archivo), 'w') as f:
        f.write(f"# FIX AUTORIZADO\n# {datetime.datetime.now().isoformat()}\n\n{codigo_fix}")
    cargar_rag()
    return jsonify({"ok": True, "mensaje": f"Fix aplicado: {archivo}"})

@app.route('/introspeccion')
def introspeccion():
    funciones = []
    try:
        lista = sorted([f for f in os.listdir(AUTOGEN_DIR) if f.endswith('.py')])
        for archivo in lista:
            try:
                with open(os.path.join(AUTOGEN_DIR, archivo)) as f:
                    codigo = f.read()
                desc = "Sin descripcion"
                valido = True
                lineas = len(codigo.split('\n'))
                try:
                    tree = ast.parse(codigo)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.FunctionDef):
                            if (node.body and isinstance(node.body[0], ast.Expr) and
                                    isinstance(node.body[0].value, ast.Constant)):
                                desc = str(node.body[0].value.value)[:100]
                            else:
                                desc = f"Funcion: {node.name}()"
                            break
                except SyntaxError:
                    valido = False
                    desc = "Error de sintaxis"
                mtime = os.path.getmtime(os.path.join(AUTOGEN_DIR, archivo))
                fecha = datetime.datetime.fromtimestamp(mtime).strftime('%d/%m %H:%M')
                funciones.append({
                    "nombre": archivo,
                    "descripcion": desc,
                    "valido": valido,
                    "lineas": lineas,
                    "fecha": fecha
                })
            except:
                pass
    except Exception as e:
        return jsonify({"funciones": [], "error": str(e)})
    return jsonify({"funciones": funciones, "total": len(funciones)})

@app.route('/rag/reload')
def rag_reload():
    ctx = cargar_rag()
    return jsonify({"ok": True, "chars": len(ctx)})

@app.route('/logs')
def logs():
    try:
        with open(os.path.expanduser("~/NEXUS/logs/supervisor_noche.log")) as f:
            lineas = f.readlines()
        return jsonify({"logs": lineas[-50:]})
    except:
        return jsonify({"logs": ["Sin logs"]})

ALLOWED_EXT = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

@app.route('/upload_avatar', methods=['POST'])
def upload_avatar():
    if 'file' not in request.files:
        return jsonify({"ok": False, "error": "Sin archivo"})
    file = request.files['file']
    if not file.filename:
        return jsonify({"ok": False, "error": "Sin nombre"})
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ALLOWED_EXT:
        return jsonify({"ok": False, "error": "Formato no permitido"})
    static_dir = os.path.join(BASE_DIR, 'static')
    os.makedirs(static_dir, exist_ok=True)
    filename = f"avatar.{ext}"
    file.save(os.path.join(static_dir, filename))
    return jsonify({"ok": True, "filename": filename, "url": f"/static/{filename}"})

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory(os.path.join(BASE_DIR, 'static'), filename)

@socketio.on('connect')
def on_connect():
    emit('status', {'msg': 'Arkani Nexus v4.0 Conectado'})

@socketio.on('mensaje')
def on_mensaje(data):
    sid = request.sid
    texto = data.get('texto', '').strip()
    if not texto:
        return

    def procesar():
        socketio.emit('typing', {'status': True}, room=sid, namespace='/')
        # Commander: intercepta comandos del sistema antes de Ollama
        cmd = commander.match_and_execute(texto)
        if cmd["executed"]:
            socketio.emit('respuesta', {
                'texto': cmd["response"],
                'action': cmd.get("action", ""),
                'param': cmd.get("param", ""),
                'nav_tab': cmd.get("nav_tab", ""),
                'timestamp': datetime.datetime.now().strftime('%H:%M:%S')
            }, room=sid, namespace='/')
            socketio.emit('typing', {'status': False}, room=sid, namespace='/')
            return
        try:
            from arkani_bridge import procesar as bridge_procesar
            respuesta = bridge_procesar(texto, engine=arkani)
        except Exception:
            respuesta = arkani.chat(texto) if arkani else "Motor no disponible"
        # Evolve: analiza la respuesta
        evolve_result = evolve_engine.process_chat_response(texto, respuesta)
        respuesta = evolve_result["response"]
        socketio.emit('respuesta', {
            'texto': respuesta,
            'action': '',
            'param': '',
            'nav_tab': '',
            'timestamp': datetime.datetime.now().strftime('%H:%M:%S')
        }, room=sid, namespace='/')
        socketio.emit('typing', {'status': False}, room=sid, namespace='/')

    socketio.start_background_task(procesar)

@app.route('/explorador/listar')
def explorador_listar():
    ruta = request.args.get('ruta', os.path.expanduser('~/NEXUS'))
    try:
        ruta_abs = os.path.realpath(os.path.expanduser(ruta))
        if not os.path.isdir(ruta_abs):
            return jsonify({"error": f"No es directorio: {ruta}"}), 400
        entradas = []
        for item in sorted(os.scandir(ruta_abs), key=lambda x: (not x.is_dir(), x.name.lower())):
            try:
                stat = item.stat()
                entradas.append({"nombre": item.name, "tipo": "dir" if item.is_dir() else "archivo",
                    "tamanio": stat.st_size if item.is_file() else None,
                    "fecha": datetime.datetime.fromtimestamp(stat.st_mtime).strftime('%d/%m %H:%M'),
                    "ruta": item.path})
            except:
                pass
        padre = str(os.path.dirname(ruta_abs)) if ruta_abs != '/' else None
        return jsonify({"ruta": ruta_abs, "padre": padre, "entradas": entradas})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/explorador/leer')
def explorador_leer():
    ruta = request.args.get('ruta', '')
    if not ruta:
        return jsonify({"error": "Sin ruta"}), 400
    try:
        ruta_abs = os.path.realpath(os.path.expanduser(ruta))
        if not os.path.isfile(ruta_abs):
            return jsonify({"error": "No es archivo"}), 404
        if os.path.getsize(ruta_abs) > 500_000:
            return jsonify({"error": "Archivo muy grande"}), 400
        with open(ruta_abs, 'r', encoding='utf-8', errors='replace') as f:
            contenido = f.read()
        return jsonify({"nombre": os.path.basename(ruta_abs), "ruta": ruta_abs,
                        "contenido": contenido[:20000], "truncado": len(contenido) > 20000})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/explorador/buscar')
def explorador_buscar():
    import fnmatch
    patron = request.args.get('patron', '')
    directorio = request.args.get('directorio', os.path.expanduser('~/NEXUS'))
    if not patron:
        return jsonify({"error": "Sin patron"}), 400
    try:
        directorio_abs = os.path.realpath(os.path.expanduser(directorio))
        resultados = []
        for root, dirs, files in os.walk(directorio_abs):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('__pycache__','venv')]
            for f in files:
                if fnmatch.fnmatch(f.lower(), patron.lower()):
                    ruta_completa = os.path.join(root, f)
                    try:
                        stat = os.stat(ruta_completa)
                        resultados.append({"nombre": f, "ruta": ruta_completa, "tamanio": stat.st_size})
                    except:
                        pass
            if len(resultados) >= 200:
                break
        return jsonify({"patron": patron, "total": len(resultados), "resultados": resultados})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

_nodos_conectados = {}

@app.route('/ping')
def ping():
    return jsonify({"status": "alive", "node_id": "arkani-main", "node_name": "Arkani NEXUS", "version": "4.0"})

@app.route('/m2m/estado')
def m2m_estado():
    import time
    activos = {nid: {**info, "hace": int(time.time() - info.get('last_seen', 0))} for nid, info in _nodos_conectados.items()}
    return jsonify({"nodos": activos, "total": len(activos)})

@app.route('/m2m/conectar', methods=['POST'])
def m2m_conectar():
    import time, uuid, requests as req
    data = request.json or {}
    url_remota = data.get('url', '').rstrip('/')
    if not url_remota:
        return jsonify({"ok": False, "error": "URL requerida"})
    try:
        r = req.get(f"{url_remota}/ping", timeout=5)
        if r.status_code != 200:
            return jsonify({"ok": False, "error": f"No responde: {r.status_code}"})
        info_remota = r.json()
        node_id = info_remota.get('node_id', str(uuid.uuid4())[:8])
        node_nombre = info_remota.get('node_name', url_remota)
        _nodos_conectados[node_id] = {"url": url_remota, "nombre": node_nombre, "last_seen": time.time()}
        return jsonify({"ok": True, "node_id": node_id, "nombre": node_nombre})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@app.route('/m2m/desconectar', methods=['POST'])
def m2m_desconectar():
    node_id = (request.json or {}).get('node_id', '')
    _nodos_conectados.pop(node_id, None)
    return jsonify({"ok": True})

@app.route('/m2m/enviar_archivo', methods=['POST'])
def m2m_enviar_archivo():
    import requests as req
    data = request.json or {}
    node_id = data.get('node_id', '')
    ruta_nxf = data.get('ruta', '')
    if node_id not in _nodos_conectados:
        return jsonify({"ok": False, "error": "Nodo no conectado"})
    if not ruta_nxf or not os.path.isfile(ruta_nxf):
        return jsonify({"ok": False, "error": "Archivo no existe"})
    info = _nodos_conectados[node_id]
    try:
        with open(ruta_nxf, 'rb') as f:
            r = req.post(f"{info['url']}/m2m/recibir_archivo",
                        files={'archivo': (os.path.basename(ruta_nxf), f, 'application/octet-stream')}, timeout=30)
        return jsonify(r.json())
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@app.route('/m2m/recibir_archivo', methods=['POST'])
def m2m_recibir_archivo():
    if 'archivo' not in request.files:
        return jsonify({"ok": False, "error": "Sin archivo"})
    archivo = request.files['archivo']
    nombre = archivo.filename or 'recibido.nxf'
    if not nombre.endswith('.nxf'):
        return jsonify({"ok": False, "error": "Solo .nxf permitido"})
    destino_dir = os.path.expanduser('~/NEXUS/recibidos')
    os.makedirs(destino_dir, exist_ok=True)
    archivo.save(os.path.join(destino_dir, nombre))
    return jsonify({"ok": True, "nombre": nombre})

@app.route('/m2m/archivos_recibidos')
def m2m_archivos_recibidos():
    destino_dir = os.path.expanduser('~/NEXUS/recibidos')
    os.makedirs(destino_dir, exist_ok=True)
    archivos = []
    for f in sorted(os.listdir(destino_dir)):
        if f.endswith('.nxf'):
            ruta = os.path.join(destino_dir, f)
            archivos.append({"nombre": f, "ruta": ruta, "tamanio": os.path.getsize(ruta)})
    return jsonify({"archivos": archivos})

@app.route('/fractal/ejecutar', methods=['POST'])
def fractal_ejecutar():
    # Usar vm persistente de ArkaniEngine (Paso 1)
    vm = arkani.vm if arkani and arkani.vm else None
    if not vm:
        return jsonify({"status": "ERROR", "error": "FractalVM no disponible"}), 500
    try:
        resultado = vm.ejecutar_todo()
        return jsonify({"status": "OK", "resultado": resultado})
    except Exception as e:
        return jsonify({"status": "ERROR", "error": str(e)}), 500

@app.route('/fractal/estado', methods=['GET'])
def fractal_estado():
    # Usar vm persistente de ArkaniEngine (Paso 1)
    vm = arkani.vm if arkani and arkani.vm else None
    if not vm:
        return jsonify({"error": "FractalVM no disponible"}), 500
    try:
        return jsonify(vm.estado())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/voz/generar', methods=['POST'])
def voz_generar():
    from nexus_voz import texto_a_voz
    texto = (request.json or {}).get('texto', '').strip()
    if not texto:
        return jsonify({"ok": False, "error": "Sin texto"})
    url = texto_a_voz(texto, nombre="respuesta")
    if url:
        return jsonify({"ok": True, "url": url})
    return jsonify({"ok": False, "error": "Error generando audio"})

@app.route('/voz/transcribir', methods=['POST'])
def voz_transcribir():
    from nexus_voz import audio_a_texto
    if 'audio' not in request.files:
        return jsonify({"ok": False, "error": "Sin archivo audio"})
    archivo = request.files['audio']
    ruta_tmp = os.path.join(os.path.expanduser("~/NEXUS/NEXUS-LANG/static/audio"), "entrada.wav")
    archivo.save(ruta_tmp)
    texto = audio_a_texto(ruta_tmp)
    if texto:
        return jsonify({"ok": True, "texto": texto})
    return jsonify({"ok": False, "error": "No se pudo transcribir"})

@app.route('/voz/modo_activo', methods=['POST'])
def voz_modo_activo():
    from nexus_voz import iniciar_escucha_activa, detener_escucha_activa, escucha_activa_estado
    accion = (request.json or {}).get('accion', '')

    def on_comando(texto):
        if not arkani:
            return
        respuesta = arkani.chat(texto)
        from nexus_voz import texto_a_voz
        url_audio = texto_a_voz(respuesta, nombre="respuesta_activa")
        socketio.emit('voz_respuesta', {
            'texto_usuario': texto,
            'respuesta':     respuesta,
            'audio_url':     url_audio,
            'timestamp':     datetime.datetime.now().strftime('%H:%M:%S')
        })

    if accion == 'activar':
        iniciar_escucha_activa(on_comando)
        return jsonify({"ok": True, "estado": "activo", "wake_word": "arkani"})
    elif accion == 'desactivar':
        detener_escucha_activa()
        return jsonify({"ok": True, "estado": "inactivo"})
    else:
        return jsonify({"ok": True, "estado": "activo" if escucha_activa_estado() else "inactivo"})

@app.route('/voz/estado')
def voz_estado():
    from nexus_voz import escucha_activa_estado
    piper_ok  = os.path.exists(os.path.expanduser("~/NEXUS/piper/piper"))
    modelo_ok = os.path.exists(os.path.expanduser("~/NEXUS/piper/es_MX-claude-high.onnx"))
    try:
        import whisper
        whisper_ok = True
    except:
        whisper_ok = False
    return jsonify({
        "piper":         piper_ok,
        "modelo_voz":    modelo_ok,
        "whisper":       whisper_ok,
        "escucha_activa": escucha_activa_estado()
    })

@app.route('/help')
def help_manual():
    ruta = os.path.join(BASE_DIR, 'ARKANI_HELP.txt')
    try:
        with open(ruta, 'r', encoding='utf-8') as f:
            return f.read(), 200, {'Content-Type': 'text/plain; charset=utf-8'}
    except:
        return 'Manual no disponible.', 404


@app.route('/subir_archivo', methods=['POST'])
def subir_archivo():
    if 'archivo' not in request.files:
        return jsonify({"ok": False, "error": "Sin archivo"}), 400
    archivo = request.files['archivo']
    aprende = request.form.get('aprende', 'false').lower() == 'true'
    nombre  = archivo.filename or 'sin_nombre'
    ext     = os.path.splitext(nombre)[1].lower()
    PERMITIDOS = {'.txt', '.py', '.md', '.pdf', '.png', '.jpg', '.jpeg', '.gif',
                  '.webp', '.docx', '.json', '.nl'}
    if ext not in PERMITIDOS:
        return jsonify({"ok": False,
                        "error": f"Extension {ext} no soportada. Permitidos: {', '.join(sorted(PERMITIDOS))}"}), 400
    destino_dir = MEMORIA_PERM_DIR if aprende else PAPELERA_DIR
    timestamp   = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    nombre_safe = f"{timestamp}_{nombre.replace(' ', '_')}"
    ruta_final  = os.path.join(destino_dir, nombre_safe)
    archivo.save(ruta_final)
    contenido = _leer_contenido(ruta_final, nombre)
    chars     = len(contenido)
    idx  = _cargar_indice()
    meta = {
        "nombre":  nombre,
        "archivo": nombre_safe,
        "ruta":    ruta_final,
        "fecha":   datetime.datetime.now().isoformat(),
        "chars":   chars,
        "aprende": aprende,
        "expira":  None if aprende else (
            datetime.datetime.now() + datetime.timedelta(days=30)).isoformat()
    }
    if aprende:
        idx["permanentes"].append(meta)
        if arkani:
            arkani.mem.aprender(f"archivo:{nombre}", contenido[:500])
            arkani.set_contexto_propio(
                arkani.ctx_propio + f"\n\n### APRENDIDO: {nombre}\n{contenido[:500]}"
            )
    else:
        idx["papelera"].append(meta)
    _guardar_indice(idx)
    return jsonify({
        "ok":      True,
        "modo":    "permanente" if aprende else "papelera_30dias",
        "archivo": nombre_safe,
        "chars":   chars,
        "preview": contenido[:300],
        "mensaje": (f"Arkani aprendio: {nombre} ({chars} chars)"
                    if aprende else f"Temporal: {nombre} (borra en 30 dias)")
    })

@app.route('/archivos_memoria')
def archivos_memoria():
    idx = _cargar_indice()
    return jsonify({
        "permanentes": idx.get("permanentes", []),
        "papelera":    idx.get("papelera", []),
        "total_perm":  len(idx.get("permanentes", [])),
        "total_pap":   len(idx.get("papelera", []))
    })

@app.route('/vaciar_papelera', methods=['POST'])
def vaciar_papelera():
    idx   = _cargar_indice()
    ahora = datetime.datetime.now()
    validos, borrados = [], 0
    for item in idx.get("papelera", []):
        try:
            if datetime.datetime.fromisoformat(item.get("expira","")) < ahora:
                try: os.remove(item["ruta"])
                except Exception: pass
                borrados += 1
                continue
        except Exception: pass
        validos.append(item)
    idx["papelera"] = validos
    _guardar_indice(idx)
    return jsonify({"ok": True, "borrados": borrados, "restantes": len(validos)})

@app.route('/leer_archivo_memoria')
def leer_archivo_memoria():
    nombre = request.args.get('nombre', '')
    aprende = request.args.get('aprende', 'true').lower() == 'true'
    if not nombre or '..' in nombre:
        return jsonify({"error": "Nombre invalido"}), 400
    ruta = os.path.join(MEMORIA_PERM_DIR if aprende else PAPELERA_DIR, nombre)
    if not os.path.exists(ruta):
        return jsonify({"error": "No encontrado"}), 404
    contenido = _leer_contenido(ruta, nombre)
    return jsonify({"nombre": nombre, "contenido": contenido, "chars": len(contenido)})


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
        lines = r.stdout.strip().split('\n')
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


# ═══════════════════════════════════════════════════════════
# NEXUS-MAIL — Asistente de correo
# ═══════════════════════════════════════════════════════════
_mail_config = {}
_mail_correos = []

@app.route('/mail/conectar', methods=['POST'])
def mail_conectar():
    try:
        data = request.json or {}
        _mail_config['proveedor'] = data.get('proveedor', 'gmail')
        _mail_config['email'] = data.get('email', '')
        return jsonify({"ok": True, "msg": f"Configurado {_mail_config['email']}"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@app.route('/mail/bandeja')
def mail_bandeja():
    try:
        return jsonify({"correos": _mail_correos, "total": len(_mail_correos),
                       "nota": "Integración IMAP en desarrollo"})
    except Exception as e:
        return jsonify({"correos": [], "error": str(e)})

@app.route('/mail/redactar', methods=['POST'])
def mail_redactar():
    try:
        data = request.json or {}
        instruccion = data.get('instruccion', '')
        destinatario = data.get('destinatario', '')
        if not instruccion:
            return jsonify({"ok": False, "error": "Sin instrucción"})
        if arkani:
            prompt = f"Redacta un correo profesional en español. Instrucción: {instruccion}. Destinatario: {destinatario}"
            borrador = arkani.chat(prompt)
            return jsonify({"ok": True, "borrador": borrador})
        return jsonify({"ok": False, "error": "Arkani no disponible"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@app.route('/mail/enviar', methods=['POST'])
def mail_enviar():
    try:
        data = request.json or {}
        return jsonify({"ok": False, "error": "Envío SMTP en desarrollo — integración próxima versión"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

if __name__ == '__main__':
    print("\n" + "=" * 50)
    print("  ARKANI WEB v4.0 - Panel de Control")
    print(f"  Engine: {'OK' if ARKANI_OK else 'ERROR'}")
    print("  http://0.0.0.0:8081")
    print("=" * 50 + "\n")
    os.makedirs(os.path.expanduser("~/NEXUS/logs"), exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, 'templates'), exist_ok=True)
    os.makedirs(os.path.expanduser("~/NEXUS/recibidos"), exist_ok=True)
    os.makedirs(MEMORIA_PERM_DIR, exist_ok=True)
    os.makedirs(PAPELERA_DIR, exist_ok=True)
    cargar_rag()
    if UPDATER_OK:
        updater_rutas(app)
    socketio.run(app, host="0.0.0.0", port=8081, debug=False, allow_unsafe_werkzeug=True)
