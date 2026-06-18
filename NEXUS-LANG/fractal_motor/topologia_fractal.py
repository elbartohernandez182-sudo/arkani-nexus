"""
topologia_fractal.py — Topologia Fractal Real (Fase 2)
========================================================
Protocolo Wardenclyffe — Motor Fractal v2.0 (experimental)

FASE 1 (modelo.py): vocabulario fractal ENCIMA de un transformer estandar
FASE 2 (este archivo): TOPOLOGIA fractal — el computo mismo fluye
                       en multiples direcciones, no en una pila lineal.

CELDA FRACTAL (inspirada en FractalNet, 2016, + nuestras 7 operaciones):

    entrada x
    ├── SPAWN: dos caminos paralelos desde x
    │     camino_corto   = short(x)                    (1 atomo)
    │     camino_profundo = deep(deep(x))              (LOOP: mismo
    │                                                    bloque 2 veces)
    ├── LINK: el camino corto actua como atajo respecto al profundo
    └── FOLD: salida = g0*camino_corto + g1*camino_profundo
              (g0,g1 = pesos APRENDIDOS, softmax)

Una "Celda Fractal" tiene 2 atomos (short, deep) — el MISMO numero
de parametros que 2 TransformerBlock estandar apilados — pero con
topologia DIFERENTE: ramificacion + recurrencia + combinacion aprendida,
en vez de una linea recta 1->2.

EVOLVE: los pesos g0,g1 son interpretables — podemos VER que camino
"pesa mas" para distintos tipos de entrada.

USO:
    python3 topologia_fractal.py --demo
    (compara loss: FractalLM estandar (n_layers=2) vs Topologia (n_cells=1),
     mismos parametros, mismos datos)
"""

import numpy as np
from copy import deepcopy
from dataclasses import dataclass

from ffn import TransformerBlock, LayerNorm
from attention import crear_causal_mask
from embeddings import FractalEmbedding
from tokenizer import FractalTokenizer, ID_PAD
from entrenamiento import (
    AdamOptimizer,
    cross_entropy_loss_and_grad,
    gradiente_layernorm,
    gradiente_ffn,
    gradiente_attention,
    preparar_batch,
)


# ─────────────────────────────────────────────────────────────────────────────
# UTILIDADES — snapshot/restore de caches (necesario por el LOOP con
# pesos compartidos: 'deep' se aplica 2 veces, cada aplicacion sobreescribe
# las caches internas, asi que guardamos una copia de cada una)
# ─────────────────────────────────────────────────────────────────────────────
def snapshot_block(bloque: TransformerBlock) -> dict:
    """Copia las caches de forward de un TransformerBlock (para LOOP)."""
    return {
        'attn':  deepcopy(bloque.attn._cache),
        'ffn':   deepcopy(bloque.ffn._cache),
        'norm1': deepcopy(bloque.norm1._cache),
        'norm2': deepcopy(bloque.norm2._cache),
    }


def restore_block(bloque: TransformerBlock, snap: dict) -> None:
    """Restaura las caches de un TransformerBlock desde un snapshot."""
    bloque.attn._cache  = snap['attn']
    bloque.ffn._cache   = snap['ffn']
    bloque.norm1._cache = snap['norm1']
    bloque.norm2._cache = snap['norm2']


