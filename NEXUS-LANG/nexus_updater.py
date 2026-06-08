"""
NEXUS UPDATER v1.0
Auto-actualizador de Arkani Nexus
Verifica GitHub, descarga e instala actualizaciones automaticamente
Constructor: Medico Radiologo, Xalapa
Clave: Arkani1979
"""

import os
import sys
import json
import shutil
import struct
import zlib
import hashlib
import requests
import threading
from pathlib import Path
from datetime import datetime

VERSION_LOCAL   = "1.0.0"
VERSION_URL     = "https://raw.githubusercontent.com/elbartohernandez182-sudo/arkani-nexus/master/version.json"
BASE_DIR        = Path(os.path.expanduser("~/NEXUS/NEXUS-LANG"))
VERSION_FILE    = Path(os.path.expanduser("~/NEXUS/version.json"))
BACKUP_DIR      = Path(os.path.expanduser("~/NEXUS/backups"))
LOG_PATH        = Path(os.path.expanduser("~/NEXUS/logs/updater.log"))


# ── LOGGER ────────────────────────────────────────────────────

def log(msg: str):
    linea = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(linea)
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, 'a') as f:
            f.write(linea + "\n")
    except:
        pass


# ── COMPARADOR DE VERSIONES ───────────────────────────────────

def version_mayor(v_remota: str, v_local: str) -> bool:
    """Retorna True si v_remota > v_local."""
    try:
        r = [int(x) for x in v_remota.split('.')]
        l = [int(x) for x in v_local.split('.')]
        return r > l
    except:
        return False


# ── DESCOMPRESOR INLINE ───────────────────────────────────────

def extraer_nxf(ruta_nxf: str, destino: str) -> bool:
    """Extrae .nxf sin depender del packager."""
    try:
        with open(ruta_nxf, 'rb') as f:
            raw = f.read()

        if raw[:4] != b'NXF\x19':
            log("ERROR: Firma invalida en .nxf")
            return False

        n_arch     = struct.unpack('<I', raw[8:12])[0]
        tam_indice = struct.unpack('<I', raw[64:68])[0]
        idx_raw    = raw[68:68+tam_indice]
        off_datos  = 68 + tam_indice

        pos = 0
        entradas = []
        for _ in range(n_arch):
            nb_len = struct.unpack('<I', idx_raw[pos:pos+4])[0]; pos+=4
            nombre = idx_raw[pos:pos+nb_len].decode('utf-8');    pos+=nb_len
            tam_o  = struct.unpack('<Q', idx_raw[pos:pos+8])[0]; pos+=8
            offset = struct.unpack('<Q', idx_raw[pos:pos+8])[0]; pos+=8
            tam_c  = struct.unpack('<I', idx_raw[pos:pos+4])[0]; pos+=4
            hash_o = idx_raw[pos:pos+64].decode('ascii');        pos+=64
            pos   += 8+1+4
            entradas.append((nombre, offset, tam_c, hash_o))

        os.makedirs(destino, exist_ok=True)
        ok = 0
        for nombre, offset, tam_c, hash_o in entradas:
            ruta_dest = Path(destino) / nombre
            ruta_dest.parent.mkdir(parents=True, exist_ok=True)
            inicio     = off_datos + offset + 4
            datos_comp = raw[inicio:inicio+tam_c]

            if datos_comp[:4] == b'FRAC':
                reps, lp = struct.unpack('<II', datos_comp[4:12])
                datos = zlib.decompress(datos_comp[12:]) * reps
            elif datos_comp[:4] == b'ZLIB':
                datos = zlib.decompress(datos_comp[4:])
            else:
                datos = datos_comp

            if hashlib.sha256(datos).hexdigest() != hash_o:
                log(f"HASH ERROR: {nombre}")
                continue

            with open(ruta_dest, 'wb') as f:
                f.write(datos)
            ok += 1

        log(f"Extraidos: {ok}/{n_arch}")
        return ok == n_arch

    except Exception as e:
        log(f"Error extrayendo: {e}")
        return False


# ── UPDATER PRINCIPAL ─────────────────────────────────────────

