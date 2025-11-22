# YouTube Shorts Downloader

A simple, fast, and high-quality Python script to download YouTube Shorts as HD MP4 files.

## Features

- **HD Quality**: Downloads the best available video and audio quality (MP4).
- **Fast Download**: Optimized for speed using `yt-dlp`.
- **Easy to Use**: Run the script and paste the URL.

## Prerequisites

- Python 3.x installed on your system.
- `ffmpeg` is recommended for merging best video and audio streams (though `yt-dlp` can often handle it, having ffmpeg ensures the best results).

## Installation

1.  Navigate to the project directory:
    ```bash
    cd yt-short-downloader
    ```

2.  Install the required Python packages:
    ```bash
    pip install -r requirements.txt
    ```

## Usage

### Interactive Mode
Run the script and follow the prompt:
```bash
python main.py
```
Enter the YouTube Short URL when asked (e.g., `https://www.youtube.com/shorts/ZWuLWQTPGgs`).

### Command Line Argument
You can also pass the URL directly:
```bash
python main.py "https://www.youtube.com/shorts/ZWuLWQTPGgs"
```

## Output
The video will be saved in the current directory with the video title as the filename.