def backward_block_grads(bloque: TransformerBlock, grad_out: np.ndarray) -> tuple:
    """
    Backprop de un TransformerBlock SIN aplicar updates —
    retorna (dx, dict_de_gradientes). Usa las caches ACTUALES
    de bloque (deben corresponder al forward que se quiere derivar).
    """
    grads = {}

    # Sub-bloque 2: FFN + norm2 (residual)
    dx_ffn, dW1, db1, dW2, db2 = gradiente_ffn(bloque.ffn, grad_out)
    dx_norm2, dg2, db_n2 = gradiente_layernorm(bloque.norm2, dx_ffn)
    dx1 = grad_out + dx_norm2

    grads['ffn.W1'] = dW1; grads['ffn.W2'] = dW2
    grads['ffn.b1'] = db1; grads['ffn.b2'] = db2
    grads['norm2.gamma'] = dg2; grads['norm2.beta'] = db_n2

    # Sub-bloque 1: Attention + norm1 (residual)
    ga = gradiente_attention(bloque.attn, dx1)
    dx_norm1, dg1, db_n1 = gradiente_layernorm(bloque.norm1, ga['dx'])
    dx_in = dx1 + dx_norm1

    for k in ['W_q', 'W_k', 'W_v', 'W_o', 'b_q', 'b_k', 'b_v', 'b_o']:
        grads[f'attn.{k}'] = ga[f'd{k}']
    grads['norm1.gamma'] = dg1; grads['norm1.beta'] = db_n1

    return dx_in, grads


def sumar_grads(g1: dict, g2: dict) -> dict:
    """Suma elemento a elemento dos diccionarios de gradientes (mismas keys)."""
    return {k: g1[k] + g2[k] for k in g1}


def apply_grads(bloque: TransformerBlock, grads: dict, opt: AdamOptimizer, prefix: str) -> None:
    """Aplica un diccionario de gradientes a un TransformerBlock via Adam."""
    opt.actualizar(f'{prefix}.ffn.W1', bloque.ffn.W1, grads['ffn.W1'])
    opt.actualizar(f'{prefix}.ffn.W2', bloque.ffn.W2, grads['ffn.W2'])
    opt.actualizar(f'{prefix}.ffn.b1', bloque.ffn.b1, grads['ffn.b1'])
    opt.actualizar(f'{prefix}.ffn.b2', bloque.ffn.b2, grads['ffn.b2'])
    opt.actualizar(f'{prefix}.norm2.gamma', bloque.norm2.gamma, grads['norm2.gamma'])
    opt.actualizar(f'{prefix}.norm2.beta',  bloque.norm2.beta,  grads['norm2.beta'])

    for k in ['W_q', 'W_k', 'W_v', 'W_o', 'b_q', 'b_k', 'b_v', 'b_o']:
        opt.actualizar(f'{prefix}.attn.{k}', getattr(bloque.attn, k), grads[f'attn.{k}'])

    opt.actualizar(f'{prefix}.norm1.gamma', bloque.norm1.gamma, grads['norm1.gamma'])
    opt.actualizar(f'{prefix}.norm1.beta',  bloque.norm1.beta,  grads['norm1.beta'])


# ─────────────────────────────────────────────────────────────────────────────
# SOFTMAX y su gradiente para el FOLD gate (2 valores: corto/profundo)
# ─────────────────────────────────────────────────────────────────────────────
def softmax_vec(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - x.max())
    return e / e.sum()


def softmax_grad_from_values(gates: np.ndarray, dvals: np.ndarray) -> np.ndarray:
    """Jacobiano-vector del softmax: d_logits = g*(dvals - sum(dvals*g))."""
    s = (dvals * gates).sum()
    return gates * (dvals - s)


