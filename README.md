# DeRo Cinematic Visualizer v0.1.1 — standalone prototype

A standalone, reusable Python 3.12 music visualizer. It renders cinematic floating dust (irregular flecks and small streaks) and a bottom-center **horizontally mirrored** fine-band spectrum. Defaults: 75% independently drifting particles, 25% mildly music-reactive. Output MP4 includes original music.

## Setup (Windows)
1. Ensure **Python 3.12** and **FFmpeg** are installed. Put `C:\FFmpeg\bin` on PATH or otherwise make `ffmpeg` available.
2. Keep all files together and double-click **Launch_DeRo_Visualizer.bat**. It checks and installs `numpy` and `Pillow` if needed.
3. Choose a music file (MP3, WAV, FLAC, M4A, etc). You may choose a JPG/PNG background, or leave blank for the dark navy gradient.
4. Adjust title, number of dust particles, reactive %, and sensitivity. Click **Refresh Preview** after changing settings, and **Export MP4** when ready.
5. Defaults: 1920×1080 / 60 FPS. 30 FPS and smaller resolutions are selectable.

**Important limitations of v0.1.1:**
- The animation preview is **silent**. It is not synchronized audio monitoring; exported MP4 *does* include music.
- Background supports **still images or built-in navy gradient only**, not background video yet. Adding video compositing later should preserve the renderer API.
- MP4 encoding uses CPU libx264, not GPU NVENC. Full-length 1080p60 can be slow.
- The exported visualization is a best-effort aesthetic interpretation, **not a pixel-perfect recreation of the reference clip**.
- The audio features are precomputed; long songs require memory and initial analysis time. Export re-analyzes at selected FPS and resolution.

## DeRo Sync / Karaoke Maker Lite integration
Do **not** copy GUI code into DeRo Sync. Import `visualizer_core.Settings`, `visualizer_core.Renderer`, and `visualizer_core.audio_features`, then use the current Karaoke Maker Lite audio samples / synchronized timeline to render frames:

```python
from visualizer_core import Settings, Renderer, audio_features
settings = Settings(width=1920, height=1080, fps=60)
features = audio_features(vocals_or_mix_mono, sample_rate, settings.fps, settings.bars)
visualizer = Renderer(settings, features)
frame_rgb = visualizer.render(time_seconds)  # PIL RGB Image; deterministic at timestamp
```

Call `render(time_seconds)` using the **same absolute music time** that your lyric overlays use, including any render-range offset; render/compose this image before overlaying lyrics. Keep lyrics timing authoritative. The renderer does not mutate song, sync, or lyric data. For background video, composite a frame from the host editor with alpha-mode layers in a later adapter; current renderer returns a full RGB frame. Preserve Studio and Lite stable exports and implement integration as a separately testable phase.

Core module imports only numpy and Pillow; no Tkinter, sound-device, Qt, or FFmpeg dependency. Exporter handles FFmpeg separately. This separation is intentional.

## v0.1.1 changes
- Reorganized the controls like the supplied screenshot: music/background browse on left, title/dust/reactivity/sensitivity and export controls on right; transport and export progress above the image preview.
- Spectrum widened from 23% to 62% of output width, centered in the same bottom area.
- Spectrum band options: 32, 64, 96, 128, 192, 256, 384, 512. Default 384 (4x original 96). Mirrored symmetrically left/right.
- Faster vectorized per-frame band extraction; preview and export both receive the selected count.
- Launcher automatically discovers C:\FFmpeg\bin without manual PATH editing.

Note: band-count changes take effect upon Refresh Preview or the next export. The preview is silent (unchanged from v0.1.0).


### v0.1.2 — Export convenience
- After a successful MP4 export, the app automatically opens the resulting file with the operating system's default video player.
- **Open Export Folder** sits alongside **Export MP4** and opens the containing directory, highlighting the last exported MP4 on Windows.
- The last export folder is tracked during the current app session. No video is launched on export failure.

## v0.1.3 particle movement
Particles drift outward, with beat impulses affecting only the reactive group. Once off-screen, they stay gone for that render; no bounce/wrap/re-entry. The random seed makes export deterministic without looping particle patterns. For a long song, the number of visible flecks will naturally diminish.

## Folder memory (v0.1.4)
Music and Background Browse each remember the last folder chosen, even after closing and reopening the program. Stored separately under `%APPDATA%\DeRo_Cinematic_Visualizer\folders.json`.

### v0.1.5 export folder memory
The Export MP4 save dialog remembers the last chosen output folder, independently of the music and background file pickers. Open Export Folder uses that same folder after app restarts. Settings are under `%APPDATA%\DeRo_Cinematic_Visualizer\folders.json`.

## Quick test exports
After loading music, drag the yellow selection handles or enter Start / End in seconds.
Use **Start at playhead** and **End at playhead** to mark the current preview position.
**Full Song** resets the range. **Play Selection**, **Pause**, **Loop Selection**, and
**Play from Start** let you check the timing (preview remains silent).
**Export MP4** exports only the selected range, including matching trimmed audio.
Choose 854 × 480 / 30 FPS for faster test renders. Export progress counts only selected frames.
Visuals retain the original song timestamps, so clips match the full-song animation.
Audio analysis still covers the full song to preserve spectrum scaling and particle trajectories.
