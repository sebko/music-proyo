#!/usr/bin/env python3
"""
Album Matcher - Phase 1 of Music Library Genre Tagger
Extract unique albums from filesystem and test matching strategies
"""

import xml.etree.ElementTree as ET
from collections import defaultdict
import re
from typing import Dict, List, Tuple, Set
from difflib import SequenceMatcher
import unicodedata
import os
from pathlib import Path
from mutagen import File as MutagenFile

class AlbumMatcher:
    def __init__(self, music_path: str):
        self.music_path = music_path
        self.albums = {}  # album_key -> album_info
        self.tracks = []
        self.supported_formats = {'.mp3', '.flac', '.m4a', '.ogg', '.wav', '.wma', '.aiff', '.aif'}
        
    def scan_filesystem(self) -> None:
        """Scan filesystem and extract album information from audio files"""
        music_path = Path(self.music_path)
        
        if not music_path.exists():
            raise ValueError(f"Music directory does not exist: {self.music_path}")
        
        print(f"Scanning {music_path} for audio files...")
        
        # Recursively scan for audio files
        for audio_file in music_path.rglob('*'):
            if audio_file.is_file() and audio_file.suffix.lower() in self.supported_formats:
                try:
                    track = self._parse_audio_file(audio_file)
                    if self._is_valid_track(track):
                        self.tracks.append(track)
                        self._process_album(track)
                except Exception as e:
                    print(f"Warning: Could not parse {audio_file}: {e}")
        
        print(f"Found {len(self.tracks)} tracks in {len(self.albums)} albums")
    
    def _parse_audio_file(self, audio_file: Path) -> Dict:
        """Parse individual audio file and extract metadata"""
        track = {
            'file_path': str(audio_file)
        }
        
        try:
            mutagen_file = MutagenFile(audio_file)
            if mutagen_file is None:
                return track
            
            # Extract common metadata fields
            tags = mutagen_file.tags or {}
            
            # Try different tag formats (ID3, Vorbis, etc.)
            track['Name'] = self._get_tag_value(tags, ['TIT2', 'TITLE', 'Title'])
            track['Artist'] = self._get_tag_value(tags, ['TPE1', 'ARTIST', 'Artist'])
            track['Album'] = self._get_tag_value(tags, ['TALB', 'ALBUM', 'Album'])
            track['Album Artist'] = self._get_tag_value(tags, ['TPE2', 'ALBUMARTIST', 'AlbumArtist'])
            track['Genre'] = self._get_tag_value(tags, ['TCON', 'GENRE', 'Genre'])
            
            # If no album artist, fall back to artist
            if not track['Album Artist'] and track['Artist']:
                track['Album Artist'] = track['Artist']
                
        except Exception as e:
            print(f"Warning: Could not read metadata from {audio_file}: {e}")
        
        return track
    
    def _get_tag_value(self, tags, tag_names: List[str]) -> str:
        """Get tag value from multiple possible tag names"""
        for tag_name in tag_names:
            if tag_name in tags:
                value = tags[tag_name]
                if isinstance(value, list) and value:
                    return str(value[0])
                elif value:
                    return str(value)
        return ''
    
    def _is_valid_track(self, track: Dict) -> bool:
        """Check if track has required fields for album identification"""
        return 'Album' in track and track['Album'] and (
            'Artist' in track or 'Album Artist' in track
        )
    
    def _process_album(self, track: Dict) -> None:
        """Process track and extract album information"""
        album = track['Album']
        artist = track.get('Album Artist', track.get('Artist', ''))
        
        if not album or not artist:
            return
        
        # Create album key for deduplication
        album_key = f"{artist}|{album}"
        
        if album_key not in self.albums:
            self.albums[album_key] = {
                'artist': artist,
                'album': album,
                'tracks': [],
                'genres': set()
            }
        
        # Add track info
        self.albums[album_key]['tracks'].append({
            'name': track.get('Name', ''),
            'artist': track.get('Artist', ''),
            'genre': track.get('Genre', ''),
            'file_path': track.get('file_path', '')
        })
        
        # Collect genres
        if track.get('Genre'):
            self.albums[album_key]['genres'].add(track['Genre'])
    
    def get_album_stats(self) -> Dict:
        """Get statistics about the album collection"""
        stats = {
            'total_albums': len(self.albums),
            'total_tracks': len(self.tracks),
            'albums_with_genres': 0,
            'unique_genres': set(),
            'genre_distribution': defaultdict(int)
        }
        
        for album_info in self.albums.values():
            if album_info['genres']:
                stats['albums_with_genres'] += 1
                for genre in album_info['genres']:
                    stats['unique_genres'].add(genre)
                    stats['genre_distribution'][genre] += 1
        
        return stats
    
    def get_sample_albums(self, count: int = 10) -> List[Dict]:
        """Get sample albums for testing matching"""
        albums = list(self.albums.values())
        return albums[:count]
    
    def normalize_string(self, text: str) -> str:
        """Normalize string for fuzzy matching"""
        if not text:
            return ""
        
        # Unicode normalization
        text = unicodedata.normalize('NFD', text)
        text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
        
        # Remove common prefixes/suffixes
        text = re.sub(r'^(The|A|An)\s+', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\s+\((Deluxe|Remastered|Expanded|Special|Extended|Bonus).*\)$', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\s+\[(Deluxe|Remastered|Expanded|Special|Extended|Bonus).*\]$', '', text, flags=re.IGNORECASE)
        
        # Remove special characters and normalize whitespace
        text = re.sub(r'[^\w\s]', '', text)
        text = re.sub(r'\s+', ' ', text).strip().lower()
        
        return text
    
    def calculate_similarity(self, str1: str, str2: str) -> float:
        """Calculate similarity between two strings using sequence matching"""
        return SequenceMatcher(None, str1, str2).ratio()
    
    def match_strategies(self, album: Dict) -> Dict[str, Dict]:
        """Test different matching strategies for an album"""
        artist = album['artist']
        album_name = album['album']
        
        strategies = {
            'exact': {
                'artist': artist,
                'album': album_name,
                'search_query': f'artist:"{artist}" AND release:"{album_name}"'
            },
            'normalized': {
                'artist': self.normalize_string(artist),
                'album': self.normalize_string(album_name),
                'search_query': f'artist:"{self.normalize_string(artist)}" AND release:"{self.normalize_string(album_name)}"'
            },
            'fuzzy_artist': {
                'artist': self.normalize_string(artist),
                'album': album_name,
                'search_query': f'artist:"{self.normalize_string(artist)}" AND release:"{album_name}"'
            },
            'fuzzy_album': {
                'artist': artist,
                'album': self.normalize_string(album_name),
                'search_query': f'artist:"{artist}" AND release:"{self.normalize_string(album_name)}"'
            },
            'loose': {
                'artist': artist,
                'album': album_name,
                'search_query': f'{artist} {album_name}'
            }
        }
        
        return strategies
    
    def test_matching_strategies(self, sample_size: int = 20) -> Dict:
        """Test different matching strategies on sample albums"""
        sample_albums = self.get_sample_albums(sample_size)
        results = {
            'exact': [],
            'normalized': [],
            'fuzzy_artist': [],
            'fuzzy_album': [],
            'loose': []
        }
        
        for album in sample_albums:
            strategies = self.match_strategies(album)
            
            for strategy_name, strategy_data in strategies.items():
                results[strategy_name].append({
                    'original_artist': album['artist'],
                    'original_album': album['album'],
                    'processed_artist': strategy_data['artist'],
                    'processed_album': strategy_data['album'],
                    'search_query': strategy_data['search_query'],
                    'existing_genres': list(album['genres'])
                })
        
        return results
    
    def print_album_report(self) -> None:
        """Print detailed album analysis report"""
        stats = self.get_album_stats()
        
        print("=" * 60)
        print("ALBUM COLLECTION ANALYSIS")
        print("=" * 60)
        print(f"Total Albums: {stats['total_albums']}")
        print(f"Total Tracks: {stats['total_tracks']}")
        print(f"Albums with Genres: {stats['albums_with_genres']} ({stats['albums_with_genres']/stats['total_albums']*100:.1f}%)")
        print(f"Unique Genres: {len(stats['unique_genres'])}")
        
        print("\nTOP 10 GENRES:")
        for genre, count in sorted(stats['genre_distribution'].items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"  {genre}: {count} albums")
        
        print("\nSAMPLE ALBUMS:")
        for i, album in enumerate(self.get_sample_albums(5)):
            print(f"  {i+1}. {album['artist']} - {album['album']}")
            print(f"     Genres: {', '.join(album['genres']) if album['genres'] else 'None'}")
            print(f"     Tracks: {len(album['tracks'])}")
    
    def get_file_paths_for_album(self, album: Dict) -> List[str]:
        """Get file paths for all tracks in an album"""
        return [track['file_path'] for track in album['tracks'] if track.get('file_path')]
    
    def print_matching_strategies_report(self, sample_size: int = 10) -> None:
        """Print report showing different matching strategies"""
        results = self.test_matching_strategies(sample_size)
        
        print("\n" + "=" * 80)
        print("MATCHING STRATEGIES COMPARISON")
        print("=" * 80)
        
        for i, album in enumerate(self.get_sample_albums(sample_size)):
            print(f"\nALBUM {i+1}: {album['artist']} - {album['album']}")
            print(f"Current Genres: {', '.join(album['genres']) if album['genres'] else 'None'}")
            print("-" * 60)
            
            strategies = self.match_strategies(album)
            for strategy_name, strategy_data in strategies.items():
                print(f"{strategy_name.upper():12} | {strategy_data['search_query']}")
            
            # Show normalization effects
            orig_artist = album['artist']
            orig_album = album['album']
            norm_artist = self.normalize_string(orig_artist)
            norm_album = self.normalize_string(orig_album)
            
            if orig_artist != norm_artist:
                print(f"             | Artist normalization: '{orig_artist}' -> '{norm_artist}'")
            if orig_album != norm_album:
                print(f"             | Album normalization: '{orig_album}' -> '{norm_album}'")

if __name__ == "__main__":
    matcher = AlbumMatcher("/Volumes/T7/Albums")
    matcher.scan_filesystem()
    matcher.print_album_report()
    matcher.print_matching_strategies_report()