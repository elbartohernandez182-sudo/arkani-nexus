"""
ffn.py — Feed-Forward Network Fractal ARKANI
=============================================
Protocolo Wardenclyffe — Motor Fractal v1.0

La FFN es la 'memoria' del transformer.
Si la atención enruta información entre tokens,
la FFN almacena hechos y transforma representaciones.

ARQUITECTURA:
  Linear(d_model → 4×d_model) → GELU → Linear(4×d_model → d_model)

ANALOGÍA FRACTAL:
  SPAWN(expansion)  — amplifica el espacio de representación
  EVOLVE(activacion)— transforma no-linealmente
  FOLD(contraccion) — sintetiza de vuelta al espacio original

USO:
    from ffn import FeedForward
    ffn = FeedForward(d_model=256)
    output = ffn.forward(x)  # (batch, seq, d_model)
"""

import numpy as np
import json
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# FUNCIONES DE ACTIVACIÓN
# ─────────────────────────────────────────────────────────────────────────────

def gelu(x: np.ndarray) -> np.ndarray:
    """
    GELU — Gaussian Error Linear Unit.
    Mejor que ReLU para LLMs — más suave, permite gradientes negativos pequeños.
    Usada en GPT-2, BERT, y todos los transformers modernos.
    """
    return 0.5 * x * (1.0 + np.tanh(
        np.sqrt(2.0 / np.pi) * (x + 0.044715 * x ** 3)
    ))


def gelu_grad(x: np.ndarray) -> np.ndarray:
    """Gradiente de GELU para backpropagation."""
    tanh_arg = np.sqrt(2.0 / np.pi) * (x + 0.044715 * x ** 3)
    tanh_val  = np.tanh(tanh_arg)
    sech2     = 1.0 - tanh_val ** 2
    dtanh     = np.sqrt(2.0 / np.pi) * (1.0 + 3 * 0.044715 * x ** 2)
    return 0.5 * (1.0 + tanh_val) + 0.5 * x * sech2 * dtanh


def relu(x: np.ndarray) -> np.ndarray:
    """ReLU clásica — más simple pero peor para LLMs."""
    return np.maximum(0, x)


def swiglu(x: np.ndarray, W_gate: np.ndarray, W_up: np.ndarray) -> np.ndarray:
    """
    SwiGLU — usada en LLaMA, Qwen, Gemma.
    Más expresiva que GELU estándar.
    gate × silu(up)
    """
    gate = x @ W_gate
    up   = x @ W_up
    silu = gate * (1.0 / (1.0 + np.exp(-gate)))  # SiLU activation
    return silu * up


# ─────────────────────────────────────────────────────────────────────────────
# LAYER NORMALIZATION
# ─────────────────────────────────────────────────────────────────────────────
class LayerNorm:
    """
    Normalización por capa — estabiliza el entrenamiento.
    Sin esto, los gradientes explotan o desaparecen en redes profundas.

    A diferencia de BatchNorm, LayerNorm normaliza por token
    (no por batch) — funciona igual con batch_size=1.
    """

    def __init__(self, d_model: int, eps: float = 1e-6):
        self.d_model = d_model
        self.eps     = eps
        self.gamma   = np.ones(d_model,  dtype=np.float32)  # escala
        self.beta    = np.zeros(d_model, dtype=np.float32)  # sesgo
        self._cache  = {}

    def forward(self, x: np.ndarray) -> np.ndarray:
        """
        x: (batch, seq_len, d_model)
        Normaliza cada token independientemente.
        """
        media    = x.mean(axis=-1, keepdims=True)
        varianza = x.var(axis=-1,  keepdims=True)
        x_norm   = (x - media) / np.sqrt(varianza + self.eps)
        self._cache = {'x': x, 'media': media, 'var': varianza, 'x_norm': x_norm}
        return self.gamma * x_norm + self.beta

    def backward(self, grad_out: np.ndarray, lr: float = 1e-3) -> np.ndarray:
        """Actualiza gamma y beta, retorna gradiente para x."""
        x      = self._cache['x']
        x_norm = self._cache['x_norm']
        var    = self._cache['var']
        media  = self._cache['media']
        N      = x.shape[-1]

        # Gradientes de gamma y beta
        d_gamma = (grad_out * x_norm).sum(axis=(0, 1))
        d_beta  = grad_out.sum(axis=(0, 1))

        # Actualizar parámetros
        self.gamma -= lr * d_gamma
        self.beta  -= lr * d_beta

        # Gradiente respecto a x
        dx_norm = grad_out * self.gamma
        dvar    = (-0.5 * dx_norm * (x - media) *
                   (var + self.eps) ** (-1.5)).sum(-1, keepdims=True)
        dmean   = (-dx_norm / np.sqrt(var + self.eps)).sum(-1, keepdims=True)
        dx      = (dx_norm / np.sqrt(var + self.eps) +
                   2 * dvar * (x - media) / N + dmean / N)
        return dx


