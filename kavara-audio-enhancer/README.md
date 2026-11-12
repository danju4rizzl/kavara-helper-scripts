# 🎧 Kavara Audio Enhancer

A command-line audio/video enhancement tool that removes background noise, adjusts playback speed without pitch distortion, applies broadcast-compliant EBU R128 loudness normalization, and uses **Gemini 3.5 Transcribe** AI to detect and cut filler words, silences, and generate synchronized `.srt` / `.vtt` subtitles in parallel.

---

## Features

| Feature | Description |
|---|---|
| **Noise Reduction** | Configurable spectral-gated denoising via `noisereduce` (60% moderate, 80% standard, 95% aggressive, or custom %) to strip background hiss. |
| **Pitch-Preserved Speed** | Time-stretch at preset (`1.0×`, `1.25×`, `1.5×`, `1.75×`, `2.0×`) or arbitrary speeds (e.g. `1.35×`) using FFmpeg's `atempo` filter without pitch distortion. |
| **Loudness Normalization** | Two-pass FFmpeg `loudnorm` (EBU R128) with precise linear gain, targeting `-16.0 LUFS` (Podcast standard), `-14.0 LUFS` (YouTube / Web Video standard), `-23.0 LUFS` (Broadcast), or custom targets. |
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
Set your API key as an environment variable (or enter it interactively when prompted):

```bash
# Linux / macOS
export GEMINI_API_KEY="your_key_here"

# Windows (PowerShell)
$env:GEMINI_API_KEY = "your_key_here"

# Windows (CMD)
set GEMINI_API_KEY=your_key_here
```

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
5. **Noise Reduction Intensity:** Select `Standard (80%)`, `Moderate (60%)`, `Aggressive (95%)`, enter a custom percentage, or disable.
6. **Loudness Normalization (EBU R128):** Choose `Podcast Standard (-16 LUFS)`, `YouTube Standard (-14 LUFS)`, `Broadcast (-23 LUFS)`, custom LUFS target, or disable.
7. **AI Smart Cuts & Subtitles:** Choose between Smart Cuts only, Subtitles & Captions only, Both, or local DSP only.
8. **Subtitle Format Selection:** If subtitles are enabled, choose between `.srt`, `.vtt`, `both`, or `all` (including plain text transcript).
9. **Job Confirmation & Progress:** Displays a formatted summary card before processing with real-time step progress and elapsed time.

### Command-Line Arguments
If you prefer using flags, all options are supported:
```bash
# Basic usage — enhance an audio file at 1.25× speed with -16 LUFS normalization
python enhancer.py --file podcast.mp3 --speed 1.25 --normalize -16.0

# Enhance a video with custom speed, 90% denoise, and YouTube loudness
python enhancer.py --file lecture.mp4 --speed 1.35 --denoise 90% --normalize -14.0

# Extract audio from a video, enable AI cuts, and generate SRT + VTT captions in parallel (8 workers)
python enhancer.py --file lecture.mp4 --speed 1.25 --extract-audio --format mp3 --use-ai --subtitles --subtitle-format both --workers 8

# Generate synchronized captions for a video without speed change
python enhancer.py --file lecture.mp4 --subtitles --subtitle-format srt

# Trim dead silence locally (no API key), write to a folder, at 1.25x
kavara-enhancer --file lecture.mp4 --cut-silence --speed 1.25 --output exports/

# Choose the exact output file (extension decides the format; .mp3 on a video extracts audio)
kavara-enhancer --file lecture.mp4 --output exports/lecture-clean.mp3

# Preview the cuts without writing anything
kavara-enhancer --file lecture.mp4 --cut-silence --silence-threshold -40 --dry-run

# Force interactive wizard mode
python enhancer.py --interactive
```

### All Options
| Flag | Short | Description |
|---|---|---|
| `--file` | `-f` | Path to the source audio or video file |
| `--speed` | `-s` | Playback speed multiplier (e.g. `1.25`, `1.5`, `1.75`, `2.0`) |
| `--denoise` | | Noise reduction strength (e.g. `0.8`, `80%`, `95%`) |
| `--no-denoise` | | Explicitly disable noise reduction |
| `--normalize` | `--lufs` | Target loudness in LUFS for EBU R128 normalization (e.g. `-16.0`, `-14.0`) |
| `--no-normalize` | | Explicitly disable loudness normalization |
| `--use-ai` | | Enable Gemini 3.5 Transcribe filler word, repeated-phrase and silence removal |
| `--no-ai` | | Explicitly disable AI smart cuts without prompting |
| `--subtitles` | `--captions` | Enable Gemini 3.5 Transcribe synchronized subtitle/caption generation |
| `--no-subtitles` | | Explicitly disable subtitle generation |
| `--subtitle-format`| `--sub-format`| Subtitle format to export: `srt`, `vtt`, `both`, or `all` (default: `srt`) |
| `--cut-silence` | | Trim dead silence locally with FFmpeg (free). Implied by `--use-ai` |
| `--silence-threshold` | | Level in dB counted as silence (default: `-35`; try `-40` for noisy rooms) |
| `--output` | `-o` | Output file (e.g. `out/clean.mp3`) or directory (e.g. `out/`). Default: `<name>_enhanced.<ext>` in the current directory |
| `--dry-run` | | Show the plan and the detected cuts without writing any output. With `--use-ai` this still calls Gemini |
| `--workers` | `-w` | Number of concurrent worker threads for chunked AI analysis (default: `4`) |
| `--extract-audio` | `-x` | Extract and enhance audio only from a video file |
| `--format` | `-fmt` | Target audio output format (e.g. mp3, wav, flac, etc.) |
| `--interactive` | `-i` | Launch interactive wizard even if flags are passed |
| `--version` | `-v` | Show version and exit |

---

## Project Layout & Tests

```
enhancer.py            # thin entry point (python enhancer.py still works)
kavara_enhancer/       # package: cli, prompts, pipeline, dsp, silence, ai, cutting, assembly, subtitles, ...
tests/                 # pytest suite (FFmpeg integration tests auto-skip if FFmpeg is missing)
```

```bash
pip install -e .[dev]
python -m pytest
```

---

## Output

The enhanced media and exported subtitle files are saved in the **current working directory** (or the `--output` location) matching your source filename:

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
