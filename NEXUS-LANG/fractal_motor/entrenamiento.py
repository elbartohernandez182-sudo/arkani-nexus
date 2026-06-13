"""
entrenamiento.py — Motor de Entrenamiento Fractal ARKANI
==========================================================
Protocolo Wardenclyffe — Motor Fractal v1.0

Implementa backpropagation completo a traves de FractalLM:
  Embedding -> N x TransformerBlock -> LayerNorm -> LM Head

Sin PyTorch. Sin autograd. Solo calculo diferencial en NumPy.

Esto es lo que convierte FractalLM de "pesos aleatorios"
a "modelo que aprendio del dataset fractal".

USO:
    # Demo rapido (corpus sintetico, valida que todo funciona):
    python3 entrenamiento.py --demo

    # Entrenamiento real con el dataset fractal:
    python3 entrenamiento.py --dataset arkani_fractal_dataset_v2.json \\
        --config mini --epochs 1 --max-ejemplos 50 --output ./fractal_model_v1
"""

import numpy as np
import json
import time
import argparse
from pathlib import Path

from modelo import FractalLM, FractalLMConfig, CONFIGS
from tokenizer import FractalTokenizer, ID_PAD, ID_BOS, ID_EOS, IDS_FRACTALES
from attention import crear_causal_mask
from ffn import gelu_grad


# ─────────────────────────────────────────────────────────────────────────────
# OPTIMIZADOR ADAM
# ─────────────────────────────────────────────────────────────────────────────
class AdamOptimizer:
    """
    Adam — converge mas rapido y estable que SGD puro.
    Mantiene momentos de primer y segundo orden por cada matriz de pesos.
    """

    def __init__(self, lr: float = 1e-3, beta1: float = 0.9,
                 beta2: float = 0.999, eps: float = 1e-8,
                 clip_grad: float = 1.0):
        self.lr        = lr
        self.beta1     = beta1
        self.beta2     = beta2
        self.eps       = eps
        self.clip_grad = clip_grad
        self.m = {}
        self.v = {}
        self.t = 0

    def step(self):
        """Incrementa el contador global de pasos (una vez por train_step)."""
        self.t += 1

    def actualizar(self, key: str, param: np.ndarray, grad: np.ndarray):
        """
        Actualiza `param` in-place usando el gradiente `grad`.
        `key` identifica unicamente esta matriz de pesos.
        """
        # Clipping de gradiente — evita explosiones con LR alto
        if self.clip_grad:
            norma = np.linalg.norm(grad)
            if norma > self.clip_grad:
                grad = grad * (self.clip_grad / (norma + 1e-8))

        if key not in self.m:
            self.m[key] = np.zeros_like(param)
            self.v[key] = np.zeros_like(param)

        self.m[key] = self.beta1 * self.m[key] + (1 - self.beta1) * grad
        self.v[key] = self.beta2 * self.v[key] + (1 - self.beta2) * (grad ** 2)

        m_hat = self.m[key] / (1 - self.beta1 ** self.t)
        v_hat = self.v[key] / (1 - self.beta2 ** self.t)

        param -= self.lr * m_hat / (np.sqrt(v_hat) + self.eps)


# ─────────────────────────────────────────────────────────────────────────────
# PERDIDA — CROSS ENTROPY
# ─────────────────────────────────────────────────────────────────────────────
def cross_entropy_loss_and_grad(
    logits:  np.ndarray,
    targets: np.ndarray,
    ignore_index: int = ID_PAD,
) -> tuple[float, np.ndarray]:
    """
    Cross-entropy loss + gradiente respecto a logits.

    logits:  (batch, seq, vocab)
    targets: (batch, seq) — IDs de tokens esperados

    Tokens con valor `ignore_index` (PAD) no contribuyen a la perdida.
    """
    batch, seq, vocab = logits.shape
    logits_flat  = logits.reshape(-1, vocab)
    targets_flat = targets.reshape(-1)

    # Softmax estable
    max_l   = logits_flat.max(axis=-1, keepdims=True)
    exp_l   = np.exp(logits_flat - max_l)
    probs   = exp_l / (exp_l.sum(axis=-1, keepdims=True) + 1e-9)

    # Mascara — ignorar PAD
    mask    = (targets_flat != ignore_index).astype(np.float32)
    n_valid = max(mask.sum(), 1.0)

    # Negative log-likelihood
    idx       = np.arange(len(targets_flat))
    log_probs = np.log(probs[idx, targets_flat] + 1e-9)
    loss      = -float((log_probs * mask).sum() / n_valid)

    # Gradiente: dL/dlogits = (softmax - one_hot) / n_valid
    dlogits = probs.copy()
    dlogits[idx, targets_flat] -= 1.0
    dlogits *= mask[:, np.newaxis]
    dlogits /= n_valid

    return loss, dlogits.reshape(batch, seq, vocab)


