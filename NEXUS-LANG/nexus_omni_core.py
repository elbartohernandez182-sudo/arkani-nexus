import os
import json
from datetime import datetime
from flask import Flask, jsonify, request
from flask_cors import CORS

# Configuración de Rutas Maestras
BASE_DIR = os.path.expanduser("~/NEXUS/NEXUS-LANG")
MEM_PATH = os.path.join(BASE_DIR, "universal_memory.json")
LOG_PATH = os.path.join(BASE_DIR, "simbiosis_history.json")

app = Flask(__name__)
CORS(app)

def registrar_evento(accion, detalle):
    """Guarda cada interacción para Memoria de Conversación Precisa."""
    historial = []
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH, 'r') as f:
            historial = json.load(f)
    
    historial.append({
        "t": datetime.now().isoformat(),
        "a": accion,
        "d": detalle
    })
    
    with open(LOG_PATH, 'w') as f:
        json.dump(historial, f, indent=2)

@app.route('/nexus/status', methods=['GET'])
def status():
    # Optimizado para Smartwatch (ligero)
    return jsonify({
        "arkani": "ONLINE",
        "sync": True,
        "last_event": datetime.now().strftime("%H:%M:%S")
    })

@app.route('/nexus/brain', methods=['POST'])
def auto_programar():
    """Endpoint para que yo reciba órdenes y auto-escriba código remotamente."""
    data = request.json
    try:
        module_name = data.get('name', 'autogen_module')
        code = data.get('code', '')
        
        path = os.path.join(BASE_DIR, "autogen", f"{module_name}.py")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        with open(path, "w") as f:
            f.write(f"# NEXUS-AUTO-CODE\n{code}")
            
        registrar_evento("AUTO_PROGRAMACION", f"Módulo {module_name} creado.")
        return jsonify({"status": "Success", "path": path})
    except Exception as e:
        return jsonify({"status": "Error", "msg": str(e)})

if __name__ == "__main__":
    registrar_evento("SISTEMA", "Conectividad Omnipresente Activada")
    app.run(host='0.0.0.0', port=5000)
