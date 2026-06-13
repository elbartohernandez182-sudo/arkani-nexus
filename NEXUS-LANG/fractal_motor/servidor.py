"""
servidor.py — ARKANI Server (reemplazo de Ollama)
===================================================
Protocolo Wardenclyffe — Motor Fractal v1.0

Servidor HTTP que expone FractalLM con API compatible con Ollama.
ARKANI no nota la diferencia — solo cambia quién responde.

ENDPOINTS:
  GET  /                  → info del servidor
  GET  /health            → estado de salud
  GET  /api/tags          → lista de modelos (compat Ollama)
  POST /api/generate      → generación de texto (compat Ollama)
  POST /api/chat          → chat con formato de mensajes
  GET  /api/evolve        → EVOLVE: inspección propia del modelo
  POST /api/evolve/reset  → EVOLVE: reinicia una capa

USO:
    python3 servidor.py --puerto 11435 --modelo ./fractal_model

  Para que ARKANI lo use, en arkani_engine.py cambiar:
    OLLAMA_URL = "http://localhost:11435/api/generate"
"""

import json
import time
import argparse
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from datetime import datetime

import numpy as np

from modelo import FractalLM, FractalLMConfig, CONFIGS
from tokenizer import FractalTokenizer
from inferencia import generar
from operaciones import SUM, IF, LOOP, SPAWN, FOLD, LINK, EVOLVE, historial


# ─────────────────────────────────────────────────────────────────────────────
# ESTADO GLOBAL DEL SERVIDOR
# ─────────────────────────────────────────────────────────────────────────────
class ArkaniServerState:
    """Estado compartido del servidor — modelo, tokenizer, estadísticas."""

    def __init__(self):
        self.modelo:     FractalLM        = None
        self.tokenizer:  FractalTokenizer = None
        self.nombre_modelo = "arkani-fractal:latest"
        self.inicio     = datetime.now()
        self.stats = {
            'requests_totales':  0,
            'tokens_generados':  0,
            'tiempo_total_seg':  0.0,
        }
        self.lock = threading.Lock()

    def cargar_modelo(self, directorio_modelo: str = None, config_nombre: str = "mini"):
        """Carga el modelo y tokenizador desde disco, o crea uno nuevo."""
        if directorio_modelo and Path(directorio_modelo).exists():
            print(f"Cargando modelo desde: {directorio_modelo}")
            self.modelo = FractalLM.cargar(directorio_modelo)

            tok_dir = f"{directorio_modelo}/tokenizer"
            if Path(tok_dir).exists():
                self.tokenizer = FractalTokenizer.cargar(tok_dir)
            else:
                print("Tokenizador no encontrado, creando uno nuevo")
                self.tokenizer = self._tokenizer_default()
        else:
            print(f"Creando modelo nuevo: config '{config_nombre}'")
            config = CONFIGS.get(config_nombre, CONFIGS["mini"])
            self.modelo = FractalLM(config)
            self.tokenizer = self._tokenizer_default(vocab_size=config.vocab_size)

        params = self.modelo.contar_parametros()
        print(f"Modelo listo: {self.modelo.config.nombre}")
        print(f"  Parametros: {params['total_M']}M")
        print(f"  RAM:        {params['ram_fp32_mb']}MB")
        print(f"  Vocab:      {len(self.tokenizer.vocab)} tokens")

    def _tokenizer_default(self, vocab_size: int = 8000) -> FractalTokenizer:
        """Tokenizador basico entrenado en corpus fractal minimo."""
        corpus = [
            "Soy ARKANI asistente fractal del Protocolo Wardenclyffe",
            "SPAWN analiza FOLD sintetiza LINK conecta EVOLVE corrige",
            "SUM integra IF bifurca LOOP itera",
            "el motor fractal corre en Python puro sin dependencias",
            "Bibliotecario Perfecto sabe donde buscar la informacion",
        ] * 30
        tok = FractalTokenizer(vocab_size=vocab_size)
        tok.entrenar(corpus, verbose=False)
        return tok


