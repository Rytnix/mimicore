# Mimicore — Voice Cloning Studio

Mimicore is a local voice cloning studio powered by OmniVoice, with a Vue web
UI and a FastAPI backend. It supports reference uploads, microphone recording,
transcription, text composition, queued synthesis jobs, and user accounts.

## Web studio

Install the environment with `./setup_omnivoice.sh`, install Node.js 20+ and npm,
then run:

```bash
./run_web.sh
```

Open `http://localhost:8002`. The launcher installs missing web dependencies
and builds the frontend. Register an account to upload a reference and create
a synthesis job. The server binds to all network interfaces; restrict access
to a trusted network.

`server.py` serves the API and built UI, `db.py` stores accounts and jobs in
SQLite, and `web/` contains the Vue frontend. Model weights, recordings,
generated audio, account databases, and installed dependencies are excluded
from Git. They are downloaded or created locally as needed.

The command-line workflow is documented below.

## Voice Cloning with OmniVoice (iPhone → Linux + NVIDIA)

A small, end-to-end pipeline that takes a Voice Memo recorded on your iPhone
and synthesises arbitrary text in your cloned voice using
[OmniVoice](https://github.com/k2-fsa/OmniVoice) on a Linux laptop with an
NVIDIA GPU.

```
iPhone .m4a  ──ffmpeg──►  16 kHz mono WAV  ──OmniVoice──►  24 kHz cloned WAV
```

---

## 1. Repo layout

| File                   | Purpose                                                |
|------------------------|--------------------------------------------------------|
| `setup_omnivoice.sh`   | One-shot installer (Python, ffmpeg, GPU check, venv, PyTorch, OmniVoice) |
| `convert_and_clone.py` | Conversion + cloning CLI                               |
| `run.sh`               | Wrapper that activates the venv and runs the CLI       |
| `README.md`            | This file                                              |

---

## 2. Prerequisites

- Linux (Ubuntu / Debian-based; tested on Ubuntu 22.04+).
- An NVIDIA GPU with a working driver. Verify with:

  ```bash
  nvidia-smi
  ```

  If that command is missing, install the proprietary driver:

  ```bash
  sudo ubuntu-drivers autoinstall
  sudo reboot
  ```

- `sudo` access (only used by the installer for `apt`).
- ~5 GB free disk for PyTorch + OmniVoice model weights.

---

## 3. Recording a clean reference on iPhone

1. Open **Voice Memos** (built-in iOS app).
2. Tap the red record button.
3. Speak naturally for **10–30 seconds**. Tips:
   - Quiet room, no background music or TV.
   - Hold the phone ~15 cm from your mouth.
   - Use full sentences, not single words. Read a short paragraph aloud.
4. Tap stop. Rename the recording so you can find it later.

Longer / cleaner reference = better clone. Less than ~3 s usually sounds bad.

---

## 4. Transferring the .m4a to the Linux laptop

Pick whichever option matches your setup.

### Option A — USB cable (simplest)

1. Plug the iPhone in. Tap **Trust** on the phone when prompted.
2. On Ubuntu, the phone shows up in **Files** under the sidebar.
3. Open `Recordings/` (or `Voice Memos`) and drag the `.m4a` into this
   project folder.

If the phone refuses to mount, install:

```bash
sudo apt install libimobiledevice6 ifuse usbmuxd
```

then re-plug the phone.

### Option B — AirDrop-style transfer over the network (sftp)

If your iPhone has an SFTP client (e.g. *Secure ShellFish*, *Documents by
Readdle*) and your laptop has `openssh-server`:

```bash
sudo apt install openssh-server
ip addr show          # note the LAN IP, e.g. 192.168.1.42
```

In the iPhone SFTP client, connect to `your-user@192.168.1.42`, navigate
to this project folder, and upload the `.m4a`.

### Option C — iCloud / email / Drive

Share the memo to yourself, then download the `.m4a` on the laptop.

Whatever route you use, end up with the file inside this project folder,
e.g. `my_voice.m4a`.

---

## 5. Install (one time)

```bash
chmod +x setup_omnivoice.sh run.sh
./setup_omnivoice.sh
```

The installer will:

1. Check / install Python 3.10+.
2. Check / install `ffmpeg`.
3. Verify your NVIDIA GPU via `nvidia-smi`.
4. Create `omnivoice_env/` (venv).
5. Install PyTorch 2.8.0 (CUDA 12.8, falling back to CUDA 12.1 if needed).
6. Install OmniVoice from PyPI.
7. Run an import smoke test.

You should end with a green `Setup complete.` banner.

---

## 6. Clone your voice

```bash
./run.sh --input my_voice.m4a --text "Hello, this is my cloned voice."
```

The first run downloads the OmniVoice model weights from HuggingFace — that's
a few hundred MB to a couple of GB depending on the release. Subsequent runs
are cached.

### CLI options

| Flag        | Default              | Meaning                                                           |
|-------------|----------------------|-------------------------------------------------------------------|
| `--input`   | *(required)*         | Source `.m4a` file from iPhone Voice Memos.                       |
| `--text`    | *(required)*         | Sentence to synthesise in the cloned voice.                       |
| `--output`  | `cloned_output.wav`  | Destination WAV path.                                             |
| `--steps`   | `32`                 | Diffusion steps. Use `16` for ~2× speed, slight quality drop.     |
| `--speed`   | `1.0`                | Speaking speed factor (`>1` faster, `<1` slower).                 |

### Examples

```bash
# Default quality
./run.sh --input me.m4a --text "Welcome to the demo."

# Fast inference
./run.sh --input me.m4a --text "Quick test." --steps 16

# Slightly faster speech, custom output filename
./run.sh --input me.m4a --text "Slow down a touch." --speed 0.9 \
         --output greeting.wav
```

### Play the result

```bash
aplay cloned_output.wav            # ALSA, ships with most distros
# or
vlc cloned_output.wav              # GUI
# or
ffplay -autoexit cloned_output.wav # bundled with ffmpeg
```

---

## 7. Troubleshooting

### `Permission denied` running `./setup_omnivoice.sh` or `./run.sh`

The scripts need the executable bit:

```bash
chmod +x setup_omnivoice.sh run.sh
```

### `nvidia-smi: command not found` / `CUDA not available`

- Confirm you actually have an NVIDIA GPU: `lspci | grep -i nvidia`
- Install the driver: `sudo ubuntu-drivers autoinstall && sudo reboot`
- After reboot, `nvidia-smi` should list your GPU.
- Inside the venv, double-check:

  ```bash
  source omnivoice_env/bin/activate
  python -c "import torch; print(torch.cuda.is_available(), torch.version.cuda)"
  ```

  If `False`, you most likely installed the CPU-only torch. Re-run
  `./setup_omnivoice.sh` — it pins the CUDA wheels explicitly.

### `ffmpeg: command not found`

```bash
sudo apt update
sudo apt install ffmpeg
```

The installer normally does this for you; only relevant if you skipped it.

### HuggingFace download stalls or times out

Common in restricted networks. Use the public mirror:

```bash
export HF_ENDPOINT=https://hf-mirror.com
./run.sh --input me.m4a --text "Hello"
```

You can put that `export` into `~/.bashrc` to make it permanent.

If you also see SSL errors, make sure system CAs are installed:

```bash
sudo apt install ca-certificates
```

### GPU out-of-memory (`CUDA out of memory`)

- Use fewer diffusion steps:  `--steps 16`
- Close other GPU-using apps (browser, games, other models).
- Check who's using VRAM: `nvidia-smi`

### The clone sounds robotic / nothing like me

- Re-record a longer reference (aim for 15–30 s of *continuous* speech).
- Avoid clipping (don't shout into the mic) and background noise.
- Drop background music, TVs, fans.
- Verify the converted reference is sane:

  ```bash
  aplay my_voice_ref16k.wav
  ```

  If it sounds wrong already, fix the recording — OmniVoice can't recover
  what isn't there.

### `m4a` won't convert (`Invalid data found when processing input`)

The file may actually be `.m4a` only by extension. Inspect it:

```bash
ffprobe my_voice.m4a
```

If `ffprobe` errors, the file is likely truncated during transfer — try the
copy again.

### Re-running setup from scratch

```bash
rm -rf omnivoice_env
./setup_omnivoice.sh
```

The HuggingFace cache (in `~/.cache/huggingface`) survives this and avoids
re-downloading the model.

---

## 8. Uninstall

```bash
rm -rf omnivoice_env
rm -rf ~/.cache/huggingface     # optional, frees model cache
```

---

## 9. Credits

- [OmniVoice](https://github.com/k2-fsa/OmniVoice) by k2-fsa — the model and
  Python library doing the actual cloning.
- [PyTorch](https://pytorch.org/) — runtime.
- [ffmpeg](https://ffmpeg.org/) — audio conversion.
