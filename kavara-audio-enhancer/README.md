# 🎧 Kavara Audio Enhancer

A command-line audio/video enhancement tool that removes background noise, adjusts playback speed without pitch distortion, applies broadcast-compliant EBU R128 loudness normalization, and uses **Gemini 3.7 Flash** AI to detect and cut filler words, silences, and generate synchronized `.srt` / `.vtt` subtitles in parallel.

---

## Features

| Feature | Description |
|---|---|
| **Noise Reduction** | Configurable spectral-gated denoising via `noisereduce` (60% moderate, 80% standard, 95% aggressive, or custom %) to strip background hiss. |
| **Pitch-Preserved Speed** | Time-stretch at preset (`1.0×`, `1.25×`, `1.5×`, `1.75×`, `2.0×`) or arbitrary speeds (e.g. `1.35×`) using `librosa` phase-vocoder without pitch distortion. |
| **Loudness Normalization** | EBU R128 integrated loudness normalization targeting `-16.0 LUFS` (Podcast standard), `-14.0 LUFS` (YouTube / Web Video standard), `-23.0 LUFS` (Broadcast), or custom targets. |
| **Parallel AI Smart Cuts** *(optional)* | Powered by **Gemini 3.7 Flash** with multithreaded chunk processing — detects "um", "uh", "like", and dead silences, then surgically cuts them from audio and video tracks. |
| **Parallel AI Subtitles** *(optional)* | Powered by **Gemini 3.7 Flash** with multithreaded chunk transcription — exports synchronized `.srt`, `.vtt`, and timestamped `.txt` transcripts in seconds. |
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

# Install dependencies
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
| `--use-ai` | | Enable Gemini 3.7 Flash filler word and silence detection |
| `--no-ai` | | Explicitly disable AI smart cuts without prompting |
| `--subtitles` | `--captions` | Enable Gemini 3.7 Flash synchronized subtitle/caption generation |
| `--no-subtitles` | | Explicitly disable subtitle generation |
| `--subtitle-format`| `--sub-format`| Subtitle format to export: `srt`, `vtt`, `both`, or `all` (default: `srt`) |
| `--workers` | `-w` | Number of concurrent worker threads for chunked AI analysis (default: `4`) |
| `--extract-audio` | `-x` | Extract and enhance audio only from a video file |
| `--format` | `-fmt` | Target audio output format (e.g. mp3, wav, flac, etc.) |
| `--interactive` | `-i` | Launch interactive wizard even if flags are passed |
| `--version` | `-v` | Show version and exit |

---

## Output

The enhanced media and exported subtitle files are saved in the **current working directory** matching your source filename:

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