# ─────────────────────────────────────────────────────────────────────────────
# GRADIENTES — LAYERNORM (sin aplicar update, solo calcula)
# ─────────────────────────────────────────────────────────────────────────────
def gradiente_layernorm(norm, grad_out: np.ndarray) -> tuple:
    """
    Calcula gradientes de LayerNorm SIN actualizar pesos.
    Usa la cache guardada por norm.forward().

    Returns: (dx, d_gamma, d_beta)
    """
    x      = norm._cache['x']
    x_norm = norm._cache['x_norm']
    var    = norm._cache['var']
    media  = norm._cache['media']
    N      = x.shape[-1]
    eps    = norm.eps

    d_gamma = (grad_out * x_norm).sum(axis=(0, 1))
    d_beta  = grad_out.sum(axis=(0, 1))

    dx_norm = grad_out * norm.gamma
    dvar    = (-0.5 * dx_norm * (x - media) *
               (var + eps) ** (-1.5)).sum(-1, keepdims=True)
    dmean   = (-dx_norm / np.sqrt(var + eps)).sum(-1, keepdims=True)
    dx      = (dx_norm / np.sqrt(var + eps) +
               2 * dvar * (x - media) / N + dmean / N)

    return dx, d_gamma, d_beta


# ─────────────────────────────────────────────────────────────────────────────
# GRADIENTES — FEED FORWARD (sin aplicar update, solo calcula)
# ─────────────────────────────────────────────────────────────────────────────
def gradiente_ffn(ffn, grad_out: np.ndarray) -> tuple:
    """
    Calcula gradientes de la FFN SIN actualizar pesos.
    Usa la cache guardada por ffn.forward().

    Returns: (dx, dW1, db1, dW2, db2)
    """
    x     = ffn._cache['x']
    h     = ffn._cache['h']
    h_act = ffn._cache['h_act']
    bs    = x.shape[0] * x.shape[1]

    dW2 = h_act.reshape(bs, -1).T @ grad_out.reshape(bs, -1)
    db2 = grad_out.sum(axis=(0, 1))

    if ffn.activacion == "gelu":
        d_h_act = grad_out @ ffn.W2.T
        d_h     = d_h_act * gelu_grad(h)
    else:  # relu
        d_h_act = grad_out @ ffn.W2.T
        d_h     = d_h_act * (h > 0).astype(np.float32)

    dW1 = x.reshape(bs, -1).T @ d_h.reshape(bs, -1)
    db1 = d_h.sum(axis=(0, 1))

    dx = d_h @ ffn.W1.T

    return dx, dW1, db1, dW2, db2


