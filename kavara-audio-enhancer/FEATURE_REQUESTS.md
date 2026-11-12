# Feature Requests & Roadmap - Kavara Audio Enhancer

Parked ideas and planned work for automating video editing, so we do not have to edit by hand.
Each entry has a status, the reason it matters, an approach, and open questions.
Rules in `AGENTS.md` still apply to every item here (output in `enhanced_files/`, transcribe once,
pipeline order, measure before changing audio/video stages, tests never call real Gemini).

**Status key:** `Done` | `Next` | `Planned` | `Idea` (needs design) | `Rejected` (with reason)

## Context

- **Targets:** YouTube long-form and Shorts/Reels/TikTok. We want to pick the target per run.
- **Content:** mostly **screen recordings**, less talking head. Zoom/framing logic must follow the
  cursor and clicks, not faces.
- **Style:** one fixed house style for now; selectable presets later.
- **Engine:** FFmpeg-only unless a feature clearly needs more (see the Remotion decision below).

## Pipeline fit (for every visual feature)

Visual effects depend on the edited timeline, so they run **after cuts and speed**, with times
re-mapped like subtitles (`timeline.remap_words`), and are drawn **in the same final FFmpeg
encode pass**. The final video re-encode is about 75% of a video job, so avoid adding a second encode.

---

## Done

### 1. Burned-in captions - `--burn-captions`
- **Status:** Done (not yet tried on a real recording).
- Short 2-7 word chunks, white bold text on a dark box, sized to the video. Portrait videos get
  narrower lines and a higher position (clear of the Shorts/Reels UI).
- On by default in the **Balanced** preset (opt out with `--no-burn-captions`); asked in the Custom wizard for video output.
- Code: `kavara_enhancer/captions.py`, drawn via the `ass` filter in `assembly.py`.
- **Follow-ups:**
  - Tune size/position on real screen recordings (e.g. taskbar at the bottom).
  - Active-word highlight (karaoke style) for the `punchy`/`shorts` presets.
  - Selectable font and colors (house font is Arial for now).

## Next

### 2. Auto zoom in/out (screen-recording aware)
- **Status:** Next.
- **Why:** screen recordings are static; zooming on what matters keeps viewers oriented and hides jump cuts.
- **Triggers to consider:**
  - Punch-in just after a jump cut (hides the cut; needs no AI).
  - Zoom on the **cursor / click location** for UI steps. Needs a cursor source - see open questions.
  - Slow push or alternating zoom to avoid a dead static shot.
- **Approach:** FFmpeg `crop` + `scale` with eased expressions (or `zoompan`, which can jitter on video).
  Zoom keyframes are computed locally from the cut list and cursor data, never decided by the model.
- **Open questions:**
  - How do we get the cursor position? Options: (a) record it alongside the screen recording (OBS plugin /
    a small logger script), (b) detect it from frames (template matching), (c) skip cursor tracking and
    use cut-point punch-ins only.
  - Max zoom level, ease duration, and how often is too often.
  - Interaction with captions (keep them readable and unzoomed - burn them after the zoom).

## Planned

### 3. Animated overlays
- **Status:** Planned.
- Keyword callouts, text pop-ups, lower thirds, progress bar, intro/outro cards.
- **Approach:** start with FFmpeg `drawtext`/`overlay`. Use Remotion only if the look needs it (see decision below).
- **Open questions:** which words deserve a callout? A local heuristic first (emphasis, numbers, product names).
  Asking Gemini would be a second model call and needs an explicit exception to "transcribe once".

### 4. Platform targets and 9:16 reframing
- **Status:** Planned.
- **Why:** picking "YouTube long-form vs Shorts/Reels/TikTok" per run (e.g. `--target youtube|shorts`).
- **Approach:** for screen recordings, a 9:16 crop that **follows the cursor / active region** (not faces).
  Talking-head clips could use face tracking (MediaPipe/OpenCV) later.
- **Open questions:** cap length for Shorts? Split long videos into several clips? Letterbox with a blurred
  background instead of cropping when the screen is wide?

### 5. Style presets
- **Status:** Planned (after the house style settles).
- Bundle captions, zoom and overlay settings into named presets, e.g. `clean`, `punchy`, `shorts`,
  with individual overrides. Avoid a pile of separate flags. Existing audio presets live in `presets.py`.

### 5b. Auto-blur sensitive info
- **Status:** Planned.
- **Why:** screen recordings often show API keys, `.env` contents, emails and tokens. Blurring by hand is
  slow and one missed frame leaks a secret.
- **Approach:** find sensitive text locally, then blur those regions with FFmpeg (`boxblur` or `delogo`
  over a time-limited `enable='between(t,a,b)'` expression) in the same final encode pass.
  - Detection: OCR sampled frames (e.g. Tesseract or EasyOCR) and match patterns (key prefixes like `AIza`,
    `sk-`, long random strings, emails, `.env` lines). Frames are never sent to an external service.
  - Also let the user list manual regions/time ranges (`--blur "00:12-00:30 x,y,w,h"`) as a fallback.
  - Optional: flag the matching spoken words in the transcript (someone reading a key aloud) so the audio can be muted.
- **Safety rules:** err on over-blurring; never write detected secrets to logs or the transcript; run a
  verification pass that re-OCRs the output and warns if anything still reads as a secret.
- **Open questions:** OCR dependency size and speed on a 10-min 1080p video (sample every N frames and
  track regions between samples); how to track a region that scrolls or moves; per-run opt-in vs on by default.

## Ideas (need design)

- **Sound effects:** subtle whoosh on zooms/transitions.
- **B-roll / stock inserts** triggered by keywords. High effort, high risk of looking cheesy.
- **Chapters:** auto chapter markers / YouTube description from the transcript.
- **Title / thumbnail suggestions** from the transcript.

## Decisions and rejected options

### Remotion - rejected for now (FFmpeg-only)
- Needs Node plus a headless-Chrome render, and **re-renders the whole video**, which is slower than the
  FFmpeg pass we already run.
- It only pays off for **rich animated overlays**: animated callouts, lower thirds, branded intros (item 3).
- Even then, Remotion can render **just the overlay** (transparent video/PNG sequence) and FFmpeg composites it.
- **Revisit when:** FFmpeg `drawtext`/`overlay` cannot produce the motion graphics we want.

### Select-based video cut graph - rejected
- Already covered in `AGENTS.md`: keep `trim` + `concat`.

## How to add a request

Copy this block under the right heading:

```
### N. Feature name
- **Status:** Idea | Planned | Next
- **Why:** the problem it solves
- **Approach:** how it fits the pipeline (and why it does not add a second encode / model call)
- **Open questions:** what we must decide first
```
