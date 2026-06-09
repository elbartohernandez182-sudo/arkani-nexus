# ── RUTAS DE VOZ - agregar en arkani_web.py ─────────────────
# Pegar ANTES del ultimo bloque if __name__ == '__main__'
# También agregar al inicio: from nexus_voz import texto_a_voz, audio_a_texto, grabador
#                                                   iniciar_escucha_activa, detener_escucha_activa
#                                                   escucha_activa_estado

@app.route('/voz/generar', methods=['POST'])
def voz_generar():
    """TTS: recibe texto, devuelve URL del WAV generado por Piper."""
    from nexus_voz import texto_a_voz
    texto = (request.json or {}).get('texto', '').strip()
    if not texto:
        return jsonify({"ok": False, "error": "Sin texto"})
    url = texto_a_voz(texto, nombre="respuesta")
    if url:
        return jsonify({"ok": True, "url": url})
    return jsonify({"ok": False, "error": "Error generando audio"})

@app.route('/voz/transcribir', methods=['POST'])
def voz_transcribir():
    """STT: recibe WAV del navegador, devuelve texto transcrito por Whisper."""
    from nexus_voz import audio_a_texto
    if 'audio' not in request.files:
        return jsonify({"ok": False, "error": "Sin archivo audio"})
    archivo = request.files['audio']
    ruta_tmp = os.path.join(os.path.expanduser("~/NEXUS/NEXUS-LANG/static/audio"), "entrada.wav")
    archivo.save(ruta_tmp)
    texto = audio_a_texto(ruta_tmp)
    if texto:
        return jsonify({"ok": True, "texto": texto})
    return jsonify({"ok": False, "error": "No se pudo transcribir"})

@app.route('/voz/modo_activo', methods=['POST'])
def voz_modo_activo():
    """Activa/desactiva modo escucha activa (wake word 'Arkani')."""
    from nexus_voz import iniciar_escucha_activa, detener_escucha_activa, escucha_activa_estado
    accion = (request.json or {}).get('accion', '')

    def on_comando(texto):
        """Callback: cuando se detecta comando por voz, lo manda a Arkani y genera respuesta."""
        if not arkani:
            return
        respuesta = arkani.chat(texto)
        # Genera audio de respuesta
        from nexus_voz import texto_a_voz
        url_audio = texto_a_voz(respuesta, nombre="respuesta_activa")
        # Emite por websocket a todos los clientes
        socketio.emit('voz_respuesta', {
            'texto_usuario': texto,
            'respuesta':     respuesta,
            'audio_url':     url_audio,
            'timestamp':     datetime.datetime.now().strftime('%H:%M:%S')
        })

    if accion == 'activar':
        iniciar_escucha_activa(on_comando)
        return jsonify({"ok": True, "estado": "activo", "wake_word": "arkani"})
    elif accion == 'desactivar':
        detener_escucha_activa()
        return jsonify({"ok": True, "estado": "inactivo"})
    else:
        return jsonify({"ok": True, "estado": "activo" if escucha_activa_estado() else "inactivo"})

@app.route('/voz/estado')
def voz_estado():
    """Devuelve estado actual del sistema de voz."""
    from nexus_voz import escucha_activa_estado
    piper_ok  = os.path.exists(os.path.expanduser("~/NEXUS/piper/piper"))
    modelo_ok = os.path.exists(os.path.expanduser("~/NEXUS/piper/es_MX-claude-high.onnx"))
    try:
        import whisper
        whisper_ok = True
    except:
        whisper_ok = False
    return jsonify({
        "piper":         piper_ok,
        "modelo_voz":    modelo_ok,
        "whisper":       whisper_ok,
        "escucha_activa": escucha_activa_estado()
    })

