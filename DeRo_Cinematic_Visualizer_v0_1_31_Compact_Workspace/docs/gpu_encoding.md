# NVIDIA GPU encoding on Windows

1. Extract the complete release ZIP to a new folder. Keep the new `video_encoder.py`
   with the other app files.
2. Install a current NVIDIA driver supporting your GPU. Use an FFmpeg build with
   `h264_nvenc`; the existing launcher finds FFmpeg in `C:\FFmpeg\bin`, the app's
   supported tools folders, or PATH. Python dependencies are unchanged.
3. Run the launcher. In Output, choose Auto (GPU if available) or NVIDIA NVENC.
4. Export a short selection first. The app performs a one-frame NVENC test at the
   chosen output dimensions/FPS on the export worker. Output must show
   **NVIDIA NVENC (GPU encoding)** to confirm that path is being used.
5. In Windows Task Manager, view the NVIDIA GPU's **Video Encode** graph during
   export. The default 3D graph is not a reliable indicator of NVENC use.

If Output says CPU fallback, its first FFmpeg error line helps distinguish a
missing encoder, driver load failure, unsupported GPU, or unsupported output.
Check `ffmpeg -hide_banner -encoders` for `h264_nvenc` and `nvidia-smi` for your
GPU/driver; listing the codec alone does not prove encoding will work. Use the
same FFmpeg installation selected by the launcher when diagnosing. Update the
GPU driver or choose an NVENC-enabled FFmpeg build from a provider linked by
ffmpeg.org. The app does not download drivers or disable verification.

## Behavior and quality

Auto and NVIDIA modes use H.264 NVENC with preset p4, HQ tuning, VBR and CQ 20.
CPU mode retains libx264 veryfast/CRF 20. These quality scales are not equivalent;
GPU output need not be byte-identical to CPU output. Both use yuv420p, AAC audio,
and the same render timestamps and selection offset. Other GPU brands are not
supported by this encoder choice.

If the probe fails, the export uses CPU immediately. If a real NVENC export fails,
it restarts once with CPU using the same deterministic renderer and analyzed
features. Progress can restart during that retry. A temporary MP4 beside the
chosen destination is replaced only after success, preserving an existing export
if both attempts fail. This needs space for the temporary output; an existing
export remains on disk until replacement. A forced process termination can leave
a `.dero-export-*.mp4` temporary file.

## Performance scope and validation

NVENC offloads video compression, not Pillow frame rendering, particle simulation,
FFT analysis, or preview. It still uploads RGB-derived frames to the GPU. If the
CPU cannot supply frames quickly enough, total speedup may be small. This release
does not claim a GPU renderer or full-project GPU acceleration.

Compare CPU and NVIDIA exports of the same project, selection, resolution and FPS,
with no other changes. Record elapsed time and verify audio sync and image quality.
A suitable comparison is a 10-second 1080p60 selection, after preview analysis is
ready. Record the actual GPU model, driver and FFmpeg version with timings.

Cloud validation covered actual CPU exports, the GUI's unavailable-NVENC fallback,
project persistence, mocked successful NVIDIA selection, timeout handling, simulated
mid-export GPU failure followed by a real CPU export, and preservation/cleanup when
both encoders fail. This cloud runtime cannot load `libcuda.so.1`; NVIDIA hardware
encoding and its speedup have not been measured here. Validate them on your Windows
GPU using the procedure above. Earlier cached-versus-fresh equivalence tests remain
applicable to CPU encoding.
