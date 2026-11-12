# AGENTS.md - Kavara Audio Enhancer

Rules for any AI agent (or human) changing this project. Each rule says **why**, so you can judge edge cases.
Guardrail tests in `tests/test_guardrails.py` enforce the most important ones - if one fails, read the rule before "fixing" the test.

## Output
- **All output goes in `enhanced_files/`** (relative to the current directory, created automatically). This includes the enhanced media and the `.srt`/`.vtt`/transcript files, which follow the output file. `--output` may override it; nothing else may change the default. Never write results next to the source file or into the project root.
- The `enhanced_files/` folder is gitignored; never commit media or generated output.

## AI model (Gemini)
- Use **`gemini-3.5-transcribe`** in **`VERBATIM`** mode with `word_timestamp=True`. `SMART` mode strips fillers but returns **no timestamps**, which cuts need.
- The client **must pin `api_version="v1beta"`**. On the default endpoint the API rejects `audio_transcription_config` (400 INVALID_ARGUMENT). Needs `google-genai>=3.0`.
- **Gemini only transcribes.** Filler / repeat / restart detection is local code in `disfluency.py`; silence detection is local FFmpeg. Do not ask the model to decide cuts.
- **Transcribe once.** One transcript of the *original* audio is shared by cuts and subtitles (`ensure_transcript`). Subtitle times are re-mapped onto the edited output (`timeline.remap_words`: removed cuts, then speed). Never add a second upload/transcription; a failed transcript must not be retried for subtitles. Reason: cost, and the two used to disagree.
- Retry 429/5xx with backoff. **Never report success when every chunk failed** (it once printed "0 fillers found" while all calls were failing). Degrading to silence-only cuts is fine only with a visible warning.

## Pipeline order (do not reorder)
extract -> transcribe + detect cuts (raw audio) -> apply cuts -> denoise -> speed -> loudnorm -> build subtitles -> assemble.
Cut timestamps refer to the original recording, so nothing that changes length may run before cuts are applied.

## Audio quality (measured, not guessed)
- **Default denoise is 40%.** At 80% spectral gating removed ~12 dB of the 3-12 kHz consonant range, making speech muffled (worse when sped up). Do not raise the default above 50%. Order of denoise vs speed made no difference; strength did.
- **Speed uses Rubber Band** (`rubberband=tempo=X:transients=mixed:window=short`), falling back to `atempo` when the FFmpeg build lacks it. Pitch must stay unchanged.
- Before changing any audio stage, measure band levels (e.g. 1-3k / 3-6k / 6-12 kHz vs 100-1k Hz) on a real speech clip before and after, and report the numbers.

## Performance (measured on a 10-min 1080p recording)
- The **final video re-encode dominates** a video job (about 75% of the time). x264 preset is `veryfast` (`VIDEO_X264_PRESET`): 104 s vs 239 s for `medium`, with a slightly smaller file at CRF 18. Do not go back to a slower preset without re-measuring; audio stages together take only ~36 s per 10 min of audio.
- Keep the video cut graph on `trim` + `concat` (a `select` expression is ~14% faster but riskier for A/V sync, and long expressions overflow FFmpeg's parser unless balanced). No GPU encoder is assumed available.

## Setups (presets)
- Three setups live in `presets.py`: **Balanced** (recommended, default choice in the wizard), **Fast**, **Custom** (= the classic per-option wizard/flags; also the behaviour whenever flags are given without `--preset`).
- Precedence for every option: **explicit flag > preset > wizard prompt/default**. A preset never decides speed, file or format.
- Preset values come from measurements (10-min 1080p clip): veryfast CRF18 82 s / 27.6 MB, veryfast CRF23 78 s / 22.6 MB, ultrafast CRF23 55 s / 46.5 MB. Re-measure before changing them; update README and `tests/test_presets.py` together.

## Cut safety (never delete real content)
- Restart rule: only a single unfinished sentence (no full stop inside), under 12 s, sharing a 3+ word opener. Asides between similar sentences must survive. A past version deleted a 27 s and an 8 s stretch of real content.
- Keep `MAX_CUT_FRACTION` (cuts removing >80% of a file are discarded as unreliable) and the repeat-gap limit (a long pause between identical phrases is deliberate).

## Secrets and tests
- The key lives in `.env` (gitignored). Never commit it, print it, or send it anywhere. `.env.example` is the template.
- Tests must never call the real Gemini API; mock the boundary (`pipeline.transcribe_words`).

## Roadmap
- Planned and parked features (auto zoom, overlays, 9:16 reframing, auto-blur, presets) and rejected options live in [FEATURE_REQUESTS.md](FEATURE_REQUESTS.md). Check it before starting a new feature, and add new ideas there instead of leaving them in chat.
- Visual effects run after cuts and speed, in the same final encode pass (no second video encode).

## Working here
- Windows + PowerShell/Git Bash; venv at `.venv`. Run `.venv/Scripts/python -m pytest` before every commit.
- Commit and push only when the user asks. Stage only this folder (`git add -- .` from here): the repo root contains other projects and unrelated changes.
- Writing files from scripts on Windows: pass `encoding="utf-8"` (a default-encoding write once corrupted a module).
