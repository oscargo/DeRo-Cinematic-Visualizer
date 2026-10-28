# DeRo Cinematic Visualizer v0.1.15 — Sound, Peaks & Alerts

A standalone, reusable Python 3.12 music visualizer. It renders cinematic floating dust (irregular flecks and small streaks) and a bottom-center **horizontally mirrored** fine-band spectrum. Defaults: 75% independently drifting particles, 25% mildly music-reactive. Output MP4 includes original music.

## Setup (Windows)
1. Ensure **Python 3.12** and **FFmpeg** are installed. Put `C:\FFmpeg\bin` on PATH or otherwise make `ffmpeg` available.
2. Keep all files together and double-click **Launch_DeRo_Visualizer.bat**. It checks and installs `numpy` and `Pillow` if needed.
3. Choose a music file (MP3, WAV, FLAC, M4A, etc). You may choose a JPG/PNG background, or leave blank for the dark navy gradient.
4. Adjust title, number of dust particles, reactive %, and sensitivity. Click **Refresh Preview** after changing settings, and **Export MP4** when ready.
5. Defaults: 1920×1080 / 60 FPS. 30 FPS and smaller resolutions are selectable.

**Current limitations:**
- Preview sound is optional: use **Sound on** beside the playback timeline. MP4 exports include music regardless of this preview toggle.
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

## v0.1.6 — Quick Export Selection
After loading music, drag the yellow selection handles or enter Start / End in seconds.
Use **Start at playhead** and **End at playhead** to mark the current preview position.
**Full Song** resets the range. **Play Selection**, **Pause**, **Loop Selection**, and
**Play from Start** let you check the timing (preview remains silent).
**Export MP4** exports only the selected range, including matching trimmed audio.
Choose 854 × 480 / 30 FPS for faster test renders. Export progress counts only selected frames.
Visuals retain the original song timestamps, so clips match the full-song animation.
Audio analysis still covers the full song to preserve spectrum scaling and particle trajectories.

## Version and package naming
Continue the existing `v0.1.x` sequence; the next incremental update is `v0.1.16`.
Each update has a short descriptive name in the app title, README, and changelog.
Git tags use `vMAJOR.MINOR.PATCH`. Distribution ZIPs and their single top-level
folder use `DeRo_Cinematic_Visualizer_vMAJOR_MINOR_PATCH_Feature_Name`.
This release: `DeRo_Cinematic_Visualizer_v0_1_15_Sound_Peaks_and_Alerts.zip`.

## v0.1.7 — Midnight Studio
A dark studio interface with an organized composition sidebar, blue accents,
clear section headings, and a preview that scales with your window.
The sidebar scrolls on smaller screens. Select **Quick test / 480p / 30 FPS**
to configure a faster test export, then set your range and click **Export MP4**.
All selection controls, folder memory, and audio exports remain available.

## v0.1.8 — Creative Projects
Use the **File** menu for **New project** (Ctrl+N), **Open project** (Ctrl+O),
**Save project** (Ctrl+S), and **Save project as** (Ctrl+Shift+S).
A new project clears media and restores every composition/output setting to defaults.
The app asks whether to save unsaved changes before New, Open, or closing.
Projects use `.dero` JSON files and retain all composition settings and the export range.
Music and background files are referenced using paths relative to the project when possible;
keep those media files with the project when moving it to another computer. Missing media
can be replaced using the sidebar. Projects do not embed music, images, or exports.

**Title & layout** includes Sans/Serif/Mono, bold, italic, uppercase, size, color,
and independent X/Y position. Size is a percentage of frame height; positions are
percentages of frame width/height with (0,0) at the top left. The title position is
its center. Use the `<`, `^`, `v`, `>` buttons to move it by 1% per click.

The spectrum now defaults to **82% width**. Set width (10–100%), height, and X/Y
position, or use **Narrower / Wider** (2% per click) and the position arrows.
Spectrum Y sets its baseline. Title and spectrum move independently; Reset buttons
restore their default layouts. Edge positions can intentionally crop a title or spectrum.
Layout and title edits appear immediately in an analyzed preview and are used in MP4/PNG exports.
Refresh Preview after changing music analysis settings such as FPS or spectrum band count.

## v0.1.9 — Studio Workflow
A more accessible studio workspace with prominent media controls, flexible panel sizing,
and direct timeline navigation. **Choose music** is teal and **Choose background** is
lavender. **New, Open, Save, Save As** are always available at the top right.

Resize or maximize the main window and drag the divider between the settings sidebar
and preview to adjust panel widths. The minimum window size is 1040 × 820 to keep
the controls usable. The sidebar has a wider, high-contrast scrollbar with a visible
grip, hover feedback, and mouse-wheel scrolling.

Click anywhere on the playback timeline to seek to that position and start playback;
drag to continuously reposition. This leaves selection-loop mode and plays from the
clicked position to the song end without altering the export range. Preview playback
remains silent; the exported video contains music.

