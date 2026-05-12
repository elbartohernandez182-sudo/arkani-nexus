import os
import json
from flask import Flask, jsonify, request
from flask_cors import CORS
from nexus_core import memory

app = Flask(__name__)
CORS(app)

@app.route('/arkani/command', methods=['POST'])
def ejecutar_remoto():
    data = request.json
    instruccion = data.get("cmd")
    tipo = data.get("type", "CODE") # CODE para programar, INFO para memoria
    
    if tipo == "CODE":
        # Arkani escribe el código automáticamente en la carpeta autogen
        filename = data.get("name", "remote_script.py")
        path = os.path.expanduser(f"~/NEXUS/NEXUS-LANG/autogen/{filename}")
        with open(path, "w") as f:
            f.write(instruccion)
        
        # Registrar en la Memoria de Conversación Precisa
        from nexus_omni_core import registrar_evento
        registrar_evento("REMOTE_WRITE", f"Escrito desde dispositivo remoto: {filename}")
        
        return jsonify({"status": "Ejecutado", "path": path})
    
    return jsonify({"status": "Error", "msg": "Tipo de comando no reconocido"})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5001)
