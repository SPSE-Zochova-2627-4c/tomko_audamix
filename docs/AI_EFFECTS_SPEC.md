# AI Effects Specification

Status: draft. Nothing in this document is implemented yet, except where marked **existing**.
Model names and licenses must be verified before implementation. This spec defines behavior,
parameters, and acceptance tests; it does not choose the final model for each effect.

## 1. Scope

| ID | Title | Phase | Replaces or extends |
|---|---|---|---|
| `ai_denoise` | AI Denoise (with strength) | 1 | Existing `ai_denoise` (DeepFilterNet3), adds `strength` |
| `ai_dereverb` | AI Dereverb | 1 | Inverse of `echo` |
| `vad_gate` | Speech Gate (VAD) | 1 | Alternative to `noise_gate` for speech |
| `ai_isolate` | AI Source Isolation | 2 | Source-based alternative to `bandpass` |
| `ai_bandwidth` | AI Bandwidth Extension | 3 | Inverse of `lowpass` for muffled audio |

Out of scope: text-to-audio generation (changes length, belongs in Generate), AI EQ matching,
AI loudness/mastering, and any AI version of Gain, Notch, Invert, Reverse, Pan, Phaser, Wahwah,
or Tremolo. These stay classical.

## 2. Cross-cutting requirements

### 2.1 Interface

Every AI effect is a pure function registered in `effects.SPECS` with the existing signature:

```python
def ai_dereverb(samples: np.ndarray, rate: int, strength: float = 100.0) -> np.ndarray
```

- Input and output: `float64`, shape `(frames,)` or `(frames, channels)`.
- Output shape must equal input shape. `apply_effect` already enforces this.
- Output must be finite. Values are clipped to `[-1, 1]` before returning.
- The input array must not be modified.
- Group name: **"AI Restoration"** for all effects in this spec.

### 2.2 Registration changes

- `Param` gains `kind="choice"` for enumerated values. `default` and the range are indices
  (`minimum=0`, `maximum=N-1`, `decimals=0`), and `labels: tuple[str, ...]` is added to render
  the dialog combo box. Only `ai_isolate` uses this kind.
- `ai_denoise` moves from the hard-coded dispatch in `real_backend.py` into `SPECS`. The
  `ai_denoise` and `ai_declip` branches in `real_backend.apply_effect` are then removed or
  reduced to `ai_declip` only.
- `window.py` (`EFFECT_NAMES`, menu tuples around lines 190–210) gets the new IDs and a
  submenu "AI Restoration".

### 2.3 Import rules

- `audamix/dsp/effects.py` must import without Torch. Each AI function imports its backend
  lazily inside the function body. This keeps the classical CLI and tests working without
  `requirements-ai.txt`.
- Model loading goes through one module-level cache in `audamix/ai/` keyed by model name.
  `AudioAI` in `real_backend.py:175` currently builds a new instance on every run; the cache
  replaces that. `unload_models()` clears the cache.

### 2.4 Selection handling

Models need surrounding context, and short selections produce edge artifacts. For any AI
effect applied to a selection:

1. Take the selection extended by `CONTEXT_MS = 500` ms on each side, clamped to the track.
2. Run the model on the extended region.
3. Crop back to the selection.
4. Crossfade `FADE_MS = 10` ms at each seam with the untouched audio, using the same linear ramp
   as `editing.smooth_join`.

The selection-level crop and seam logic lives in one helper, `audamix/ai/segments.py`, so every
AI effect uses it. The helper must keep the length of the input.

The helper is applied in `effects.apply_effect` for AI specs only, and it receives the full track
plus the selection bounds. This requires a small change to the signature: AI specs get an extra
optional keyword, `context: np.ndarray | None`, filled by the caller. Classical specs are
unchanged. (Alternative: the caller in `real_backend` handles the padding. Pick one during
implementation and record it in `OMISSIONS.md`.)

### 2.5 Strength (dry/wet)

Every AI effect in this spec has a `strength` parameter, `0`–`100` percent:

```
output = (1 - s) * input + s * model_output,   s = strength / 100
```

- `strength = 0` returns the input unchanged (bit-exact).
- `strength = 100` returns the model output.
- The blend happens after the model output is cropped and aligned to the input length.

### 2.6 Errors and honesty

- A missing model or dependency raises `RuntimeError` with an installation hint. The effect
  must not pass audio through unchanged.
- Results that are estimates (bandwidth extension, dereverb, isolation) set a metadata flag
  `ai_model` and show the existing "result is an estimate" message in the status line.