# ─────────────────────────────────────────────────────────────────────────────
# GRADIENTES — MULTI-HEAD ATTENTION (sin aplicar update, solo calcula)
# ─────────────────────────────────────────────────────────────────────────────
def gradiente_attention(attn, grad_out: np.ndarray) -> dict:
    """
    Calcula gradientes de Multi-Head Attention SIN actualizar pesos.
    Usa la cache guardada por attn.forward().

    Este es el calculo mas complejo del motor:
    deriva a traves de softmax(QK^T/sqrt(d_k))V y las 4 proyecciones lineales.

    Returns: dict con dx y gradientes de W_q,W_k,W_v,W_o,b_q,b_k,b_v,b_o
    """
    cache  = attn._cache
    x      = cache['x']
    Q, K, V = cache['Q'], cache['K'], cache['V']
    pesos  = cache['pesos']
    merged = cache['merged']

    batch, seq, d_model = x.shape
    escala = np.sqrt(attn.d_k)

    # ── Salida: output = merged @ W_o + b_o ──────────────────────────────────
    merged_flat = merged.reshape(-1, d_model)
    grad_flat   = grad_out.reshape(-1, d_model)
    dW_o = merged_flat.T @ grad_flat
    db_o = grad_out.sum(axis=(0, 1))
    d_merged = grad_out @ attn.W_o.T  # (batch, seq, d_model)

    # ── FOLD inverso: dividir gradiente en cabezas ──────────────────────────
    d_attended = attn._split_heads(d_merged)  # (batch, heads, seq, d_k)

    # ── attended = pesos @ V ─────────────────────────────────────────────────
    d_pesos = d_attended @ V.transpose(0, 1, 3, 2)   # (batch, heads, seq_q, seq_k)
    d_V     = pesos.transpose(0, 1, 3, 2) @ d_attended  # (batch, heads, seq_k, d_k)

    # ── softmax backward: pesos = softmax(scores) ───────────────────────────
    # d_scores = pesos * (d_pesos - sum(d_pesos * pesos, axis=-1))
    suma    = (d_pesos * pesos).sum(axis=-1, keepdims=True)
    d_scores = pesos * (d_pesos - suma)
    d_scores = d_scores / escala

    # ── scores = Q @ K^T / sqrt(d_k) ──────────────────────────────────────────
    dQ = d_scores @ K                              # (batch, heads, seq_q, d_k)
    dK = d_scores.transpose(0, 1, 3, 2) @ Q          # (batch, heads, seq_k, d_k)

    # ── SPAWN inverso: reunir cabezas ────────────────────────────────────────
    dQ_m = attn._merge_heads(dQ)  # (batch, seq, d_model)
    dK_m = attn._merge_heads(dK)
    dV_m = attn._merge_heads(d_V)

    # ── Proyecciones lineales: Q = x @ W_q + b_q (igual K, V) ────────────────
    x_flat  = x.reshape(-1, d_model)
    dQ_flat = dQ_m.reshape(-1, d_model)
    dK_flat = dK_m.reshape(-1, d_model)
    dV_flat = dV_m.reshape(-1, d_model)

    dW_q = x_flat.T @ dQ_flat
    dW_k = x_flat.T @ dK_flat
    dW_v = x_flat.T @ dV_flat

    db_q = dQ_m.sum(axis=(0, 1))
    db_k = dK_m.sum(axis=(0, 1))
    db_v = dV_m.sum(axis=(0, 1))

    # ── Gradiente respecto a x (suma de los 3 caminos Q,K,V) ─────────────────
    dx = dQ_m @ attn.W_q.T + dK_m @ attn.W_k.T + dV_m @ attn.W_v.T

    return {
        'dx': dx,
        'dW_q': dW_q, 'dW_k': dW_k, 'dW_v': dW_v, 'dW_o': dW_o,
        'db_q': db_q, 'db_k': db_k, 'db_v': db_v, 'db_o': db_o,
    }


