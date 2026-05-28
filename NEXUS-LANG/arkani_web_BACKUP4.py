import os
import sys
import json
import datetime
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit

# ============================================
# ARKANI WEB v3.0 — Motor Unificado
# Constructor: Medico Radiologo, Xalapa
# ============================================

app = Flask(__name__)
app.config['SECRET_KEY'] = 'arkani1979nexus'
socketio = SocketIO(app, cors_allowed_origins="*")

BASE_DIR = os.path.expanduser("~/NEXUS/NEXUS-LANG")
sys.path.insert(0, BASE_DIR)

# ── Cargar motor unificado ────────────────────
try:
    from arkani_engine import ArkaniEngine
    arkani = ArkaniEngine()
    ARKANI_OK = True
except Exception as e:
    ARKANI_OK = False
    arkani = None
    print(f"⚠️ ArkaniEngine no disponible: {e}")

# ── RAG propio ────────────────────────────────
def cargar_contexto_rag():
    archivos = [
        "arkani_engine.py",
        "arkani_tools.py",
        "nexus_fractal_compiler.py",
        "autogen/fn_corregir_terminologia.py",
        "autogen/fn_validador_simetria.py",
        "autogen/fn_calcular_volumen_lesion.py",
    ]
    fragmentos = []
    for nombre in archivos:
        ruta = os.path.join(BASE_DIR, nombre)
        try:
            with open(ruta) as f:
                contenido = f.read(1000)
            fragmentos.append(f"### {nombre}\n{contenido}")
        except Exception:
            pass
    # Lista de nodos autogen
    autogen = os.path.join(BASE_DIR, "autogen")
    try:
        nodos = sorted([f for f in os.listdir(autogen) if f.endswith('.py')])
        fragmentos.append("### NODOS AUTOGEN\n" + "\n".join(nodos))
    except Exception:
        pass
    contexto = "\n\n".join(fragmentos)
    if arkani:
        arkani.set_contexto_propio(contexto)
    print(f"🧠 [RAG]: {len(fragmentos)} archivos, {len(contexto)} chars")
    return contexto

# ── Rutas ─────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/status')
def status():
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=1)
        ram = psutil.virtual_memory().percent
    except Exception:
        cpu = ram = 0
    info = arkani.resumen() if arkani else {}
    return jsonify({
        'cpu': cpu, 'ram': ram,
        'arkani_ok': ARKANI_OK,
        **info,
        'timestamp': datetime.datetime.now().strftime('%H:%M:%S')
    })

@app.route('/tasks', methods=['GET', 'POST'])
def tasks():
    path = os.path.join(BASE_DIR, 'tareas_pendientes.json')
    if request.method == 'POST':
        data = request.json
        try:
            with open(path) as f: tareas = json.load(f)
        except Exception:
            tareas = {"tareas": []}
        tareas['tareas'].append({
            "id": f"tarea_{len(tareas['tareas'])+1:03d}",
            "objetivo": data.get('objetivo', ''),
            "prioridad": data.get('prioridad', 'normal'),
            "estado": "pendiente",
            "creada": datetime.datetime.now().isoformat()
        })
        with open(path, 'w') as f:
            json.dump(tareas, f, indent=2, ensure_ascii=False)
        return jsonify({"ok": True})
    try:
        with open(path) as f: return jsonify(json.load(f))
    except Exception:
        return jsonify({"tareas": []})

@app.route('/logs')
def logs():
    try:
        with open(os.path.expanduser("~/NEXUS/logs/supervisor_noche.log")) as f:
            lineas = f.readlines()
        return jsonify({"logs": lineas[-50:]})
    except Exception:
        return jsonify({"logs": ["Sin logs disponibles"]})

@app.route('/rag/reload')
def rag_reload():
    ctx = cargar_contexto_rag()
    return jsonify({"ok": True, "chars": len(ctx)})

@app.route('/capacidades')
def capacidades():
    return jsonify({"capacidades": arkani.capacidades() if arkani else "N/A"})

@app.route('/hipocampo')
def hipocampo():
    if not arkani:
        return jsonify({"error": "Arkani no disponible"})
    instr = arkani.motor.hipocampo.instructions
    return jsonify({
        "total": len(instr),
        "bytes": len(instr) * 16,
        "resumen": arkani.motor.hipocampo.resumen(),
        "instrucciones": [str(i) for i in instr]
    })

# ── WebSocket ──────────────────────────────────

@socketio.on('connect')
def on_connect():
    emit('status', {'msg': '🧠 Arkani Engine v3.0 conectado'})

@socketio.on('mensaje')
def on_mensaje(data):
    sid  = request.sid
    texto = data.get('texto', '').strip()
    if not texto:
        return

    def procesar():
        socketio.emit('typing', {'status': True}, room=sid, namespace='/')

        if not arkani:
            respuesta = "⚠️ Motor no disponible. Verifica arkani_engine.py"
        else:
            respuesta = arkani.chat(texto)

        socketio.emit('respuesta', {
            'texto': respuesta,
            'timestamp': datetime.datetime.now().strftime('%H:%M:%S')
        }, room=sid, namespace='/')
        socketio.emit('typing', {'status': False}, room=sid, namespace='/')

    socketio.start_background_task(procesar)

# ── Main ───────────────────────────────────────

if __name__ == '__main__':
    print("\n" + "="*50)
    print("  ARKANI WEB v3.0 — Motor Unificado")
    print("="*50)
    print(f"  Engine: {'OK' if ARKANI_OK else 'NO DISPONIBLE'}")
    print(f"  Acceso: http://0.0.0.0:8081")
    print(f"  Rutas extra: /hipocampo /capacidades /rag/reload")
    print("="*50 + "\n")

    os.makedirs(os.path.expanduser("~/NEXUS/logs"), exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, 'templates'), exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, 'static'), exist_ok=True)

    cargar_contexto_rag()
    socketio.run(app, host='0.0.0.0', port=8081, debug=False)