# ─────────────────────────────────────────────────────────────────────────────
# CELDA FRACTAL
# ─────────────────────────────────────────────────────────────────────────────
class FractalCell:
    """
    Unidad minima de topologia fractal — 2 atomos (short, deep),
    misma cuenta de parametros que 2 TransformerBlock secuenciales,
    pero conectados con SPAWN+LOOP+FOLD+LINK en vez de una linea recta.
    """

    def __init__(self, d_model: int, n_heads: int, d_ff: int, seed: int):
        self.short = TransformerBlock(d_model, n_heads, d_ff, seed=seed)
        self.deep  = TransformerBlock(d_model, n_heads, d_ff, seed=seed + 1000)
        # FOLD gate — 2 logits, softmax -> [g_corto, g_profundo]
        # Inicializado en 0 -> arranca en 50/50
        self.fold_logits = np.zeros(2, dtype=np.float32)
        self._cache = {}

    def forward(self, x: np.ndarray, mask: np.ndarray) -> np.ndarray:
        # SPAWN: dos perspectivas paralelas desde x
        out_short = self.short.forward(x, mask=mask)          # camino_corto

        h = self.deep.forward(x, mask=mask)                    # LOOP paso 1
        cache_deep_1 = snapshot_block(self.deep)
        out_deep = self.deep.forward(h, mask=mask)             # LOOP paso 2
        cache_deep_2 = snapshot_block(self.deep)

        # FOLD: combinacion aprendida
        gates = softmax_vec(self.fold_logits)
        out = gates[0] * out_short + gates[1] * out_deep

        self._cache = {
            'out_short': out_short, 'out_deep': out_deep, 'gates': gates,
            'cache_short':  snapshot_block(self.short),
            'cache_deep_1': cache_deep_1, 'cache_deep_2': cache_deep_2,
        }
        return out

    def backward(self, grad_out: np.ndarray, opt: AdamOptimizer, idx: int) -> np.ndarray:
        c = self._cache
        gates = c['gates']
        out_short, out_deep = c['out_short'], c['out_deep']

        # ── Gradiente del FOLD gate ──────────────────────────────────────────
        d_g0 = float((grad_out * out_short).sum())
        d_g1 = float((grad_out * out_deep).sum())
        d_logits = softmax_grad_from_values(gates, np.array([d_g0, d_g1], dtype=np.float32))
        opt.actualizar(f'cell{idx}.fold_logits', self.fold_logits, d_logits)

        d_out_short = gates[0] * grad_out
        d_out_deep  = gates[1] * grad_out

        # ── Camino corto (SPAWN rama A) ──────────────────────────────────────
        restore_block(self.short, c['cache_short'])
        dx_short, grads_short = backward_block_grads(self.short, d_out_short)
        apply_grads(self.short, grads_short, opt, f'cell{idx}.short')

        # ── Camino profundo (SPAWN rama B, LOOP 2 pasos, pesos compartidos) ──
        # Paso 2 (h -> out_deep)
        restore_block(self.deep, c['cache_deep_2'])
        dh2, grads_d2 = backward_block_grads(self.deep, d_out_deep)
        # Paso 1 (x -> h)
        restore_block(self.deep, c['cache_deep_1'])
        dx_deep, grads_d1 = backward_block_grads(self.deep, dh2)

        # LOOP: pesos compartidos -> sumar gradientes de ambos pasos
        grads_deep = sumar_grads(grads_d1, grads_d2)
        apply_grads(self.deep, grads_deep, opt, f'cell{idx}.deep')

        # LINK: el atajo corto y el camino profundo se suman al gradiente de x
        dx = dx_short + dx_deep
        return dx

    def contar_parametros(self) -> int:
        return (self.short.contar_parametros()['total'] +
                self.deep.contar_parametros()['total'] + 2)  # +2 = fold_logits


# ─────────────────────────────────────────────────────────────────────────────
# MODELO COMPLETO CON TOPOLOGIA FRACTAL
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class FractalTopologyConfig:
    vocab_size:  int = 4000
    d_model:     int = 128
    n_heads:     int = 4
    d_ff:        int = 512
    n_cells:     int = 1
    max_seq_len: int = 1024
    seed:        int = 1979
    nombre:      str = "FractalTopology-NANO"


