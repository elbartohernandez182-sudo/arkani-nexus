"""
NEXUS FRACTAL PACKAGER v1.0
Compresor y Descompresor .nxf unificado
Usa nexus_fractal_compiler.py como base
Constructor: Medico Radiologo, Xalapa
Clave: Arkani1979
"""

import os
import io
import zlib
import struct
import json
import hashlib
import time
import argparse
from pathlib import Path
from typing import List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


# ── TIPOS ────────────────────────────────────────────────────

class TipoArchivo(Enum):
    DATOS      = 0
    EJECUTABLE = 1
    LIBRERIA   = 2
    CONFIG     = 3
    FRACTAL    = 4  # archivos .bin .nl del hipocampo


@dataclass
class EntradaArchivo:
    nombre:            str
    tamanio_original:  int
    tamanio_comprimido:int
    hash_original:     str
    offset_datos:      int
    timestamp:         float
    tipo:              TipoArchivo = TipoArchivo.DATOS
    permisos:          int = 0o644


# ── COMPRESOR FRACTAL ─────────────────────────────────────────

class CompresorFractal:
    """
    Detecta auto-similitud en los datos (patron fractal)
    y comprime usando esa informacion.
    Si no hay auto-similitud usa zlib normal.
    """

    MIN_PATRON = 32   # minimo bytes para buscar patron
    MIN_REPS   = 3    # minimo repeticiones para considerar fractal

    @staticmethod
    def comprimir(datos: bytes) -> Tuple[bytes, str]:
        """Retorna (datos_comprimidos, tipo) donde tipo es FRACTAL o ZLIB."""

        patron, reps = CompresorFractal._buscar_patron(datos)

        if patron and reps >= CompresorFractal.MIN_REPS:
            # Comprimir solo el patron base
            patron_comprimido = zlib.compress(patron, level=9)
            # Formato: FRAC + repeticiones(4B) + len_patron(4B) + patron_comprimido
            cabecera = b'FRAC' + struct.pack('<II', reps, len(patron))
            return cabecera + patron_comprimido, 'FRACTAL'
        else:
            return b'ZLIB' + zlib.compress(datos, level=9), 'ZLIB'

    @staticmethod
    def descomprimir(datos: bytes) -> bytes:
        """Detecta el tipo y descomprime."""
        if datos[:4] == b'FRAC':
            reps, len_patron = struct.unpack('<II', datos[4:12])
            patron = zlib.decompress(datos[12:])
            return patron * reps
        elif datos[:4] == b'ZLIB':
            return zlib.decompress(datos[4:])
        else:
            return datos  # sin comprimir

    @staticmethod
    def _buscar_patron(datos: bytes) -> Tuple[Optional[bytes], int]:
        """Busca el patron repetido mas eficiente."""
        n = len(datos)
        if n < CompresorFractal.MIN_PATRON * 3:
            return None, 0

        mejor_patron = None
        mejor_reps   = 0
        mejor_ahorro = 0

        for tam in [32, 64, 128, 256, 512]:
            if n < tam * 3:
                continue
            patron = datos[:tam]
            reps = 0
            pos  = 0
            while pos + tam <= n:
                if datos[pos:pos+tam] == patron:
                    reps += 1
                    pos  += tam
                else:
                    break
            if reps >= CompresorFractal.MIN_REPS:
                ahorro = tam * reps - tam
                if ahorro > mejor_ahorro:
                    mejor_patron = patron
                    mejor_reps   = reps
                    mejor_ahorro = ahorro

        return mejor_patron, mejor_reps


# ── PACKAGER PRINCIPAL ────────────────────────────────────────

