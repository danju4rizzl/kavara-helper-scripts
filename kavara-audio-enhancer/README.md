# 🎧 Kavara Audio Enhancer

A command-line audio/video enhancement tool that removes background noise, adjusts playback speed without pitch distortion, applies broadcast-compliant EBU R128 loudness normalization, and uses **Gemini 3.5 Transcribe** AI to detect and cut filler words, silences, and generate synchronized `.srt` / `.vtt` subtitles in parallel.

---

## Features

| Feature | Description |
|---|---|
| **Noise Reduction** | Pick your engine: spectral gating via `noisereduce` (default), **RNNoise** neural denoising (`--denoise-engine rnnoise`) or **DeepFilterNet** (`--denoise-engine deepfilternet`). Strength is configurable (default 40% light, 60% moderate, 95% aggressive, or custom %). Keep it low: strengths above ~60% strip the consonants and make speech sound muffled. |
| **Pitch-Preserved Speed** | Time-stretch at preset (`1.0×`, `1.25×`, `1.5×`, `1.75×`, `2.0×`) or arbitrary speeds (e.g. `1.35×`) using FFmpeg's **Rubber Band** time-stretcher (falls back to `atempo` if your FFmpeg build lacks it) without pitch distortion. |
| **Loudness Normalization** | Two-pass FFmpeg `loudnorm` (EBU R128) with precise linear gain, targeting `-16.0 LUFS` (Podcast standard), `-14.0 LUFS` (YouTube / Web Video standard), `-23.0 LUFS` (Broadcast), or custom targets. |
| **Batch Mode** | Pass several files, folders or globs (`kavara-enhancer *.mp4`): one set of settings, one job per file, a failing file never stops the rest, and a summary at the end. |
| **Local Silence Removal** *(optional, free)* | `--cut-silence` trims dead air with FFmpeg `silencedetect` - no API key needed. Keeps a short natural pause on each side. |
| **Parallel AI Smart Cuts** *(optional)* | Powered by **Gemini 3.5 Transcribe** with multithreaded chunk processing — transcribes with word-level timestamps, then removes filler words ("um", "uh") and restarted phrases (in "I just want to… I just want to click here" the first take is deleted); silence is found locally and merged in. All cuts are validated (clamped, de-duplicated, sanity-checked) and joined with 10 ms declick fades, then surgically removed from audio and video tracks. |
| **Parallel AI Subtitles** *(optional)* | Powered by **Gemini 3.5 Transcribe** with multithreaded chunk transcription — exports synchronized `.srt`, `.vtt`, and timestamped `.txt` transcripts in seconds. |
| **Video & Audio Support** | Accepts `.mp4`, `.mkv`, `.avi`, `.mov`, `.webm` — extracts audio, enhances it, and remuxes back with the video at the correct speed. |
| **Audio Extraction** | Separate and extract audio from video files into standalone audio formats (`.mp3`, `.wav`, `.aac`, `.flac`). |

---

## Prerequisites

### 1. Python 3.10+
Ensure Python 3.10 or later is installed on your system.

### 2. FFmpeg
FFmpeg **must** be installed and available on your system `PATH`.

- **Windows**: Download from [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) and add the `bin/` folder to your PATH.
- **macOS**: `brew install ffmpeg`
- **Linux**: `sudo apt install ffmpeg` or equivalent for your distro.

Verify with:
```bash
ffmpeg -version
```

### 3. Gemini API Key *(only if using AI smart cuts or subtitle generation)*
Put it in a `.env` file next to `enhancer.py` (copy `.env.example`; it is gitignored): `GEMINI_API_KEY=your_key`. Or set it as an environment variable:
The key is looked up in this order: **environment variable / `.env`** → **system keyring** → an interactive prompt (hidden input, with an offer to save it to the keyring).

Environment variable examples:

```bash
# Linux / macOS
export GEMINI_API_KEY="your_key_here"

# Windows (PowerShell)
$env:GEMINI_API_KEY = "your_key_here"

# Windows (CMD)
set GEMINI_API_KEY=your_key_here
```

**System keyring** (optional; Windows Credential Manager, macOS Keychain, Secret Service):

