#!/bin/bash
FECHA=$(date '+%Y-%m-%d %H:%M:%S')
GIT_LOG=$(cd ~/NEXUS && git log --oneline -10)
ULTIMO_COMMIT=$(cd ~/NEXUS && git log -1 --pretty=format:"%h - %s")

cat > ~/NEXUS/CONTEXTO_CLAUDE.md << CONTEXT
# CONTEXTO ARKANI NEXUS - PARA CLAUDE
Actualizado: $FECHA
Último commit: $ULTIMO_COMMIT

## Arquitectura activa
- arkani_web.py (Flask + SocketIO, puerto 8081)
- arkani_engine.py (motor principal)
- nexus_fractal_vm.py (VM fractal)
- arkani_bridge.py (core + agent)
- nexus_mapper_daemon.py (puerto 5010)
- URL: https://outscore-goes-january.ngrok-free.dev

## Git History (últimos 10 commits)
$GIT_LOG

## Pendientes
- nexus_remote_daemon.py (M2M JWT)
- .env secrets
- Dashboard completo
- Voz Piper TTS
CONTEXT

cd ~/NEXUS
git add CONTEXTO_CLAUDE.md
git commit -m "Auto: Contexto actualizado $FECHA"
git push origin master
echo "✅ Contexto actualizado y subido a GitHub"
