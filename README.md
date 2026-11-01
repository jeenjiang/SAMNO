# SAMNO: Spectral-Attention Multiwavelet Neural Operator

**SAMNO** is a diagnostic-guided 4D neural operator for full-field thermomechanical prediction in electron-beam powder bed fusion (EB-PBF). It combines a tensor-product multiwavelet backbone with level-wise heterogeneous kernels: FFT, linear attention, and softmax multi-head attention.

The core idea is simple: different physical fields have different regularity. Temperature is diffusion-smoothed, while von Mises stress and displacement contain sharper geometry-controlled structures. Instead of applying the same spectral kernel everywhere, SAMNO assigns different operators to different multiwavelet levels according to wavelet-energy diagnostics and memory/complexity feasibility.

> Paper: **A diagnostic-guided spectral-attention multiwavelet neural operator for mixed-regularity 4D thermomechanical field prediction**  
> Authors: Jing Jiang and Liu Hong

---

## Highlights

- **One-shot 4D prediction**: maps the first deposited-layer field to the remaining 19 layers in a single forward pass.
- **Mixed-regularity modeling**: targets temperature `T`, von Mises equivalent stress `S`, and displacement magnitude `U`.
- **Diagnostic-guided kernel assignment**:
  - decomposition level `lvl = 0` / paper level `j = n`: FFT kernel
  - decomposition level `lvl = 1` / paper level `j = n - 1`: linear attention kernel
  - decomposition level `lvl >= 2` / paper levels `j <= n - 2`: softmax multi-head attention kernel
- **Hard switching, no gating**: the operator type is selected directly by decomposition level, making ablation and attribution cleaner.
- **Low overhead**: the paper reports a small parameter increase relative to the MWT baseline while improving overall and per-field relative `L2` errors.

---

## Problem Setting

SAMNO is designed for surrogate modeling of EB-PBF thermomechanical fields.

Given the first-layer state

```text
a_1 ∈ R^{D_x × D_y × D_z × C}
```

the model predicts the subsequent deposited-layer sequence

```text
G_θ: a_1 → (a_2, ..., a_20)
```

where the output channels are:

| Channel | Meaning |
|---|---|
| `T` | Temperature |
| `S` | von Mises equivalent stress |
| `U` | Displacement magnitude |

In the paper benchmark, the data come from sequential thermomechanical finite-element simulations of a Ti-6Al-4V honeycomb EB-PBF structure. The task uses `T_in = 1` and `T_out = 19`.

---

## Model Overview

The uploaded implementation defines two main modules:

| Class | Description |
|---|---|
| `sparseKernelLinearAttn4d` | Linear-attention coefficient-space kernel using ELU feature mapping |
| `sparseKernelSoftmaxAttn4d` | Standard softmax multi-head attention kernel for smaller token counts |
| `MWT_CZ4d` | One multiwavelet CZ block with level-wise FFT / LinAttn / SoftAttn assignment |
| `MWT4d` | Top-level SAMNO model with temporal alignment, channel lifting, stacked CZ blocks, GroupNorm, residual updates, and projection head |

The top-level forward pass follows:

```text
input:  x ∈ R^{B × D1 × D2 × D3 × T_in × C_in}

1. TemporalAlign: expand or align T_in to T_out
2. Linear lifting: C_in → c · k^4
3. Reshape into coefficient channels
4. Apply nCZ multiwavelet CZ blocks
5. Optional GroupNorm and residual update
6. Projection head: c · k^4 → 128 → C_out

output: y ∈ R^{B × D1 × D2 × D3 × T_out × C_out}
```

---

## Level-wise Kernel Assignment

Inside `MWT_CZ4d.forward`, the detail coefficients are processed by different kernels depending on the decomposition loop level:

```python
if lvl < attn_start_level:
    # lvl = 0: FFT
    Ud_val = self.A_fft(d_r) + self.B(x_r)
elif lvl < softmax_start_level:
    # lvl = 1: Linear Attention
    Ud_val = self.A_linear_attn(d_r) + self.B(x_r)
else:
    # lvl >= 2: Softmax Attention
    Ud_val = self.A_softmax_attn(d_r) + self.B(x_r)
```

Default SAMNO/C1 setting:

```python
attn_start_level = 1
softmax_start_level = 2
n_heads = 6
```

This corresponds to the paper design:

