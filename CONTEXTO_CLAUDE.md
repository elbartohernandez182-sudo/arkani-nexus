# CONTEXTO ARKANI NEXUS - PARA CLAUDE
Actualizado: 2026-06-03 22:33:54
Último commit: 1761621 - Bridge conectado a arkani_web, auto-contexto GitHub

## Arquitectura activa
- arkani_web.py (Flask + SocketIO, puerto 8081)
- arkani_engine.py (motor principal)
- nexus_fractal_vm.py (VM fractal)
- arkani_bridge.py (core + agent)
- nexus_mapper_daemon.py (puerto 5010)
- URL: https://outscore-goes-january.ngrok-free.dev

## Git History (últimos 10 commits)
1761621 Bridge conectado a arkani_web, auto-contexto GitHub
54a7289 Auto: Contexto actualizado 2026-06-03 20:39:55
7259b7d Auto-contexto: script update_context.sh + arrancar_arkani actualizado
ef0259c Auto: Contexto actualizado 2026-06-03 20:30:31
1ebc638 Fix: avatar persistente, VM fractal sin signal error, fractal usa estado()
804a166 Deploy: icono escritorio Linux y Windows launcher .bat
f8a9fa1 Fusión fractal: VM integrada en engine, recuerdo desactivado, hipocampo UI corregido
fb26194 Fix: hipocampo UI, modelo arkani, ngrok 8081, sin Recuerdo, rutas explorables, socket.io
e64cbf4 Fix L65: limpieza caracteres control en respuesta Ollama
2aaa28e Fix: agregar autogen/ a RUTAS_PERMITIDAS

## Pendientes
- nexus_remote_daemon.py (M2M JWT)
- .env secrets
- Dashboard completo
- Voz Piper TTS
