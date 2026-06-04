# CONTEXTO ARKANI NEXUS - PARA CLAUDE
Actualizado: 2026-06-03 20:30:31
Último commit: 1ebc638 - Fix: avatar persistente, VM fractal sin signal error, fractal usa estado()

## Arquitectura activa
- arkani_web.py (Flask + SocketIO, puerto 8081)
- arkani_engine.py (motor principal)
- nexus_fractal_vm.py (VM fractal)
- arkani_bridge.py (core + agent)
- nexus_mapper_daemon.py (puerto 5010)
- URL: https://outscore-goes-january.ngrok-free.dev

## Git History (últimos 10 commits)
1ebc638 Fix: avatar persistente, VM fractal sin signal error, fractal usa estado()
804a166 Deploy: icono escritorio Linux y Windows launcher .bat
f8a9fa1 Fusión fractal: VM integrada en engine, recuerdo desactivado, hipocampo UI corregido
fb26194 Fix: hipocampo UI, modelo arkani, ngrok 8081, sin Recuerdo, rutas explorables, socket.io
e64cbf4 Fix L65: limpieza caracteres control en respuesta Ollama
2aaa28e Fix: agregar autogen/ a RUTAS_PERMITIDAS
6d4bbb9 Fix 5 bugs criticos: regex rutas, timeout, division cero, importacion, race condition
e33545d arrancar_arkani.sh actualizado con mapper daemon
b0d6386 Arkani v3.0 - nexus_fractal_vm + mapper_daemon + fractal endpoints 01Jun2026
35693d5 Fix aprendizaje + modulos leer_mis_archivos y olvidaybusca

## Pendientes
- nexus_remote_daemon.py (M2M JWT)
- .env secrets
- Dashboard completo
- Voz Piper TTS