class NexusUpdater:

    def __init__(self):
        self.version_local = self._leer_version_local()

    def _leer_version_local(self) -> str:
        try:
            with open(VERSION_FILE) as f:
                return json.load(f).get("version", VERSION_LOCAL)
        except:
            return VERSION_LOCAL

    def verificar(self) -> dict | None:
        """
        Verifica si hay actualización disponible.
        Retorna info de la nueva versión o None si está al día.
        """
        try:
            r = requests.get(VERSION_URL, timeout=10)
            if r.status_code != 200:
                log(f"No se pudo verificar versión: HTTP {r.status_code}")
                return None

            info_remota = r.json()
            v_remota    = info_remota.get("version", "0.0.0")

            if version_mayor(v_remota, self.version_local):
                log(f"Nueva version disponible: {v_remota} (local: {self.version_local})")
                return info_remota
            else:
                log(f"Arkani al dia: v{self.version_local}")
                return None

        except requests.exceptions.ConnectionError:
            log("Sin conexion — omitiendo verificacion")
            return None
        except Exception as e:
            log(f"Error verificando: {e}")
            return None

    def hacer_backup(self) -> bool:
        """Hace backup de los archivos actuales antes de actualizar."""
        try:
            ts     = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup = BACKUP_DIR / f"backup_{self.version_local}_{ts}"
            shutil.copytree(str(BASE_DIR), str(backup),
                           ignore=shutil.ignore_patterns(
                               '__pycache__', '*.pyc', 'logs'
                           ))
            log(f"Backup creado: {backup}")

            # Mantener solo los ultimos 3 backups
            backups = sorted(BACKUP_DIR.iterdir()) if BACKUP_DIR.exists() else []
            for viejo in backups[:-3]:
                shutil.rmtree(viejo, ignore_errors=True)

            return True
        except Exception as e:
            log(f"Error en backup: {e}")
            return False

    def descargar(self, url: str) -> str | None:
        """Descarga el .nxf con barra de progreso."""
        try:
            ruta_tmp = Path(os.path.expanduser("~/NEXUS/update_tmp.nxf"))
            log(f"Descargando desde: {url}")

            r = requests.get(url, stream=True, timeout=30)
            if r.status_code != 200:
                log(f"Error descargando: HTTP {r.status_code}")
                return None

            total    = int(r.headers.get('content-length', 0))
            descargado = 0

            with open(ruta_tmp, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
                    descargado += len(chunk)
                    if total:
                        pct = descargado / total * 100
                        print(f"\r  Descargando... {pct:.0f}% ({descargado:,}/{total:,} bytes)", end='')

            print()  # nueva linea
            log(f"Descarga completa: {descargado:,} bytes")
            return str(ruta_tmp)

        except Exception as e:
            log(f"Error descargando: {e}")
            return None

    def aplicar(self, info_remota: dict, ruta_nxf: str) -> bool:
        """Aplica la actualización extraindo el .nxf."""
        try:
            log("Aplicando actualizacion...")

            # Extraer a directorio temporal primero
            tmp_dir = Path(os.path.expanduser("~/NEXUS/update_staging"))
            if tmp_dir.exists():
                shutil.rmtree(tmp_dir)

            if not extraer_nxf(ruta_nxf, str(tmp_dir)):
                log("Error extrayendo actualizacion")
                return False

            # Copiar archivos nuevos a NEXUS-LANG
            archivos_actualizados = 0
            for archivo in tmp_dir.rglob('*'):
                if archivo.is_file():
                    relativo  = archivo.relative_to(tmp_dir)
                    destino   = BASE_DIR / relativo
                    destino.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(archivo), str(destino))
                    archivos_actualizados += 1

            log(f"Archivos actualizados: {archivos_actualizados}")

            # Limpiar temporales
            shutil.rmtree(tmp_dir, ignore_errors=True)
            Path(ruta_nxf).unlink(missing_ok=True)

            # Actualizar version.json local
            with open(VERSION_FILE, 'w') as f:
                json.dump(info_remota, f, indent=2, ensure_ascii=False)

            self.version_local = info_remota.get("version", self.version_local)
            log(f"Actualizacion completada: v{self.version_local}")

            # Mostrar cambios
            cambios = info_remota.get("cambios", [])
            if cambios:
                log("Cambios en esta version:")
                for c in cambios:
                    log(f"  + {c}")

            return True

        except Exception as e:
            log(f"Error aplicando actualizacion: {e}")
            return False

    def actualizar(self) -> bool:
        """Flujo completo: verificar → backup → descargar → aplicar."""
        log(f"Verificando actualizaciones (local: v{self.version_local})...")

        info_remota = self.verificar()
        if not info_remota:
            return False  # Sin actualizacion o sin internet

        url_nxf = info_remota.get("url_nxf")
        if not url_nxf:
            log("Sin URL de descarga en version remota")
            return False

        # Backup
        if not self.hacer_backup():
            log("No se pudo hacer backup — cancelando")
            return False

        # Descargar
        ruta_nxf = self.descargar(url_nxf)
        if not ruta_nxf:
            return False

        # Aplicar
        return self.aplicar(info_remota, ruta_nxf)

    def actualizar_en_background(self, callback=None):
        """Actualiza en un hilo separado para no bloquear Arkani."""
        def _run():
            resultado = self.actualizar()
            if callback:
                callback(resultado)

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        return t

    def estado(self) -> dict:
        return {
            "version_local": self.version_local,
            "version_url":   VERSION_URL,
            "backup_dir":    str(BACKUP_DIR)
        }


# ── INTEGRACIÓN CON FLASK ─────────────────────────────────────

def registrar_rutas(app):
    """Registra rutas de actualización en arkani_web.py."""
    from flask import jsonify

    updater = NexusUpdater()

    @app.route('/updater/estado')
    def updater_estado():
        return jsonify(updater.estado())

    @app.route('/updater/verificar')
    def updater_verificar():
        info = updater.verificar()
        if info:
            return jsonify({"hay_actualizacion": True, "info": info})
        return jsonify({"hay_actualizacion": False,
                       "version_local": updater.version_local})

    @app.route('/updater/actualizar', methods=['POST'])
    def updater_actualizar():
        def on_done(exito):
            log(f"Actualizacion background: {'OK' if exito else 'FALLO'}")
        updater.actualizar_en_background(callback=on_done)
        return jsonify({"ok": True, "msg": "Actualizacion iniciada en background"})

    log("Rutas updater registradas: /updater/estado, /updater/verificar, /updater/actualizar")


# ── MAIN ─────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 55)
    print("  NEXUS UPDATER v1.0")
    print("=" * 55)

    updater = NexusUpdater()
    print(f"\n  Version local: {updater.version_local}")
    print(f"  Verificando GitHub...\n")

    resultado = updater.actualizar()

    if resultado:
        print("\n  Arkani actualizado correctamente.")
    else:
        print("\n  Sin actualizaciones disponibles o ya al dia.")

