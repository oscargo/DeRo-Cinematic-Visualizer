# Export reports, remaining time, and cancellation

Use the buttons in the top progress panel. **View report** opens the latest
completed attempt; **Copy report** copies its summary and JSON. **Save report**
saves JSON to the location you choose. Nothing is automatically uploaded or saved.
The latest report is replaced when a new export starts. Save reports you want to
compare before the next export or application close.

## What the report measures

- Status: success, failed, or canceled; total wall time; failure stage and exception
  type. Raw exception messages and FFmpeg logs are excluded.
- Resolution, FPS, selection length, band/frequency settings, particle workload,
  spectrum style, requested encoder, and actual encoder attempt history.
- Cache reuse or a reason for fresh analysis: no preview cache, changed source,
  changed sample rate/analysis settings, unavailable source, or custom FFmpeg.
- Wall time for environment/version checks, audio decoding, analysis, renderer
  preparation (particles plus background), encoder probe, render/encode phase,
  and final atomic output replacement.
- Per-attempt rendered/written frames, total and slowest frame-render time, time
  spent writing frames to FFmpeg, and final wait after the frame pipe closes.
  Average frame-render time and effective successful-export FPS are included.
- Sampled peak RSS RAM of the application and tracked subprocesses at 250 ms
  intervals, when psutil can read it. These are sampled maxima, not guaranteed
  operating-system peaks. App RAM includes the existing preview, caches, and other
  work in the app. Subprocess RAM includes FFmpeg and environment-check tools;
  GPU VRAM is not measured. The separate maxima need not occur simultaneously.
- App, Python, NumPy, Pillow, FFmpeg, OS/architecture, logical CPU count, and, when
  `nvidia-smi` is available, available NVIDIA GPU names/driver versions. The listed
  devices do not establish which adapter NVENC used on a multi-GPU system.

The report excludes media data, text titles, artist names, filenames, full paths,
project contents, credentials, raw error messages, and raw subprocess logs. Version
and GPU-name metadata comes from local software tools. Encoder failures are stored
as categories, while the app continues showing its normal error messages locally.

## Interpret the numbers carefully

CPU frame rendering and FFmpeg encoding overlap. **Pipe-write time** includes RGB
transfer and time blocked waiting for FFmpeg; it is not an isolated measurement of
GPU/CPU encoder work. **Final wait** covers FFmpeg finishing video/audio encoding
and muxing after input closes. Per-attempt frame-render time includes converting
the PIL image to RGB bytes. Renderer preparation includes trajectory construction
and background preparation; it is not a layer-by-layer particle profile.

The render/encode phase contains its per-attempt timings. Do not add that phase to
its sub-timings. A GPU failure followed by CPU fallback records two attempts and
includes repeated frame rendering in the totals. Effective export FPS uses final
output frames divided by total export duration; frame-render throughput alone is
not the overall export rate. Environment/version queries are included in total
time and each has a short timeout.

High render time suggests CPU visual composition is limiting export. High frame-
feed blocking or final wait suggests FFmpeg/encoding/transfer pressure, but does
not by itself identify a specific hardware bottleneck. Compare the same project,
selection, resolution and FPS using CPU versus NVIDIA modes. GPU utilization,
CPU utilization, VRAM monitoring, a benchmark runner, and per-layer profiling are
not provided by this report.

## Remaining-time estimate

The estimate uses recent frame progress from the export worker, not the GUI's
message-processing delay. It requires enough measurements, resets for a new
encoder attempt, and becomes unknown when measurements are stale. It estimates
remaining frames only; final encoding/audio mux time is explicitly additional.
Once frames are complete it says "finalizing audio/video" instead of claiming
zero seconds remaining. Preparation and fallback time remain in the elapsed timer.

## Cancel and close

Cancel interrupts registered FFmpeg/probe processes, including an export blocked
writing to stdin, and checks cooperatively during FFT and trajectory loops. A
single NumPy/Pillow operation or frame render can finish before the next check.
Cancellation is not a GPU failure and never triggers a CPU retry. Temporary MP4s
are removed; an existing export is preserved if cancellation wins before commit.
The atomic destination replacement and cancellation have a defined ordering: once
replacement has committed, completion is reported as success. A failed/canceled
export has its own report and does not open a video or play a success chime.

Closing during export requests cancellation and waits for cleanup before destroying
the window. Forced termination or a machine crash can still leave temporary files.

## Validation scope

Tests cover real CPU exports, report schema/privacy, cache reasons, unavailable
memory monitoring, cancellation before work and during frame submission, blocked
pipe interruption, registered subprocess cleanup, no CPU retry after cancellation,
atomic commit ordering, and ETA reset/stall/finalization. GUI checks exercised
report viewing/saving and cancellation while preserving an existing output file.
NVIDIA hardware encoding and physical Windows GPU speed remain unverified in the
cloud runtime. Follow the GPU setup guide to confirm NVENC on your machine.