## v0.1.10 — Song & Artist
The first text row is the song name; the second is the artist name. Each row has
independent typeface, size, bold/italic, capitalization, color, and position controls,
including position arrows. Both are retained in `.dero` projects. Existing project
settings remain intact; older projects receive a blank artist row.

Choosing a music file reads its title and artist tags through **ffprobe** (normally
included beside FFmpeg). It reads no album or other fields. Missing titles fall back
to the audio filename; missing artists remain blank. If ffprobe is unavailable,
manual entry still works. Edit either name freely after loading. Opening a saved
project preserves those edits and does not overwrite them with metadata.

New project saves, Save As, MP4 exports, and PNG saves suggest **Artist - Song**.
If one name is blank, only the available name is used; both blank gives Untitled.
Windows-forbidden filename characters are replaced safely. Save continues writing
to the current project path; use Save As to rename it after editing names.

## v0.1.11 — Preview Workspace
Rearranged the workspace to match the supplied layout: export status and progress
are at the top, and Export MP4 sits beside the export range fields. The separate
bottom status/export panel has been removed so the preview expands into that space.
All project settings, spectrum bands, title/artist controls, and export behavior are retained.

## v0.1.12 — Project Identity
The current project name is shown beneath the app name in the upper-left header.
Saved projects show the filename without `.dero`; unsaved projects show Artist - Song
when available, otherwise Untitled project. The label updates on New, Open, Save,
and Save As. Long names wrap within the header. No composition settings are changed.

## v0.1.13 — Export Access
Moved **Open export folder** from the sidebar to the export range controls,
immediately left of **Export MP4**, matching the supplied screenshot.

## v0.1.14 — Particle Motion
**Atmosphere → Particle speed (x)** adjusts all particle movement from 0.1× to 5×.
1× preserves previous behavior, 2× doubles the speed, and 3× triples it.
Changes update the analyzed preview and are saved in projects. Faster particles
leave the frame sooner; particles still do not wrap or recycle.

The distributable is now committed under `releases/` with its full descriptive
filename and a single matching folder inside. Use the named package below instead
of GitHub's automatic source archive. Project, video, and PNG filenames still
default to Artist - Song.

[Download DeRo_Cinematic_Visualizer_v0_1_14_Particle_Motion.zip](https://github.com/oscargo/DeRo-Cinematic-Visualizer/raw/refs/heads/main/releases/DeRo_Cinematic_Visualizer_v0_1_14_Particle_Motion.zip)

## Version folders on GitHub
Every released version from v0.1.6 onward has its own descriptively named folder
at the repository root, following the same convention as Voice FX Studio.
Older tagged releases are preserved as snapshots; the newest folder is
**DeRo_Cinematic_Visualizer_v0_1_15_Sound_Peaks_and_Alerts**. Open that folder and run
`Launch_DeRo_Visualizer.bat`, or download its matching ZIP from `releases/`.
The app files at the repository root remain available for the existing development workflow.

## v0.1.15 — Sound Preview
Preview music now plays in stereo. Use **Sound on** beside the playback timeline to
toggle sound without stopping or restarting playback. Sound is on by default and
the toggle is saved with each project. Seeking, selection playback, looping, Pause,
and Play from Start control both audio and visuals. Playback follows the audio device
clock when sound is active. Muting preview does not remove audio from exported MP4s.

Run `Launch_DeRo_Visualizer.bat` after extracting the complete folder. It installs
`sounddevice` when needed; Windows wheels include PortAudio. Linux users also need
the system PortAudio library (for example, `libportaudio2` on Debian/Ubuntu).
If no output device is available, the app reports the problem and permits visual-only
playback. Sound tests exercised audio callbacks and desktop controls; physical
speaker playback was not verified in the cloud environment.

[Download DeRo_Cinematic_Visualizer_v0_1_15_Sound_Peaks_and_Alerts.zip](https://github.com/oscargo/DeRo-Cinematic-Visualizer/raw/refs/heads/main/releases/DeRo_Cinematic_Visualizer_v0_1_15_Sound_Peaks_and_Alerts.zip)

### Natural peaks and independent spectrum sensitivity
Removed the old percentile ceiling that flattened strong spectrum peaks. Analysis
now scales against the actual song-wide maximum with headroom, preserving peak
differences. Click Refresh Preview after upgrading to reanalyze the song, then
export again; existing rendered videos are not altered.

Under **Spectrum**, set **Spectrum sensitivity (x)** from 0.1 to 3.0.
**Lower = 0.5**, **Normal = 1.0**, **Higher = 1.5**. Lower settings give shorter bars.
This updates the preview immediately and is independent of Particle response.
Older projects inherit their previous sensitivity value for spectrum response.

### Export completion notification
Successful exports show a green **Export complete** heading and the output filename
in the top notification area, with a gentle completion tone. Windows uses the
system Asterisk sound asynchronously. **Export completion tone** in Output toggles
this independently of preview sound. Failed exports never play the success tone.
The notification does not change your existing automatic-open behavior.
