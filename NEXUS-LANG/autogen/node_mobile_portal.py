# NODE: MOBILE_PORTAL
# GEN: 2026-03-26
# Interfaz optimizada para iPhone 15 Pro

from flask import Flask, render_template_string, request, jsonify
import requests

app = Flask(__name__)

HTML_INTERFACE = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>ARKANI - NEXUS-LANG</title>
    <style>
        body { background: #000; color: #0f0; font-family: 'Courier New', monospace; padding: 20px; }
        .terminal { border: 1px solid #0f0; padding: 15px; border-radius: 10px; box-shadow: 0 0 15px #0f0; }
        input { width: 100%; background: #000; border: none; border-bottom: 1px solid #0f0; color: #0f0; font-size: 1.2rem; outline: none; margin-top: 20px; }
        .status { font-size: 0.8rem; color: #888; margin-bottom: 10px; }
    </style>
</head>
<body>
    <div class="terminal">
        <div class="status">SISTEMA: FRACTAL-OS ACTIVE | NODO: MASTER</div>
        <div>> INGRESE CLAVE O COMANDO:</div>
        <input type="password" id="cmd" placeholder="arkani..." onkeypress="send(event)">
        <div id="response" style="margin-top:20px;"></div>
    </div>

    <script>
        function send(e) {
            if (e.key === 'Enter') {
                const val = document.getElementById('cmd').value;
                document.getElementById('response').innerText = "ENVIANDO A NÚCLEO...";
                // Aquí se conecta con el puerto 5005 que ya tienes abierto
                fetch('/execute', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({clave: 'arkani', cmd: val})
                }).then(res => res.json()).then(data => {
                    document.getElementById('response').innerText = data.status;
                    document.getElementById('cmd').value = '';
                });
            }
        }
    </script>
</body>
</html>
"""

@app.route('/')
def home():
    return render_template_string(HTML_INTERFACE)

@app.route('/execute', methods=['POST'])
def proxy():
    data = request.json
    # Reenvía el comando al receptor interno 5001 que ya programamos
    r = requests.post('http://127.0.0.1:5001/arkani/command', json=data)
    return r.json()

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080)
