"""Shared helpers for denoise_videos.py and compress_videos.py."""

import shutil
import subprocess
import sys
from pathlib import Path

VIDEO_EXTS = {'.mp4', '.mov', '.m4v', '.avi', '.mkv', '.mts', '.m2ts', '.wmv', '.flv', '.webm'}


def require_tools() -> None:
    if not shutil.which('HandBrakeCLI'):
        print("HandBrakeCLI not found on PATH. Install with: brew install handbrake")
        sys.exit(1)
    if not shutil.which('ffprobe'):
        print("ffprobe not found on PATH. Install with: brew install ffmpeg")
        sys.exit(1)


def already_processed(path: Path) -> bool:
    result = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'format_tags=encoder',
         '-of', 'default=noprint_wrappers=1:nokey=1', str(path)],
        capture_output=True, text=True)
    return bool(result.stdout.strip())


def discover_videos(folder: Path, exclude_suffix: str | None = None) -> list[Path]:
    """Recursively find video files under folder, smallest first."""
    files = [
        p for p in folder.rglob('*')
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS
        and not (exclude_suffix and p.stem.endswith(exclude_suffix))
    ]
    return sorted(files, key=lambda p: p.stat().st_size)


def print_file_list(files: list[Path], folder: Path) -> None:
    print(f"Found {len(files)} video file(s) in {folder} (processing order, smallest first):")
    for i, f in enumerate(files, 1):
        size_mb = f.stat().st_size / 1_048_576
        print(f"  {i}. {f.name}  ({size_mb:.0f} MB)")
    print()


def run_handbrake(cmd: list[str], dest: Path) -> bool:
    """Run a HandBrakeCLI command, showing only its live "Encoding: ..." progress
    line (updated in place). Its scan/title logging is noisy, so it's captured
    and only printed if the encode fails.
    """
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, bufsize=1)
    log = []
    showed_progress = False
    for line in proc.stdout:
        log.append(line)
        if line.startswith('Encoding:'):
            print(f"\r  {line.rstrip()}", end='', flush=True)
            showed_progress = True
    proc.wait()
    if showed_progress:
        print()

    ok = proc.returncode == 0 and dest.exists() and dest.stat().st_size > 0
    if not ok:
        print(''.join(log))
    return ok


def swap_in(working_path: Path, final_path: Path, source: Path) -> None:
    """Replace final_path with working_path, then remove source — unless source
    and final_path are the same file on disk. Checked via the filesystem
    (Path.samefile), not by comparing path strings: on a case-insensitive
    filesystem (the macOS default), a source like GX016273.MP4 and a
    final_path of GX016273.mp4 are the same file even though the strings
    differ, and unlinking "source" after the replace would delete the
    just-written output instead of a leftover original.
    """
    same_file = final_path.exists() and source.exists() and final_path.samefile(source)
    working_path.replace(final_path)
    if not same_file:
        source.unlink(missing_ok=True)
