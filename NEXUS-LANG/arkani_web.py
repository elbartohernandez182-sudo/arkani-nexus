import os, sys, json, ast, datetime
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'arkani1979nexus'
socketio = SocketIO(app, cors_allowed_origins="*")
BASE_DIR = os.path.expanduser("~/NEXUS/NEXUS-LANG")
AUTOGEN_DIR = os.path.join(BASE_DIR, "autogen")
sys.path.insert(0, BASE_DIR)

try:
    from arkani_engine import ArkaniEngine, verificar_codigo_seguro, exec_seguro
    arkani = ArkaniEngine()
    ARKANI_OK = True
except Exception as e:
    ARKANI_OK = False
    arkani = None
    print(f"warning: {e}")

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
        respuesta = arkani.chat(texto) if arkani else "Motor no disponible"
        socketio.emit('respuesta', {
            'texto': respuesta,
            'timestamp': datetime.datetime.now().strftime('%H:%M:%S')
        }, room=sid, namespace='/')
        socketio.emit('typing', {'status': False}, room=sid, namespace='/')

    socketio.start_background_task(procesar)

if __name__ == '__main__':
    print("\n" + "=" * 50)
    print("  ARKANI WEB v4.0 - Panel de Control")
    print(f"  Engine: {'OK' if ARKANI_OK else 'ERROR'}")
    print("  http://0.0.0.0:8081")
    print("=" * 50 + "\n")
    os.makedirs(os.path.expanduser("~/NEXUS/logs"), exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, 'templates'), exist_ok=True)
    cargar_rag()
    socketio.run(app, host='0.0.0.0', port=8081, debug=False)