```bash
pip install "kavara-audio-enhancer[keyring]"
kavara-enhancer --save-api-key     # prompts (hidden) and stores it
kavara-enhancer --delete-api-key   # removes it again
```

**Choosing the Gemini model:** use `--model MODEL_ID` or set `GEMINI_MODEL` (also works in `.env`). The model name shown in the interface follows your choice.

---

## Installation

```bash
# Clone the repository (or navigate to the project directory)
cd kavara-audio-enhancer

# Create and activate a virtual environment
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

# Install the package (adds the `kavara-enhancer` command)
pip install -e .

# or just the dependencies, then use `python enhancer.py`
pip install -r requirements.txt
```

---

## Usage

### Interactive Mode (Default)
Simply run:
```bash
python enhancer.py
```
The interactive wizard will guide you through:
1. **Source File Selection:** Automatically lists media files in your current directory with single-key selection, or allows typing/dragging & dropping any custom file path.
2. **Output Mode:** Choose between enhancing the video container or extracting standalone audio (when a video file is selected).
3. **Audio Format Selection:** Choose your target audio format (`.mp3`, `.wav`, `.aac`, `.flac`, or match original).
4. **Playback Speed:** Select `1.0x`, `1.25x`, `1.5x`, `1.75x`, `2.0x`, or enter any arbitrary custom speed (e.g. `1.35x`).
5. **Noise Reduction Intensity:** Select `Light (40%, default)`, `Moderate (60%)`, `Aggressive (95%)`, enter a custom percentage, or disable.
6. **Loudness Normalization (EBU R128):** Choose `Podcast Standard (-16 LUFS)`, `YouTube Standard (-14 LUFS)`, `Broadcast (-23 LUFS)`, custom LUFS target, or disable.
7. **AI Smart Cuts & Subtitles:** Choose between Smart Cuts only, Subtitles & Captions only, Both, or local DSP only.
8. **Subtitle Format Selection:** If subtitles are enabled, choose between `.srt`, `.vtt`, `both`, or `all` (including plain text transcript).
   For video output you are then asked whether to **burn the captions into the video** (default: yes).
9. **Job Confirmation & Progress:** Displays a formatted summary card before processing with real-time step progress and elapsed time.

### Setups: Balanced, Fast or Custom

In the interactive wizard (after the speed question) or with `--preset`, pick how much you want to decide:

| Setup | What it does | Best for |
|---|---|---|
| **Balanced** *(recommended)* | Silence removal + AI removal of fillers, repeats and restarts, light 40% denoise, loudness normalization, **captions burned into video**, high-quality video (`veryfast`, CRF 20). Falls back to local-only cuts if no Gemini key is set. | Most recordings |
| **Fast** | Local silence removal + loudness only. No AI, no denoise. Quickest video encode (`ultrafast`, CRF 23) so the video file is larger. | Quick turnaround, no API use |
| **Custom** | You choose every option (the classic wizard / flags). Default when you pass flags without `--preset`. | Full control |

Speed, file and format are always your choice. Any explicit flag overrides the preset, e.g. `--preset balanced --no-ai --denoise 60%`, `--preset balanced --no-burn-captions` (keeps `.srt`, skips burn-in) or `--preset fast --subtitles`.

On a 10-minute 1080p screen recording with 134 cuts at 1.25x, Fast took about 65 s and Balanced about 105 s (video file 41 MB vs 24 MB).

```bash
python enhancer.py --file lecture.mp4 --preset balanced --speed 1.25
python enhancer.py --file lecture.mp4 --preset fast
```

