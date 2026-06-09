#!/usr/bin/env python3
# nexus_voz.py - Motor de Voz Bidireccional ARKANI NEXUS
# TTS: Piper | STT: Whisper | Modos: Activo (wake word) / Pasivo (botón)
# Integrar en arkani_web.py

import os, subprocess, threading, tempfile, time, queue
import numpy as np

BASE_DIR     = os.path.expanduser("~/NEXUS/NEXUS-LANG")
PIPER_BIN    = os.path.expanduser("~/NEXUS/piper/piper")
PIPER_MODEL  = os.path.expanduser("~/NEXUS/piper/es_MX-claude-high.onnx")
PIPER_ESPEAK = os.path.expanduser("~/NEXUS/piper/espeak-ng-data")
AUDIO_DIR    = os.path.join(BASE_DIR, "static", "audio")
WAKE_WORD    = "arkani"

os.makedirs(AUDIO_DIR, exist_ok=True)

# ── TTS: texto → WAV con Piper ──────────────────────────────
def texto_a_voz(texto: str, nombre: str = "respuesta") -> str:
    """Convierte texto a WAV usando Piper. Retorna ruta del archivo."""
    ruta_wav = os.path.join(AUDIO_DIR, f"{nombre}.wav")
    try:
        proc = subprocess.run(
            [PIPER_BIN,
             "--model",       PIPER_MODEL,
             "--espeak_data", PIPER_ESPEAK,
             "--output_file", ruta_wav,
             "--length_scale", "0.9",    # un poco más rápido (tono Jarvis)
             "--noise_scale",  "0.3"],   # más limpio/robótico
            input=texto.encode("utf-8"),
            capture_output=True,
            timeout=30
        )
        if proc.returncode == 0 and os.path.exists(ruta_wav):
            return f"/static/audio/{nombre}.wav"
        else:
            print(f"[VOZ] Error piper: {proc.stderr.decode()}")
            return None
    except Exception as e:
        print(f"[VOZ] Excepcion TTS: {e}")
        return None

# ── STT: audio → texto con Whisper ─────────────────────────
def audio_a_texto(ruta_audio: str) -> str:
    """Transcribe audio a texto usando Whisper tiny."""
    try:
        import whisper
        modelo = whisper.load_model("tiny")
        result = modelo.transcribe(ruta_audio, language="es", fp16=False)
        texto = result.get("text", "").strip()
        print(f"[VOZ] Transcripcion: {texto}")
        return texto
    except Exception as e:
        print(f"[VOZ] Error Whisper: {e}")
        return ""

# ── GRABADOR DE MICRÓFONO ───────────────────────────────────
class GrabadorVoz:
    def __init__(self, duracion=5, sample_rate=16000):
        self.duracion    = duracion
        self.sample_rate = sample_rate
        self.grabando    = False

    def grabar(self, duracion=None) -> str:
        """Graba audio del micrófono. Retorna ruta del WAV temporal."""
        try:
            import sounddevice as sd
            from scipy.io.wavfile import write as wav_write
            dur = duracion or self.duracion
            print(f"[VOZ] Grabando {dur}s...")
            audio = sd.rec(int(dur * self.sample_rate),
                           samplerate=self.sample_rate,
                           channels=1, dtype='int16')
            sd.wait()
            ruta = os.path.join(AUDIO_DIR, "entrada.wav")
            wav_write(ruta, self.sample_rate, audio)
            print(f"[VOZ] Grabacion guardada: {ruta}")
            return ruta
        except Exception as e:
            print(f"[VOZ] Error grabacion: {e}")
            return None

# ── DETECTOR DE WAKE WORD (Modo Activo) ────────────────────
class EscuchaActiva:
    def __init__(self, callback_texto, wake_word=WAKE_WORD):
        self.wake_word      = wake_word.lower()
        self.callback_texto = callback_texto
        self.activo         = False
        self.hilo           = None
        self.grabador       = GrabadorVoz(duracion=5)

    def iniciar(self):
        if self.activo:
            return
        self.activo = True
        self.hilo = threading.Thread(target=self._bucle, daemon=True)
        self.hilo.start()
        print(f"[VOZ] Escucha activa ON — wake word: '{self.wake_word}'")

    def detener(self):
        self.activo = False
        print("[VOZ] Escucha activa OFF")

    def _bucle(self):
        """Ciclo continuo: graba 3s, busca wake word, si detecta graba comando."""
        while self.activo:
            try:
                import sounddevice as sd
                from scipy.io.wavfile import write as wav_write
                # Escucha corta para detectar wake word
                audio = sd.rec(int(3 * 16000), samplerate=16000,
                               channels=1, dtype='int16')
                sd.wait()
                ruta_tmp = os.path.join(AUDIO_DIR, "wake_check.wav")
                wav_write(ruta_tmp, 16000, audio)
                texto = audio_a_texto(ruta_tmp)
                if self.wake_word in texto.lower():
                    print(f"[VOZ] Wake word detectado!")
                    # Graba el comando completo (5 segundos)
                    ruta_cmd = self.grabador.grabar(duracion=5)
                    if ruta_cmd:
                        texto_cmd = audio_a_texto(ruta_cmd)
                        # Limpia el wake word del comando
                        texto_limpio = texto_cmd.lower().replace(self.wake_word, "").strip()
                        if texto_limpio:
                            self.callback_texto(texto_limpio)
            except Exception as e:
                print(f"[VOZ] Error en bucle activo: {e}")
                time.sleep(1)

# ── INSTANCIA GLOBAL ────────────────────────────────────────
grabador    = GrabadorVoz()
_escucha    = None  # Se inicializa cuando el usuario activa modo activo

def iniciar_escucha_activa(callback):
    global _escucha
    _escucha = EscuchaActiva(callback)
    _escucha.iniciar()

def detener_escucha_activa():
    global _escucha
    if _escucha:
        _escucha.detener()
        _escucha = None

def escucha_activa_estado() -> bool:
    return _escucha is not None and _escucha.activo