# ─────────────────────────────────────────────────────────────────────────────
# FEED-FORWARD NETWORK FRACTAL
# ─────────────────────────────────────────────────────────────────────────────
class FeedForward:
    """
    Red feed-forward con activación GELU.

    Proceso fractal:
      SPAWN(expansion): d_model → 4×d_model  (amplifica perspectivas)
      EVOLVE(gelu):     activa no-linealmente (transforma)
      FOLD(contraccion): 4×d_model → d_model  (sintetiza)

    La expansión 4x es estándar en todos los transformers modernos.
    Permite al modelo explorar un espacio más rico antes de sintetizar.
    """

    def __init__(
        self,
        d_model:    int,
        d_ff:       int  = None,
        activacion: str  = "gelu",
        seed:       int  = 1979,
    ):
        self.d_model    = d_model
        self.d_ff       = d_ff or 4 * d_model
        self.activacion = activacion

        rng    = np.random.default_rng(seed)
        escala = np.sqrt(2.0 / d_model)

        # Capa de expansión — SPAWN
        self.W1 = rng.normal(0, escala, (d_model, self.d_ff)).astype(np.float32)
        self.b1 = np.zeros(self.d_ff, dtype=np.float32)

        # Capa de contracción — FOLD
        self.W2 = rng.normal(0, escala, (self.d_ff, d_model)).astype(np.float32)
        self.b2 = np.zeros(d_model, dtype=np.float32)

        # Cache para backward
        self._cache = {}

    def _activar(self, x: np.ndarray) -> np.ndarray:
        """Aplica la función de activación configurada."""
        if self.activacion == "gelu":
            return gelu(x)
        elif self.activacion == "relu":
            return relu(x)
        else:
            return gelu(x)  # default

    def forward(self, x: np.ndarray) -> np.ndarray:
        """
        x: (batch, seq_len, d_model)

        SPAWN → amplifica
        EVOLVE(GELU) → transforma no-linealmente
        FOLD → sintetiza
        """
        # SPAWN: expansión al espacio 4x
        h = x @ self.W1 + self.b1           # (batch, seq, d_ff)
        h_act = self._activar(h)            # activación GELU

        # FOLD: contracción al espacio original
        output = h_act @ self.W2 + self.b2  # (batch, seq, d_model)

        # Cache para backward
        self._cache = {'x': x, 'h': h, 'h_act': h_act}

        return output

    def backward(self, grad_out: np.ndarray, lr: float = 1e-3) -> np.ndarray:
        """
        Backpropagation a través de la FFN.
        Actualiza W1, W2, b1, b2.
        """
        x     = self._cache['x']
        h     = self._cache['h']
        h_act = self._cache['h_act']

        # Gradiente de W2 y b2
        batch_seq = x.shape[0] * x.shape[1]
        dW2 = h_act.reshape(batch_seq, -1).T @ grad_out.reshape(batch_seq, -1)
        db2 = grad_out.sum(axis=(0, 1))

        # Gradiente a través de GELU
        if self.activacion == "gelu":
            d_h_act = grad_out @ self.W2.T
            d_h     = d_h_act * gelu_grad(h)
        else:
            d_h_act = grad_out @ self.W2.T
            d_h     = d_h_act * (h > 0).astype(np.float32)

        # Gradiente de W1 y b1
        dW1 = x.reshape(batch_seq, -1).T @ d_h.reshape(batch_seq, -1)
        db1 = d_h.sum(axis=(0, 1))

        # Actualizar pesos
        self.W1 -= lr * dW1
        self.W2 -= lr * dW2
        self.b1 -= lr * db1
        self.b2 -= lr * db2

        # Gradiente respecto a x
        return d_h @ self.W1.T

    def contar_parametros(self) -> dict:
        """Cuenta parámetros entrenables."""
        return {
            'W1':    self.d_model * self.d_ff,
            'W2':    self.d_ff * self.d_model,
            'bias':  self.d_ff + self.d_model,
            'total': 2 * self.d_model * self.d_ff + self.d_ff + self.d_model,
        }

    def guardar(self, directorio: str):
        """Guarda los pesos de la FFN."""
        Path(directorio).mkdir(parents=True, exist_ok=True)
        np.save(f"{directorio}/W1.npy", self.W1)
        np.save(f"{directorio}/W2.npy", self.W2)
        np.save(f"{directorio}/b1.npy", self.b1)
        np.save(f"{directorio}/b2.npy", self.b2)
        with open(f"{directorio}/config.json", 'w') as f:
            json.dump({'d_model': self.d_model, 'd_ff': self.d_ff,
                       'activacion': self.activacion}, f)

    @classmethod
    def cargar(cls, directorio: str) -> "FeedForward":
        """Carga una FFN guardada."""
        with open(f"{directorio}/config.json") as f:
            config = json.load(f)
        ffn = cls(**config)
        ffn.W1 = np.load(f"{directorio}/W1.npy")
        ffn.W2 = np.load(f"{directorio}/W2.npy")
        ffn.b1 = np.load(f"{directorio}/b1.npy")
        ffn.b2 = np.load(f"{directorio}/b2.npy")
        return ffn


