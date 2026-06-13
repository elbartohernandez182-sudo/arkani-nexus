"""
inferencia.py — Motor de Inferencia Fractal ARKANI
===================================================
Protocolo Wardenclyffe — Motor Fractal v1.0

Genera texto token por token (autorregresivo).
Usa KV-Cache para acelerar — O(n) en lugar de O(n²).

ESTRATEGIAS DE SAMPLING:
  Greedy:      siempre el token más probable (determinístico)
  Temperature: escala la distribución (más alta = más aleatorio)
  Top-K:       solo considera los K tokens más probables
  Top-P:       considera tokens hasta acumular probabilidad P (nucleus)

USO:
    from inferencia import generar
    texto = generar(modelo, tokenizer, "Hola ARKANI", max_tokens=50)
"""

import numpy as np
import time
from typing import Optional, Callable

from modelo import FractalLM
from tokenizer import FractalTokenizer, ID_BOS, ID_EOS, ID_PAD, IDS_FRACTALES
from attention import crear_causal_mask


# ─────────────────────────────────────────────────────────────────────────────
# FUNCIONES DE SAMPLING
# ─────────────────────────────────────────────────────────────────────────────

def softmax(x: np.ndarray) -> np.ndarray:
    """Softmax numéricamente estable."""
    x = x - x.max()
    e = np.exp(x)
    return e / (e.sum() + 1e-8)


def aplicar_temperatura(logits: np.ndarray, temperatura: float) -> np.ndarray:
    """
    Escala los logits por temperatura.

    temperatura < 1.0 → distribución más "afilada" (más determinístico)
    temperatura > 1.0 → distribución más "plana" (más aleatorio)
    temperatura = 0   → equivalente a greedy (argmax)
    """
    if temperatura <= 0:
        return logits
    return logits / temperatura


def aplicar_top_k(logits: np.ndarray, k: int) -> np.ndarray:
    """
    Solo conserva los K logits más altos, el resto a -inf.
    Evita que el modelo elija tokens muy improbables.
    """
    if k <= 0 or k >= len(logits):
        return logits

    indices_top = np.argpartition(logits, -k)[-k:]
    mascara = np.full_like(logits, -np.inf)
    mascara[indices_top] = logits[indices_top]
    return mascara


def aplicar_top_p(logits: np.ndarray, p: float) -> np.ndarray:
    """
    Nucleus sampling — conserva el conjunto mínimo de tokens
    cuya probabilidad acumulada supera p.

    Más adaptativo que top-k: en contextos con un token muy
    probable, considera pocos; en contextos ambiguos, considera más.
    """
    if p >= 1.0:
        return logits

    indices_ordenados = np.argsort(logits)[::-1]
    probs_ordenadas   = softmax(logits[indices_ordenados])
    acumulado         = np.cumsum(probs_ordenadas)

    # Encontrar el corte
    corte = np.searchsorted(acumulado, p) + 1
    corte = max(1, min(corte, len(logits)))

    indices_descartar = indices_ordenados[corte:]
    logits_filtrados  = logits.copy()
    logits_filtrados[indices_descartar] = -np.inf

    return logits_filtrados


def aplicar_repetition_penalty(
    logits: np.ndarray,
    tokens_previos: list[int],
    penalty: float = 1.1,
) -> np.ndarray:
    """
    Penaliza tokens que ya aparecieron — evita loops repetitivos.
    penalty > 1.0 reduce la probabilidad de repetir.
    """
    if penalty == 1.0:
        return logits

    logits_penalizados = logits.copy()
    for token in set(tokens_previos):
        if 0 <= token < len(logits):
            if logits_penalizados[token] > 0:
                logits_penalizados[token] /= penalty
            else:
                logits_penalizados[token] *= penalty

    return logits_penalizados


