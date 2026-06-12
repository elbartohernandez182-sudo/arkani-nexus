"""
operaciones.py — Las 7 Operaciones Fractales de ARKANI
=======================================================
Protocolo Wardenclyffe — Motor Fractal v1.0

Estas NO son metáforas en un prompt.
Son funciones Python reales que el motor ejecuta
antes de generar cada token.

USAR:
    from operaciones import SUM, IF, LOOP, SPAWN, FOLD, LINK, EVOLVE
"""

from typing import Any, Callable, Iterable, Optional
from functools import reduce
import inspect
import traceback
import datetime

# ─────────────────────────────────────────────────────────────────────────────
# REGISTRO FRACTAL — historial de operaciones ejecutadas
# ─────────────────────────────────────────────────────────────────────────────
_registro = []

def _log(op: str, args: tuple, resultado: Any):
    """Registra cada operación fractal ejecutada."""
    _registro.append({
        "op":        op,
        "timestamp": datetime.datetime.now().isoformat(),
        "args_repr": str(args)[:100],
        "resultado": str(resultado)[:100],
    })

def historial(n: int = 10) -> list:
    """Retorna las últimas N operaciones ejecutadas."""
    return _registro[-n:]

def limpiar_historial():
    """Reinicia el registro de operaciones."""
    _registro.clear()


# ─────────────────────────────────────────────────────────────────────────────
# SUM(A, B, ...) — Integra conceptos preservando ambos
# ─────────────────────────────────────────────────────────────────────────────
def SUM(*args: Any) -> Any:
    """
    SUM(A, B) — integración fractal.
    No reemplaza — une. Preserva la esencia de cada argumento.

    Ejemplos:
        SUM("hola", "mundo")        → "hola mundo"
        SUM([1,2], [3,4])           → [1, 2, 3, 4]
        SUM({"a":1}, {"b":2})       → {"a":1, "b":2}
        SUM(3, 4)                   → 7
        SUM(concepto_A, concepto_B) → síntesis de ambos
    """
    if not args:
        return None
    if len(args) == 1:
        return args[0]

    # Todos dicts — merge preservando ambos
    if all(isinstance(a, dict) for a in args):
        resultado = {}
        for d in args:
            resultado.update(d)
        _log("SUM", args, resultado)
        return resultado

    # Todos listas — concatenar
    if all(isinstance(a, list) for a in args):
        resultado = [item for a in args for item in a]
        _log("SUM", args, resultado)
        return resultado

    # Todos strings — unir con espacio
    if all(isinstance(a, str) for a in args):
        resultado = " ".join(a for a in args if a)
        _log("SUM", args, resultado)
        return resultado

    # Todos numéricos — sumar
    if all(isinstance(a, (int, float)) for a in args):
        resultado = sum(args)
        _log("SUM", args, resultado)
        return resultado

    # Tipos mixtos — convertir a string y unir
    resultado = " | ".join(str(a) for a in args)
    _log("SUM", args, resultado)
    return resultado


# ─────────────────────────────────────────────────────────────────────────────
# IF(cond, entonces, sino) — Bifurca según contexto
# ─────────────────────────────────────────────────────────────────────────────
def IF(condicion: Any, entonces: Any, sino: Any = None) -> Any:
    """
    IF(cond, A, B) — bifurcación fractal.
    Versión funcional del if — puede recibir funciones como ramas.

    Ejemplos:
        IF(x > 0, "positivo", "negativo")
        IF(error, lambda: corregir(), lambda: continuar())
        IF(lista_vacia, valor_default, lista[0])
    """
    rama = entonces if condicion else sino

    # Si la rama es callable, ejecutarla
    if callable(rama):
        try:
            resultado = rama()
        except Exception as e:
            resultado = EVOLVE(rama, e)
    else:
        resultado = rama

    _log("IF", (condicion, entonces, sino), resultado)
    return resultado


