#!/usr/bin/env python3
"""
Tag Writer - Safe ID3 tag writing
"""

import os
from pathlib import Path
from urllib.parse import unquote
from typing import Dict, List, Optional, Tuple

try:
    from mutagen.flac import FLAC
    from mutagen.mp3 import MP3
    from mutagen.id3 import TIT2, TPE1, TALB, TPE2, TCON, ID3NoHeaderError
    from mutagen import File
except ImportError:
    print("mutagen not installed. Run: pip install mutagen")
    exit(1)

from album_matcher import AlbumMatcher

class TagWriter:
    def __init__(self, music_path: str):
        self.music_path = music_path
        
        self.matcher = AlbumMatcher(music_path)
        self.matcher.scan_filesystem()
        
    
    
    def merge_genres(self, existing_genres: str, new_genres: List[str]) -> List[str]:
        """Merge existing and new genres, avoiding duplicates"""
        # Parse existing genres
        existing_list = []
        if existing_genres:
            # Split on semicolon and clean up
            existing_list = [g.strip() for g in existing_genres.split(';') if g.strip()]
        
        # Combine with new genres
        all_genres = existing_list + new_genres
        
        # Remove duplicates while preserving order
        seen = set()
        merged = []
        for genre in all_genres:
            genre_lower = genre.lower()
            if genre_lower not in seen:
                seen.add(genre_lower)
                merged.append(genre)
        
        return merged

    def write_genre_tags(self, file_path: Path, new_genres: List[str], 
                        test_mode: bool = True, preserve_existing: bool = True) -> bool:
        """Write genre tags to music file, optionally preserving existing genres"""
        try:
            # Load the audio file
            audio_file = File(file_path)
            if not audio_file:
                print(f"Could not read audio file: {file_path}")
                return False
            
            # Get existing genres if preserving
            existing_genres = ""
            final_genres = new_genres
            
            if preserve_existing:
                if isinstance(audio_file, FLAC):
                    existing_genres = audio_file.get('GENRE', [''])[0]
                elif isinstance(audio_file, MP3) and audio_file.tags:
                    existing_genres = str(audio_file.tags.get('TCON', ''))
                
                # Merge existing and new genres
                final_genres = self.merge_genres(existing_genres, new_genres)
            
            # Format genres with semicolon delimiter
            genre_string = "; ".join(final_genres)
            
            # Show what's happening
            if existing_genres and preserve_existing:
                action_desc = f"Merged: '{existing_genres}' + {new_genres} -> {genre_string}"
            else:
                action_desc = f"Set: {genre_string}"
            
            # Write tags based on file type
            if isinstance(audio_file, FLAC):
                # FLAC uses Vorbis Comments
                audio_file['GENRE'] = genre_string
                if not test_mode:
                    audio_file.save()
                    print(f"✓ Updated FLAC: {file_path.name}")
                    print(f"  {action_desc}")
                else:
                    print(f"[TEST] Would update FLAC: {file_path.name}")
                    print(f"  {action_desc}")
                    
            elif isinstance(audio_file, MP3):
                # MP3 uses ID3 tags
                if audio_file.tags is None:
                    audio_file.add_tags()
                
                # Remove existing TCON tag and add new one
                if 'TCON' in audio_file.tags:
                    del audio_file.tags['TCON']
                audio_file.tags.add(TCON(encoding=3, text=genre_string))
                
                if not test_mode:
                    audio_file.save()
                    print(f"✓ Updated MP3: {file_path.name}")
                    print(f"  {action_desc}")
                else:
                    print(f"[TEST] Would update MP3: {file_path.name}")
                    print(f"  {action_desc}")
            else:
                print(f"Unsupported file type: {file_path}")
                return False
                
            return True
            
        except Exception as e:
            print(f"Error writing tags to {file_path}: {e}")
            return False
    
    def test_local_albums(self, local_music_dir: str = None) -> None:
        """Test tag writing on local sample albums"""
        if local_music_dir is None:
            local_music_dir = self.music_path
        
        local_path = Path(local_music_dir)
        if not local_path.exists():
            print(f"Local music directory not found: {local_path}")
            return
        
        print("🎵 TESTING TAG WRITING ON LOCAL ALBUMS")
        print("=" * 60)
        
        # Find all audio files in the local directory
        audio_files = []
        for ext in ['*.flac', '*.mp3', '*.m4a']:
            audio_files.extend(local_path.rglob(ext))
        
        if not audio_files:
            print("No audio files found in local directory")
            return
        
        # Group files by album (based on parent directory)
        albums = {}
        for file_path in audio_files:
            album_dir = file_path.parent.name
            if album_dir not in albums:
                albums[album_dir] = []
            albums[album_dir].append(file_path)
        
        print(f"Found {len(albums)} albums with {len(audio_files)} tracks")
        
        # Test each album
        for album_name, files in albums.items():
            print(f"\n📁 ALBUM: {album_name}")
            print(f"   Tracks: {len(files)}")
            
            # Try to parse artist and album from directory name
            # Common formats: "Artist - Album (Year)" or "Artist - Album"
            if " - " in album_name:
                parts = album_name.split(" - ", 1)
                artist = parts[0].strip()
                album = parts[1].strip()
                
                # Remove year and format info
                album = album.split(" (")[0].strip()
                album = album.split(" [")[0].strip()
                
                print(f"   Parsed: {artist} - {album}")
                
                # Test genre assignment (simulate API result)
                test_genres = self.get_test_genres(artist, album)
                print(f"   Test Genres: {'; '.join(test_genres)}")
                
                # Test writing to first file only
                if files:
                    test_file = files[0]
                    print(f"   Testing on: {test_file.name}")
                    success = self.write_genre_tags(test_file, test_genres, test_mode=True)
                    if success:
                        print(f"   ✓ Tag writing test successful")
                    else:
                        print(f"   ✗ Tag writing test failed")
            else:
                print(f"   ⚠️  Could not parse artist/album from directory name")
    
    def get_test_genres(self, artist: str, album: str) -> List[str]:
        """Get test genres based on artist/album (simulated API result)"""
        # This simulates what we'd get from MusicBrainz API
        # In real implementation, this would come from API results
        
        test_genre_map = {
            "annette brissett": ["Reggae", "Dancehall", "Caribbean"],
            "ranking dread": ["Reggae", "Dub", "Jamaican"],
            "tomorrow": ["Psychedelic Rock", "Rock", "1960s"]
        }
        
        artist_lower = artist.lower()
        for key, genres in test_genre_map.items():
            if key in artist_lower:
                return genres
        
        # Default test genres
        return ["Rock", "Alternative"]
    
    def read_current_tags(self, file_path: Path) -> Dict:
        """Read current tags from file"""
        try:
            audio_file = File(file_path)
            if not audio_file:
                return {}
            
            tags = {}
            if isinstance(audio_file, FLAC):
                tags = {
                    'genre': audio_file.get('GENRE', [''])[0],
                    'title': audio_file.get('TITLE', [''])[0],
                    'artist': audio_file.get('ARTIST', [''])[0],
                    'album': audio_file.get('ALBUM', [''])[0]
                }
            elif isinstance(audio_file, MP3):
                if audio_file.tags:
                    tags = {
                        'genre': str(audio_file.tags.get('TCON', '')),
                        'title': str(audio_file.tags.get('TIT2', '')),
                        'artist': str(audio_file.tags.get('TPE1', '')),
                        'album': str(audio_file.tags.get('TALB', ''))
                    }
            
            return tags
            
        except Exception as e:
            print(f"Error reading tags from {file_path}: {e}")
            return {}
    
    def show_current_tags(self, local_music_dir: str = None) -> None:
        """Show current tags in local albums"""
        if local_music_dir is None:
            local_music_dir = self.music_path
        
        local_path = Path(local_music_dir)
        if not local_path.exists():
            print(f"Local music directory not found: {local_path}")
            return
        
        print("🏷️  CURRENT TAGS IN LOCAL ALBUMS")
        print("=" * 60)
        
        # Find all audio files
        audio_files = []
        for ext in ['*.flac', '*.mp3', '*.m4a']:
            audio_files.extend(local_path.rglob(ext))
        
        for file_path in audio_files[:10]:  # Show first 10 files
            tags = self.read_current_tags(file_path)
            print(f"\n📁 {file_path.parent.name}")
            print(f"   🎵 {file_path.name}")
            print(f"   Artist: {tags.get('artist', 'None')}")
            print(f"   Album: {tags.get('album', 'None')}")
            print(f"   Genre: {tags.get('genre', 'None')}")
    

if __name__ == "__main__":
    writer = TagWriter("/Volumes/T7/Albums")
    
    # Show current tags
    writer.show_current_tags()
    
    # Test tag writing
    writer.test_local_albums()