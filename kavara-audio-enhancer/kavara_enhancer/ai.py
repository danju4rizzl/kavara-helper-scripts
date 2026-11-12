"""Gemini transcribe engine: parallel chunked word-timed transcription for smart cuts and subtitles."""

from __future__ import annotations

import concurrent.futures
import math
import os
import time

from .constants import (
    CHUNK_DURATION_SECONDS, DEFAULT_MAX_WORKERS,
    STYLE_DIM, STYLE_RESET, STYLE_SUCCESS, STYLE_WARNING,
    SUBTITLE_BREAK_GAP_SECONDS, SUBTITLE_MAX_SECONDS, SUBTITLE_MAX_WORDS,
)
from .disfluency import find_disfluency_cuts
from .gemini_config import active_model, gemini_label
from .models import CutSegment, SubtitleEntry, TimedWord
from .system import get_audio_duration, run_ffmpeg
from .ui import format_duration


def create_analysis_payload(input_wav: str, temp_dir: str, filename_prefix: str = "analysis_payload") -> str:
    """Compress the WAV down to a small 64 kbps MP3 for fast upload to Gemini."""
    mp3_path = os.path.join(temp_dir, f"{filename_prefix}.mp3")
    run_ffmpeg(
        ["-i", input_wav, "-b:a", "64k", "-ar", "16000", "-ac", "1", mp3_path],
        description="analysis payload compression",
    )
    return mp3_path


def split_audio_into_chunks(
    mp3_path: str,
    temp_dir: str,
    chunk_duration_seconds: float = CHUNK_DURATION_SECONDS,
) -> list[tuple[str, float, float]]:
    """Split an MP3 into temporal chunks for reliable and fast parallel AI analysis."""
    total_duration = get_audio_duration(mp3_path)
    if total_duration <= chunk_duration_seconds:
        return [(mp3_path, 0.0, total_duration)]

    chunks: list[tuple[str, float, float]] = []
    num_chunks = math.ceil(total_duration / chunk_duration_seconds)
    chunks_dir = os.path.join(temp_dir, "ai_chunks")
    os.makedirs(chunks_dir, exist_ok=True)

    for i in range(num_chunks):
        start_time = i * chunk_duration_seconds
        remaining = total_duration - start_time
        duration = min(chunk_duration_seconds, remaining)
        if duration <= 0.5:
            break
        chunk_file = os.path.join(chunks_dir, f"chunk_{i:03d}.mp3")
        run_ffmpeg(
            ["-ss", f"{start_time:.3f}", "-i", mp3_path, "-t", f"{duration:.3f}",
             "-c:a", "libmp3lame", "-b:a", "64k", "-ar", "16000", "-ac", "1", chunk_file],
            description=f"audio chunk extraction [{i+1}/{num_chunks}]",
        )
        chunks.append((chunk_file, start_time, duration))

    return chunks or [(mp3_path, 0.0, total_duration)]


def _parse_offset(value) -> float | None:
    """Parse a protobuf-style duration ("1.250s"), a number, or a numeric string into seconds."""
    if value is None:
        return None
    try:
        return float(str(value).strip().rstrip("sS"))
    except ValueError:
        return None


def extract_words(response, offset_seconds: float = 0.0, duration_seconds: float | None = None) -> list[TimedWord]:
    """Pull word-timed text out of a transcribe response, shifted to absolute time."""
    words: list[TimedWord] = []
    for candidate in getattr(response, "candidates", None) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or []:
            transcription = getattr(part, "audio_transcription", None)
            for info in getattr(transcription, "words", None) or []:
                text = (info.word or "").strip()
                start = _parse_offset(info.start_offset)
                end = _parse_offset(info.end_offset)
                if not text or start is None or end is None or end < start:
                    continue
                if duration_seconds is not None and start >= duration_seconds:
                    continue  # model hallucinated a timestamp beyond this chunk
                words.append(TimedWord(text, round(start + offset_seconds, 3), round(end + offset_seconds, 3)))
    return words


RETRY_DELAYS_SECONDS = (20, 40, 70, 100)  # backoff for rate limits / overload


def _is_retryable(exc: Exception) -> bool:
    return getattr(exc, "code", None) in (429, 500, 503, 504)


def _with_retries(call, label: str, delays=RETRY_DELAYS_SECONDS):
    """Run ``call()``, retrying transient API errors (rate limits, overload) with backoff."""
    for attempt, delay in enumerate((*delays, None)):
        try:
            return call()
        except Exception as exc:
            if delay is None or not _is_retryable(exc):
                raise
            print(f"    {STYLE_WARNING}[!] {label}: {getattr(exc, 'code', 'error')} - retrying in {delay}s "
                  f"({attempt + 1}/{len(delays)}){STYLE_RESET}")
            time.sleep(delay)


