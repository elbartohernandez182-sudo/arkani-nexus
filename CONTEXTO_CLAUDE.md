# CONTEXTO ARKANI NEXUS - PARA CLAUDE
Actualizado: 2026-06-22 23:52:56
Último commit: 281c065 - v4.9 — daemon reinicia Ollama cada 2 archivos, menos timeouts

## Arquitectura activa
- arkani_web.py (Flask + SocketIO, puerto 8081)
- arkani_engine.py (motor principal)
- nexus_fractal_vm.py (VM fractal)
- arkani_bridge.py (core + agent)
- nexus_mapper_daemon.py (puerto 5010)
- URL: https://outscore-goes-january.ngrok-free.dev

## Git History (últimos 10 commits)
281c065 v4.9 — daemon reinicia Ollama cada 2 archivos, menos timeouts
ca07d02 v4.8 — dataset 1060 ejemplos, digestor completamente funcional
18b2955 v4.7 — fix digestor: timeout 90s, fragmentos 400ch, tokens 60, modelo qwen2.5:3b
7d304b8 Auto: Contexto actualizado 2026-06-22 00:26:27
68a62a3 Auto: Contexto actualizado 2026-06-21 21:48:17
fc4a059 v4.6 — optimizar daemon: timeout 20min, fragmentos 3000ch, prioridad archivos recientes, limpieza duplicados
94899e7 Auto: Contexto actualizado 2026-06-19 00:13:11
e918ccd v4.5 — Google Search configurado + manuales IA, NLP, redes neuronales, Python, radiologia DICOM TAC, pydicom
0cda7f2 v4.5 — Google Search integrado + manuales radiologia DICOM TAC pydicom
a1af15e Auto: Contexto actualizado 2026-06-18 11:58:11

## Pendientes
- nexus_remote_daemon.py (M2M JWT)
- .env secrets
- Dashboard completo
- Voz Piper TTS