- Errors are caught by `real_backend.apply_effect` and shown as `"<name> failed: <reason>"`.
  The track is not changed.

### 2.7 Performance targets

These are targets for a 4-core CPU without GPU, used as acceptance guidance, not hard limits:

| Effect | Target |
|---|---|
| `ai_denoise` | ≤ 1× real time |
| `ai_dereverb` | ≤ 2× real time |
| `vad_gate` | ≤ 0.2× real time |
| `ai_isolate` | ≤ 3× real time for 4-stem output |
| `ai_bandwidth` | ≤ 2× real time |

If a target is missed, the status line should say that processing takes time. The effect
still runs in the existing effect thread with a progress indicator.

## 3. Effect specifications

### 3.1 `ai_denoise` (existing, updated)

- **Purpose:** remove background noise from speech and general recordings.
- **Model:** DeepFilterNet3 (existing, via `AudioAI.denoise`).
- **Parameters:**

| key | label | default | min | max | decimals | suffix |
|---|---|---|---|---|---|---|
| `strength` | Strength | 100 | 0 | 100 | 0 | % |

- **Behavior:** runs the model on the (context-extended) selection, then applies §2.5.
- **Metadata:** `denoised=True`, `ai_model="DeepFilterNet3"`, `denoise_strength=<value>`.
- **Changes to existing code:**
  - `AudioAI.denoise(threshold, strength)` stops ignoring `strength`; the blend in §2.5 replaces
    the current `del threshold, strength`. `threshold` is removed from the signature and the
    call sites in `real_backend.py` and `main.py`.
  - The status message stays "Denoising completed with pretrained DeepFilterNet3".

### 3.2 `ai_dereverb` (new)

- **Purpose:** remove room reverberation and echo tails. This is the AI counterpart of the
  classical `echo` effect, which adds echoes.
- **Model:** a pretrained speech dereverberation model (candidates: SGMSE+ or a DNS-challenge
  dereverb checkpoint). The final choice needs a license check and a listening test on
  speech samples recorded in a small room.
- **Parameters:**

| key | label | default | min | max | decimals | suffix |
|---|---|---|---|---|---|---|
| `strength` | Strength | 100 | 0 | 100 | 0 | % |

- **Behavior:** resample to the model's rate, run the model, resample back, apply §2.5.
  Output length equals input length; reverb tails cut at the selection end are not restored.
- **Metadata:** `dereverbed=True`, `ai_model=<model name>`.
- **Status message:** "Dereverb completed with pretrained <model>; result is an estimate".
- **Known limit:** designed for speech. Music results are not guaranteed; the dialog shows a
  note: "Designed for speech."

### 3.3 `vad_gate` (new)

- **Purpose:** mute non-speech segments (hiss, room tone, breaths between words) using voice
  activity detection instead of a level threshold. Complements `noise_gate`, which reacts to
  loudness only.
- **Model:** Silero VAD (pretrained, runs on CPU in milliseconds). Input rate 16 kHz, 512-sample
  frames (32 ms). Verify the exact input constraints for the chosen release.
- **Parameters:**

| key | label | default | min | max | decimals | suffix |
|---|---|---|---|---|---|---|
| `threshold` | Speech probability | 0.5 | 0.05 | 0.95 | 2 | |
| `hold_ms` | Hold | 200 | 0 | 2000 | 0 | ms |
| `release_ms` | Release | 150 | 0 | 1000 | 0 | ms |
| `floor_db` | Floor | -60 | -90 | 0 | 0 | dB |

- **Algorithm:**
  1. Resample the mono mix (max over channels, same as `noise_gate`) to 16 kHz.
  2. Run VAD per 32 ms frame to get a speech probability `p[i]`.
  3. Mark frame `i` open if `p[i] >= threshold`.
  4. Extend open regions by `hold_ms` forward and `hold_ms` backward (so short pauses are kept).
  5. Build a gain envelope: `1.0` where open, `10^(floor_db/20)` where closed, interpolated
     over `release_ms` on closing (no hard steps).
  6. Map the envelope back to the input rate and apply it to every channel.
- **Behavior:** length preserved, no model weights changed. The gate is linked across channels.
- **Metadata:** none added; the effect is classical in use.
- **Acceptance (see §4):** on a speech file with added pink noise at −30 dB, noise in pauses
  drops by at least 20 dB while speech segments change by less than 0.5 dB RMS.

### 3.4 `ai_isolate` (new, phase 2)