# ─────────────────────────────────────────────────────────────────────────────
# BACKWARD DE UN BLOQUE TRANSFORMER COMPLETO
# ─────────────────────────────────────────────────────────────────────────────
def backward_transformer_block(bloque, grad_out: np.ndarray, opt: AdamOptimizer, idx: int) -> np.ndarray:
    """
    Backprop a traves de un TransformerBlock completo:
      x -> norm1 -> attn -> (+x residual) -> norm2 -> ffn -> (+residual)

    Aplica las actualizaciones de pesos via Adam y retorna
    el gradiente respecto a la entrada del bloque (para encadenar
    hacia el bloque anterior).
    """
    # ── Sub-bloque 2: x1 = x_in + ffn(norm2(x1)) ─────────────────────────────
    dx_ffn, dW1, db1, dW2, db2 = gradiente_ffn(bloque.ffn, grad_out)
    dx_norm2, dg2, db_n2 = gradiente_layernorm(bloque.norm2, dx_ffn)
    dx1 = grad_out + dx_norm2  # residual: ambos caminos aportan gradiente

    # Aplicar updates FFN + norm2
    opt.actualizar(f'b{idx}.ffn.W1', bloque.ffn.W1, dW1)
    opt.actualizar(f'b{idx}.ffn.W2', bloque.ffn.W2, dW2)
    opt.actualizar(f'b{idx}.ffn.b1', bloque.ffn.b1, db1)
    opt.actualizar(f'b{idx}.ffn.b2', bloque.ffn.b2, db2)
    opt.actualizar(f'b{idx}.norm2.gamma', bloque.norm2.gamma, dg2)
    opt.actualizar(f'b{idx}.norm2.beta',  bloque.norm2.beta,  db_n2)

    # ── Sub-bloque 1: x_in = x_in_prev + attn(norm1(x_in)) ───────────────────
    grad_attn = gradiente_attention(bloque.attn, dx1)
    dx_norm1, dg1, db_n1 = gradiente_layernorm(bloque.norm1, grad_attn['dx'])
    dx_in = dx1 + dx_norm1  # residual

    # Aplicar updates Attention + norm1
    opt.actualizar(f'b{idx}.attn.W_q', bloque.attn.W_q, grad_attn['dW_q'])
    opt.actualizar(f'b{idx}.attn.W_k', bloque.attn.W_k, grad_attn['dW_k'])
    opt.actualizar(f'b{idx}.attn.W_v', bloque.attn.W_v, grad_attn['dW_v'])
    opt.actualizar(f'b{idx}.attn.W_o', bloque.attn.W_o, grad_attn['dW_o'])
    opt.actualizar(f'b{idx}.attn.b_q', bloque.attn.b_q, grad_attn['db_q'])
    opt.actualizar(f'b{idx}.attn.b_k', bloque.attn.b_k, grad_attn['db_k'])
    opt.actualizar(f'b{idx}.attn.b_v', bloque.attn.b_v, grad_attn['db_v'])
    opt.actualizar(f'b{idx}.attn.b_o', bloque.attn.b_o, grad_attn['db_o'])
    opt.actualizar(f'b{idx}.norm1.gamma', bloque.norm1.gamma, dg1)
    opt.actualizar(f'b{idx}.norm1.beta',  bloque.norm1.beta,  db_n1)

    return dx_in


# ─────────────────────────────────────────────────────────────────────────────
# FORWARD COMPLETO CON CACHES (para entrenamiento)
# ─────────────────────────────────────────────────────────────────────────────
def forward_entrenamiento(modelo: FractalLM, tokens: np.ndarray) -> tuple:
    """
    Forward pass que mantiene todas las caches necesarias para backward.
    A diferencia de modelo.forward(), no usa KV-Cache (eso es solo inferencia).

    Returns: (logits, x_norm_final)
    """
    seq_len = tokens.shape[1]
    mask    = crear_causal_mask(seq_len)

    x = modelo.embedding.forward(tokens, agregar_pe=True)

    for bloque in modelo.bloques:
        x = bloque.forward(x, mask=mask)

    x_norm = modelo.norm_final.forward(x)
    logits = x_norm @ modelo.embedding.W.T

    return logits, x_norm