### Command-Line Arguments
If you prefer using flags, all options are supported:
```bash
# Basic usage — enhance an audio file at 1.25× speed with -16 LUFS normalization
python enhancer.py --file podcast.mp3 --speed 1.25 --normalize -16.0

# Enhance a video with custom speed, 90% denoise, and YouTube loudness
python enhancer.py --file lecture.mp4 --speed 1.35 --denoise 90% --normalize -14.0

# Extract audio from a video, enable AI cuts, and generate SRT + VTT captions in parallel (8 workers)
python enhancer.py --file lecture.mp4 --speed 1.25 --extract-audio --format mp3 --use-ai --subtitles --subtitle-format both --workers 8

# Burn captions into the video itself (drawn after cuts/speed, in the same encode pass)
python enhancer.py --file demo.mp4 --use-ai --burn-captions

# Generate synchronized captions for a video without speed change
python enhancer.py --file lecture.mp4 --subtitles --subtitle-format srt

# Trim dead silence locally (no API key), write to a folder, at 1.25x
kavara-enhancer --file lecture.mp4 --cut-silence --speed 1.25 --output exports/

# Choose the exact output file (extension decides the format; .mp3 on a video extracts audio)
kavara-enhancer --file lecture.mp4 --output exports/lecture-clean.mp3

# Preview the cuts without writing anything
kavara-enhancer --file lecture.mp4 --cut-silence --silence-threshold -40 --dry-run

# Batch: every supported file in a folder (or a glob), results in exports/
kavara-enhancer lectures/ --speed 1.25 --cut-silence --output exports/
kavara-enhancer "*.mp4" --lufs -14

# Neural denoise with RNNoise (one-time ~300 KB model download), at 90% strength
kavara-enhancer --download-rnnoise-model
kavara-enhancer --file noisy.wav --denoise-engine rnnoise --denoise 90

# Use a specific Gemini model
kavara-enhancer --file talk.mp4 --subtitles --model gemini-2.5-flash

# Force interactive wizard mode
python enhancer.py --interactive
```

### All Options
| Flag | Short | Description |
|---|---|---|
| `FILE ...` | | Positional: files, folders or glob patterns. More than one file runs as a batch |
| `--file` | `-f` | Source file(s), folder(s) or glob(s); same as the positional form |
| `--speed` | `-s` | Playback speed multiplier (e.g. `1.25`, `1.5`, `1.75`, `2.0`) |
| `--preset` | | Ready-made setup: `balanced`, `fast` or `custom` (see above). Explicit flags override it |
| `--denoise` | | Noise reduction strength (e.g. `0.4`, `40%`, `60%`; default 40%) |
| `--no-denoise` | | Explicitly disable noise reduction |
| `--normalize` | `--lufs` | Target loudness in LUFS for EBU R128 normalization (e.g. `-16.0`, `-14.0`) |
| `--no-normalize` | | Explicitly disable loudness normalization |
| `--use-ai` | | Enable Gemini 3.5 Transcribe filler word, repeated-phrase and silence removal |
| `--no-ai` | | Explicitly disable AI smart cuts without prompting |
| `--subtitles` | `--captions` | Enable Gemini 3.5 Transcribe synchronized subtitle/caption generation |
| `--burn-captions` | | Burn captions into the video (implies `--subtitles`; video output only). Short 2-7 word lines, white bold text on a dark box, sized to the video; re-encodes the video |
| `--no-burn-captions` | | Do not burn captions into the video (overrides the Balanced default; subtitle files are still made) |
| `--no-subtitles` | | Explicitly disable subtitle generation (also turns off burn-in unless `--burn-captions` is given) |
| `--subtitle-format`| `--sub-format`| Subtitle format to export: `srt`, `vtt`, `both`, or `all` (default: `srt`) |
| `--cut-silence` | | Trim dead silence locally with FFmpeg (free). Implied by `--use-ai` |
| `--silence-threshold` | | Level in dB counted as silence (default: `-35`; try `-40` for noisy rooms) |
| `--output` | `-o` | Output file (e.g. `out/clean.mp3`) or directory (e.g. `out/`). Default: `enhanced_files/<name>_enhanced.<ext>` |
| `--dry-run` | | Show the plan and the detected cuts without writing any output. With `--use-ai` this still calls Gemini |
| `--no-sound` | | Turn off the sound cues: one short blip when a job starts, three rising notes when it finishes, two low falling notes on error. Also `KAVARA_SOUND=0`. Silent when output isn't a terminal |
| `--model` | | Gemini model id (default: `$GEMINI_MODEL`, then the built-in default) |
| `--denoise-engine` | | `spectral` (default), `rnnoise` or `deepfilternet` |
| `--rnnoise-model` | | Path to an RNNoise `.rnnn` model; implies `--denoise-engine rnnoise` |
| `--download-rnnoise-model` | | Download and verify the RNNoise model, then exit |
| `--save-api-key` / `--delete-api-key` | | Store / remove the Gemini API key in the system keyring, then exit |
| `--workers` | `-w` | Number of concurrent worker threads for chunked AI analysis (default: `4`) |
| `--extract-audio` | `-x` | Extract and enhance audio only from a video file |
| `--format` | `-fmt` | Target audio output format (e.g. mp3, wav, flac, etc.) |
| `--interactive` | `-i` | Launch interactive wizard even if flags are passed |
| `--version` | `-v` | Show version and exit |

