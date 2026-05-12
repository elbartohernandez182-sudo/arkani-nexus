from flask import Flask, jsonify, request
from flask_cors import CORS
import os
import json
from nexus_recovery import recuperar_conciencia_arkani

app = Flask(__name__)
CORS(app)

@app.route('/brain/status', methods=['GET'])
def get_status():
    root = recuperar_conciencia_arkani()
    return jsonify({
        "status": "ONLINE",
        "simbiosis": "ACTIVE",
        "last_memory": root.last_update,
        "nodes": list(root.children.keys())
    })

@app.route('/brain/sync', methods=['POST'])
def sync_data():
    data = request.json
    root = recuperar_conciencia_arkani()
    # Auto-programación: Arkani crea un nodo basado en lo que mandas desde el celular
    new_node = root.manage_child(data['node_name'], data['value'], data.get('role', 'DATA'))
    
    # Guardar snapshot actualizado
    with open(os.path.expanduser("~/NEXUS/NEXUS-LANG/system_snapshot.json"), "w") as f:
        json.dump(root.export_state(), f, indent=4)
        
    return jsonify({"message": "Sincronización Exitosa", "node": new_node.name})

if __name__ == "__main__":
    # Correr en puerto 5000 para acceso remoto
    app.run(host='0.0.0.0', port=5000)