class NexusPackager:
    """
    Crea y extrae archivos .nxf (Nexus Fractal File).

    Estructura del archivo:
    [CABECERA 64B][TAMANIO_INDICE 4B][INDICE][DATOS][COLA JSON]
    """

    FIRMA    = b'NXF\x19'
    VERSION  = 1

    def __init__(self):
        self.entradas: List[EntradaArchivo] = []
        self._buffer  = io.BytesIO()

    # ── COMPRIMIR ─────────────────────────────────────────────

    def agregar_archivo(self, ruta: str,
                        nombre_interno: str = None) -> bool:
        """Agrega un archivo al paquete."""
        try:
            ruta_abs = Path(ruta).resolve()
            if not ruta_abs.is_file():
                print(f"  No existe: {ruta}")
                return False

            with open(ruta_abs, 'rb') as f:
                datos = f.read()

            nombre = nombre_interno or ruta_abs.name
            hash_orig = hashlib.sha256(datos).hexdigest()

            # Detectar tipo
            sufijo = ruta_abs.suffix.lower()
            if sufijo in ('.py', '.sh', '.bat'):
                tipo = TipoArchivo.EJECUTABLE
            elif sufijo in ('.so', '.dll'):
                tipo = TipoArchivo.LIBRERIA
            elif sufijo in ('.json', '.conf', '.cfg', '.md'):
                tipo = TipoArchivo.CONFIG
            elif sufijo in ('.bin', '.nl'):
                tipo = TipoArchivo.FRACTAL
            else:
                tipo = TipoArchivo.DATOS

            # Comprimir
            datos_comp, metodo = CompresorFractal.comprimir(datos)

            offset = self._buffer.tell()
            # Escribir: tamanio_comprimido(4B) + datos
            self._buffer.write(struct.pack('<I', len(datos_comp)))
            self._buffer.write(datos_comp)

            entrada = EntradaArchivo(
                nombre            = nombre,
                tamanio_original  = len(datos),
                tamanio_comprimido= len(datos_comp),
                hash_original     = hash_orig,
                offset_datos      = offset,
                timestamp         = ruta_abs.stat().st_mtime,
                tipo              = tipo,
                permisos          = 0o755 if tipo == TipoArchivo.EJECUTABLE else 0o644
            )
            self.entradas.append(entrada)

            ratio = len(datos_comp) / len(datos) * 100 if datos else 0
            print(f"  {metodo:6s} | {nombre:45s} | {ratio:5.1f}%")
            return True

        except Exception as e:
            print(f"  ERROR {ruta}: {e}")
            return False

    def agregar_directorio(self, directorio: str,
                           excluir: List[str] = None) -> int:
        """Agrega todos los archivos de un directorio recursivamente."""
        excluir = excluir or [
            '.git', '__pycache__', '.pyc', 'venv',
            'node_modules', 'logs', '.env'
        ]
        dir_path = Path(directorio)
        if not dir_path.is_dir():
            print(f"No es directorio: {directorio}")
            return 0

        print(f"\nEmpaquetando: {directorio}")
        print(f"  {'Tipo':<8} {'Archivo':<47} {'Ratio'}")
        print(f"  {'-'*65}")

        contador = 0
        for archivo in sorted(dir_path.rglob('*')):
            if any(ex in str(archivo) for ex in excluir):
                continue
            if archivo.is_file():
                nombre_rel = str(archivo.relative_to(dir_path)).replace(os.sep, '/')
                if self.agregar_archivo(str(archivo), nombre_rel):
                    contador += 1

        print(f"\n  Total: {contador} archivos empaquetados")
        return contador

    def crear_nxf(self, ruta_salida: str) -> bool:
        """Crea el archivo .nxf final."""
        try:
            datos_blob = self._buffer.getvalue()
            tam_orig   = sum(e.tamanio_original for e in self.entradas)
            tam_comp   = len(datos_blob)

            # CABECERA (64 bytes)
            cabecera  = self.FIRMA
            cabecera += struct.pack('<I', self.VERSION)
            cabecera += struct.pack('<I', len(self.entradas))
            cabecera += struct.pack('<Q', tam_orig)
            cabecera += struct.pack('<Q', tam_comp)
            cabecera += struct.pack('<Q', int(time.time()))
            # Checksum 16 bytes
            checksum = hashlib.sha256(datos_blob).digest()[:16]
            cabecera += checksum
            cabecera  = cabecera.ljust(64, b'\x00')

            # INDICE
            idx = io.BytesIO()
            for e in self.entradas:
                nb = e.nombre.encode('utf-8')
                idx.write(struct.pack('<I', len(nb)))
                idx.write(nb)
                idx.write(struct.pack('<Q', e.tamanio_original))
                idx.write(struct.pack('<Q', e.offset_datos))
                idx.write(struct.pack('<I', e.tamanio_comprimido))
                idx.write(e.hash_original.encode('ascii'))  # 64 bytes hex
                idx.write(struct.pack('<Q', int(e.timestamp)))
                idx.write(struct.pack('<B', e.tipo.value))
                idx.write(struct.pack('<I', e.permisos))
            indice = idx.getvalue()

            # COLA (metadatos legibles)
            meta = {
                "creador":  "Arkani Nexus Packager v1.0",
                "fecha":    time.strftime('%Y-%m-%d %H:%M:%S'),
                "archivos": len(self.entradas),
                "ratio":    f"{tam_comp/tam_orig*100:.1f}%" if tam_orig else "0%",
                "clave":    "Arkani1979"
            }
            cola_json = json.dumps(meta, ensure_ascii=False).encode('utf-8')
            cola = struct.pack('<I', len(cola_json)) + cola_json

            # ESCRIBIR
            with open(ruta_salida, 'wb') as f:
                f.write(cabecera)
                f.write(struct.pack('<I', len(indice)))
                f.write(indice)
                f.write(datos_blob)
                f.write(cola)

            tam_final = os.path.getsize(ruta_salida)
            print(f"\n{'='*55}")
            print(f"  PAQUETE CREADO: {Path(ruta_salida).name}")
            print(f"  Original:    {tam_orig:>15,} bytes")
            print(f"  Comprimido:  {tam_final:>15,} bytes")
            if tam_orig:
                print(f"  Ratio:       {tam_final/tam_orig*100:>14.1f}%")
            print(f"  Archivos:    {len(self.entradas):>15}")
            print(f"{'='*55}\n")
            return True

        except Exception as e:
            print(f"Error creando .nxf: {e}")
            return False

    # ── DESCOMPRIMIR ──────────────────────────────────────────

    @staticmethod
    def leer_info(ruta: str) -> Tuple[Optional[dict], Optional[List[EntradaArchivo]]]:
        """Lee cabecera e indice sin extraer datos."""
        try:
            with open(ruta, 'rb') as f:
                raw = f.read()

            if raw[:4] != b'NXF\x19':
                print("Firma invalida — no es un archivo .nxf")
                return None, None

            version    = struct.unpack('<I', raw[4:8])[0]
            n_archivos = struct.unpack('<I', raw[8:12])[0]
            tam_orig   = struct.unpack('<Q', raw[12:20])[0]
            tam_comp   = struct.unpack('<Q', raw[20:28])[0]
            timestamp  = struct.unpack('<Q', raw[28:36])[0]

            info = {
                "version":    version,
                "archivos":   n_archivos,
                "tam_original": tam_orig,
                "tam_comprimido": tam_comp,
                "fecha": time.strftime('%Y-%m-%d %H:%M:%S',
                                       time.localtime(timestamp))
            }

            tam_indice = struct.unpack('<I', raw[64:68])[0]
            idx_raw    = raw[68:68+tam_indice]

            entradas = []
            pos = 0
            for _ in range(n_archivos):
                nb_len  = struct.unpack('<I', idx_raw[pos:pos+4])[0]; pos+=4
                nombre  = idx_raw[pos:pos+nb_len].decode('utf-8');    pos+=nb_len
                tam_o   = struct.unpack('<Q', idx_raw[pos:pos+8])[0]; pos+=8
                offset  = struct.unpack('<Q', idx_raw[pos:pos+8])[0]; pos+=8
                tam_c   = struct.unpack('<I', idx_raw[pos:pos+4])[0]; pos+=4
                hash_o  = idx_raw[pos:pos+64].decode('ascii');        pos+=64
                ts      = struct.unpack('<Q', idx_raw[pos:pos+8])[0]; pos+=8
                tipo_v  = struct.unpack('<B', idx_raw[pos:pos+1])[0]; pos+=1
                perms   = struct.unpack('<I', idx_raw[pos:pos+4])[0]; pos+=4

                entradas.append(EntradaArchivo(
                    nombre=nombre, tamanio_original=tam_o,
                    tamanio_comprimido=tam_c, hash_original=hash_o,
                    offset_datos=offset, timestamp=ts,
                    tipo=TipoArchivo(tipo_v), permisos=perms
                ))

            return info, entradas

        except Exception as e:
            print(f"Error leyendo .nxf: {e}")
            return None, None

    @staticmethod
    def extraer_nxf(ruta_nxf: str, destino: str) -> bool:
        """Extrae todos los archivos del .nxf al directorio destino."""
        print(f"\nDesempaquetando: {Path(ruta_nxf).name}")
        print(f"  {'Archivo':<48} {'Tamanio':>10}  {'Estado'}")
        print(f"  {'-'*70}")

        info, entradas = NexusPackager.leer_info(ruta_nxf)
        if not info or not entradas:
            return False

        with open(ruta_nxf, 'rb') as f:
            raw = f.read()

        tam_indice   = struct.unpack('<I', raw[64:68])[0]
        offset_datos = 68 + tam_indice

        os.makedirs(destino, exist_ok=True)
        extraidos = 0
        errores   = 0

        for entrada in entradas:
            try:
                ruta_dest = Path(destino) / entrada.nombre
                ruta_dest.parent.mkdir(parents=True, exist_ok=True)

                inicio   = offset_datos + entrada.offset_datos + 4
                tam_comp = struct.unpack(
                    '<I',
                    raw[offset_datos+entrada.offset_datos:
                        offset_datos+entrada.offset_datos+4]
                )[0]
                datos_comp = raw[inicio:inicio+tam_comp]

                datos = CompresorFractal.descomprimir(datos_comp)

                # Verificar integridad
                hash_calc = hashlib.sha256(datos).hexdigest()
                if hash_calc != entrada.hash_original:
                    print(f"  HASH ERROR | {entrada.nombre}")
                    errores += 1
                    continue

                with open(ruta_dest, 'wb') as f:
                    f.write(datos)

                if entrada.tipo == TipoArchivo.EJECUTABLE:
                    os.chmod(ruta_dest, 0o755)

                tam_fmt = f"{entrada.tamanio_original:,}"
                print(f"  OK  | {entrada.nombre:<48} {tam_fmt:>10}B")
                extraidos += 1

            except Exception as e:
                print(f"  ERR | {entrada.nombre}: {e}")
                errores += 1

        print(f"\n  Extraidos: {extraidos} | Errores: {errores}")
        return errores == 0


