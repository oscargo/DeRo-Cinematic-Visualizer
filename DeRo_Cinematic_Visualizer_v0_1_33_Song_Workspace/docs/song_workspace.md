# Song workspace: DeRo Sync port

The source reference is the uploaded DeRo Sync v0.2.0.75 Python file, not the
previous Cinematic Visualizer Audio screen. Its Song-tab responsibilities are
ported into Tkinter; the supplied DeRo Sync source and launcher are unchanged.

## Import and project protection

Browse audio reads local title/artist tags with Mutagen, fills gaps with FFprobe,
and uses a filename fallback, then opens
Confirm song information. The dialog contains the two editable names, Restore
Original, Cancel, and OK — Continue. Cleanup is proposed, never silently written
to the original music file. Cancel preserves the current project, media, settings,
and selection. Continuing checks whether the old project needs saving before
resetting the workspace. A disappeared input file prevents that reset.

A confirmed import starts a fresh project, clearing previous source/stem
references, background/overlay references, cached analysis, preview and export
range. Old media files and separated stems are not deleted. New composition
settings use the approved default preset. Song/artist remain shared with the
visualizer's text rendering, project documents, and suggested filenames.

The title prefix comparison tolerates punctuation and common honorific differences.
For example, a title `Lauryn Hill - Can't Take My Eyes Off Of You` and artist
`Ms. Lauryn Hill` suggest the title `Can't Take My Eyes Off Of You`, preserving
`Ms. Lauryn Hill` as the artist. Restore Original remains available. Local data
can still be wrong; online lookup and manual review remain available.

## Song information controls

- Song title, artist, and audio path mirror the source tab's information fields.
- Retrieve artist and song metadata rereads the local source and fills available
  names, with conservative cleanup. It does not search online.
- Review song information opens local review with original values available.
- Find artist and song online retains the MusicBrainz review workflow added in
  v0.1.32, and applies only the two name fields after review.
- Song language offers Auto Detect, English, and Spanish / Español, and is saved
  in the project. In DeRo Sync this choice controls later WhisperX alignment.
  Cinematic Visualizer stores the choice as song metadata; it does not run the
  separate DeRo Sync lyrics/WhisperX workflow or claim to detect language here.
- Project overview is informational. Its six steps describe the actual visualizer
  workflow: import, separate, background, text appearance, preview, export. It
  does not present unimplemented lyric/synchronization stages as available tools.

Use Browse for the complete new-song workflow. As in the source Song tab, typing
an audio path by itself does not run that entire import/reset/separation sequence.

## Automatic separation

After confirmed import, the app opens Separation and starts the existing Demucs
CLI using this app's Python executable. Fine-tuned HTDemucs (`htdemucs_ft`) is the
default; standard `htdemucs` is also available. Demucs chooses CUDA if supported,
otherwise CPU. This is separate from NVENC video encoding.

FFmpeg first creates temporary stereo 44.1 kHz PCM WAV processing audio, matching
the source app's compatibility approach. Demucs produces vocals/no-vocals stems.
A short FFmpeg decode checks each output before publication; this is not a full
quality or whole-file integrity assessment. Stems are stored alongside
the original under `Karaoke Maker Stems/<model>/<song>`. Existing runs are preserved
using distinct directories rather than overwritten. Source audio is never rewritten.

The Separation workspace shows activity, elapsed time and bounded processing logs.
Cancel interrupts registered processes and removes staged output. Successful jobs
populate both stem fields, play the enabled completion tone, and open the visualizer preview. Failed/canceled jobs
stay in Separation. You can import existing instrumental/vocal tracks or open
preview using the original mix without waiting for a successful separation.

Original mix, Instrumental, and Vocals feed the same analysis/cache/preview/export
pipeline. A missing selected stem produces an error rather than silently exporting
another track. Project files retain relative stem references when possible, and
exports cannot overwrite the original mix or either referenced stem.

## Dependencies and validation

The main app adds Mutagen for local tags. Separation additionally requires
Demucs and compatible PyTorch/torchaudio in the same Python 3.12 installation.
The supplied DeRo Sync launcher also uses `py -3.12`; use that existing working
environment. `Install_Vocal_Separation.bat` checks PyTorch/CUDA availability first
and installs `requirements-separation.txt` only after that prerequisite passes.
The installer pins the exact installed torch/torchaudio versions during dependency
resolution. A conflicting Demucs requirement fails instead of upgrading or
replacing those packages. It does not force a CPU build.

Demucs models require first-use access to `dl.fbaipublicfiles.com` unless already
cached. Validation installed actual Demucs 4.1.0 with isolated CPU PyTorch and
verified its CLI. A real separation attempt reached model loading but the cloud
proxy denied the model download (HTTP 403). Neural separation quality, actual
Windows CUDA execution, and the user's existing model cache could not be verified
here. Tests cover real FFmpeg normalization/output checks and a simulated Demucs
result, source preservation, staged failure/cancellation cleanup, and project
persistence. GUI checks cover import cancellation, Restore Original, title cleanup,
fresh reset, automatic job dispatch, stem-driven preview and saved project data.