- **Purpose:** keep one source (vocals, drums, bass, or other) and remove the rest. This is a
  source-based alternative to the frequency-based `bandpass`.
- **Model:** HTDemucs (candidate; verify license and weight distribution).
- **Parameters:**

| key | label | default | min | max | decimals | kind | labels |
|---|---|---|---|---|---|---|---|
| `source` | Keep | 0 | 0 | 3 | 0 | choice | Vocals, Drums, Bass, Other |

- **Behavior:**
  - The model separates the selection into four stems. The chosen stem is output; the others
    are discarded.
  - Mono input is converted to a stereo model input and the result is mixed back to mono.
  - Model rate is resampled per §2.4 conventions.
- **Metadata:** `isolated_source=<label>`, `ai_model=<model name>`.
- **Status message:** "Isolation completed with pretrained <model>; result is an estimate".
- **Known limit:** artifacts appear when sources overlap heavily. Stems with little energy may
  sound muffled.

### 3.5 `ai_bandwidth` (new, phase 3)

- **Purpose:** rebuild missing high frequencies in muffled or low-sample-rate recordings. This
  is the AI counterpart of `lowpass` in the restoration direction.
- **Model:** AudioSR (candidate; verify license and supported input rates).
- **Parameters:**

| key | label | default | min | max | decimals | suffix |
|---|---|---|---|---|---|---|
| `strength` | Strength | 100 | 0 | 100 | 0 | % |

- **Behavior:** model output replaces the content above the detected cutoff. The detected
  cutoff is estimated from the spectrum with a 1 kHz resolution before running the model.
  If no cutoff is found below Nyquist minus 1 kHz, the effect returns the input unchanged and
  the status line says "No band limit detected; nothing changed."
- **Metadata:** `bandwidth_extended=True`, `ai_model=<model name>`.
- **Status message:** "Bandwidth extension completed with pretrained <model>; result is an
  estimate".
- **Known limit:** the model generates plausible detail. It does not recover the original
  content. The UI must not describe it as restoration of lost information.

## 4. Acceptance tests

Tests go in `tests/test_ai_effects.py`. Model-dependent tests use
`pytest.importorskip("torch")` and the specific package, so the suite still passes without the
optional dependencies.

| Test | Applies to | Requirement |
|---|---|---|
| Shape and finiteness | all | Mono and stereo output match input shape; no NaN or Inf |
| Strength zero is identity | `ai_denoise`, `ai_dereverb`, `ai_bandwidth` | Output equals input exactly |
| Strength 100 equals model output | same | Output equals the model output within 1e-6 |
| Selection seams | all AI | No sample jump above 0.05 at the selection boundaries (crossfade works) |
| Outside selection untouched | all AI | Samples outside the selection are bit-identical |
| Missing model raises | all AI | `RuntimeError` with install hint; input not returned as output |
| Import without Torch | `effects.py` | Module imports and `SPECS` builds with Torch absent |
| Model cache | all AI | Second call does not reload weights (mock loader counts calls) |
| Gate attenuation | `vad_gate` | Noise in pauses reduced ≥ 20 dB; speech RMS change < 0.5 dB |
| Gate hold | `vad_gate` | Pauses shorter than `hold_ms` are not gated |
| Isolation stem count | `ai_isolate` | Output differs for each `source` value; choice index validated 0–3 |
| No band limit | `ai_bandwidth` | Full-band input returned unchanged with the status message |
| Parameter validation | all | Out-of-range values raise `ValueError` via `apply_effect` |

Listening checks (manual, not automated): one speech sample with room echo for dereverb,
one noisy speech sample for denoise and gate, one muffled recording for bandwidth. Record the
results in `VERIFICATION.md`.

## 5. Documentation updates required with implementation

- `README.md`: Effects section lists the AI Restoration submenu and the optional packages.
- `requirements-ai.txt`: each new model's package, with pinned versions after verification.
- `OMISSIONS.md`: model licenses, and any model left out because it was not verified.
- `VERIFICATION.md`: results of the acceptance and listening checks in §4.
- `docs/ARCHITECTURE.md`: the new `audamix/ai/segments.py` helper and the model cache.

## 6. Open decisions

1. Where selection context is applied: inside `apply_effect` (§2.4, first option) or in
   `real_backend` (second option).
2. Whether `vad_gate` should also drive `ai_denoise` as a pre-step (ignore non-speech).
   Default: no; keep the effects independent.
3. Final models for dereverb, isolation, and bandwidth extension, after license review.
4. Whether `strength` should be shown as a percentage or as a mix knob in the dialog.