estado = ArkaniServerState()


# ─────────────────────────────────────────────────────────────────────────────
# HANDLER HTTP — compatible con API de Ollama
# ─────────────────────────────────────────────────────────────────────────────
class ArkaniHandler(BaseHTTPRequestHandler):
    """
    Maneja requests HTTP — API compatible con Ollama
    para no romper clientes existentes (arkani_engine.py).
    """

    # ── GET ──────────────────────────────────────────────────────────────────

    def do_GET(self):
        try:
            if self.path == "/":
                self._info_servidor()
            elif self.path == "/health":
                self._health()
            elif self.path == "/api/tags":
                self._tags()
            elif self.path == "/api/evolve":
                self._evolve_inspeccion()
            elif self.path.startswith("/api/historial"):
                self._historial_operaciones()
            else:
                self._responder(404, {"error": "endpoint no encontrado", "path": self.path})
        except Exception as e:
            self._responder(500, {"error": str(e)})

    # ── POST ─────────────────────────────────────────────────────────────────

    def do_POST(self):
        try:
            largo = int(self.headers.get("Content-Length", 0))
            body_raw = self.rfile.read(largo) if largo > 0 else b"{}"
            body = json.loads(body_raw)

            if self.path == "/api/generate":
                self._generate(body)
            elif self.path == "/api/chat":
                self._chat(body)
            elif self.path == "/api/evolve/reset":
                self._evolve_reset(body)
            else:
                self._responder(404, {"error": "endpoint no encontrado", "path": self.path})

        except json.JSONDecodeError:
            self._responder(400, {"error": "JSON invalido"})
        except Exception as e:
            self._responder(500, {"error": str(e)})

    # ── ENDPOINTS ────────────────────────────────────────────────────────────

    def _info_servidor(self):
        params = estado.modelo.contar_parametros()
        self._responder(200, {
            "servidor":   "ARKANI Server",
            "version":    "1.0",
            "protocolo":  "Wardenclyffe",
            "modelo":     estado.modelo.config.nombre,
            "parametros": f"{params['total_M']}M",
            "ram_mb":     params['ram_fp32_mb'],
            "uptime_seg": (datetime.now() - estado.inicio).total_seconds(),
            "mensaje":    "Motor fractal - sin Ollama, sin CUDA, 100% Python",
        })

    def _health(self):
        self._responder(200, {
            "status": "ok",
            "modelo": estado.modelo.config.nombre,
            "stats":  estado.stats,
        })

    def _tags(self):
        """Compatible con GET /api/tags de Ollama - lista modelos disponibles."""
        params = estado.modelo.contar_parametros()
        self._responder(200, {
            "models": [{
                "name":    estado.nombre_modelo,
                "size":    int(params['ram_fp32_mb'] * 1e6),
                "details": {
                    "family":             "fractal",
                    "parameter_size":     f"{params['total_M']}M",
                    "quantization_level": "FP32",
                }
            }]
        })

    def _generate(self, body: dict):
        """
        Compatible con POST /api/generate de Ollama.

        Payload esperado (igual que Ollama):
          {"model": "...", "prompt": "...", "stream": false,
           "options": {"temperature": 0.7, "num_predict": 200}}
        """
        prompt   = body.get("prompt", "")
        stream   = body.get("stream", False)
        opciones = body.get("options", {})

        temperatura = opciones.get("temperature", 0.7)
        max_tokens  = opciones.get("num_predict", 200)
        top_k       = opciones.get("top_k", 40)
        top_p       = opciones.get("top_p", 0.9)
        rep_penalty = opciones.get("repeat_penalty", 1.1)

        if stream:
            self._generate_streaming(prompt, temperatura, max_tokens, top_k, top_p, rep_penalty)
        else:
            self._generate_completo(prompt, temperatura, max_tokens, top_k, top_p, rep_penalty)

    def _generate_completo(self, prompt, temperatura, max_tokens, top_k, top_p, rep_penalty):
        """Genera la respuesta completa de una vez (no streaming)."""
        t0 = time.time()

        resultado = generar(
            estado.modelo, estado.tokenizer, prompt,
            max_tokens=max_tokens,
            temperatura=temperatura,
            top_k=top_k,
            top_p=top_p,
            repetition_penalty=rep_penalty,
            usar_cache=True,
        )

        with estado.lock:
            estado.stats['requests_totales'] += 1
            estado.stats['tokens_generados'] += resultado['n_tokens']
            estado.stats['tiempo_total_seg'] += resultado['tiempo_segundos']

        # Formato compatible con Ollama
        self._responder(200, {
            "model":               estado.nombre_modelo,
            "created_at":          datetime.now().isoformat(),
            "response":            resultado['texto'],
            "done":                True,
            "total_duration":      int((time.time() - t0) * 1e9),  # nanosegundos
            "eval_count":          resultado['n_tokens'],
            "eval_duration":       int(resultado['tiempo_segundos'] * 1e9),
            # Extra ARKANI - operaciones fractales detectadas
            "operaciones_fractales": resultado['operaciones_fractales'],
            "tokens_por_segundo":    resultado['tokens_por_segundo'],
        })

    def _generate_streaming(self, prompt, temperatura, max_tokens, top_k, top_p, rep_penalty):
        """
        Streaming compatible con Ollama - envia un JSON por linea (ndjson).
        El cliente (arkani_engine.py) puede leer linea por linea.
        """
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.end_headers()

        tokens_acumulados = []

        def callback(texto_token):
            tokens_acumulados.append(texto_token)
            chunk = json.dumps({
                "model":    estado.nombre_modelo,
                "response": texto_token,
                "done":     False,
            }, ensure_ascii=False) + "\n"
            try:
                self.wfile.write(chunk.encode("utf-8"))
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass

        resultado = generar(
            estado.modelo, estado.tokenizer, prompt,
            max_tokens=max_tokens,
            temperatura=temperatura,
            top_k=top_k,
            top_p=top_p,
            repetition_penalty=rep_penalty,
            usar_cache=True,
            callback_token=callback,
        )

        with estado.lock:
            estado.stats['requests_totales'] += 1
            estado.stats['tokens_generados'] += resultado['n_tokens']
            estado.stats['tiempo_total_seg'] += resultado['tiempo_segundos']

        # Linea final con done=True
        final = json.dumps({
            "model": estado.nombre_modelo,
            "done":  True,
            "eval_count":    resultado['n_tokens'],
            "eval_duration": int(resultado['tiempo_segundos'] * 1e9),
        }) + "\n"
        try:
            self.wfile.write(final.encode("utf-8"))
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _chat(self, body: dict):
        """
        Compatible con POST /api/chat de Ollama.
        Convierte el historial de mensajes a un prompt unico.
        """
        mensajes = body.get("messages", [])
        stream   = body.get("stream", False)
        opciones = body.get("options", {})

        # Construir prompt desde mensajes (formato ChatML)
        prompt_parts = []
        for msg in mensajes:
            rol = msg.get("role", "user")
            contenido = msg.get("content", "")
            if rol == "system":
                prompt_parts.append(f"<|SYS|>{contenido}")
            elif rol == "user":
                prompt_parts.append(f"<|USER|>{contenido}")
            elif rol == "assistant":
                prompt_parts.append(f"<|ASST|>{contenido}")

        prompt_parts.append("<|ASST|>")  # esperar respuesta del asistente
        prompt = " ".join(prompt_parts)

        temperatura = opciones.get("temperature", 0.7)
        max_tokens  = opciones.get("num_predict", 200)

        resultado = generar(
            estado.modelo, estado.tokenizer, prompt,
            max_tokens=max_tokens,
            temperatura=temperatura,
            usar_cache=True,
        )

        with estado.lock:
            estado.stats['requests_totales'] += 1
            estado.stats['tokens_generados'] += resultado['n_tokens']

        self._responder(200, {
            "model":      estado.nombre_modelo,
            "created_at": datetime.now().isoformat(),
            "message": {
                "role":    "assistant",
                "content": resultado['texto'],
            },
            "done": True,
            "operaciones_fractales": resultado['operaciones_fractales'],
        })

    def _evolve_inspeccion(self):
        """
        EVOLVE: el modelo se inspecciona a si mismo.
        Endpoint unico - no existe en Ollama, es exclusivo de ARKANI.
        """
        informe = estado.modelo.evolve_inspeccion()
        informe['historial_operaciones'] = historial(20)
        self._responder(200, informe)

    def _evolve_reset(self, body: dict):
        """
        EVOLVE: reinicia una capa especifica del modelo.
        Permite auto-correccion si una capa se daña.
        """
        capa = body.get("capa", -1)
        if 0 <= capa < estado.modelo.config.n_layers:
            estado.modelo.evolve_reiniciar_capa(capa)
            self._responder(200, {"status": "ok", "capa_reiniciada": capa})
        else:
            self._responder(400, {"error": f"capa invalida: {capa}"})

    def _historial_operaciones(self):
        """Retorna el historial de operaciones fractales ejecutadas."""
        self._responder(200, {"historial": historial(50)})

    # ── UTILIDADES ───────────────────────────────────────────────────────────

    def _responder(self, codigo: int, datos: dict):
        body = json.dumps(datos, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        """Log simplificado - solo metodo, path y codigo."""
        print(f"  {self.command} {self.path}")


# ─────────────────────────────────────────────────────────────────────────────
# INICIAR SERVIDOR
# ─────────────────────────────────────────────────────────────────────────────
def iniciar_servidor(
    host:             str = "0.0.0.0",
    puerto:           int = 11435,
    directorio_modelo: str = None,
    config_nombre:    str = "mini",
):
    """
    Inicia el ArkaniServer.

    Por defecto en puerto 11435 (Ollama usa 11434, para no chocar).
    Para reemplazar Ollama completamente, cambiar a 11434 cuando
    Ollama este detenido.
    """
    print("=" * 55)
    print("  ARKANI SERVER - Motor Fractal v1.0")
    print("  Protocolo Wardenclyffe")
    print("=" * 55)

    estado.cargar_modelo(directorio_modelo, config_nombre)

    server = HTTPServer((host, puerto), ArkaniHandler)

    print(f"\nServidor iniciado en http://{host}:{puerto}")
    print(f"\n  Endpoints disponibles:")
    print(f"    GET  /              - info del servidor")
    print(f"    GET  /health        - estado de salud")
    print(f"    GET  /api/tags      - modelos disponibles (compat Ollama)")
    print(f"    POST /api/generate  - generacion de texto (compat Ollama)")
    print(f"    POST /api/chat      - chat (compat Ollama)")
    print(f"    GET  /api/evolve    - EVOLVE: inspeccion propia")
    print(f"    POST /api/evolve/reset - EVOLVE: reinicia capa")
    print(f"\n  Para que ARKANI use este motor en lugar de Ollama:")
    print(f"    En arkani_engine.py cambiar OLLAMA_URL a:")
    print(f"    http://localhost:{puerto}/api/generate")
    print(f"\n  Ctrl+C para detener")
    print("=" * 55)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\nServidor detenido")
        server.shutdown()


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ARKANI Server - reemplazo de Ollama")
    parser.add_argument("--host", default="0.0.0.0", help="Host (default: 0.0.0.0)")
    parser.add_argument("--puerto", type=int, default=11435,
                        help="Puerto (default: 11435, Ollama usa 11434)")
    parser.add_argument("--modelo", default=None,
                        help="Directorio con modelo guardado (default: crear nuevo)")
    parser.add_argument("--config", default="mini",
                        choices=list(CONFIGS.keys()),
                        help="Configuracion si se crea modelo nuevo (default: mini)")

    args = parser.parse_args()

    iniciar_servidor(
        host=args.host,
        puerto=args.puerto,
        directorio_modelo=args.modelo,
        config_nombre=args.config,
    )

