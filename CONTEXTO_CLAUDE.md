# CONTEXTO ARKANI NEXUS - PARA CLAUDE
Actualizado: 2026-06-10 03:16:27
Último commit: f4747c9 - docs: ROADMAP Protocolo Wardenclyffe 2.0 - plan completo 4 meses

## Arquitectura activa
- arkani_web.py (Flask + SocketIO, puerto 8081)
- arkani_engine.py (motor principal)
- nexus_fractal_vm.py (VM fractal)
- arkani_bridge.py (core + agent)
- nexus_mapper_daemon.py (puerto 5010)
- URL: https://outscore-goes-january.ngrok-free.dev

## Git History (últimos 10 commits)
f4747c9 docs: ROADMAP Protocolo Wardenclyffe 2.0 - plan completo 4 meses
9716d1c feat: voz bidireccional Piper+Whisper, llamada M2M, avatar personalizador
db5825f feat: instalador Windows, acceso directo escritorio
1f8fc78 Auto: Contexto actualizado 2026-06-08 02:43:08
3de42f1 context: sesion 08jun2026 - packager, updater, repo publico
c8a3761 Auto: Contexto actualizado 2026-06-08 01:34:49
6b60cb4 feat: updater integrado en web+arranque, repo publico
515d361 feat: version.json updater
5d3592c feat: nexus_updater v1.0, version.json, nexus_fractal_packager v1.0
e48e814 feat: nexus_fractal_packager v1.0 - compresor/descompresor .nxf funcionando

## Pendientes
- nexus_remote_daemon.py (M2M JWT)
- .env secrets
- Dashboard completo
- Voz Piper TTS