---

## Batch Mode

```bash
kavara-enhancer a.mp4 b.wav c.mkv          # several files
kavara-enhancer lectures/                  # every supported file in a folder (not recursive)
kavara-enhancer "*.mp3" -o cleaned/        # glob (quote it so it works the same on Windows)
```

- Settings you choose (flags, or the wizard once) apply to every file. Per-file details are worked out for each file: video vs. audio, output extension and the default loudness target.
- `--output` must be a **folder** in batch mode, and two inputs that would write the same output name (e.g. `a/talk.wav` and `b/talk.wav`) are rejected up front.
- Folders and globs skip earlier `*_enhanced` results; a file you name explicitly is always processed.
- A failing file is reported and the batch continues; the exit code is `1` if any file failed.
- Interactive mode picks a single source file; use the flags above for batches.

---

## Noise Reduction Engines

| Engine | Flag | Notes |
|---|---|---|
| Spectral gating | `--denoise-engine spectral` *(default)* | Built in, fast, good for steady hiss and hum. |
| RNNoise | `--denoise-engine rnnoise` | Neural, runs through FFmpeg's `arnndn` filter (your FFmpeg build must include it). Needs a small model file: run `kavara-enhancer --download-rnnoise-model` once (SHA-256 verified, saved to your user data folder; override with `KAVARA_MODELS_DIR`) or pass `--rnnoise-model PATH` / set `KAVARA_RNNOISE_MODEL`. The model is the general-purpose `sh.rnnn` from [GregorR/rnnoise-models](https://github.com/GregorR/rnnoise-models). |
| DeepFilterNet | `--denoise-engine deepfilternet` | Highest-quality neural option. Optional and heavy: `pip install "kavara-audio-enhancer[deepfilternet]"` (pulls in PyTorch). Works at 48 kHz internally. |

`--denoise` sets the strength for every engine (RNNoise: wet/dry mix; DeepFilterNet: maximum attenuation). The chosen engine is validated before any work starts, so a missing model or package fails immediately with instructions.

---

## Project Layout & Tests

```
enhancer.py            # thin entry point (python enhancer.py still works)
kavara_enhancer/       # package: cli, batch, prompts, pipeline, dsp, denoise, silence, ai, gemini_config, credentials, cutting, assembly, subtitles, ...
tests/                 # pytest suite (FFmpeg integration tests auto-skip if FFmpeg is missing)
```

```bash
pip install -e .[dev]
python -m pytest
```

---

## Output

The enhanced media and exported subtitle files are saved in an **`enhanced_files/`** folder in the current working directory (created automatically; or the `--output` location) matching your source filename:

```
lecture.mp4  →  lecture_enhanced.mp4             (Enhanced Video)
             →  lecture_enhanced.srt             (Synchronized SubRip Subtitles)
             →  lecture_enhanced.vtt             (Synchronized WebVTT Captions)
             →  lecture_enhanced_transcript.txt  (Timestamped Transcript)

podcast.wav  →  podcast_enhanced.mp3             (Converted & Enhanced Audio)
             →  podcast_enhanced.srt             (Synchronized Subtitles)
```

---

## Supported Formats

| Type | Extensions |
|---|---|
| **Audio** | `.wav`, `.mp3`, `.aac`, `.flac`, `.ogg`, `.m4a`, `.wma`, `.opus` |
| **Video** | `.mp4`, `.mkv`, `.avi`, `.mov`, `.webm`, `.flv`, `.ts` |
| **Subtitles** | `.srt` (SubRip), `.vtt` (WebVTT), `.txt` (Transcript) |

---

## License

MIT