def _transcribe_chunk(
    client,
    model_name: str,
    chunk_index: int,
    total_chunks: int,
    chunk_path: str,
    offset_seconds: float,
    duration_seconds: float,
    purpose: str,
) -> tuple[int, list[TimedWord]]:
    """Worker: transcribe one audio chunk verbatim with word-level timestamps."""
    start_str = format_duration(offset_seconds)
    end_str = format_duration(offset_seconds + duration_seconds)
    chunk_label = f"[{chunk_index}/{total_chunks}]" if total_chunks > 1 else ""
    print(f"    {STYLE_DIM}>> Transcribing {purpose} chunk {chunk_label} ({start_str} - {end_str}) with {gemini_label()}...{STYLE_RESET}")

    from google.genai import types

    uploaded_file = client.files.upload(file=chunk_path)
    try:
        response = _with_retries(lambda: client.models.generate_content(
            model=model_name,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_uri(
                            file_uri=uploaded_file.uri,
                            mime_type=uploaded_file.mime_type or "audio/mp3",
                        ),
                    ],
                )
            ],
            config=types.GenerateContentConfig(
                # VERBATIM keeps fillers and repeats (SMART strips them and has no timestamps).
                audio_transcription_config=types.AudioTranscriptionConfig(
                    mode="VERBATIM",
                    word_timestamp=True,
                ),
            ),
        ), f"chunk {chunk_label or '[1/1]'}")
        words = extract_words(response, offset_seconds, duration_seconds)
        if total_chunks > 1:
            print(f"    {STYLE_SUCCESS}[OK] Chunk {chunk_label} transcribed ({len(words)} words).{STYLE_RESET}")
        return chunk_index, words
    finally:
        try:
            client.files.delete(name=uploaded_file.name)
        except Exception:
            pass


def transcribe_words(
    mp3_path: str,
    temp_dir: str,
    max_workers: int = DEFAULT_MAX_WORKERS,
    purpose: str = "audio",
) -> list[TimedWord]:
    """Transcribe audio in parallel chunks; returns word timings in chronological order."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY environment variable is not set.")

    from google import genai

    from google.genai import types as genai_types

    # audio_transcription_config is only accepted by the v1beta endpoint.
    client = genai.Client(api_key=api_key, http_options=genai_types.HttpOptions(api_version="v1beta"))
    model_name = active_model()

    chunks = split_audio_into_chunks(mp3_path, temp_dir)
    total_chunks = len(chunks)

    if total_chunks == 1:
        path, offset, duration = chunks[0]
        return _transcribe_chunk(client, model_name, 1, 1, path, offset, duration, purpose)[1]

    worker_count = min(total_chunks, max_workers)
    print(f"    {STYLE_DIM}>> Dispatching {total_chunks} chunks across {worker_count} parallel threads with {gemini_label()}...{STYLE_RESET}")

    results: dict[int, list[TimedWord]] = {}
    failures: list[Exception] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_to_index = {
            executor.submit(_transcribe_chunk, client, model_name, index, total_chunks,
                            path, offset, duration, purpose): index
            for index, (path, offset, duration) in enumerate(chunks, start=1)
        }
        for future in concurrent.futures.as_completed(future_to_index):
            index = future_to_index[future]
            try:
                _, words = future.result()
                results[index] = words
            except Exception as exc:
                print(f"    {STYLE_WARNING}[!] Chunk [{index}/{total_chunks}] failed: {exc}{STYLE_RESET}")
                failures.append(exc)
                results[index] = []

    if len(failures) == total_chunks:
        raise RuntimeError(f"all {total_chunks} transcription chunks failed (first error: {failures[0]})")
    if failures:
        print(f"    {STYLE_WARNING}[!] {len(failures)}/{total_chunks} chunks failed; those sections were NOT analyzed.{STYLE_RESET}")

    return [w for i in range(1, total_chunks + 1) for w in results.get(i, [])]


def analyze_audio_with_gemini(
    mp3_path: str,
    temp_dir: str,
    max_workers: int = DEFAULT_MAX_WORKERS,
    fillers_only: bool = False,
) -> list[CutSegment]:
    """Transcribe with word timings, then cut filler words and restarted/repeated phrases.

    Silence is detected locally elsewhere. ``fillers_only`` is kept for backward
    compatibility and has no effect: disfluency detection is always applied.
    """
    words = transcribe_words(mp3_path, temp_dir, max_workers, purpose="smart cuts")
    return find_disfluency_cuts(words)


def build_subtitles_from_words(words: list[TimedWord]) -> list[SubtitleEntry]:
    """Group word timings into readable subtitle lines."""
    entries: list[SubtitleEntry] = []
    line: list[TimedWord] = []

    def flush() -> None:
        if line:
            entries.append(SubtitleEntry(
                index=len(entries) + 1,
                start_time=line[0].start_time,
                end_time=line[-1].end_time,
                text=" ".join(w.text for w in line),
            ))
            line.clear()

    for word in words:
        if line:
            gap = word.start_time - line[-1].end_time
            too_long = (
                len(line) >= SUBTITLE_MAX_WORDS
                or word.end_time - line[0].start_time > SUBTITLE_MAX_SECONDS
            )
            if too_long or gap > SUBTITLE_BREAK_GAP_SECONDS:
                flush()
        line.append(word)
        if word.text.endswith((".", "?", "!")) and len(line) >= 3:
            flush()
    flush()
    return entries


def generate_subtitles_with_gemini(
    mp3_path: str,
    temp_dir: str,
    max_workers: int = DEFAULT_MAX_WORKERS,
) -> list[SubtitleEntry]:
    """Transcribe audio in parallel chunks and build synchronized subtitle lines."""
    words = transcribe_words(mp3_path, temp_dir, max_workers, purpose="subtitles")
    return build_subtitles_from_words(words)