# ─────────────────────────────────────────────────────────────────────────────
# LOOP(n, op) — Itera refinando
# ─────────────────────────────────────────────────────────────────────────────
def LOOP(
    n: int | Iterable,
    op: Callable,
    estado_inicial: Any = None,
    condicion_parada: Callable = None
) -> Any:
    """
    LOOP(n, op) — iteración fractal.
    Cada iteración refina el estado anterior.

    Ejemplos:
        LOOP(5, lambda i, s: s + i, 0)          → 10
        LOOP(datos, lambda x: procesar(x))       → [resultados]
        LOOP(100, entrenar, modelo)              → modelo_entrenado
    """
    if isinstance(n, int):
        estado = estado_inicial
        for i in range(n):
            try:
                # op puede aceptar (índice, estado) o solo (índice)
                sig = inspect.signature(op)
                n_params = len(sig.parameters)
                if n_params >= 2:
                    estado = op(i, estado)
                else:
                    estado = op(i)
            except Exception as e:
                estado = EVOLVE(estado, e)

            # Condición de parada anticipada
            if condicion_parada and condicion_parada(estado):
                break

        _log("LOOP", (n, op.__name__ if hasattr(op, '__name__') else str(op)), estado)
        return estado

    else:
        # n es iterable — mapear op sobre cada elemento
        resultados = []
        for item in n:
            try:
                resultados.append(op(item))
            except Exception as e:
                resultados.append(EVOLVE(item, e))

        _log("LOOP", ("iterable", op.__name__ if hasattr(op, '__name__') else str(op)), resultados)
        return resultados


# ─────────────────────────────────────────────────────────────────────────────
# SPAWN(nombre, funcion, contexto) — Crea perspectiva especializada
# ─────────────────────────────────────────────────────────────────────────────
def SPAWN(
    nombre: str,
    funcion: Callable = None,
    contexto: dict = None,
    paralelo: bool = False
) -> dict:
    """
    SPAWN(entidad, ctx) — sub-agente fractal.
    Crea una perspectiva especializada que analiza desde un ángulo único.

    Ejemplos:
        SPAWN("quimico", analizar_molecula, {"mol": "H2O"})
        SPAWN("critico", lambda: revisar_codigo(fn))
        SPAWN("optimista") → perspectiva optimista sin función
    """
    ctx = contexto or {}
    resultado_spawn = {
        "nombre":    nombre,
        "activo":    True,
        "contexto":  ctx,
        "timestamp": datetime.datetime.now().isoformat(),
    }

    if funcion is not None:
        try:
            sig = inspect.signature(funcion)
            n_params = len(sig.parameters)

            if n_params == 0:
                resultado_spawn["resultado"] = funcion()
            elif ctx:
                # Pasar solo los parámetros que la función acepta
                params_validos = {k: v for k, v in ctx.items() if k in sig.parameters}
                resultado_spawn["resultado"] = funcion(**params_validos) if params_validos else funcion()
            else:
                resultado_spawn["resultado"] = funcion()

        except Exception as e:
            resultado_spawn["resultado"] = None
            resultado_spawn["error"] = str(e)
            resultado_spawn["fix"] = EVOLVE(funcion, e)

    _log("SPAWN", (nombre,), resultado_spawn.get("resultado", "activo"))
    return resultado_spawn


# ─────────────────────────────────────────────────────────────────────────────
# FOLD(items, fn) — Reduce múltiples ideas a una síntesis
# ─────────────────────────────────────────────────────────────────────────────
def FOLD(
    items: list | dict,
    fn: Callable = None,
    inicial: Any = None,
    filtro: Callable = None
) -> Any:
    """
    FOLD(lista, fn) — síntesis fractal.
    Reduce N perspectivas a una conclusión unificada.

    Ejemplos:
        FOLD([1,2,3,4,5], lambda a,b: a+b)              → 15
        FOLD(spawns, lambda acc, s: acc + s["resultado"]) → síntesis
        FOLD({"a":1,"b":2,"c":3})                        → {"a":1,"b":2,"c":3}
        FOLD(ideas, sintetizar)                           → idea_unificada
    """
    if isinstance(items, dict):
        _log("FOLD", (items,), items)
        return items

    if not items:
        _log("FOLD", (items,), inicial)
        return inicial

    # Filtrar items si se especificó filtro
    if filtro:
        items = [i for i in items if filtro(i)]

    if not items:
        return inicial

    if fn is None:
        # Sin función — retornar el último elemento (síntesis natural)
        resultado = items[-1]
        _log("FOLD", (items,), resultado)
        return resultado

    try:
        if inicial is not None:
            resultado = reduce(fn, items, inicial)
        else:
            resultado = reduce(fn, items)
    except Exception as e:
        resultado = EVOLVE(items, e)

    _log("FOLD", (len(items), fn.__name__ if hasattr(fn, '__name__') else "fn"), resultado)
    return resultado


