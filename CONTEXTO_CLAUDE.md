# CONTEXTO ARKANI NEXUS - PARA CLAUDE
Actualizado: 2026-06-16 00:04:35
Último commit: 21982c6 - chore: gitignore *.gguf (modelos grandes)

## Arquitectura activa
- arkani_web.py (Flask + SocketIO, puerto 8081)
- arkani_engine.py (motor principal)
- nexus_fractal_vm.py (VM fractal)
- arkani_bridge.py (core + agent)
- nexus_mapper_daemon.py (puerto 5010)
- URL: https://outscore-goes-january.ngrok-free.dev

## Git History (últimos 10 commits)
21982c6 chore: gitignore *.gguf (modelos grandes)
0267dc6 feat: Motor Fractal COMPLETO 9/9 - entrenamiento.py con backprop+Adam validado (loss 17.78->1.74, 90% mejora en 50 steps)
2189f49 feat: Motor Fractal COMPLETO 9/9 - entrenamiento.py con backprop+Adam validado (loss 17.78->1.74, 90% mejora en 50 steps)
4ef6787 feat: Motor Fractal completo - 8 archivos (operaciones a servidor) + integracion paralela puerto 11435
3e5848b feat: Motor Fractal completo - 8 archivos (operaciones a servidor) + integracion paralela puerto 11435
8ad7124 Auto: Contexto actualizado 2026-06-12 19:33:35
2c10b05 chore: gitignore para checkpoints y archivos pesados
77ecaa2 feat: Motor Fractal — tokenizer + embeddings + attention + ffn listos
4aeb9a8 feat: Motor Fractal v1.0 — operaciones.py + finetune_v2 + memoria humana + dataset 1016 ejemplos + guardian Ollama
0d95c3c feat: Motor Fractal v1.0 — operaciones.py + finetune_v2 + memoria humana + dataset 1016 ejemplos

## Pendientes
- nexus_remote_daemon.py (M2M JWT)
- .env secrets
- Dashboard completo
- Voz Piper TTS