| Paper multiwavelet level | Code decomposition level | Kernel |
|---|---:|---|
| `j = n` | `lvl = 0` | FFT |
| `j = n - 1` | `lvl = 1` | Linear Attention |
| `j <= n - 2` | `lvl >= 2` | Softmax Multi-head Attention |

---

## Installation

This repository requires PyTorch and NumPy. A minimal environment is:

```bash
conda create -n samno python=3.10 -y
conda activate samno

# Install PyTorch according to your CUDA version:
# https://pytorch.org/get-started/locally/
pip install torch numpy
```

The current model file also depends on the repository-local modules:

```text
mwt4d_k4.py
tools.py
```

Make sure these files are available in the same project or import path.

---

## Recommended Repository Structure

```text
SAMNO/
├── README.md
├── samno.py                 # SAMNO/C1 model implementation
├── mwt4d_k4.py              # Multiwavelet filters and FFT/sparse kernels
├── tools.py                 # TemporalAlign and utility functions
├── train.py                 # Optional: training script
├── eval.py                  # Optional: evaluation script
├── configs/
│   └── samno_c1.yaml
├── data/
│   └── README.md            # Dataset instructions or download notes
└── checkpoints/
    └── .gitkeep
```

---

## Quick Sanity Check

The provided `samno.py` includes a quick test. After placing all required local modules in the repository, run:

```bash
python samno.py
```

Expected behavior:

```text
[C1] input:  torch.Size([2, 11, 21, 19, 1, 3])
[C1] output: torch.Size([2, 11, 21, 19, 19, 3])
[C1] params: ...
  A_fft:          ...
  A_linear_attn:  ...
  A_softmax_attn: ...
[OK]
```

---

## Basic Usage

```python
import torch

from samno import MWT4d
from mwt4d_k4 import get_initializer

device = "cuda" if torch.cuda.is_available() else "cpu"

model = MWT4d(
    ich=3,
    och=3,
    k=2,
    c=3,
    nCZ=4,
    L=0,
    alpha1=8,
    alpha2=8,
    alpha3=8,
    alpha4=4,
    tout=19,
    align_mode="repeat",
    base="legendre",
    initializer=get_initializer("kaiming_uniform"),
    use_xin_gn=True,
    use_residual=True,
    use_gelu=True,
    attn_start_level=1,
    softmax_start_level=2,
    n_heads=6,
).to(device)

x = torch.randn(2, 11, 21, 19, 1, 3, device=device)
y = model(x)

print(y.shape)
# torch.Size([2, 11, 21, 19, 19, 3])
```

For the paper-scale EB-PBF benchmark, the expected full-grid input is:

```text
x: [B, 41, 41, 41, 1, 3]
y: [B, 41, 41, 41, 19, 3]
```

---

## Training Protocol Used in the Paper

The paper trains all models under the same protocol:

| Item | Setting |
|---|---|
| Samples | 168 total |
| Split | 136 train / 32 test |
| Input | Layer 1 |
| Target | Layers 2–20 |
| Loss | Multi-channel relative `L2` loss on FEM point-cloud nodes |
| Optimizer | AdamW |
| Learning rate | `5e-4` |
| Weight decay | `1e-4` |
| Batch size | `4` |
| Epochs | `300` |
| LR schedule | `ReduceLROnPlateau`, factor `0.5`, patience `15` |
| Mixed precision | bfloat16 autocast |
| Random seed | `0` for initialization/shuffling, `2025` for split |

---

## Notes on Reproducibility

- The uploaded `samno.py` is the model definition and quick-test implementation.
- Training and evaluation scripts are not included in this file; add your own `train.py` / `eval.py` around the `MWT4d` interface.
- The paper computes loss and reported metrics after mapping predictions back from the regular grid to FEM nodes.
- If the EB-PBF dataset is large or private, add a `data/README.md` describing how to obtain or preprocess it rather than committing raw data to GitHub.

---

## Citation

If this repository helps your research, please cite the manuscript:

```bibtex
@misc{jiang_samno,
  title  = {A diagnostic-guided spectral-attention multiwavelet neural operator for mixed-regularity 4D thermomechanical field prediction},
  author = {Jiang, Jing and Hong, Liu},
  note   = {Manuscript}
}
```

---

## License

Please add a `LICENSE` file before public release.
