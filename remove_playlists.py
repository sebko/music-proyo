#!/usr/bin/env python3
"""
Remove Playlist Files from Music Library

This script safely removes playlist files while preserving all media files.
Supports common playlist formats: m3u, m3u8, pls, xspf, wpl, asx, b4s
"""

import os
import sys
import argparse
from pathlib import Path
from typing import List, Set

# Define playlist file extensions
PLAYLIST_EXTENSIONS = {'.m3u', '.m3u8', '.pls', '.xspf', '.wpl', '.asx', '.b4s', '.smil', '.ram'}

# Define media file extensions (for safety checking)
MEDIA_EXTENSIONS = {
    # Audio formats
    '.mp3', '.flac', '.wav', '.aac', '.ogg', '.wma', '.m4a', '.opus', '.ape', '.dsd',
    '.aiff', '.alac', '.mp2', '.mpc', '.tta', '.wv', '.ac3', '.dts', '.amr', '.au',
    # Video formats (in case they're in the library)
    '.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.mpg', '.mpeg',
    # Other audio-related formats
    '.cue', '.log'  # These are metadata, not playlists
}


def is_playlist_file(file_path: Path) -> bool:
    """Check if a file is a playlist based on its extension."""
    return file_path.suffix.lower() in PLAYLIST_EXTENSIONS


def is_media_file(file_path: Path) -> bool:
    """Check if a file is a media file (for safety verification)."""
    return file_path.suffix.lower() in MEDIA_EXTENSIONS


def find_playlist_files(root_path: Path) -> List[Path]:
    """Find all playlist files in the given directory tree."""
    playlist_files = []
    
    for dirpath, _, filenames in os.walk(root_path):
        for filename in filenames:
            file_path = Path(dirpath) / filename
            if is_playlist_file(file_path):
                playlist_files.append(file_path)
    
    return playlist_files


def remove_playlists(root_path: Path, dry_run: bool = True):
    """Remove all playlist files from the music library."""
    print(f"Scanning for playlist files in: {root_path}")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print("-" * 60)
    
    # Find all playlist files
    playlist_files = find_playlist_files(root_path)
    
    if not playlist_files:
        print("No playlist files found.")
        return
    
    print(f"Found {len(playlist_files)} playlist file(s):")
    print()
    
    # Group by extension for summary
    extension_count = {}
    for pf in playlist_files:
        ext = pf.suffix.lower()
        extension_count[ext] = extension_count.get(ext, 0) + 1
    
    print("Summary by type:")
    for ext, count in sorted(extension_count.items()):
        print(f"  {ext}: {count} file(s)")
    print()
    
    # Process each playlist file
    removed_count = 0
    error_count = 0
    
    for playlist_file in sorted(playlist_files):
        try:
            # Double-check it's not a media file (extra safety)
            if is_media_file(playlist_file):
                print(f"⚠️  SKIPPING (safety check): {playlist_file}")
                continue
            
            if dry_run:
                print(f"[DRY RUN] Would remove: {playlist_file}")
            else:
                playlist_file.unlink()
                print(f"✓ Removed: {playlist_file}")
            removed_count += 1
            
        except PermissionError:
            print(f"❌ Permission denied: {playlist_file}")
            error_count += 1
        except Exception as e:
            print(f"❌ Error removing {playlist_file}: {e}")
            error_count += 1
    
    # Summary
    print()
    print("-" * 60)
    print(f"Total playlist files found: {len(playlist_files)}")
    if dry_run:
        print(f"Files that would be removed: {removed_count}")
    else:
        print(f"Files removed: {removed_count}")
    if error_count > 0:
        print(f"Errors encountered: {error_count}")


def main():
    parser = argparse.ArgumentParser(
        description="Remove playlist files from music library while preserving media files"
    )
    parser.add_argument(
        "path",
        nargs="?",
        default="/Volumes/T7/Albums",
        help="Path to music library (default: /Volumes/T7/Albums)"
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Actually remove files (default is dry-run mode)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip confirmation prompt (use with --live)"
    )
    parser.add_argument(
        "--extensions",
        action="store_true",
        help="Show supported playlist extensions and exit"
    )
    
    args = parser.parse_args()
    
    if args.extensions:
        print("Supported playlist extensions:")
        for ext in sorted(PLAYLIST_EXTENSIONS):
            print(f"  {ext}")
        print("\nProtected media extensions:")
        for ext in sorted(MEDIA_EXTENSIONS):
            print(f"  {ext}")
        sys.exit(0)
    
    root_path = Path(args.path)
    
    if not root_path.exists():
        print(f"Error: Path does not exist: {root_path}")
        sys.exit(1)
    
    if not root_path.is_dir():
        print(f"Error: Path is not a directory: {root_path}")
        sys.exit(1)
    
    # Safety confirmation for live mode
    if args.live and not args.force:
        print("⚠️  WARNING: This will permanently delete playlist files!")
        print(f"Target directory: {root_path}")
        response = input("Are you sure you want to proceed? (yes/no): ")
        if response.lower() != "yes":
            print("Operation cancelled.")
            sys.exit(0)
        print()
    
    remove_playlists(root_path, dry_run=not args.live)


if __name__ == "__main__":
    main()