class FractalTopologyLM:
    """
    Como FractalLM (modelo.py) pero las capas son FractalCell
    en vez de TransformerBlock — topologia fractal en vez de pila.
    """

    def __init__(self, config: FractalTopologyConfig):
        self.config = config
        self.embedding = FractalEmbedding(
            vocab_size=config.vocab_size, embed_dim=config.d_model,
            max_seq_len=config.max_seq_len, seed=config.seed,
        )
        self.celdas = [
            FractalCell(config.d_model, config.n_heads, config.d_ff, seed=config.seed + i * 7)
            for i in range(config.n_cells)
        ]
        self.norm_final = LayerNorm(config.d_model)

    def contar_parametros(self) -> dict:
        p_emb  = self.config.vocab_size * self.config.d_model
        p_cell = sum(c.contar_parametros() for c in self.celdas)
        p_norm = 2 * self.config.d_model
        total  = p_emb + p_cell + p_norm
        return {'embedding': p_emb, 'celdas': p_cell, 'norm_final': p_norm,
                'total': total, 'total_M': round(total / 1e6, 3)}

    def resumen(self) -> str:
        p = self.contar_parametros()
        return (f"{'='*50}\n  {self.config.nombre} — Topologia Fractal\n{'='*50}\n"
                f"  vocab_size: {self.config.vocab_size:,}\n"
                f"  d_model:    {self.config.d_model}\n"
                f"  n_cells:    {self.config.n_cells} (= {2*self.config.n_cells} atomos)\n"
                f"  Parametros: {p['total_M']}M\n{'='*50}")

    def gates_actuales(self) -> list:
        """EVOLVE: inspeccion de los pesos FOLD de cada celda."""
        return [softmax_vec(c.fold_logits).tolist() for c in self.celdas]


def forward_topologia(modelo: FractalTopologyLM, tokens: np.ndarray) -> tuple:
    """Forward completo con caches (para entrenamiento)."""
    seq_len = tokens.shape[1]
    mask = crear_causal_mask(seq_len)

    x = modelo.embedding.forward(tokens, agregar_pe=True)
    for celda in modelo.celdas:
        x = celda.forward(x, mask)

    x_norm = modelo.norm_final.forward(x)
    logits = x_norm @ modelo.embedding.W.T
    return logits, x_norm


def train_step_topologia(modelo: FractalTopologyLM, tokens: np.ndarray, opt: AdamOptimizer) -> float:
    """Un paso de entrenamiento completo (forward + backward + Adam)."""
    opt.step()

    inputs  = tokens[:, :-1]
    targets = tokens[:, 1:]

    logits, x_norm = forward_topologia(modelo, inputs)
    loss, dlogits = cross_entropy_loss_and_grad(logits, targets)

    batch, seq, vocab = logits.shape
    d_model = modelo.config.d_model

    dlogits_flat = dlogits.reshape(-1, vocab)
    x_norm_flat  = x_norm.reshape(-1, d_model)

    dW_head = dlogits_flat.T @ x_norm_flat
    dx_norm = dlogits @ modelo.embedding.W

    dx, dg_f, db_f = gradiente_layernorm(modelo.norm_final, dx_norm)
    opt.actualizar('norm_final.gamma', modelo.norm_final.gamma, dg_f)
    opt.actualizar('norm_final.beta',  modelo.norm_final.beta,  db_f)

    for idx in reversed(range(len(modelo.celdas))):
        dx = modelo.celdas[idx].backward(dx, opt, idx)

    grad_emb = np.zeros_like(modelo.embedding.W)
    np.add.at(grad_emb, inputs.flatten(), dx.reshape(-1, d_model))
    grad_emb_total = grad_emb + dW_head
    opt.actualizar('embedding.W', modelo.embedding.W, grad_emb_total)

    if opt.t % 50 == 0:
        modelo.embedding._normalizar_fractales()

    return loss