# ─────────────────────────────────────────────────────────────────────────────
# LINK(A, B) — Conecta conceptos distantes
# ─────────────────────────────────────────────────────────────────────────────
def LINK(
    origen: Any,
    destino: Any,
    tipo: str = "semantico",
    peso: float = 1.0,
    bidireccional: bool = True
) -> dict:
    """
    LINK(nodo_A, nodo_B) — conexión fractal.
    Crea una relación semántica entre dos conceptos.
    La conexión tiene peso — cuanto más fuerte, más relevante.

    Ejemplos:
        LINK("fotosíntesis", "wardenclyffe")
        LINK(modulo_A, modulo_B, tipo="depende_de", peso=0.9)
        LINK(error, solucion, tipo="resuelve")
    """
    enlace = {
        "origen":          str(origen)[:100],
        "destino":         str(destino)[:100],
        "tipo":            tipo,
        "peso":            peso,
        "bidireccional":   bidireccional,
        "timestamp":       datetime.datetime.now().isoformat(),
    }

    if bidireccional:
        enlace["inverso"] = {
            "origen":  str(destino)[:100],
            "destino": str(origen)[:100],
            "tipo":    tipo,
            "peso":    peso,
        }

    _log("LINK", (origen, destino), f"{origen}↔{destino}")
    return enlace


# ─────────────────────────────────────────────────────────────────────────────
# EVOLVE(objeto, error, fix) — Aprende de errores y auto-corrige
# ─────────────────────────────────────────────────────────────────────────────
def EVOLVE(
    objeto: Any,
    error: Any = None,
    fix: Callable = None,
    max_intentos: int = 3
) -> Any:
    """
    EVOLVE(code, err, fix) — auto-corrección fractal.
    El corazón del motor: detecta errores, genera fixes, aprende.

    Ejemplos:
        EVOLVE(funcion, error_detectado)
        EVOLVE(codigo, SyntaxError, lambda c: corregir(c))
        EVOLVE(modelo, loss_alto, optimizar)
    """
    # Sin error — objeto ya es correcto
    if error is None and fix is None:
        _log("EVOLVE", (objeto,), "sin_cambios")
        return objeto

    # Hay fix disponible — aplicarlo
    if fix is not None and callable(fix):
        for intento in range(max_intentos):
            try:
                resultado = fix(objeto)
                _log("EVOLVE", (objeto, error, fix.__name__), f"fix_aplicado_intento_{intento+1}")
                return resultado
            except Exception as e:
                if intento == max_intentos - 1:
                    # Último intento fallido
                    _log("EVOLVE", (objeto, error), f"fix_fallido_{e}")
                    return {
                        "objeto_original": str(objeto)[:100],
                        "error_original":  str(error)[:100],
                        "error_fix":       str(e)[:100],
                        "estado":          "requiere_intervencion",
                    }

    # Hay error pero no fix — clasificar y reportar
    tipo_error = _clasificar_error(error)
    fix_sugerido = _sugerir_fix(tipo_error, objeto, error)

    resultado = {
        "objeto_original": str(objeto)[:200],
        "error":           str(error)[:200],
        "tipo":            tipo_error,
        "fix_sugerido":    fix_sugerido,
        "estado":          "evolucionado",
        "timestamp":       datetime.datetime.now().isoformat(),
    }

    _log("EVOLVE", (objeto, error), tipo_error)
    return resultado


def _clasificar_error(error: Any) -> str:
    """Clasifica el tipo de error — 13 categorías ARKANI."""
    mapa = {
        SyntaxError:         "syntax",
        TypeError:           "type",
        IndexError:          "index",
        KeyError:            "key",
        AttributeError:      "attribute",
        ImportError:         "import",
        ModuleNotFoundError: "import",
        ZeroDivisionError:   "zero_division",
        MemoryError:         "memory",
        RecursionError:      "recursion",
        ValueError:          "value",
        FileNotFoundError:   "file_not_found",
        PermissionError:     "permission",
    }
    if isinstance(error, Exception):
        return mapa.get(type(error), "unknown")
    return "unknown"


def _sugerir_fix(tipo: str, objeto: Any, error: Any) -> str:
    """Genera sugerencia de fix según el tipo de error."""
    sugerencias = {
        "syntax":        "Verificar indentación y sintaxis Python",
        "type":          "Verificar tipos de datos — usar type() o isinstance()",
        "index":         "Verificar len(lista) antes de acceder por índice",
        "key":           "Usar dict.get(key, default) en lugar de dict[key]",
        "attribute":     "Verificar que el objeto tiene ese atributo con hasattr()",
        "import":        "Instalar módulo con pip install o verificar nombre",
        "zero_division": "Agregar validación: if denominador != 0",
        "memory":        "Reducir batch_size o usar generadores en lugar de listas",
        "recursion":     "Agregar caso base o aumentar sys.setrecursionlimit()",
        "value":         "Validar rango del valor antes de operar",
        "file_not_found":"Verificar ruta con os.path.exists() antes de abrir",
        "permission":    "Verificar permisos con os.access() o usar sudo",
        "unknown":       "Revisar traceback completo para diagnóstico",
    }
    return sugerencias.get(tipo, "Revisar el error manualmente")


# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE FRACTAL — compone operaciones en secuencia
# ─────────────────────────────────────────────────────────────────────────────
def pipeline(*operaciones: Callable) -> Callable:
    """
    Compone N operaciones fractales en un pipeline.
    La salida de cada operación es la entrada de la siguiente.

    Ejemplo:
        proc = pipeline(
            lambda x: SPAWN("analista", lambda: x.split()),
            lambda s: FOLD(s["resultado"], lambda a,b: a+" "+b),
            lambda r: EVOLVE(r, fix=lambda x: x.strip())
        )
        resultado = proc("  hola mundo  ")
    """
    def ejecutar(entrada):
        estado = entrada
        for op in operaciones:
            try:
                estado = op(estado)
            except Exception as e:
                estado = EVOLVE(estado, e)
        return estado
    return ejecutar


# ─────────────────────────────────────────────────────────────────────────────
# MAIN — demo de las 7 operaciones
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print("  ARKANI — 7 Operaciones Fractales")
    print("  Protocolo Wardenclyffe — Motor v1.0")
    print("=" * 55)

    # SUM
    print("\n1. SUM:")
    print(SUM("ARKANI", "Protocolo Wardenclyffe"))
    print(SUM({"motor": "FractalLM"}, {"version": "1.0"}))
    print(SUM([1, 2, 3], [4, 5, 6]))

    # IF
    print("\n2. IF:")
    ram_gb = 8
    print(IF(ram_gb >= 8, "RAM suficiente para 0.5b", "RAM insuficiente"))
    print(IF(False, "esto no sale", "bifurcación correcta"))

    # LOOP
    print("\n3. LOOP:")
    suma = LOOP(5, lambda i, s: s + i, estado_inicial=0)
    print(f"  LOOP(5, suma): {suma}")
    cuadrados = LOOP([1,2,3,4,5], lambda x: x**2)
    print(f"  LOOP(lista, x²): {cuadrados}")

    # SPAWN
    print("\n4. SPAWN:")
    perspectiva = SPAWN("ingeniero", lambda: "analizar arquitectura fractal")
    print(f"  SPAWN resultado: {perspectiva['resultado']}")

    # FOLD
    print("\n5. FOLD:")
    sintesis = FOLD([1, 2, 3, 4, 5], lambda a, b: a + b)
    print(f"  FOLD(suma): {sintesis}")
    sintesis_str = FOLD(["Motor", "Fractal", "ARKANI"], lambda a, b: f"{a} {b}")
    print(f"  FOLD(strings): {sintesis_str}")

    # LINK
    print("\n6. LINK:")
    conexion = LINK("fotosíntesis", "Protocolo Wardenclyffe")
    print(f"  LINK: {conexion['origen']} ↔ {conexion['destino']}")

    # EVOLVE
    print("\n7. EVOLVE:")
    resultado_ok = EVOLVE("código correcto")
    print(f"  EVOLVE sin error: {resultado_ok}")

    def codigo_con_error():
        return 1 / 0

    resultado_fix = EVOLVE(
        codigo_con_error,
        ZeroDivisionError("division by zero"),
        fix=lambda fn: "división por cero — usar denominador seguro"
    )
    print(f"  EVOLVE con fix: {resultado_fix}")

    # Pipeline
    print("\n8. PIPELINE:")
    proc = pipeline(
        lambda x: SPAWN("tokenizador", lambda: x.lower().split()),
        lambda s: FOLD(s["resultado"], lambda a, b: f"{a}_{b}"),
        lambda r: EVOLVE(r) if r else EVOLVE("vacío", ValueError("sin tokens"))
    )
    print(f"  pipeline('Hola Mundo'): {proc('Hola Mundo')}")

    # Historial
    print("\n9. HISTORIAL de operaciones:")
    for h in historial(5):
        print(f"  [{h['op']:8}] {h['args_repr'][:40]} → {h['resultado'][:40]}")

    print("\n✓ Motor fractal operaciones.py — listo")
    print("  Siguiente: tokenizer.py")
