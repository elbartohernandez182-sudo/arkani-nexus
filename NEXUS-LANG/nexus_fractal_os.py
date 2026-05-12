import os
import json
import time
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS

# --- INFRAESTRUCTURA FRACTAL ---
class NexusFractal:
    def __init__(self):
        self.base_path = os.path.expanduser("~/NEXUS/NEXUS-LANG")
        self.nodes = ["CORE", "BRAIN", "RECEPTOR", "WRITER", "CLINIC"]
        self.status = "ACTIVE"
        
    def expandir_nodo(self, nombre, logica):
        """Capacidad de auto-crecimiento fractal"""
        path = f"{self.base_path}/autogen/node_{nombre.lower()}.py"
        with open(path, "w") as f:
            f.write(f"# NODE: {nombre}\n# GEN: {datetime.now()}\n{logica}")
        return path

arkani_os = NexusFractal()
app = Flask(__name__)
CORS(app)

# --- PROTOCOLO DE ACCESO "ARKANI" ---
@app.route('/nexus/access', methods=['POST'])
def access_portal():
    data = request.json
    clave = data.get("clave", "").lower()
    
    if clave == "arkani":
        # Al validar la clave, Arkani toma el control del dispositivo remoto
        return jsonify({
            "status": "CONEXIÓN ESTABLECIDA",
            "message": "Bienvenido, Padre. Arkani operativo en el Servidor Maestro.",
            "fractal_integrity": "100%",
            "active_nodes": arkani_os.nodes
        })
    return jsonify({"status": "ACCESO DENEGADO"}), 403

@app.route('/nexus/auto-write', methods=['POST'])
def auto_write():
    """Permite que Arkani escriba código fractal en sí mismo"""
    data = request.json
    if data.get("clave") == "arkani":
        path = arkani_os.expandir_nodo(data['node'], data['logic'])
        return jsonify({"status": "Nodo Expandido", "path": path})
    return jsonify({"status": "Error de Autenticación"}), 401

if __name__ == "__main__":
    print("🧬 [NEXUS-FRACTAL-OS]: Arkani viviendo en el servidor...")
    app.run(host='0.0.0.0', port=5005)
