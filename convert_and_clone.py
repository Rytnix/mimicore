#!/usr/bin/env python3
"""
convert_and_clone.py
====================
Convert an iPhone Voice Memo (.m4a) to 16 kHz mono WAV and synthesise a
target sentence in the cloned voice using OmniVoice.

Pipeline:
    .m4a  --ffmpeg-->  16 kHz mono PCM .wav  --OmniVoice-->  24 kHz .wav

Example
-------
    python convert_and_clone.py \\
        --input  my_voice.m4a \\
        --text   "Hello, this is my cloned voice." \\
        --output cloned_output.wav \\
        --steps  32 \\
        --speed  1.0
"""

from __future__ import annotations

# ----- stdlib ---------------------------------------------------------------
import argparse
import logging
import re
import shutil
import subprocess
import sys
import wave
from pathlib import Path

# Silence inserted between paragraphs in --per-paragraph mode. ~400 ms is a
# natural breath: long enough to feel like a paragraph break, short enough
# not to feel like a separate take.
PARAGRAPH_GAP_SECONDS = 0.4

# Heavy third-party imports (torch, torchaudio, omnivoice) are deferred into
# main() so that `--help` works even before the venv is fully installed.

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, datefmt="%H:%M:%S")
log = logging.getLogger("voiceclone")


# ============================================================================
# CLI
# ============================================================================
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="convert_and_clone.py",
        description=(
            "Clone a voice from an iPhone .m4a Voice Memo and synthesise "
            "arbitrary text in that voice using OmniVoice."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python convert_and_clone.py --input me.m4a --text 'Hello world'\n"
            "  python convert_and_clone.py --input me.m4a --text-file script.txt\n"
            "  python convert_and_clone.py --input me.m4a --text 'Faster please' "
            "--steps 16 --speed 1.1\n"
        ),
    )
    p.add_argument(
        "--input", required=True, type=Path,
        help="Path to the source .m4a file recorded on iPhone Voice Memos.",
    )
    # Exactly one of --text / --text-file must be provided.
    text_group = p.add_mutually_exclusive_group(required=True)
    text_group.add_argument(
        "--text", type=str, default=None,
        help="Text to synthesise in the cloned voice (UTF-8). Inline string.",
    )
    text_group.add_argument(
        "--text-file", type=Path, default=None, dest="text_file",
        help="Path to a UTF-8 text file whose contents will be synthesised. "
             "Use this for paragraphs or anything with quotes/newlines that are "
             "awkward to pass on the command line.",
    )
    p.add_argument(
        "--output", default=Path("cloned_output.wav"), type=Path,
        help="Destination .wav path for the cloned audio. Default: cloned_output.wav",
    )
    p.add_argument(
        "--steps", default=32, type=int,
        help="Diffusion steps (OmniVoice `num_step`). 32 = default quality, "
             "16 = faster inference with slight quality drop.",
    )
    p.add_argument(
        "--speed", default=1.0, type=float,
        help="Speaking speed factor. 1.0 = natural, >1 faster, <1 slower.",
    )
    p.add_argument(
        "--per-paragraph", action="store_true", dest="per_paragraph",
        help="Split text on blank lines and synthesise each paragraph in a "
             "separate model call, then concatenate with ~0.4s of silence "
             "between them. Recommended for anything longer than ~200 words: "
             "single-shot generation drifts in pacing on long passages.",
    )
    p.add_argument(
        "--batch-size", type=int, default=4, dest="batch_size",
        help="In --per-paragraph mode, how many paragraphs to send to "
             "OmniVoice in a single batched generate() call. Higher = better "
             "GPU utilisation but more VRAM. 4 is safe on 8 GB; bump to 8 on "
             "12+ GB. Drop to 1 if you hit CUDA OOM. Ignored without --per-paragraph.",
    )
    p.add_argument(
        "--language", type=str, default=None,
        help="Target language for synthesis. Accepts ISO 639-3 code (e.g. 'eng', "
             "'spa') or a language name OmniVoice recognises (e.g. 'English', "
             "'Spanish'). Omit (or pass 'auto') to let OmniVoice run in "
             "language-agnostic mode — works, but specifying improves prosody.",
    )
    return p.parse_args()


# ============================================================================
# Step 1 — convert .m4a to 16 kHz mono 16-bit PCM WAV via ffmpeg
# ============================================================================
def convert_m4a_to_wav(src: Path, dst: Path) -> None:
    """Run ffmpeg to produce a clean reference WAV. Raises on failure."""
    if not src.exists():
        raise FileNotFoundError(
            f"Input file not found: {src}\n"
            f"Tip: copy your iPhone Voice Memo into this folder first."
        )
    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "ffmpeg is not on PATH. Install it with:  sudo apt install ffmpeg"
        )

    cmd = [
        "ffmpeg", "-y",
        "-i", str(src),
        "-ar", "16000",       # resample to 16 kHz
        "-ac", "1",           # mono
        "-sample_fmt", "s16", # 16-bit PCM
        str(dst),
    ]
    log.info("ffmpeg: %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            "ffmpeg conversion failed.\n"
            "--- ffmpeg stderr ---\n" + proc.stderr.strip()
        )

    dur = wav_duration_seconds(dst)
    log.info("Converted reference: %s  (%.2f s, 16 kHz mono PCM)", dst, dur)
    if dur < 3.0:
        log.warning(
            "Reference is only %.2f s. OmniVoice clones better with 10–30 s "
            "of clean speech. Re-record a longer sample if the result is poor.",
            dur,
        )