# ── CLI ───────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Nexus Fractal Packager v1.0 — Compresor/Descompresor .nxf',
        epilog="""
Ejemplos:
  # Comprimir directorio
  python3 nexus_fractal_packager.py --comprimir ~/NEXUS/NEXUS-LANG arkani.nxf

  # Comprimir archivo unico
  python3 nexus_fractal_packager.py --comprimir arkani_engine.py motor.nxf

  # Descomprimir
  python3 nexus_fractal_packager.py --extraer arkani.nxf ~/destino/

  # Ver contenido sin extraer
  python3 nexus_fractal_packager.py --info arkani.nxf
        """
    )
    parser.add_argument('--comprimir', nargs=2,
                        metavar=('ORIGEN', 'SALIDA.nxf'),
                        help='Comprimir directorio o archivo')
    parser.add_argument('--extraer', nargs=2,
                        metavar=('ARCHIVO.nxf', 'DESTINO'),
                        help='Extraer .nxf a directorio')
    parser.add_argument('--info', metavar='ARCHIVO.nxf',
                        help='Ver contenido del .nxf sin extraer')

    args = parser.parse_args()

    if args.comprimir:
        origen, salida = args.comprimir
        p = NexusPackager()
        if os.path.isdir(origen):
            p.agregar_directorio(origen)
        else:
            p.agregar_archivo(origen)
        p.crear_nxf(salida)

    elif args.extraer:
        archivo, destino = args.extraer
        NexusPackager.extraer_nxf(archivo, destino)

    elif args.info:
        info, entradas = NexusPackager.leer_info(args.info)
        if info and entradas:
            print(f"\nArchivo: {args.info}")
            print(f"Version:    {info['version']}")
            print(f"Fecha:      {info['fecha']}")
            print(f"Archivos:   {info['archivos']}")
            print(f"Original:   {info['tam_original']:,} bytes")
            print(f"Comprimido: {info['tam_comprimido']:,} bytes")
            if info['tam_original']:
                ratio = info['tam_comprimido']/info['tam_original']*100
                print(f"Ratio:      {ratio:.1f}%")
            print(f"\n{'Archivo':<50} {'Tamanio':>10}")
            print('-'*62)
            for e in entradas:
                print(f"  {e.nombre:<48} {e.tamanio_original:>10,}B")
    else:
        parser.print_help()


if __name__ == '__main__':
    main()

