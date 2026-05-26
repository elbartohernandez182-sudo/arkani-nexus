import os
import sys
import json
import datetime
import threading
import subprocess
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit

# ============================================
# ARKANI WEB v1.0 - Interfaz Web Flask
# Acceso desde cualquier navegador
# Constructor: Medico Radiologo, Xalapa
# ============================================

app = Flask(__name__)
app.config['SECRET_KEY'] = 'arkani1979nexus'
socketio = SocketIO(app, cors_allowed_origins="*")

BASE_DIR = os.path.expanduser("~/NEXUS/NEXUS-LANG")
sys.path.insert(0, BASE_DIR)

# Importar Arkani
try:
    from arkani_core import RAGAgent as ArkaniCore
    arkani = ArkaniCore()
    ARKANI_OK = True
except Exception as e:
    ARKANI_OK = False
    print(f"Arkani core no disponible: {e}")

# ============================================
# RUTAS PRINCIPALES
# ============================================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/status')
def status():
    """Estado del sistema"""
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=1)
        ram = psutil.virtual_memory().percent
    except:
        cpu = 0
        ram = 0

    # Leer memoria de Arkani
    memoria_path = os.path.join(BASE_DIR, 'memoria_arkani.json')
    try:
        with open(memoria_path, 'r') as f:
            memoria = json.load(f)
        conversaciones = len(memoria.get('conversaciones', []))
        pendientes = len(memoria.get('pendientes', []))
        aprendizajes = len(memoria.get('aprendizajes', []))
    except:
        conversaciones = pendientes = aprendizajes = 0

    return jsonify({
        'cpu': cpu,
        'ram': ram,
        'arkani_ok': ARKANI_OK,
        'conversaciones': conversaciones,
        'pendientes': pendientes,
        'aprendizajes': aprendizajes,
        'timestamp': datetime.datetime.now().strftime('%H:%M:%S')
    })

@app.route('/tasks', methods=['GET', 'POST'])
def tasks():
    """Ver y agregar tareas"""
    tareas_path = os.path.join(BASE_DIR, 'tareas_pendientes.json')

    if request.method == 'POST':
        data = request.json
        try:
            with open(tareas_path, 'r') as f:
                tareas = json.load(f)
        except:
            tareas = {"tareas": []}

        nueva = {
            "id": f"tarea_{len(tareas['tareas'])+1:03d}",
            "objetivo": data.get('objetivo', ''),
            "prioridad": data.get('prioridad', 'normal'),
            "estado": "pendiente",
            "creada": datetime.datetime.now().isoformat()
        }
        tareas['tareas'].append(nueva)

        with open(tareas_path, 'w') as f:
            json.dump(tareas, f, indent=2, ensure_ascii=False)

        return jsonify({"ok": True, "tarea": nueva})

    else:
        try:
            with open(tareas_path, 'r') as f:
                tareas = json.load(f)
        except:
            tareas = {"tareas": []}
        return jsonify(tareas)

@app.route('/logs')
def logs():
    """Ver logs del supervisor"""
    log_path = os.path.expanduser("~/NEXUS/logs/supervisor_noche.log")
    try:
        with open(log_path, 'r') as f:
            lineas = f.readlines()
        ultimas = lineas[-50:] if len(lineas) > 50 else lineas
        return jsonify({"logs": ultimas})
    except:
        return jsonify({"logs": ["No hay logs disponibles aun"]})

# ============================================
# WEBSOCKET - Chat en tiempo real
# ============================================

@socketio.on('connect')
def on_connect():
    emit('status', {'msg': 'Conectado a Arkani Nexus'})

@socketio.on('mensaje')
def on_mensaje(data):
    sid = request.sid
    texto = data.get('texto', '').strip()
    if not texto:
        return

    def procesar():
        with app.app_context():
            socketio.emit('typing', {'status': True}, room=sid, namespace='/')

        # MODO AGENTE - detectar comando autoprograma:
        if texto.lower().startswith("autoprograma:"):
            objetivo = texto[13:].strip()
            try:
                from arkani_agent import correr_agente
                respuesta = correr_agente(objetivo, verbose=False)
                respuesta = f"Agente completo:\n{respuesta}"
            except Exception as e:
                respuesta = f"Error en agente: {e}"
        elif ARKANI_OK:
            try:
                ctx, src = arkani.buscar(texto)
                from arkani_core import main as arkani_main
                import requests as req
                r = req.post("http://127.0.0.1:11434/api/generate",
                    json={"model":"qwen2.5:7b","prompt":f"{texto}","stream":False,
                    "options":{"num_predict":150,"temperature":0.7}},timeout=400)
                respuesta = r.json().get("response","Sin respuesta").strip() if r.status_code==200 else "Error Ollama"
            except Exception as e:
                respuesta = f"Error: {e}"
        else:
            # Fallback sin Arkani core
            respuesta = respuesta_simple(texto)

        socketio.emit('respuesta', {
            'texto': respuesta,
            'timestamp': datetime.datetime.now().strftime('%H:%M:%S')
        }, room=sid, namespace='/')
        socketio.emit('typing', {'status': False}, room=sid, namespace='/')

    socketio.start_background_task(procesar)

def respuesta_simple(texto):
    """Respuesta basica si Arkani core no esta disponible"""
    if 'hola' in texto.lower():
        return "Hola! Estoy en modo basico. Verifica arkani_core.py"
    return f"Recibido: {texto} (modo basico)"

# ============================================
# MAIN
# ============================================

if __name__ == '__main__':
    print("\n" + "="*50)
    print("  ARKANI WEB v1.0")
    print("="*50)
    print(f"  Arkani Core: {'OK' if ARKANI_OK else 'NO DISPONIBLE'}")
    print(f"  Acceso local:   http://localhost:8080")
    print(f"  Acceso red:     http://0.0.0.0:8080")
    print("="*50 + "\n")

    # Crear directorios necesarios
    os.makedirs(os.path.expanduser("~/NEXUS/logs"), exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, 'templates'), exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, 'static'), exist_ok=True)

    socketio.run(app, host='0.0.0.0', port=8081, debug=False)

