"""
server.py — FastAPI backend for the VoiceClone studio UI.

Wraps the existing convert_and_clone.py CLI:
  - References:  upload audio  ->  ffmpeg convert  ->  faster-whisper streaming transcript
  - Jobs:        ref + text     ->  subprocess(convert_and_clone.py)  ->  streamed logs

Live channels:
  - WS /api/refs/{id}/transcribe   — streaming whisper segments + status
  - WS /api/jobs/{id}/stream       — live job logs + state transitions
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import (
    BackgroundTasks,
    Cookie,
    Depends,
    FastAPI,
    File,
    HTTPException,
    Request,
    Response,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import db

ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
DIST_DIR = WEB_DIR / "dist"
DATA_DIR = ROOT / "data"
# Per-user audio lives under voice_data/<username>/{reference_audio,converted_audio}/.
# A small "_dictate" scratch dir under DATA_DIR holds in-flight blobs from
# /api/transcribe (one-shot dictation) so we never write user-namespaced files
# without an authenticated user.
SCRATCH_DIR = DATA_DIR / "_scratch"
PYTHON = sys.executable  # current venv python — same one running the server

DATA_DIR.mkdir(parents=True, exist_ok=True)
SCRATCH_DIR.mkdir(parents=True, exist_ok=True)

SESSION_COOKIE = "mc_session"


# ---------------------------------------------------------------------------
# In-memory state. Single-process server, so plain dicts are fine.
# ---------------------------------------------------------------------------
refs: dict[str, dict[str, Any]] = {}
jobs: dict[str, dict[str, Any]] = {}

# Per-resource broadcast channels.  Each is a list of asyncio.Queue;
# every event published is fanned out to every subscriber's queue.
_ref_channels: dict[str, list[asyncio.Queue]] = {}
_job_channels: dict[str, list[asyncio.Queue]] = {}

# Whisper model is loaded lazily on first transcribe.
_whisper = None
_whisper_lock = asyncio.Lock()

# ---------------------------------------------------------------------------
# Job scheduler: VRAM-aware, capped concurrency.
# ---------------------------------------------------------------------------
# Each clone subprocess loads OmniVoice into its own CUDA context (~5GB).
# Two unconstrained concurrent jobs OOM the GPU. We dispatch through a
# scheduler that gates on (a) a hard cap, (b) free VRAM headroom.
# Tunables (env-overridable):
#   VOICECLONE_MAX_PARALLEL    – hard cap on concurrent jobs.
#   VOICECLONE_JOB_VRAM_MB     – per-job VRAM budget. We *reserve* this per
#                                running job, so a freshly-dispatched job
#                                that hasn't yet loaded the model still
#                                counts against the budget.
#   VOICECLONE_VRAM_HEADROOM_MB – minimum free VRAM to keep at all times.
#                                256 MB is enough to avoid driver thrash;
#                                bump it if the box runs other GPU work.
SCHED_MAX_PARALLEL  = int(os.environ.get("VOICECLONE_MAX_PARALLEL", "2"))
SCHED_VRAM_PER_JOB  = int(os.environ.get("VOICECLONE_JOB_VRAM_MB", "4500"))
SCHED_VRAM_HEADROOM = int(os.environ.get("VOICECLONE_VRAM_HEADROOM_MB", "256"))

_job_pending: asyncio.Queue[str] | None = None
_job_running: set[str] = set()
_job_slot_event: asyncio.Event | None = None


def _free_vram_mb() -> int | None:
    """Free VRAM in MB on the active CUDA device, or None if no GPU."""
    try:
        import torch
        if not torch.cuda.is_available():
            return None
        free, _total = torch.cuda.mem_get_info()
        return free // (1024 * 1024)
    except Exception:
        return None


def _queue_position(job_id: str) -> int:
    """1-based position of `job_id` in the pending queue, 0 if not waiting."""
    if _job_pending is None:
        return 0
    # asyncio.Queue exposes _queue (deque). Reading is fine for telemetry.
    items = list(getattr(_job_pending, "_queue", []))
    try:
        return items.index(job_id) + 1
    except ValueError:
        return 0


async def _scheduler_loop():
    """Single dispatcher: pulls jobs off _job_pending, waits for a free slot
    + enough VRAM, then launches them as background tasks."""
    assert _job_pending is not None and _job_slot_event is not None
    while True:
        job_id = await _job_pending.get()
        job = jobs.get(job_id)
        if job is None:
            continue

        # Block until we have both a slot and (reserved) VRAM headroom.
        while True:
            running_n = len(_job_running)
            slot_free = running_n < SCHED_MAX_PARALLEL
            free_mb = _free_vram_mb()

            # Pessimistic accounting: assume each running job will eventually
            # consume its full VRAM_PER_JOB budget. The kernel may not reflect
            # that yet (subprocess still loading), so we subtract it ourselves.
            need = SCHED_VRAM_PER_JOB + SCHED_VRAM_HEADROOM
            if free_mb is None:
                vram_ok = True   # No GPU info — trust the slot cap alone.
                effective_free = None
            else:
                effective_free = max(0, free_mb - running_n * SCHED_VRAM_PER_JOB)
                vram_ok = effective_free >= need

            if slot_free and vram_ok:
                break

            if not slot_free:
                reason = f"concurrency cap reached ({running_n}/{SCHED_MAX_PARALLEL})"
            else:
                reason = (f"VRAM low — {effective_free}MB free after reserving "
                          f"{running_n}×{SCHED_VRAM_PER_JOB}MB for running jobs (need {need}MB)")
            job["wait_reason"] = reason
            _publish(_job_channels, job_id, {
                "type": "wait",
                "reason": reason,
                "queue_position": _queue_position(job_id),
                "running": running_n,
                "max_parallel": SCHED_MAX_PARALLEL,
                "free_vram_mb": free_mb,
                "effective_free_mb": effective_free,
            })

            # Wake on slot release; re-check periodically in case another
            # GPU consumer frees memory.
            try:
                await asyncio.wait_for(_job_slot_event.wait(), timeout=4.0)
            except asyncio.TimeoutError:
                pass
            _job_slot_event.clear()

        job.pop("wait_reason", None)
        _job_running.add(job_id)
        asyncio.create_task(_run_then_release(job_id))
        # Give the freshly-dispatched subprocess a moment to start loading
        # before we evaluate the next job — this isn't load-bearing thanks
        # to the reserve-per-running-job accounting above, but it makes the
        # `free_vram_mb` numbers reported via WS reflect reality sooner.
        await asyncio.sleep(0.5)


async def _run_then_release(job_id: str) -> None:
    try:
        await run_clone_job(job_id)
    finally:
        _job_running.discard(job_id)
        if _job_slot_event is not None:
            _job_slot_event.set()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _publish(channels: dict[str, list[asyncio.Queue]], key: str, event: dict) -> None:
    for q in list(channels.get(key, [])):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass


def _subscribe(channels: dict[str, list[asyncio.Queue]], key: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=1024)
    channels.setdefault(key, []).append(q)
    return q


def _unsubscribe(channels: dict[str, list[asyncio.Queue]], key: str, q: asyncio.Queue) -> None:
    if key in channels and q in channels[key]:
        channels[key].remove(q)
        if not channels[key]:
            channels.pop(key, None)


# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------
def ffmpeg_to_wav(src: Path, dst: Path, *, clean: bool = False) -> None:
    """Convert any audio container to 16 kHz mono PCM WAV via ffmpeg.

    When ``clean=True`` runs a studio-style cleanup chain on the way:
      - highpass    : kill rumble/AC hum below 80 Hz
      - afftdn      : FFT-based noise reduction (~12 dB)
      - silenceremove: trim leading + trailing silence; collapse internal gaps >0.6s
      - loudnorm    : EBU R128 loudness normalisation to -16 LUFS, true-peak -1.5 dB

    This matches what every commercial voice-AI product (ElevenLabs Voice
    Isolator, Adobe Enhance Speech, Krisp) ships as a "magic" cleanup step.
    """
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is not installed (sudo apt install ffmpeg).")
    cmd = ["ffmpeg", "-y", "-i", str(src)]
    if clean:
        af = (
            "highpass=f=80,"
            "afftdn=nr=12:nf=-25,"
            "silenceremove="
              "start_periods=1:start_silence=0.10:start_threshold=-40dB:"
              "stop_periods=-1:stop_silence=0.60:stop_threshold=-40dB,"
            "loudnorm=I=-16:TP=-1.5:LRA=11"
        )
        cmd += ["-af", af]
    cmd += ["-ar", "16000", "-ac", "1", "-sample_fmt", "s16", str(dst)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr.strip()[-400:]}")


def wav_seconds(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as w:
            rate = w.getframerate()
            return w.getnframes() / float(rate) if rate else 0.0
    except Exception:
        return 0.0


def _ensure_ct2_cuda_libs() -> None:
    """ctranslate2 (faster-whisper backend) ships only against CUDA 12 wheels;
    torch in this venv is CUDA 13. Add the pip-installed nvidia-cublas-cu12 /
    nvidia-cudnn-cu12 lib dirs to the dynamic loader path so ct2 can find them.
    Must run *before* ctranslate2 is imported."""
    import sysconfig
    site = Path(sysconfig.get_paths()["purelib"])
    extra = []
    for sub in (
        "nvidia/cublas/lib",
        "nvidia/cudnn/lib",
        "nvidia/cuda_nvrtc/lib",
    ):
        p = site / sub
        if p.is_dir():
            extra.append(str(p))
    if not extra:
        return
    cur = os.environ.get("LD_LIBRARY_PATH", "")
    parts = [p for p in cur.split(":") if p]
    for p in extra:
        if p not in parts:
            parts.insert(0, p)
    os.environ["LD_LIBRARY_PATH"] = ":".join(parts)


# Whisper accuracy is heavily model-size-bound. "base" (~74M) is fast but
# notably weaker than "small" (~244M); for our use case (script dictation +
# reference transcripts) the latency hit is worth the accuracy. The user can
# override via env: tiny / base / small / medium / large-v3 / large-v3-turbo.
WHISPER_MODEL = os.environ.get("VOICECLONE_WHISPER_MODEL", "small")


async def get_whisper():
    """Lazy-load faster-whisper. Tries GPU+fp16; falls back to CPU+int8."""
    global _whisper
    async with _whisper_lock:
        if _whisper is None:
            _ensure_ct2_cuda_libs()
            from faster_whisper import WhisperModel
            try:
                import torch
                cuda = torch.cuda.is_available()
            except Exception:
                cuda = False
            print(f"[whisper] loading model={WHISPER_MODEL} cuda={cuda}", flush=True)
            if cuda:
                try:
                    _whisper = WhisperModel(WHISPER_MODEL, device="cuda", compute_type="float16")
                except Exception as e:
                    # Library mismatch (cublas/cudnn) — fall back gracefully.
                    print(f"[whisper] CUDA load failed ({e}); falling back to CPU.", flush=True)
                    _whisper = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
            else:
                _whisper = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
        return _whisper


# Whisper takes ISO 639-1 (2-letter) codes; OmniVoice's catalogue is ISO
# 639-3 with some 2-letter aliases. This map covers our popular set + Arabic
# dialects (which Whisper only knows as "ar"). Anything else: pass through if
# 2-letter, else give up and let Whisper auto-detect.
_WHISPER_LANG_ALIAS: dict[str, str] = {
    # Arabic dialects → Modern Standard Arabic in Whisper.
    "arz": "ar", "arq": "ar", "shu": "ar", "aao": "ar", "abv": "ar",
    "adf": "ar", "afb": "ar", "avl": "ar",
    # 3-letter ISO 639-3 → 2-letter ISO 639-1 for popular languages.
    "eng": "en", "spa": "es", "fra": "fr", "deu": "de", "ita": "it",
    "por": "pt", "rus": "ru", "zho": "zh", "jpn": "ja", "kor": "ko",
    "hin": "hi", "ben": "bn", "urd": "ur", "tur": "tr", "vie": "vi",
    "ind": "id", "tha": "th", "fas": "fa", "pol": "pl", "nld": "nl",
    "ukr": "uk", "swe": "sv", "fin": "fi", "heb": "he", "ell": "el",
    "ces": "cs", "ron": "ro", "hun": "hu", "dan": "da", "msa": "ms",
    "swa": "sw", "tam": "ta", "tel": "te", "mar": "mr", "mal": "ml",
    "pan": "pa", "guj": "gu", "kan": "kn", "mya": "my", "amh": "am",
    "nor": "no", "nob": "no",
}


def to_whisper_lang(code: str | None) -> str | None:
    if not code:
        return None
    c = code.strip().lower()
    if not c or c in {"auto", "none"}:
        return None
    if c in _WHISPER_LANG_ALIAS:
        return _WHISPER_LANG_ALIAS[c]
    # Already a 2-letter code → trust it. Whisper rejects unknown codes so
    # invalid hints just raise; the caller falls back to auto-detect.
    if len(c) == 2:
        return c
    return None


# ---------------------------------------------------------------------------
# Reference transcription (runs in a thread, publishes segments live).
# ---------------------------------------------------------------------------
async def transcribe_ref(ref_id: str) -> None:
    ref = refs.get(ref_id)
    if not ref:
        return
    wav_path = Path(ref["wav_path"])
    ref["status"] = "transcribing"
    ref["transcript"] = ""
    ref["segments"] = []
    _publish(_ref_channels, ref_id, {"type": "status", "status": "transcribing"})
    db.update_ref(ref_id, status="transcribing", transcript="", segments_json="[]")

    try:
        model = await get_whisper()
    except Exception as e:
        ref["status"] = "error"
        ref["error"] = f"whisper load failed: {e}"
        _publish(_ref_channels, ref_id, {"type": "error", "error": ref["error"]})
        db.update_ref(ref_id, status="error", error=ref["error"])
        return

    loop = asyncio.get_running_loop()
    # Optional hint stored on the ref at upload time. Without it, Whisper
    # autodetects — which is where the Hindi-as-Urdu confusion comes from.
    lang_hint = to_whisper_lang(ref.get("language_hint"))

    def _run():
        # faster-whisper returns a generator of segments — stream them.
        segments, info = model.transcribe(
            str(wav_path),
            beam_size=1,
            vad_filter=True,
            condition_on_previous_text=False,
            language=lang_hint,
        )
        for seg in segments:
            yield {
                "start": float(seg.start),
                "end": float(seg.end),
                "text": seg.text.strip(),
            }, info

    def _worker():
        try:
            for seg, info in _run():
                asyncio.run_coroutine_threadsafe(_emit_seg(seg, info), loop)
            asyncio.run_coroutine_threadsafe(_emit_done(), loop)
        except Exception as e:
            asyncio.run_coroutine_threadsafe(_emit_error(str(e)), loop)

    async def _emit_seg(seg: dict, info) -> None:
        ref["segments"].append(seg)
        ref["transcript"] = (ref["transcript"] + " " + seg["text"]).strip()
        ref["language"] = getattr(info, "language", None)
        _publish(_ref_channels, ref_id, {"type": "segment", "segment": seg, "language": ref.get("language")})
        # Persist incremental progress so a page refresh shows partial transcripts.
        db.update_ref(ref_id,
                      transcript=ref["transcript"],
                      language=ref.get("language"),
                      segments_json=json.dumps(ref["segments"]))

    async def _emit_done() -> None:
        ref["status"] = "ready"
        ref["ready_at"] = now_iso()
        _publish(_ref_channels, ref_id, {
            "type": "done",
            "transcript": ref["transcript"],
            "segments": ref["segments"],
        })
        db.update_ref(ref_id, status="ready", ready_at=ref["ready_at"],
                      transcript=ref["transcript"], language=ref.get("language"),
                      segments_json=json.dumps(ref["segments"]))

    async def _emit_error(msg: str) -> None:
        ref["status"] = "error"
        ref["error"] = msg
        _publish(_ref_channels, ref_id, {"type": "error", "error": msg})
        db.update_ref(ref_id, status="error", error=msg)

    await asyncio.to_thread(_worker)


# ---------------------------------------------------------------------------
# Cloning job runner — subprocess convert_and_clone.py and stream logs.
# ---------------------------------------------------------------------------
async def run_clone_job(job_id: str) -> None:
    job = jobs[job_id]
    ref = refs[job["ref_id"]]
    job["status"] = "running"
    job["started_at"] = now_iso()
    _publish(_job_channels, job_id, {"type": "status", "status": "running"})
    db.update_job(job_id, status="running", started_at=job["started_at"])

    # Per-user output directory. The job dict carries its owner so we can
    # write into the right tree without needing the request context here.
    user = db.get_user_by_id(job["user_id"])
    out_dir = db.user_dirs(user["username"])["outs"] if user else (DATA_DIR / "_orphan")
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / f"{job_id}.wav"
    job["output_path"] = str(output_path)

    # We bypass the .m4a step and feed the already-converted ref WAV directly.
    # convert_and_clone.py expects an --input file and re-derives a *_ref16k.wav
    # next to it. Easiest: hand it the WAV; it will run a no-op ffmpeg pass.
    src = Path(ref["src_path"])

    cmd = [
        PYTHON, str(ROOT / "convert_and_clone.py"),
        "--input", str(src),
        "--text", job["text"],
        "--output", str(output_path),
        "--steps", str(job["steps"]),
        "--speed", str(job["speed"]),
    ]
    if job.get("per_paragraph"):
        cmd += ["--per-paragraph", "--batch-size", str(job.get("batch_size", 4))]
    if job.get("language"):
        cmd += ["--language", str(job["language"])]

    _publish(_job_channels, job_id, {"type": "log", "line": "$ " + " ".join(cmd)})

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=str(ROOT),
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )

    job["pid"] = proc.pid

    assert proc.stdout is not None
    while True:
        chunk = await proc.stdout.readline()
        if not chunk:
            break
        line = chunk.decode("utf-8", errors="replace").rstrip()
        job["log"].append(line)
        _publish(_job_channels, job_id, {"type": "log", "line": line})

        # Lightweight stage detection — a hint, not a hard contract.
        low = line.lower()
        if "loading omnivoice" in low:
            _publish(_job_channels, job_id, {"type": "stage", "stage": "loading"})
        elif "model ready" in low or "cloning voice" in low or "per-paragraph mode" in low:
            _publish(_job_channels, job_id, {"type": "stage", "stage": "synthesising"})
        elif "wrote " in low:
            _publish(_job_channels, job_id, {"type": "stage", "stage": "finalising"})

    rc = await proc.wait()
    job["return_code"] = rc
    job["finished_at"] = now_iso()
    if rc == 0 and output_path.exists():
        job["status"] = "ready"
        job["duration"] = wav_seconds(output_path)
        _publish(_job_channels, job_id, {
            "type": "done",
            "duration": job["duration"],
            "output_url": f"/api/jobs/{job_id}/audio",
        })
        db.update_job(job_id,
                      status="ready", duration=job["duration"],
                      output_path=str(output_path), return_code=rc,
                      finished_at=job["finished_at"], log=job.get("log", []))
    else:
        job["status"] = "failed"
        _publish(_job_channels, job_id, {"type": "failed", "return_code": rc})
        db.update_job(job_id,
                      status="failed", return_code=rc,
                      finished_at=job["finished_at"], log=job.get("log", []))


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="Mimicore")


@app.on_event("startup")
async def _startup_scheduler():
    """Boot the job scheduler + hydrate the in-memory caches from SQLite so
    refs/jobs survive a server restart."""
    global _job_pending, _job_slot_event
    _job_pending = asyncio.Queue()
    _job_slot_event = asyncio.Event()
    asyncio.create_task(_scheduler_loop())

    # Touch the DB connection once at boot so the schema migration runs even
    # before the first request.
    db._connect()


# ---------------------------------------------------------------------------
# Auth dependency — pulled from the session cookie. Used to scope refs/jobs
# to the requesting user. WS endpoints can't depend on FastAPI's Depends
# for cookies the way HTTP can, so they read websocket.cookies directly.
# ---------------------------------------------------------------------------
async def current_user(request: Request) -> dict:
    token = request.cookies.get(SESSION_COOKIE)
    user = db.user_for_session(token)
    if not user:
        raise HTTPException(401, "not authenticated")
    return user


def user_for_websocket(websocket: WebSocket) -> dict | None:
    return db.user_for_session(websocket.cookies.get(SESSION_COOKIE))

# Permissive CORS so Vite dev server (port 5173) can talk to the API on 8000.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# Language catalogue is loaded once from omnivoice's bundled lang_map. ~646
# entries; cheap to load, but we cache it to avoid the import cost per request.
_LANG_CATALOGUE: list[dict[str, str]] | None = None


def _load_language_catalogue() -> list[dict[str, str]]:
    global _LANG_CATALOGUE
    if _LANG_CATALOGUE is not None:
        return _LANG_CATALOGUE
    try:
        from omnivoice.utils.lang_map import LANG_NAME_TO_ID
    except Exception as e:
        print(f"[langs] failed to load OmniVoice language map: {e}", flush=True)
        _LANG_CATALOGUE = []
        return _LANG_CATALOGUE
    seen: dict[str, str] = {}
    for name, code in LANG_NAME_TO_ID.items():
        # Multiple display-names can collapse to the same ISO 639-3 code
        # (dialects → parent code). Keep the shortest name for each code.
        if code not in seen or len(name) < len(seen[code]):
            seen[code] = name
    items = [{"code": code, "name": name.title()} for code, name in seen.items()]
    items.sort(key=lambda x: x["name"])
    _LANG_CATALOGUE = items
    return items


# A short curated list of "popular" languages we surface at the top of the
# picker. Keep the codes exactly as they appear in OmniVoice's lang_map.
POPULAR_LANGUAGE_CODES: list[str] = [
    "en", "es", "fr", "de", "it", "pt", "ru", "zh", "ja", "ko",
    "arz", "hi", "bn", "ur", "tr", "vi", "id", "th", "fa", "pl",
    "nl", "uk", "sv", "fi", "he", "el", "cs", "ro", "hu", "da",
    "ms", "sw", "ta", "te", "mr", "ml", "pa", "gu", "kn", "my",
]


@app.get("/api/languages")
async def list_languages():
    """Return all languages OmniVoice can synthesise. Used by the UI's
    language picker. The list comes straight from omnivoice's bundled
    LANG_NAME_TO_ID map (~646 entries)."""
    items = _load_language_catalogue()
    code_set = {l["code"] for l in items}
    popular = [c for c in POPULAR_LANGUAGE_CODES if c in code_set]
    return {
        "languages": items,
        "popular": popular,
        "count": len(items),
    }


# ---------------------------------------------------------------------------
# AI script generator — small instruction-tuned LM behind /api/generate.
#
# We default to HuggingFaceTB/SmolLM2-360M-Instruct: ~360M params, GGUF/HF
# weights ~720MB, CPU-friendly, instruction-tuned. The user can override via
# env (MIMICORE_LM_MODEL) to point at any chat-template HF model.
# ---------------------------------------------------------------------------
LM_MODEL = os.environ.get("MIMICORE_LM_MODEL", "HuggingFaceTB/SmolLM2-360M-Instruct")
_lm_pipe = None
_lm_lock = asyncio.Lock()


async def get_lm():
    """Lazy-load the script-generation pipeline. First call downloads ~720MB
    on cold start; subsequent calls are instant."""
    global _lm_pipe
    async with _lm_lock:
        if _lm_pipe is not None:
            return _lm_pipe
        from transformers import pipeline, AutoTokenizer
        try:
            import torch
            cuda = torch.cuda.is_available()
        except Exception:
            cuda = False
        kwargs = {"model": LM_MODEL}
        if cuda:
            try:
                import torch
                kwargs["torch_dtype"] = torch.float16
                kwargs["device_map"] = "auto"
            except Exception:
                pass
        print(f"[lm] loading {LM_MODEL} cuda={cuda}", flush=True)
        try:
            _lm_pipe = pipeline("text-generation", **kwargs)
        except Exception as e:
            print(f"[lm] pipeline load failed: {e}", flush=True)
            raise
        return _lm_pipe


@app.post("/api/generate")
async def generate_script(payload: dict):
    """Generate a voice-friendly script from a short prompt. Designed for
    Mimicore's "AI" composer mode — the user types a prompt, gets back a
    paragraph or two suitable for synthesis."""
    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        raise HTTPException(400, "prompt is empty")
    max_new = int(payload.get("max_new_tokens", 220))
    max_new = max(40, min(600, max_new))

    pipe = await get_lm()

    system = (
        "You write short, natural-sounding scripts for text-to-speech. "
        "Write 1–3 short paragraphs of plain prose. No bullet points, no "
        "headings, no markdown — just sentences a person can read aloud. "
        "Aim for the length and tone the user asks for; default to 80–160 "
        "words if they don't specify."
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]

    def _run():
        out = pipe(
            messages,
            max_new_tokens=max_new,
            do_sample=True,
            temperature=0.7,
            top_p=0.9,
            repetition_penalty=1.05,
        )
        # transformers returns either [{"generated_text": "..."}] or chat-style
        # nested messages depending on version. Handle both.
        first = out[0] if isinstance(out, list) and out else {}
        gen = first.get("generated_text", first)
        if isinstance(gen, list):
            # chat format: list of messages — last one is the assistant reply
            for m in reversed(gen):
                if isinstance(m, dict) and m.get("role") == "assistant":
                    return (m.get("content") or "").strip()
            return ""
        if isinstance(gen, str):
            # text-completion format — strip the prompt prefix if echoed.
            return gen.strip()
        return ""

    text = await asyncio.to_thread(_run)
    if not text:
        raise HTTPException(500, "model returned no text")
    return {"text": text, "model": LM_MODEL}


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------
def _set_session_cookie(response: Response, token: str) -> None:
    # 30-day cookie. SameSite=lax so the cookie still flows on top-level GETs
    # (e.g. clicking an in-app link). Not Secure so dev over http://localhost
    # works; flip to Secure behind HTTPS in production.
    response.set_cookie(
        SESSION_COOKIE, token,
        max_age=db.SESSION_TTL_DAYS * 24 * 3600,
        httponly=True, samesite="lax", path="/",
    )


@app.post("/api/auth/register")
async def auth_register(payload: dict, response: Response):
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    try:
        user = db.create_user(username, password)
    except ValueError as e:
        raise HTTPException(400, str(e))
    token = db.create_session(user["id"])
    _set_session_cookie(response, token)
    return {"user": user}


@app.post("/api/auth/login")
async def auth_login(payload: dict, response: Response):
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    user = db.authenticate(username, password)
    if not user:
        raise HTTPException(401, "invalid username or password")
    token = db.create_session(user["id"])
    _set_session_cookie(response, token)
    return {"user": user}


@app.post("/api/auth/logout")
async def auth_logout(request: Request, response: Response):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        db.revoke_session(token)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@app.get("/api/auth/me")
async def auth_me(request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    user = db.user_for_session(token)
    return {"user": user}  # null when not signed in — frontend handles redirect


@app.get("/api/health")
async def health():
    cuda_ok = False
    try:
        import torch
        cuda_ok = torch.cuda.is_available()
    except Exception:
        pass
    pending = _job_pending.qsize() if _job_pending is not None else 0
    return {
        "ok": True,
        "cuda": cuda_ok,
        "refs": len(refs),
        "jobs": len(jobs),
        "scheduler": {
            "max_parallel": SCHED_MAX_PARALLEL,
            "running": len(_job_running),
            "pending": pending,
            "free_vram_mb": _free_vram_mb(),
            "vram_per_job_mb": SCHED_VRAM_PER_JOB,
        },
    }


# ---------- references ----------
def _load_ref_for(user_id: int, ref_id: str) -> dict:
    """Pull a ref into the in-memory cache from SQLite if not loaded.
    Enforces ownership so users can't access each other's refs."""
    cached = refs.get(ref_id)
    if cached and cached.get("user_id") == user_id:
        return cached
    row = db.get_ref(ref_id, user_id)
    if not row:
        raise HTTPException(404, "ref not found")
    refs[ref_id] = row
    return row


@app.post("/api/refs")
async def upload_ref(
    file: UploadFile = File(...),
    clean: bool = True,
    language: str | None = None,
    user: dict = Depends(current_user),
):
    """Upload a reference voice sample. Lands under
    voice_data/<username>/reference_audio/."""
    dirs = db.user_dirs(user["username"])
    ref_dir = dirs["refs"]
    ref_id = uuid.uuid4().hex[:12]
    suffix = Path(file.filename or "upload").suffix or ".bin"
    src_path = ref_dir / f"{ref_id}{suffix}"
    raw_wav_path = ref_dir / f"{ref_id}_raw16k.wav"
    wav_path = ref_dir / f"{ref_id}_ref16k.wav"

    with src_path.open("wb") as f:
        while chunk := await file.read(1 << 20):
            f.write(chunk)

    cleaned_ok = False
    raw_duration = 0.0
    try:
        ffmpeg_to_wav(src_path, raw_wav_path, clean=False)
        raw_duration = wav_seconds(raw_wav_path)
        if clean:
            try:
                ffmpeg_to_wav(src_path, wav_path, clean=True)
                cleaned_ok = True
            except Exception as e:
                print(f"[refs] cleanup failed for {ref_id}: {e}", flush=True)
                shutil.copyfile(raw_wav_path, wav_path)
        else:
            shutil.copyfile(raw_wav_path, wav_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"audio conversion failed: {e}")

    ref = {
        "id": ref_id,
        "user_id": user["id"],
        "name": file.filename or f"ref-{ref_id}",
        "src_path": str(src_path),
        "wav_path": str(wav_path),
        "raw_wav_path": str(raw_wav_path),
        "duration": wav_seconds(wav_path),
        "raw_duration": raw_duration,
        "cleaned": cleaned_ok,
        "uploaded_at": now_iso(),
        "status": "queued",
        "transcript": "",
        "segments": [],
        "language": None,
        "language_hint": (language.strip() if language and language.strip() else None),
    }
    refs[ref_id] = ref
    db.insert_ref(user["id"], ref)

    asyncio.create_task(transcribe_ref(ref_id))
    return ref


@app.get("/api/refs")
async def list_refs(user: dict = Depends(current_user)):
    rows = db.list_refs(user["id"])
    # Hydrate cache for any ref that isn't already there — keeps WS streams
    # working after a restart.
    for r in rows:
        refs.setdefault(r["id"], r)
    return rows


@app.get("/api/refs/{ref_id}")
async def get_ref(ref_id: str, user: dict = Depends(current_user)):
    return _load_ref_for(user["id"], ref_id)


@app.delete("/api/refs/{ref_id}")
async def delete_ref(ref_id: str, user: dict = Depends(current_user)):
    row = db.delete_ref(ref_id, user["id"])
    if not row:
        raise HTTPException(404, "ref not found")
    refs.pop(ref_id, None)
    for k in ("src_path", "wav_path", "raw_wav_path"):
        if not row.get(k):
            continue
        try:
            Path(row[k]).unlink(missing_ok=True)
        except Exception:
            pass
    return {"deleted": ref_id}


@app.get("/api/refs/{ref_id}/audio")
async def ref_audio(ref_id: str, raw: bool = False, user: dict = Depends(current_user)):
    """Stream the reference audio. ``?raw=1`` returns the un-cleaned source."""
    ref = _load_ref_for(user["id"], ref_id)
    path = ref.get("raw_wav_path") if raw else ref["wav_path"]
    if not path or not Path(path).exists():
        path = ref["wav_path"]
    return FileResponse(path, media_type="audio/wav")


@app.post("/api/transcribe")
async def transcribe_one(
    file: UploadFile = File(...),
    language: str | None = None,
    user: dict = Depends(current_user),
):
    """One-shot transcription. Powers the in-composer dictate feature."""
    tmp_id = uuid.uuid4().hex[:8]
    suffix = Path(file.filename or "blob").suffix or ".webm"
    src = SCRATCH_DIR / f"_dictate_{tmp_id}{suffix}"
    wav = SCRATCH_DIR / f"_dictate_{tmp_id}.wav"
    try:
        with src.open("wb") as f:
            while chunk := await file.read(1 << 20):
                f.write(chunk)
        try:
            ffmpeg_to_wav(src, wav)
        except Exception as e:
            raise HTTPException(400, f"audio conversion failed: {e}")

        model = await get_whisper()
        lang_hint = to_whisper_lang(language)

        def _run():
            segs, info = model.transcribe(
                str(wav),
                beam_size=1,
                vad_filter=True,
                condition_on_previous_text=False,
                language=lang_hint,
            )
            text = " ".join(s.text.strip() for s in segs).strip()
            return text, getattr(info, "language", None)

        text, lang = await asyncio.to_thread(_run)
        return {"text": text, "language": lang}
    finally:
        try: src.unlink(missing_ok=True)
        except Exception: pass
        try: wav.unlink(missing_ok=True)
        except Exception: pass


@app.websocket("/api/refs/{ref_id}/transcribe")
async def ws_ref_transcribe(websocket: WebSocket, ref_id: str):
    await websocket.accept()
    user = user_for_websocket(websocket)
    if not user:
        await websocket.send_json({"type": "error", "error": "not authenticated"})
        await websocket.close()
        return
    # Pull from DB on a cold restart, but enforce ownership.
    ref = refs.get(ref_id)
    if not ref or ref.get("user_id") != user["id"]:
        ref = db.get_ref(ref_id, user["id"])
        if ref:
            refs[ref_id] = ref
    if not ref:
        await websocket.send_json({"type": "error", "error": "ref not found"})
        await websocket.close()
        return
    await websocket.send_json({
        "type": "snapshot",
        "status": ref["status"],
        "transcript": ref["transcript"],
        "segments": ref["segments"],
        "language": ref.get("language"),
    })

    q = _subscribe(_ref_channels, ref_id)
    try:
        while True:
            event = await q.get()
            await websocket.send_json(event)
            if event.get("type") in ("done", "error"):
                # Stay open briefly so the client sees the final frame, then close.
                await asyncio.sleep(0.05)
                break
    except WebSocketDisconnect:
        pass
    finally:
        _unsubscribe(_ref_channels, ref_id, q)
        try:
            await websocket.close()
        except Exception:
            pass


def _load_job_for(user_id: int, job_id: str) -> dict:
    cached = jobs.get(job_id)
    if cached and cached.get("user_id") == user_id:
        return cached
    row = db.get_job(job_id, user_id)
    if not row:
        raise HTTPException(404, "job not found")
    jobs[job_id] = row
    return row


# ---------- jobs ----------
@app.post("/api/jobs")
async def create_job(payload: dict, user: dict = Depends(current_user)):
    ref_id = payload.get("ref_id")
    text = (payload.get("text") or "").strip()
    if not ref_id:
        raise HTTPException(400, "ref_id missing")
    ref = _load_ref_for(user["id"], ref_id)
    if not text:
        raise HTTPException(400, "text is empty")

    job_id = uuid.uuid4().hex[:12]
    raw_lang = (payload.get("language") or "").strip()
    language = raw_lang if raw_lang and raw_lang.lower() not in {"auto", "none"} else None
    job = {
        "id": job_id,
        "user_id": user["id"],
        "ref_id": ref_id,
        "ref_name": ref["name"],
        "text": text,
        "steps": int(payload.get("steps", 32)),
        "speed": float(payload.get("speed", 1.0)),
        "per_paragraph": bool(payload.get("per_paragraph", False)),
        "batch_size": int(payload.get("batch_size", 4)),
        "language": language,
        "status": "queued",
        "log": [],
        "created_at": now_iso(),
    }
    jobs[job_id] = job
    db.insert_job(user["id"], job)
    if _job_pending is None:
        asyncio.create_task(_run_then_release(job_id))
        _job_running.add(job_id)
    else:
        await _job_pending.put(job_id)
        job["queue_position"] = _queue_position(job_id)
    return job


@app.get("/api/jobs")
async def list_jobs(user: dict = Depends(current_user)):
    rows = db.list_jobs(user["id"])
    for j in rows:
        jobs.setdefault(j["id"], j)
    return rows


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str, user: dict = Depends(current_user)):
    return _load_job_for(user["id"], job_id)


@app.get("/api/jobs/{job_id}/audio")
async def job_audio(job_id: str, user: dict = Depends(current_user)):
    job = _load_job_for(user["id"], job_id)
    if job.get("status") != "ready" or not job.get("output_path"):
        raise HTTPException(404, "audio not ready")
    return FileResponse(job["output_path"], media_type="audio/wav")


@app.websocket("/api/jobs/{job_id}/stream")
async def ws_job_stream(websocket: WebSocket, job_id: str):
    await websocket.accept()
    user = user_for_websocket(websocket)
    if not user:
        await websocket.send_json({"type": "error", "error": "not authenticated"})
        await websocket.close()
        return
    job = jobs.get(job_id)
    if not job or job.get("user_id") != user["id"]:
        job = db.get_job(job_id, user["id"])
        if job:
            jobs[job_id] = job
    if not job:
        await websocket.send_json({"type": "error", "error": "job not found"})
        await websocket.close()
        return
    await websocket.send_json({
        "type": "snapshot",
        "status": job["status"],
        "log": job["log"],
        "wait_reason": job.get("wait_reason"),
        "queue_position": _queue_position(job_id),
        "running": len(_job_running),
        "max_parallel": SCHED_MAX_PARALLEL,
    })

    q = _subscribe(_job_channels, job_id)
    try:
        while True:
            event = await q.get()
            await websocket.send_json(event)
            if event.get("type") in ("done", "failed"):
                await asyncio.sleep(0.05)
                break
    except WebSocketDisconnect:
        pass
    finally:
        _unsubscribe(_job_channels, job_id, q)
        try:
            await websocket.close()
        except Exception:
            pass


# ---------- static frontend (after `npm run build`) ----------
if DIST_DIR.exists():
    app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")

    @app.get("/")
    async def root_index():
        return FileResponse(DIST_DIR / "index.html")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        # Anything that's not /api or /assets falls back to index.html (SPA).
        if full_path.startswith(("api/", "assets/")):
            raise HTTPException(404)
        return FileResponse(DIST_DIR / "index.html")
else:
    @app.get("/")
    async def root_dev_hint():
        return JSONResponse({
            "ok": True,
            "hint": "Frontend not built. In ./web run: npm install && npm run dev "
                    "(then open http://localhost:5173). For prod: npm run build.",
        })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="192.168.1.42", port=8000, reload=False)