# ─────────────────────────────────────────────────────────────────────────────
# MAIN — comparativa Topologia Fractal vs Transformer estandar
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from modelo import FractalLM, FractalLMConfig
    from entrenamiento import train_step as train_step_estandar

    print("=" * 60)
    print("  ARKANI — Topologia Fractal vs Transformer Estandar")
    print("  Protocolo Wardenclyffe — Motor v2.0 (experimental)")
    print("=" * 60)

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

    tokenizer = FractalTokenizer(vocab_size=4000)
    tokenizer.entrenar(corpus, verbose=False)
    print(f"\nTokenizador: {len(tokenizer.vocab)} tokens")

    # ── Configs equivalentes en parametros ───────────────────────────────────
    cfg_estandar = FractalLMConfig(
        vocab_size=len(tokenizer.vocab), d_model=128, n_layers=2,
        n_heads=4, d_ff=512, nombre="Estandar-2capas",
    )
    cfg_fractal = FractalTopologyConfig(
        vocab_size=len(tokenizer.vocab), d_model=128, n_heads=4,
        d_ff=512, n_cells=1, nombre="Fractal-1celda(2atomos)",
    )

    modelo_estandar = FractalLM(cfg_estandar)
    modelo_fractal  = FractalTopologyLM(cfg_fractal)

    p_est = modelo_estandar.contar_parametros()
    p_fra = modelo_fractal.contar_parametros()
    print(f"\nParametros estandar: {p_est['total']:,}")
    print(f"Parametros fractal:  {p_fra['total']:,}")
    print(f"Diferencia:          {abs(p_est['total']-p_fra['total']):,} "
          f"({'igual' if p_est['total']==p_fra['total'] else 'distinto'})")

    opt_est = AdamOptimizer(lr=1e-3)
    opt_fra = AdamOptimizer(lr=1e-3)

    print("\n--- ENTRENANDO AMBOS (50 steps, mismos batches) ---")
    print(f"{'Step':>6} | {'Estandar':>10} | {'Fractal':>10}")
    print("-" * 32)

    loss_est_hist, loss_fra_hist = [], []
    for step in range(1, 51):
        rng = np.random.default_rng(step)
        batch_textos = [corpus[i] for i in rng.choice(len(corpus), 4, replace=False)]
        batch_tokens = preparar_batch(batch_textos, tokenizer, max_length=32)

        l_est = train_step_estandar(modelo_estandar, batch_tokens, opt_est)
        l_fra = train_step_topologia(modelo_fractal, batch_tokens, opt_fra)

        loss_est_hist.append(l_est)
        loss_fra_hist.append(l_fra)

        if step % 10 == 0 or step == 1:
            print(f"{step:6} | {l_est:10.4f} | {l_fra:10.4f}")

    print("-" * 32)
    print(f"\nEstandar — inicial: {loss_est_hist[0]:.4f}  final: {loss_est_hist[-1]:.4f}  "
          f"mejora: {(1-loss_est_hist[-1]/loss_est_hist[0])*100:.1f}%")
    print(f"Fractal  — inicial: {loss_fra_hist[0]:.4f}  final: {loss_fra_hist[-1]:.4f}  "
          f"mejora: {(1-loss_fra_hist[-1]/loss_fra_hist[0])*100:.1f}%")

    assert all(np.isfinite(l) for l in loss_est_hist), "Estandar: NaN/Inf!"
    assert all(np.isfinite(l) for l in loss_fra_hist), "Fractal: NaN/Inf!"
    print("\n✓ Ambos entrenamientos numericamente estables (sin NaN/Inf)")

    # ── EVOLVE: inspeccion de los gates FOLD ─────────────────────────────────
    print("\n--- EVOLVE: PESOS FOLD APRENDIDOS (celda 0) ---")
    gates = modelo_fractal.gates_actuales()[0]
    print(f"  camino_corto (LINK):     {gates[0]*100:.1f}%")
    print(f"  camino_profundo (LOOP):  {gates[1]*100:.1f}%")
    if gates[1] > gates[0]:
        print("  -> el modelo aprendio a confiar MAS en el camino profundo/recurrente")
    else:
        print("  -> el modelo aprendio a confiar MAS en el atajo corto")

    print("\n✓ topologia_fractal.py — Celda Fractal validada")
    print("  SPAWN (ramas) + LOOP (recurrencia) + FOLD (gate aprendido)")
    print("  + LINK (atajo) — topologia real, no solo vocabulario")