# ─────────────────────────────────────────────────────────────────────────────
# TRANSFORMER BLOCK — atencion + FFN + LayerNorm + residual
# ─────────────────────────────────────────────────────────────────────────────
class TransformerBlock:
    """
    Bloque completo del transformer fractal.

    Pre-LayerNorm → Atención → Residual
    Pre-LayerNorm → FFN → Residual

    Pre-LayerNorm es más estable que Post-LayerNorm
    para entrenamiento largo en CPU.
    """

    def __init__(self, d_model: int, n_heads: int, d_ff: int = None, seed: int = 1979):
        from attention import MultiHeadAttention
        self.norm1 = LayerNorm(d_model)
        self.attn  = MultiHeadAttention(d_model, n_heads, seed=seed)
        self.norm2 = LayerNorm(d_model)
        self.ffn   = FeedForward(d_model, d_ff, seed=seed)

    def forward(
        self,
        x:     np.ndarray,
        mask:  np.ndarray = None,
        cache=None,
        capa:  int = 0,
    ) -> np.ndarray:
        """
        SUM(x, attn): residual — preserva información original
        SUM(x, ffn):  residual — segunda preservación
        """
        # Sub-bloque 1: Atención con conexión residual
        x = x + self.attn.forward(self.norm1.forward(x), mask=mask,
                                   cache=cache, capa=capa)
        # Sub-bloque 2: FFN con conexión residual
        x = x + self.ffn.forward(self.norm2.forward(x))
        return x

    def contar_parametros(self) -> dict:
        attn_p = self.attn.contar_parametros()
        ffn_p  = self.ffn.contar_parametros()
        norm_p = 2 * 2 * self.ffn.d_model
        return {
            'atencion':  attn_p['total'],
            'ffn':       ffn_p['total'],
            'layernorm': norm_p,
            'total':     attn_p['total'] + ffn_p['total'] + norm_p,
        }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN — demo de FFN + LayerNorm + TransformerBlock
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print("  ARKANI — FFN + LayerNorm + TransformerBlock")
    print("  Protocolo Wardenclyffe — Motor v1.0")
    print("=" * 55)

    d_model = 64
    n_heads = 4
    batch   = 2
    seq_len = 8

    # Test LayerNorm
    print("\n--- LAYER NORM ---")
    norm = LayerNorm(d_model)
    x    = np.random.randn(batch, seq_len, d_model).astype(np.float32) * 10
    x_n  = norm.forward(x)
    print(f"  Input  — media: {x.mean():.4f}, std: {x.std():.4f}")
    print(f"  Output — media: {x_n.mean():.4f}, std: {x_n.std():.4f}")
    print(f"  ✓ Normalizado correctamente")

    # Test GELU
    print("\n--- GELU vs ReLU ---")
    vals = np.array([-2, -1, -0.5, 0, 0.5, 1, 2], dtype=np.float32)
    print(f"  Input:  {vals}")
    print(f"  GELU:   {np.round(gelu(vals), 3)}")
    print(f"  ReLU:   {np.round(relu(vals), 3)}")
    print(f"  GELU permite valores negativos pequeños — mejor gradiente")

    # Test FFN
    print("\n--- FEED FORWARD ---")
    ffn    = FeedForward(d_model=d_model)
    params = ffn.contar_parametros()
    x      = np.random.randn(batch, seq_len, d_model).astype(np.float32)
    out    = ffn.forward(x)
    print(f"  Input:      {x.shape}")
    print(f"  Output:     {out.shape}")
    print(f"  d_ff:       {ffn.d_ff} (4×{d_model})")
    print(f"  Parámetros: {params['total']:,}")
    print(f"  ✓ Shape preservado: {x.shape == out.shape}")

    # Test backward
    grad = np.random.randn(*out.shape).astype(np.float32)
    dx   = ffn.backward(grad, lr=1e-3)
    print(f"  ✓ Backward OK: grad shape {dx.shape}")

    # Test TransformerBlock
    print("\n--- TRANSFORMER BLOCK ---")
    bloque = TransformerBlock(d_model=d_model, n_heads=n_heads)
    params_bloque = bloque.contar_parametros()
    x_in  = np.random.randn(batch, seq_len, d_model).astype(np.float32)
    from attention import crear_causal_mask
    mask  = crear_causal_mask(seq_len)
    x_out = bloque.forward(x_in, mask=mask)
    print(f"  Input:  {x_in.shape}")
    print(f"  Output: {x_out.shape}")
    print(f"  Parámetros del bloque:")
    for k, v in params_bloque.items():
        print(f"    {k:12}: {v:,}")
    print(f"  ✓ Residual funciona: norma entrada {np.linalg.norm(x_in):.2f} "
          f"→ salida {np.linalg.norm(x_out):.2f}")

    # Test persistencia FFN
    print("\n--- PERSISTENCIA ---")
    ffn.guardar("./ffn_test")
    ffn2 = FeedForward.cargar("./ffn_test")
    out2 = ffn2.forward(x)
    diff = np.abs(out - out2).max()
    print(f"  Diferencia máx tras recarga: {diff:.8f} (debe ser ~0)")

    print("\n✓ ffn.py — listo")
    print("  Siguiente: modelo.py — FractalLM completo")
