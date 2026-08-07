# 🎧 Kavara Audio Enhancer

A command-line audio/video enhancement tool that removes background noise, adjusts playback speed without pitch distortion, and optionally uses **Gemini 2.5 Flash** AI to detect and cut filler words and dead silences.

---

## Features

| Feature | Description |
|---|---|
| **Noise Reduction** | Spectral-gated denoising via `noisereduce` — strips background hiss while preserving the human voice. |
| **Pitch-Preserved Speed** | Time-stretch at 1.0×, 1.5×, or 2.0× using `librosa` phase-vocoder — no chipmunk or Darth Vader effects. |
| **AI Filler Removal** *(optional)* | Upload audio to Gemini 2.5 Flash to detect "um", "uh", "like", and long silences, then surgically cut them out. |
| **Video Support** | Accepts `.mp4`, `.mkv`, `.avi`, `.mov`, `.webm` — extracts audio, enhances it, and remuxes back with the video at the correct speed. |
| **Audio Extraction** | Separate and extract audio from video files into standalone audio formats (like MP3, WAV, AAC, FLAC) with custom format prompts. |

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

### 3. Gemini API Key *(only if using `--use-ai`)*
Set your API key as an environment variable:

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

### Interactive Mode
```bash
python enhancer.py
```
The tool will prompt you for the file path and speed selection.

### Command-Line Arguments
```bash
# Basic usage — enhance an audio file at 1.5× speed
python enhancer.py --file podcast.mp3 --speed 1.5

# Enhance a video at 2.0× speed
python enhancer.py --file lecture.mp4 --speed 2.0

# Extract audio from a video and convert to MP3 at 1.5× speed
python enhancer.py --file lecture.mp4 --speed 1.5 --extract-audio --format mp3

# Enable AI filler word and silence removal
python enhancer.py --file interview.mp4 --speed 1.0 --use-ai
```

### All Options
| Flag | Short | Description |
|---|---|---|
| `--file` | `-f` | Path to the source audio or video file |
| `--speed` | `-s` | Playback speed: `1.0`, `1.5`, or `2.0` |
| `--use-ai` | | Enable Gemini AI filler/silence detection |
| `--extract-audio` | `-x` | Extract and enhance audio only from a video file |
| `--format` | `-fmt` | Target output format (e.g. mp3, wav, flac, etc.) |
| `--version` | `-v` | Show version and exit |

---

## Output

The enhanced file is saved in the **current working directory** with an `_enhanced` suffix and the selected format's extension:

```
lecture.mp4  →  lecture_enhanced.mp4  (Enhance Video Mode)
lecture.mp4  →  lecture_enhanced.mp3  (Extract Audio Mode - MP3 format)
podcast.mp3  →  podcast_enhanced.mp3
podcast.wav  →  podcast_enhanced.mp3  (Convert Audio Mode - MP3 format)
```

---

## Supported Formats

| Type | Extensions |
|---|---|
| **Audio** | `.wav`, `.mp3`, `.aac`, `.flac`, `.ogg`, `.m4a`, `.wma`, `.opus` |
| **Video** | `.mp4`, `.mkv`, `.avi`, `.mov`, `.webm`, `.flv`, `.ts` |

---

## How It Works

1. **Extract** — Audio is extracted from the source file (or read directly if audio-only) into a high-quality WAV.
2. **AI Analysis** *(optional)* — Audio is compressed to a tiny MP3, uploaded to Gemini 2.5 Flash, which returns structured JSON timestamps of filler words and silences to cut.
3. **Cut** *(optional)* — An FFmpeg `trim`/`concat` filtergraph surgically removes the detected segments from the track.
4. **Denoise** — Spectral noise gating removes background hiss.
5. **Time-Stretch** — `librosa` phase-vocoder adjusts playback speed without altering pitch.
6. **Assemble** — The enhanced audio is encoded to the target audio format. If the input was a video and we are NOT extracting audio, the enhanced audio is remuxed back into the video container.

---

## License

MIT