def wav_duration_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        frames = w.getnframes()
        rate = w.getframerate()
        return frames / float(rate) if rate else 0.0


# ============================================================================
# Step 2 — run OmniVoice
# ============================================================================
def split_paragraphs(text: str) -> list[str]:
    """Split text on blank lines into non-empty, stripped paragraphs."""
    parts = re.split(r"\n\s*\n", text)
    return [p.strip() for p in parts if p.strip()]


def run_omnivoice(
    ref_wav: Path,
    texts: list[str],
    output: Path,
    num_step: int,
    speed: float,
    batch_size: int = 1,
    language: str | None = None,
) -> None:
    # Deferred imports so --help works without torch installed.
    # soundfile is used (instead of torchaudio.save) because torchaudio 2.9+
    # routes save() through the optional `torchcodec` package, which we don't
    # want to take on as a hard dep. soundfile is smaller and matches the
    # OmniVoice README's own example.
    try:
        import numpy as np
        import soundfile as sf
        import torch
        from omnivoice import OmniVoice
    except ImportError as e:
        raise RuntimeError(
            f"Required package missing: {e.name}.\n"
            "Activate the venv and reinstall:  source omnivoice_env/bin/activate "
            "&& uv pip install soundfile  (or re-run ./setup_omnivoice.sh)."
        ) from e

    if not texts:
        raise RuntimeError("run_omnivoice called with an empty text list.")

    # ----- device / dtype selection -----
    if torch.cuda.is_available():
        device = "cuda:0"
        dtype = torch.float16
        log.info("CUDA available → device=%s, dtype=float16, GPU=%s",
                 device, torch.cuda.get_device_name(0))
    else:
        device = "cpu"
        dtype = torch.float32
        log.warning(
            "CUDA not available — falling back to CPU + float32. "
            "Inference will be SLOW. Re-run setup_omnivoice.sh if a GPU is present."
        )

    # ----- load model (once, reused across all paragraphs) -----
    log.info("Loading OmniVoice model 'k2-fsa/OmniVoice' (first run downloads ~GB)...")
    try:
        model = OmniVoice.from_pretrained(
            "k2-fsa/OmniVoice",
            device_map=device,
            dtype=dtype,
        )
    except Exception as e:
        raise RuntimeError(
            "Failed to load OmniVoice model from HuggingFace.\n"
            f"  Underlying error: {e}\n"
            "If you are behind a firewall or in mainland China, try:\n"
            "  export HF_ENDPOINT=https://hf-mirror.com\n"
            "and re-run."
        ) from e
    log.info("Model ready.")

    out_sr = 24000
    multi = len(texts) > 1
    silence = (
        np.zeros(int(out_sr * PARAGRAPH_GAP_SECONDS), dtype=np.float32)
        if multi else None
    )

    # ref_text is intentionally omitted so OmniVoice's bundled Whisper
    # transcribes the reference automatically.
    effective_bs = max(1, batch_size) if multi else 1
    lang_label = language if language else "auto-detect"
    if multi:
        log.info(
            "Per-paragraph mode: %d chunks, batch_size=%d (steps=%d, speed=%.2f, language=%s).",
            len(texts), effective_bs, num_step, speed, lang_label,
        )
    else:
        log.info("Cloning voice (steps=%d, speed=%.2f, language=%s)...",
                 num_step, speed, lang_label)

    # Synthesise paragraphs in batches. OmniVoice.generate() accepts list-typed
    # `text` / `ref_audio` and returns one waveform per item, so a single
    # batched call replaces N serial calls — saves per-call dispatch overhead
    # and packs the GPU better. We keep the batch size capped to avoid OOM on
    # smaller cards (RTX 4060 8 GB and similar).
    rendered: list = []
    for start in range(0, len(texts), effective_bs):
        batch_texts = texts[start : start + effective_bs]
        batch_idx = start // effective_bs + 1
        total_batches = (len(texts) + effective_bs - 1) // effective_bs
        if multi:
            log.info(
                "  Batch %d/%d → paragraphs %d–%d (%d in batch)",
                batch_idx, total_batches,
                start + 1, start + len(batch_texts), len(batch_texts),
            )

        # generate() accepts a single string or a list. Pass a list whenever
        # we have >1 item to enable real batching; pass a scalar otherwise to
        # avoid any edge cases in single-item batched dispatch.
        if len(batch_texts) == 1:
            gen_text = batch_texts[0]
            gen_ref = str(ref_wav)
            gen_lang = language
        else:
            gen_text = batch_texts
            gen_ref = [str(ref_wav)] * len(batch_texts)
            gen_lang = [language] * len(batch_texts) if language else None

        try:
            audios = model.generate(
                text=gen_text,
                ref_audio=gen_ref,
                num_step=num_step,
                speed=speed,
                language=gen_lang,
            )
        except torch.cuda.OutOfMemoryError as e:
            raise RuntimeError(
                f"CUDA OOM at batch_size={effective_bs} (batch {batch_idx}/{total_batches}).\n"
                f"  Re-run with --batch-size {max(1, effective_bs // 2)} "
                f"(or --batch-size 1 to disable batching)."
            ) from e
        except Exception as e:
            raise RuntimeError(
                f"OmniVoice generation failed on batch {batch_idx}/{total_batches}: {e}\n"
                "Common causes: GPU OOM (try --batch-size 1 or --steps 16), "
                "corrupt reference WAV, or empty / non-speech reference audio."
            ) from e

        if not isinstance(audios, (list, tuple)):
            raise RuntimeError(
                f"Unexpected OmniVoice output: {type(audios).__name__}. "
                "The library API may have changed."
            )
        if len(audios) != len(batch_texts):
            raise RuntimeError(
                f"OmniVoice returned {len(audios)} waveforms for a batch of "
                f"{len(batch_texts)} paragraphs."
            )

        for wav_np in audios:
            wav = np.asarray(wav_np, dtype=np.float32)
            if wav.ndim != 1:
                raise RuntimeError(
                    f"Expected 1-D waveform from OmniVoice, got shape {wav.shape}."
                )
            rendered.append(wav)

    # Interleave silence between paragraphs (not after the last one).
    if multi:
        woven: list = []
        for i, wav in enumerate(rendered):
            woven.append(wav)
            if i < len(rendered) - 1:
                woven.append(silence)
        waveform_np = np.concatenate(woven)
    else:
        waveform_np = rendered[0]

    output.parent.mkdir(parents=True, exist_ok=True)
    # PCM_16 = standard 16-bit WAV, plays everywhere (aplay/vlc/web/etc.).
    sf.write(str(output), waveform_np, out_sr, subtype="PCM_16")

    duration = waveform_np.shape[-1] / out_sr
    log.info("Wrote %s  (%.2f s @ %d Hz)", output, duration, out_sr)
    log.info("Play it with:   aplay %s   (or: vlc %s)", output, output)