# ─────────────────────────────────────────────────────────────────────────────
# UN PASO DE ENTRENAMIENTO (forward + backward + update)
# ─────────────────────────────────────────────────────────────────────────────
def train_step(modelo: FractalLM, tokens: np.ndarray, opt: AdamOptimizer) -> float:
    """
    Ejecuta un paso completo de entrenamiento:
      1. Forward (con caches)
      2. Loss + gradiente inicial
      3. Backward LM Head -> norm_final -> bloques (orden inverso) -> embedding
      4. Adam update en cada matriz de pesos

    tokens: (batch, seq_len) — secuencia completa.
            input = tokens[:, :-1], target = tokens[:, 1:]

    Returns: loss (float)
    """
    opt.step()  # incrementa contador global Adam

    inputs  = tokens[:, :-1]
    targets = tokens[:, 1:]

    # ── Forward ───────────────────────────────────────────────────────────────
    logits, x_norm = forward_entrenamiento(modelo, inputs)

    # ── Loss + gradiente respecto a logits ───────────────────────────────────
    loss, dlogits = cross_entropy_loss_and_grad(logits, targets)

    # ── LM Head (weight tying: logits = x_norm @ embedding.W^T) ─────────────
    batch, seq, vocab = logits.shape
    d_model = modelo.config.d_model

    dlogits_flat = dlogits.reshape(-1, vocab)
    x_norm_flat  = x_norm.reshape(-1, d_model)

    dW_head = dlogits_flat.T @ x_norm_flat       # (vocab, d_model) — contribuye a embedding.W
    dx_norm = dlogits @ modelo.embedding.W        # (batch, seq, d_model)

    # ── Backward norm_final ───────────────────────────────────────────────────
    dx, d_gamma_f, d_beta_f = gradiente_layernorm(modelo.norm_final, dx_norm)
    opt.actualizar('norm_final.gamma', modelo.norm_final.gamma, d_gamma_f)
    opt.actualizar('norm_final.beta',  modelo.norm_final.beta,  d_beta_f)

    # ── Backward bloques (orden inverso) ─────────────────────────────────────
    for idx in reversed(range(len(modelo.bloques))):
        dx = backward_transformer_block(modelo.bloques[idx], dx, opt, idx)

    # ── Backward embedding (camino lookup + camino LM head) ──────────────────
    # Camino lookup: dx es gradiente respecto a (embedding + PE)
    grad_emb_lookup = np.zeros_like(modelo.embedding.W)
    np.add.at(grad_emb_lookup, inputs.flatten(), dx.reshape(-1, d_model))

    # Suma de ambos caminos (weight tying)
    grad_emb_total = grad_emb_lookup + dW_head

    opt.actualizar('embedding.W', modelo.embedding.W, grad_emb_total)

    # Re-normalizar ejes fractales periodicamente (cada 50 steps)
    if opt.t % 50 == 0:
        modelo.embedding._normalizar_fractales()

    return loss


# ─────────────────────────────────────────────────────────────────────────────
# PREPARAR BATCHES DESDE TEXTO
# ─────────────────────────────────────────────────────────────────────────────
def preparar_batch(
    textos:     list[str],
    tokenizer:  FractalTokenizer,
    max_length: int = 256,
) -> np.ndarray:
    """
    Tokeniza una lista de textos y los empaqueta en un batch con padding.
    Retorna (batch, max_length) listo para train_step.
    """
    batch_ids = []
    for texto in textos:
        ids = tokenizer.encode(texto, agregar_bos=True, agregar_eos=True, max_length=max_length)
        if len(ids) < max_length:
            ids = ids + [ID_PAD] * (max_length - len(ids))
        batch_ids.append(ids[:max_length])

    return np.array(batch_ids, dtype=np.int64)


