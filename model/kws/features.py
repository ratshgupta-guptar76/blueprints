"""Log-mel spectrogram: 40 mel bands, 25 ms Hann window, 10 ms hop, 98 frames
for one second. This is the FPGA's front end; it is fixed, not learned."""
from __future__ import annotations

import math

import torch

RATE, WIN, HOP, N_MELS, FMIN, FMAX = 16000, 400, 160, 40, 20.0, 7600.0
FRAMES = 1 + (RATE - WIN) // HOP        # 98


def _mel(f):
    return 2595.0 * math.log10(1.0 + f / 700.0)


def mel_matrix(device) -> torch.Tensor:
    """[WIN // 2 + 1, N_MELS] triangular filters, HTK mel scale."""
    n_bins = WIN // 2 + 1
    freqs = torch.linspace(0, RATE / 2, n_bins, dtype=torch.float64)
    pts = torch.tensor([700.0 * (10 ** (m / 2595.0) - 1.0) for m in
                        torch.linspace(_mel(FMIN), _mel(FMAX), N_MELS + 2).tolist()], dtype=torch.float64)
    fb = torch.zeros(n_bins, N_MELS, dtype=torch.float64)
    for j in range(N_MELS):
        lo, mid, hi = pts[j], pts[j + 1], pts[j + 2]
        up = (freqs - lo) / (mid - lo)
        down = (hi - freqs) / (hi - mid)
        fb[:, j] = torch.clamp(torch.minimum(up, down), min=0)
    return fb.float().to(device)


class LogMel:
    def __init__(self, device):
        self.window = torch.hann_window(WIN, device=device)
        self.fb = mel_matrix(device)

    def __call__(self, wave_i16: torch.Tensor) -> torch.Tensor:
        """int16 or float [B, 16000] -> [B, 98, 40]."""
        x = wave_i16.float() / 32768.0
        spec = torch.stft(x, n_fft=WIN, hop_length=HOP, win_length=WIN, window=self.window,
                          center=False, return_complex=True)
        power = spec.real ** 2 + spec.imag ** 2                 # [B, 201, 98]
        return torch.log(power.transpose(1, 2) @ self.fb + 1e-6)