def muestrear_token(
    logits: np.ndarray,
    temperatura: float = 0.7,
    top_k: int = 40,
    top_p: float = 0.9,
    tokens_previos: list[int] = None,
    repetition_penalty: float = 1.1,
    rng: np.random.Generator = None,
) -> int:
    """
    Pipeline completo de sampling — combina todas las estrategias.

    Orden: repetition_penalty → temperatura → top_k → top_p → muestreo
    """
    rng = rng or np.random.default_rng()

    logits = logits.copy()

    # 1. Penalizar repeticiones
    if tokens_previos and repetition_penalty != 1.0:
        logits = aplicar_repetition_penalty(logits, tokens_previos, repetition_penalty)

    # 2. Temperatura
    if temperatura == 0:
        return int(np.argmax(logits))  # greedy puro

    logits = aplicar_temperatura(logits, temperatura)

    # 3. Top-K
    if top_k > 0:
        logits = aplicar_top_k(logits, top_k)

    # 4. Top-P (nucleus)
    if top_p < 1.0:
        logits = aplicar_top_p(logits, top_p)

    # 5. Muestreo final
    probs = softmax(logits)
    return int(rng.choice(len(probs), p=probs))


# ─────────────────────────────────────────────────────────────────────────────
# GENERACIÓN AUTORREGRESIVA
# ─────────────────────────────────────────────────────────────────────────────
def generar(
    modelo:             FractalLM,
    tokenizer:          FractalTokenizer,
    prompt:             str,
    max_tokens:         int = 100,
    temperatura:        float = 0.7,
    top_k:              int = 40,
    top_p:              float = 0.9,
    repetition_penalty: float = 1.1,
    usar_cache:         bool = True,
    seed:               int = None,
    callback_token:     Callable[[str], None] = None,
    verbose:            bool = False,
) -> dict:
    """
    Genera texto de forma autorregresiva — token por token.

    Args:
        modelo:      FractalLM entrenado
        tokenizer:   FractalTokenizer correspondiente
        prompt:      texto inicial
        max_tokens:  máximo de tokens nuevos a generar
        temperatura: 0=greedy, >1=más aleatorio
        top_k:       considerar solo los K tokens más probables
        top_p:       nucleus sampling
        repetition_penalty: penaliza repeticiones
        usar_cache:  acelerar con KV-Cache
        seed:        semilla para reproducibilidad
        callback_token: función llamada con cada token generado (streaming)
        verbose:     imprimir progreso

    Returns:
        dict con texto generado, tokens, tiempos, operaciones fractales detectadas
    """
    rng = np.random.default_rng(seed)

    # Tokenizar prompt (sin EOS, vamos a continuar generando)
    tokens = tokenizer.encode(prompt, agregar_bos=True, agregar_eos=False)

    if verbose:
        print(f"Prompt tokenizado: {len(tokens)} tokens")

    # Reiniciar KV-Cache si se usa
    if usar_cache:
        modelo.kv_cache.limpiar()
        # Procesar prompt completo primero para llenar el cache
        modelo.kv_cache.pos = 0

    tokens_generados   = []
    operaciones_fractales = []
    tiempo_inicio = time.time()

    # ── Fase 1: procesar el prompt (forward completo) ────────────────────────
    tokens_actuales = np.array([tokens])

    if usar_cache:
        # Procesar el prompt token por token para llenar el cache correctamente
        for i, tok in enumerate(tokens):
            x = np.array([[tok]])
            mask = None  # con cache no necesitamos máscara causal explícita
            logits = modelo.forward(x, mask=mask, usar_cache=True)
            if i < len(tokens) - 1:
                modelo.kv_cache.avanzar()
        ultimo_logits = logits[0, -1]
    else:
        logits = modelo.forward(tokens_actuales, usar_cache=False)
        ultimo_logits = logits[0, -1]

    # ── Fase 2: generación autorregresiva ────────────────────────────────────
    for paso in range(max_tokens):
        # Muestrear siguiente token
        token_id = muestrear_token(
            ultimo_logits,
            temperatura=temperatura,
            top_k=top_k,
            top_p=top_p,
            tokens_previos=tokens + tokens_generados,
            repetition_penalty=repetition_penalty,
            rng=rng,
        )

        tokens_generados.append(token_id)

        # Detectar operaciones fractales
        for op, id_op in IDS_FRACTALES.items():
            if token_id == id_op:
                operaciones_fractales.append({'paso': paso, 'operacion': op})

        # Decodificar token individual para streaming
        if callback_token:
            texto_token = tokenizer.decode([token_id], limpiar=False)
            callback_token(texto_token)

        # Condición de parada
        if token_id == ID_EOS:
            if verbose:
                print(f"  EOS en paso {paso}")
            break

        # ── Siguiente forward pass ───────────────────────────────────────────
        if usar_cache:
            modelo.kv_cache.avanzar()
            x = np.array([[token_id]])
            logits = modelo.forward(x, mask=None, usar_cache=True)
            ultimo_logits = logits[0, -1]
        else:
            tokens_actuales = np.array([tokens + tokens_generados])
            seq_len = tokens_actuales.shape[1]
            if seq_len > modelo.config.max_seq_len:
                # Ventana deslizante si excede el contexto
                tokens_actuales = tokens_actuales[:, -modelo.config.max_seq_len:]
                seq_len = modelo.config.max_seq_len
            mask = crear_causal_mask(seq_len)
            logits = modelo.forward(tokens_actuales, mask=mask, usar_cache=False)
            ultimo_logits = logits[0, -1]

        if verbose and (paso + 1) % 10 == 0:
            print(f"  Token {paso+1}/{max_tokens} generado")

    tiempo_total = time.time() - tiempo_inicio

    # Decodificar resultado completo
    texto_generado = tokenizer.decode(tokens_generados, limpiar=True)

    return {
        'texto':              texto_generado,
        'tokens_generados':   tokens_generados,
        'n_tokens':           len(tokens_generados),
        'tiempo_segundos':    round(tiempo_total, 3),
        'tokens_por_segundo': round(len(tokens_generados) / max(tiempo_total, 1e-6), 2),
        'operaciones_fractales': operaciones_fractales,
        'prompt_tokens':      len(tokens),
    }