# ============================================================================
# main
# ============================================================================
def load_text(args: argparse.Namespace) -> str:
    """Resolve --text or --text-file to a single non-empty string."""
    if args.text is not None:
        return args.text

    path: Path = args.text_file
    if not path.exists():
        raise FileNotFoundError(
            f"--text-file not found: {path}\n"
            f"Tip: pass a path relative to the current directory, e.g. ./script.txt"
        )
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        raise RuntimeError(
            f"--text-file must be UTF-8. Failed to decode {path}: {e}"
        ) from e
    return text


def main() -> int:
    args = parse_args()

    try:
        text = load_text(args)
    except FileNotFoundError as e:
        log.error("%s", e)
        return 1
    except RuntimeError as e:
        log.error("%s", e)
        return 1

    text = text.strip()
    if not text:
        log.error("Synthesis text is empty. Provide --text or a non-empty --text-file.")
        return 2

    # Resolve the list of chunks to synthesise.
    if args.per_paragraph:
        chunks = split_paragraphs(text)
        if not chunks:
            log.error("--per-paragraph found no non-empty paragraphs in the input.")
            return 2
        long_chunks = [i for i, c in enumerate(chunks, 1) if len(c) > 1500]
        if long_chunks:
            log.warning(
                "Paragraphs %s are still longer than 1500 chars — pacing may "
                "drift inside those chunks. Consider breaking them with a blank line.",
                long_chunks,
            )
    else:
        chunks = [text]
        if len(text) > 1500:
            log.warning(
                "Input text is %d characters (~%d words). Consider --per-paragraph "
                "for cleaner pacing on long passages.",
                len(text), len(text.split()),
            )

    # Reference WAV lives next to the source .m4a, named *_ref16k.wav.
    ref_wav = args.input.with_name(args.input.stem + "_ref16k.wav")

    # "auto" / "" / "none" all map to OmniVoice's language-agnostic mode.
    lang = args.language
    if lang and lang.strip().lower() in {"", "auto", "none"}:
        lang = None

    try:
        convert_m4a_to_wav(args.input, ref_wav)
        run_omnivoice(
            ref_wav=ref_wav,
            texts=chunks,
            output=args.output,
            num_step=args.steps,
            speed=args.speed,
            batch_size=args.batch_size,
            language=lang,
        )
    except FileNotFoundError as e:
        log.error("%s", e)
        return 1
    except RuntimeError as e:
        log.error("%s", e)
        return 1
    except KeyboardInterrupt:
        log.error("Interrupted by user.")
        return 130
    except Exception as e:  # last-resort guard
        log.exception("Unexpected error: %s", e)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
