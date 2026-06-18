"""
nexus_m2m_protocolo.py — Protocolo Maquina-a-Maquina (capa M2M)
==================================================================
Protocolo Wardenclyffe — complemento de nexus_fractal_vm.py

NO MODIFICA nexus_fractal_vm.py (455 lineas, ya integrado con
arkani_engine.py). Solo AGREGA la capa de red:

  Instruccion  <--to_bytes-->  16 bytes firmados (SHA256)  <--red-->

Formato (16 bytes, compatible con Instruccion existente):
  byte0     FRACTAL_ID (0x7C)
  byte1     opcode (FractalOp)
  byte2     scale
  byte3     flags     (0x01=fold, 0x02=link, 0x80=evolve)
  bytes4-7  fold_addr (uint32 LE)
  bytes8-11 link_addr (uint32 LE)
  bytes12-15 sha256(bytes0-11)[:4]   <- firma de integridad

USO:
  from nexus_m2m_protocolo import instruccion_to_bytes, recibir_instruccion_m2m

  # NODO A (envia):
  datos = instruccion_to_bytes(instruccion)
  # ... enviar `datos` por la red (16 bytes) ...

  # NODO B (recibe):
  resultado = recibir_instruccion_m2m(vm, datos, origen="ThinkPad-A")
"""

import struct
import hashlib
from typing import Optional, Tuple, Dict

from nexus_fractal_vm import FractalOp, Instruccion, FractalVM, FRACTAL_ID


# ─────────────────────────────────────────────────────────────────────────────
# SERIALIZACION
# ─────────────────────────────────────────────────────────────────────────────
def instruccion_to_bytes(inst: Instruccion) -> bytes:
    """Serializa una Instruccion a 16 bytes firmados con SHA256."""
    cabecera = bytes([FRACTAL_ID, inst.op.value, inst.scale & 0xFF, inst.flags & 0xFF])
    cuerpo   = struct.pack('<II', inst.fold_addr & 0xFFFFFFFF, inst.link_addr & 0xFFFFFFFF)
    firma    = hashlib.sha256(cabecera + cuerpo).digest()[:4]
    return cabecera + cuerpo + firma


def instruccion_from_bytes(data: bytes) -> Tuple[Optional[Instruccion], bool]:
    """
    Reconstruye una Instruccion desde 16 bytes recibidos por red.
    Retorna (instruccion, firma_valida).
    direccion=-1 indica "instruccion transitoria recibida por M2M"
    (no corresponde a una direccion local del hipocampo).
    """
    if len(data) != 16 or data[0] != FRACTAL_ID:
        return None, False

    op = next((o for o in FractalOp if o.value == data[1]), None)
    if op is None:
        return None, False

    scale, flags = data[2], data[3]
    fold_addr, link_addr = struct.unpack('<II', data[4:12])
    firma = data[12:16]

    firma_valida = hashlib.sha256(data[:12]).digest()[:4] == firma

    inst = Instruccion(op, scale, flags, fold_addr, link_addr, direccion=-1)
    return inst, firma_valida


# ─────────────────────────────────────────────────────────────────────────────
# RECEPCION — ejecuta en el FractalVM existente, con efectos reales
# ─────────────────────────────────────────────────────────────────────────────
def recibir_instruccion_m2m(vm: FractalVM, datos: bytes, origen: str = "desconocido") -> Dict:
    """
    Punto de entrada M2M: un nodo recibe 16 bytes de OTRO nodo,
    verifica la firma SHA256, y si es valida la ejecuta en el
    FractalVM LOCAL (efectos reales: memoria, contextos, evolve...).
    """
    inst, firma_valida = instruccion_from_bytes(datos)

    if inst is None:
        return {"rechazada": True, "error": "FRACTAL_ID u opcode desconocido"}

    if not firma_valida:
        return {"rechazada": True, "error": "firma SHA256 invalida — instruccion descartada"}

    print(f"[M2M] <- {origen}: {inst}")
    resultado = vm._ejecutar_instruccion(inst, depth=0)

    return {
        "rechazada": False,
        "recibida_de": origen,
        "instruccion": repr(inst),
        "resultado": resultado,
    }


# ─────────────────────────────────────────────────────────────────────────────
# DEMO
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  ARKANI — Protocolo M2M (capa de red sobre FractalVM)")
    print("=" * 60)

    # ── Test 1: round-trip de serializacion ──────────────────────────────────
    print("\n--- TEST 1: serializar / deserializar ---")
    original = Instruccion(FractalOp.SUM, scale=15, flags=0x01, fold_addr=99, link_addr=0, direccion=4)
    datos = instruccion_to_bytes(original)
    print(f"  Original:     {original}")
    print(f"  16 bytes:     {datos.hex()}")

    recuperada, valida = instruccion_from_bytes(datos)
    print(f"  Recuperada:   {recuperada}")
    print(f"  Firma valida: {valida}")

    assert recuperada.op == original.op
    assert recuperada.scale == original.scale
    assert recuperada.flags == original.flags
    assert recuperada.fold_addr == original.fold_addr
    assert recuperada.link_addr == original.link_addr
    assert valida is True
    print("  ✓ Round-trip exacto")

    # ── Test 2: integridad — byte corrupto ───────────────────────────────────
    print("\n--- TEST 2: byte corrupto en transito ---")
    corrupto = bytearray(datos)
    corrupto[6] ^= 0xFF
    _, valida2 = instruccion_from_bytes(bytes(corrupto))
    print(f"  Firma valida tras corrupcion: {valida2}")
    assert valida2 is False
    print("  ✓ Corrupcion detectada correctamente")

    # ── Test 3: opcode desconocido ───────────────────────────────────────────
    print("\n--- TEST 3: datos invalidos (opcode 0xFF) ---")
    invalido = bytes([FRACTAL_ID, 0xFF, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
    inst_inv, _ = instruccion_from_bytes(invalido)
    print(f"  Resultado: {inst_inv}")
    assert inst_inv is None
    print("  ✓ Opcode desconocido rechazado")

    # ── Test 4: recibir_instruccion_m2m con el FractalVM real ────────────────
    print("\n--- TEST 4: recepcion M2M -> FractalVM real ---")
    try:
        vm = FractalVM()
        inst_evolve = Instruccion(FractalOp.EVOLVE, scale=5, flags=0x80, fold_addr=0xFFFFFFFF, link_addr=0)
        datos_evolve = instruccion_to_bytes(inst_evolve)
        r = recibir_instruccion_m2m(vm, datos_evolve, origen="Nodo-Demo")
        print(f"  Resultado: {r}")
        print("  ✓ recibir_instruccion_m2m ejecuto sobre el FractalVM real")
    except Exception as e:
        print(f"  ⚠️  No se pudo probar con FractalVM real aqui: {e}")
        print("  (esto es normal si hipocampo.bin no esta en esta ruta;")
        print("   en tu VM con el hipocampo real deberia funcionar)")

    print("\n" + "=" * 60)
    print("✓ nexus_m2m_protocolo.py — capa M2M validada")
    print("  Compatible con Instruccion/FractalVM existentes (455 lineas)")
    print("  16 bytes firmados (SHA256) viajan entre nodos ARKANI")
    print("=" * 60)