# ─────────────────────────────────────────────────────────────────────────────
# GENERACIÓN CON STREAMING (para servidor HTTP)
# ─────────────────────────────────────────────────────────────────────────────
def generar_streaming(
    modelo:    FractalLM,
    tokenizer: FractalTokenizer,
    prompt:    str,
    **kwargs
):
    """
    Generador (yield) que produce tokens de texto uno por uno.
    Útil para streaming en servidor HTTP — el usuario ve la
    respuesta aparecer en tiempo real, como ChatGPT.
    """
    tokens_buffer = []

    def callback(texto_token):
        tokens_buffer.append(texto_token)

    # Ejecutar generación con callback que acumula tokens
    # En una implementación real con threading, esto cedería
    # control después de cada callback. Aquí simulamos batch.
    resultado = generar(modelo, tokenizer, prompt, callback_token=callback, **kwargs)

    for token_texto in tokens_buffer:
        yield token_texto


# ─────────────────────────────────────────────────────────────────────────────
# BENCHMARK DE VELOCIDAD
# ─────────────────────────────────────────────────────────────────────────────
def benchmark_inferencia(modelo: FractalLM, tokenizer: FractalTokenizer) -> dict:
    """Mide velocidad de inferencia con y sin KV-Cache."""
    prompt = "ARKANI piensa en fractal:"

    # Con cache
    t0 = time.time()
    r1 = generar(modelo, tokenizer, prompt, max_tokens=20,
                  temperatura=0.7, usar_cache=True, seed=42)
    t_con_cache = time.time() - t0

    # Sin cache
    t0 = time.time()
    r2 = generar(modelo, tokenizer, prompt, max_tokens=20,
                  temperatura=0.7, usar_cache=False, seed=42)
    t_sin_cache = time.time() - t0

    return {
        'con_cache':    {'tiempo': round(t_con_cache, 3), 'tok/s': r1['tokens_por_segundo']},
        'sin_cache':    {'tiempo': round(t_sin_cache, 3), 'tok/s': r2['tokens_por_segundo']},
        'speedup':      round(t_sin_cache / max(t_con_cache, 1e-6), 2),
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN — demo del motor de inferencia
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from modelo import CONFIGS

    print("=" * 55)
    print("  ARKANI — Motor de Inferencia Fractal")
    print("  Protocolo Wardenclyffe — Motor v1.0")
    print("=" * 55)

    # Crear modelo pequeño para demo (sin entrenar — pesos aleatorios)
    config = CONFIGS["nano"]
    modelo = FractalLM(config)
    print(f"\n✓ Modelo: {config.nombre} ({config.contar_parametros()/1e6:.2f}M params)")

    # Tokenizador entrenado en mini-corpus
    corpus = [
        "ARKANI piensa en lenguaje fractal usando SPAWN FOLD LINK EVOLVE",
        "el motor fractal corre en Python puro sin dependencias externas",
        "SPAWN analiza el problema desde multiples perspectivas",
        "FOLD sintetiza las ideas en una respuesta unificada",
        "EVOLVE detecta errores y genera correcciones automaticas",
        "Protocolo Wardenclyffe inteligencia distribuida sin GPU",
    ] * 20

    tokenizer = FractalTokenizer(vocab_size=config.vocab_size)
    tokenizer.entrenar(corpus, verbose=False)
    print(f"✓ Tokenizador: {len(tokenizer.vocab)} tokens")

    # Test 1: estrategias de sampling
    print("\n--- ESTRATEGIAS DE SAMPLING ---")
    logits_demo = np.array([1.0, 5.0, 2.0, 0.5, 4.0, 0.1, 3.0])
    print(f"  Logits originales: {logits_demo}")

    for temp in [0.0, 0.5, 1.0, 1.5]:
        token = muestrear_token(logits_demo, temperatura=temp, top_k=0, top_p=1.0,
                                 rng=np.random.default_rng(42))
        nombre = "greedy" if temp == 0 else f"temp={temp}"
        print(f"  {nombre:10}: token elegido = {token}")

    # Test 2: top-k y top-p
    print("\n--- TOP-K / TOP-P ---")
    logits_tk = aplicar_top_k(logits_demo.copy(), k=3)
    print(f"  top_k=3: {logits_tk}")
    logits_tp = aplicar_top_p(logits_demo.copy(), p=0.7)
    print(f"  top_p=0.7: {logits_tp}")

    # Test 3: generación (con pesos aleatorios — texto será ruido,
    # pero valida que el pipeline completo funciona end-to-end)
    print("\n--- GENERACIÓN (pesos sin entrenar — valida el pipeline) ---")
    resultado = generar(
        modelo, tokenizer,
        prompt="ARKANI",
        max_tokens=15,
        temperatura=0.8,
        top_k=20,
        top_p=0.9,
        usar_cache=True,
        seed=42,
        verbose=False,
    )
    print(f"  Prompt:          'ARKANI'")
    print(f"  Tokens generados: {resultado['n_tokens']}")
    print(f"  Tiempo:          {resultado['tiempo_segundos']}s")
    print(f"  Velocidad:       {resultado['tokens_por_segundo']} tok/s")
    print(f"  Ops fractales detectadas: {len(resultado['operaciones_fractales'])}")
    print(f"  IDs generados:   {resultado['tokens_generados'][:10]}...")

    # Test 4: benchmark cache vs sin cache
    print("\n--- BENCHMARK: KV-CACHE vs SIN CACHE ---")
    bench = benchmark_inferencia(modelo, tokenizer)
    print(f"  Con cache:  {bench['con_cache']['tiempo']}s ({bench['con_cache']['tok/s']} tok/s)")
    print(f"  Sin cache:  {bench['sin_cache']['tiempo']}s ({bench['sin_cache']['tok/s']} tok/s)")
    print(f"  Speedup:    {bench['speedup']}x")

    # Test 5: streaming
    print("\n--- STREAMING (simulado) ---")
    print("  Tokens: ", end="", flush=True)
    for token_texto in generar_streaming(modelo, tokenizer, "ARKANI",
                                          max_tokens=8, seed=1, usar_cache=True):
        print(f"[{token_texto}]", end="", flush=True)
    print()

    print("\n✓ inferencia.py — listo")
    print("  Siguiente: servidor.py — reemplaza Ollama")