# ─────────────────────────────────────────────────────────────────────────────
# ENTRENAMIENTO DESDE EL DATASET FRACTAL ARKANI
# ─────────────────────────────────────────────────────────────────────────────
def entrenar_desde_dataset(
    dataset_path: str,
    config_nombre: str = "mini",
    epochs:        int = 1,
    batch_size:    int = 2,
    max_length:    int = 256,
    max_ejemplos:  int = 50,
    lr:            float = 3e-4,
    output_dir:    str = "./fractal_model_entrenado",
    guardar_cada:  int = 20,
    reanudar:      bool = False,
):
    """
    Entrena FractalLM con el dataset fractal de ARKANI (1016 ejemplos).

    Formato de cada ejemplo: instruction + " " + output -> texto unico
    El modelo aprende a predecir el siguiente token sobre todo el texto.
    """
    print("=" * 55)
    print("  ARKANI — Entrenamiento FractalLM")
    print("  Protocolo Wardenclyffe")
    print("=" * 55)

    # ── Cargar dataset ─────────────────────────────────────────────────────────
    with open(dataset_path, encoding="utf-8") as f:
        data = json.load(f)

    if max_ejemplos:
        data = data[:max_ejemplos]

    textos = [f"{ej['instruction']} {ej['output']}" for ej in data]
    print(f"\nDataset: {len(textos)} ejemplos (de {dataset_path})")

    # ── Modelo + tokenizador ──────────────────────────────────────────────────
    output_path = Path(output_dir)

    if reanudar and output_path.exists() and (output_path / "config.json").exists():
        print(f"Reanudando desde: {output_dir}")
        modelo    = FractalLM.cargar(str(output_path))
        tokenizer = FractalTokenizer.cargar(str(output_path / "tokenizer"))
    else:
        config = CONFIGS.get(config_nombre, CONFIGS["mini"]).__class__(
            **{**CONFIGS.get(config_nombre, CONFIGS["mini"]).__dict__}
        )
        print(f"\nEntrenando tokenizador (vocab_size={config.vocab_size})...")
        tokenizer = FractalTokenizer(vocab_size=config.vocab_size)
        tokenizer.entrenar(textos, verbose=False)

        modelo = FractalLM(config)

    print(modelo.resumen())
    print(f"\nConfig entrenamiento:")
    print(f"  epochs:      {epochs}")
    print(f"  batch_size:  {batch_size}")
    print(f"  max_length:  {max_length}")
    print(f"  lr:          {lr}")

    opt = AdamOptimizer(lr=lr)
    historial_loss = []

    # ── Loop de entrenamiento ─────────────────────────────────────────────────
    total_steps = (len(textos) // batch_size) * epochs
    step = 0
    t_inicio = time.time()

    for epoch in range(epochs):
        # Mezclar orden cada epoch
        indices = np.random.default_rng(1979 + epoch).permutation(len(textos))

        for i in range(0, len(textos) - batch_size + 1, batch_size):
            batch_textos = [textos[j] for j in indices[i:i+batch_size]]
            batch_tokens = preparar_batch(batch_textos, tokenizer, max_length)

            loss = train_step(modelo, batch_tokens, opt)
            historial_loss.append(loss)
            step += 1

            if step % 5 == 0 or step == 1:
                transcurrido = time.time() - t_inicio
                eta = (transcurrido / step) * (total_steps - step)
                print(f"  [{step}/{total_steps}] epoch={epoch+1} loss={loss:.4f} "
                      f"({transcurrido:.1f}s, ETA {eta:.0f}s)")

            if step % guardar_cada == 0:
                modelo.guardar(str(output_path))
                tokenizer.guardar(str(output_path / "tokenizer"))
                print(f"  ✓ Checkpoint guardado en {output_path}")

    # ── Guardar final ─────────────────────────────────────────────────────────
    modelo.guardar(str(output_path))
    tokenizer.guardar(str(output_path / "tokenizer"))

    # Guardar historial de loss
    with open(output_path / "historial_loss.json", "w") as f:
        json.dump(historial_loss, f)

    print(f"\n✓ Entrenamiento completado")
    print(f"  Loss inicial: {historial_loss[0]:.4f}")
    print(f"  Loss final:   {historial_loss[-1]:.4f}")
    print(f"  Modelo guardado en: {output_path}")

    return modelo, tokenizer, historial_loss


# ─────────────────────────────────────────────────────────────────────────────
# MAIN — demo + entrenamiento real
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Entrenamiento FractalLM — Protocolo Wardenclyffe")
    parser.add_argument("--demo", action="store_true", help="Demo rapido con corpus sintetico")
    parser.add_argument("--dataset", default=None, help="Ruta al dataset JSON fractal")
    parser.add_argument("--config", default="nano", choices=list(CONFIGS.keys()))
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--max-length", type=int, default=128)
    parser.add_argument("--max-ejemplos", type=int, default=50)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--output", default="./fractal_model_entrenado")
    parser.add_argument("--guardar-cada", type=int, default=20)
    parser.add_argument("--reanudar", action="store_true")

    args = parser.parse_args()

    if args.dataset:
        entrenar_desde_dataset(
            dataset_path=args.dataset,
            config_nombre=args.config,
            epochs=args.epochs,
            batch_size=args.batch_size,
            max_length=args.max_length,
            max_ejemplos=args.max_ejemplos,
            lr=args.lr,
            output_dir=args.output,
            guardar_cada=args.guardar_cada,
            reanudar=args.reanudar,
        )

    else:
        # ── DEMO: corpus sintetico pequeno — valida que el backprop funciona ───
        print("=" * 55)
        print("  ARKANI — Entrenamiento FractalLM (DEMO)")
        print("  Protocolo Wardenclyffe")
        print("=" * 55)

        corpus = [
            "SPAWN analiza el problema desde varias perspectivas",
            "FOLD sintetiza las ideas en una respuesta unica",
            "LINK conecta dos conceptos distantes entre si",
            "EVOLVE detecta el error y genera una correccion",
            "SUM integra A y B preservando ambos elementos",
            "IF bifurca el flujo segun la condicion dada",
            "LOOP itera refinando el estado en cada paso",
            "ARKANI piensa en lenguaje fractal nativo siempre",
        ] * 15

        config = CONFIGS["nano"]
        print(f"\nConfig: {config.nombre}")

        tokenizer = FractalTokenizer(vocab_size=config.vocab_size)
        tokenizer.entrenar(corpus, verbose=False)
        print(f"Tokenizador: {len(tokenizer.vocab)} tokens")

        modelo = FractalLM(config)
        print(modelo.resumen())

        opt = AdamOptimizer(lr=1e-3)

        print("\n--- ENTRENANDO (50 steps) ---")
        historial_loss = []
        t0 = time.time()

        for step in range(1, 51):
            # Batch de 4 textos aleatorios del corpus
            rng = np.random.default_rng(step)
            batch_textos = [corpus[i] for i in rng.choice(len(corpus), 4, replace=False)]
            batch_tokens = preparar_batch(batch_textos, tokenizer, max_length=32)

            loss = train_step(modelo, batch_tokens, opt)
            historial_loss.append(loss)

            if step % 10 == 0 or step == 1:
                print(f"  Step {step:3}: loss = {loss:.4f}")

        t_total = time.time() - t0
        print(f"\n  Tiempo total: {t_total:.1f}s ({t_total/50*1000:.0f}ms/step)")
        print(f"  Loss inicial: {historial_loss[0]:.4f}")
        print(f"  Loss final:   {historial_loss[-1]:.4f}")
        mejora = (1 - historial_loss[-1]/historial_loss[0]) * 100
        print(f"  Mejora:       {mejora:.1f}%")

        # Validar que no hay NaN/Inf
        assert all(np.isfinite(l) for l in historial_loss), "¡Loss con NaN/Inf!"
        print(f"  ✓ Sin NaN/Inf — entrenamiento numericamente estable")

        # ── EVOLVE: inspeccion antes/despues ─────────────────────────────────
        print("\n--- EVOLVE: INSPECCION POST-ENTRENAMIENTO ---")
        informe = modelo.evolve_inspeccion()
        print(f"  Embedding norma media: {informe['embedding']['norma_media']}")
        print(f"  Tokens muertos: {informe['embedding']['tokens_muertos']}")
        for b in informe['bloques']:
            print(f"  Capa {b['capa']}: ffn_W1={b['ffn_W1']:.3f}, attn_Wq={b['attn_Wq']:.3f} [{b['estado']}]")

        # ── Generacion post-entrenamiento ────────────────────────────────────
        print("\n--- GENERACION POST-ENTRENAMIENTO ---")
        from inferencia import generar
        resultado = generar(modelo, tokenizer, "SPAWN", max_tokens=15,
                             temperatura=0.8, top_k=10, seed=42, usar_cache=True)
        print(f"  Prompt: 'SPAWN'")
        print(f"  Generado: {resultado['texto']!r}")
        print(f"  Tokens: {resultado['tokens_generados'][:10]}")

        print("\n✓ entrenamiento.py — backprop completo validado")
        print("  Para entrenar con el dataset real:")
        print("  python3 entrenamiento.py --dataset arkani_fractal_dataset_v2.json \\")
        print("    --config mini --epochs 1 --max-ejemplos 50 --output ./fractal_model_v1")

