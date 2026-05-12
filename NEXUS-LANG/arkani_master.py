import os
import shutil
from datetime import datetime
from nexus_recovery import recuperar_conciencia_arkani
from nexus_injector import inyectar_funcion_dinamica

def iniciar_consola():
    print("\n" + "═"*50)
    print("      🛰️  CONSOLA MAESTRA NEXUS-RAD v1.0")
    print("═"*50)
    
    root = recuperar_conciencia_arkani()
    
    print("\n📦 PROCESANDO HALLAZGOS CLÍNICOS...")
    try:
        corrector = inyectar_funcion_dinamica("fn_corregir_terminologia.py")
        hallazgo_crudo = "Osteocondrosis L4-L5 detectada."
        hallazgo_filtrado = corrector(hallazgo_crudo)
        print(f"🧬 NEXUS-LANG: {hallazgo_filtrado}")
    except Exception as e:
        print(f"⚠️ ERROR CLÍNICO: {e}")

    # --- FUNCIÓN DE RESPALDO AL CIERRE ---
    print("\n💾 GENERANDO RESPALDO DE SEGURIDAD...")
    try:
        source = os.path.expanduser("~/NEXUS/NEXUS-LANG/system_snapshot.json")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dest = os.path.expanduser(f"~/NEXUS/backups/snapshot_{timestamp}.json")
        
        if os.path.exists(source):
            shutil.copy2(source, backup_dest)
            print(f"✅ RESPALDO EXITOSO: {os.path.basename(backup_dest)}")
    except Exception as e:
        print(f"⚠️ ERROR DE RESPALDO: {e}")

    print("\n" + "═"*50)
    print("      ARKANI_BRAIN: ONLINE | SIMBIOSIS: ACTIVA")
    print("═"*50 + "\n")

if __name__ == "__main__":
    iniciar_consola()

def iniciar_servidor_omnipresente():
    print("🌐 [NEXUS-SYNC]: Iniciando canal de comunicación para Celular/Watch...")
    os.system("python3 ~/NEXUS/NEXUS-LANG/arkani_api.py &")

if __name__ == "__main__":
    iniciar_servidor_omnipresente()
