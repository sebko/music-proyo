#!/usr/bin/env python3
"""
Album Match Viewer - Shows diff between unmatched albums and their closest API matches
"""

import sqlite3
import json
from flask import Flask, render_template, jsonify
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from album_matcher import AlbumMatcher
from hybrid_genre_fetcher import HybridGenreFetcher
from fuzzywuzzy import fuzz

app = Flask(__name__)

class AlbumMatchViewer:
    """Viewer for albums that failed to match in batch processing"""
    
    def __init__(self, music_path: str = "/Volumes/T7/Albums"):
        self.music_path = music_path
        self.album_matcher = AlbumMatcher(music_path)
        self.hybrid_fetcher = HybridGenreFetcher()
        self.failed_albums = []
        self.albums_with_matches = []
        self.current_index = 0
        self.confidence_threshold = 60.0  # Default threshold
        
    def load_failed_albums(self):
        """Load albums that failed to match or need review from database"""
        db = sqlite3.connect('batch_processing.db')
        cursor = db.cursor()
        
        # Get albums that failed or need review
        cursor.execute('''
            SELECT album_key, artist, album, confidence, final_genres, created_at
            FROM album_results 
            WHERE status IN ('failed', 'needs_review', 'no_match')
            ORDER BY confidence ASC, created_at DESC
        ''')
        
        results = cursor.fetchall()
        db.close()
        
        # Load detailed album info from album matcher
        self.album_matcher.scan_filesystem()
        
        self.failed_albums = []
        for row in results:
            album_key, artist, album, confidence, genres_json, created_at = row
            
            # Get full album info from matcher
            album_info = self.album_matcher.albums.get(album_key)
            if album_info:
                # Extract all available metadata
                first_track = album_info['tracks'][0] if album_info['tracks'] else {}
                
                self.failed_albums.append({
                    'album_key': album_key,
                    'local': {
                        'artist': album_info['artist'],
                        'album': album_info['album'],
                        'album_artist': album_info.get('album_artist', ''),
                        'year': album_info.get('year', ''),
                        'track_count': len(album_info['tracks']),
                        'genres': list(album_info.get('genres', [])),
                        'directory': album_info.get('directory', ''),
                        'format': first_track.get('format', ''),
                        'bitrate': first_track.get('bitrate', ''),
                        'sample_rate': first_track.get('sample_rate', ''),
                    },
                    'last_confidence': confidence or 0,
                    'attempted_at': created_at
                })
        
        print(f"Loaded {len(self.failed_albums)} failed/needs_review albums")
        
        # Now find which ones have matches
        self.find_albums_with_matches()
        
        return len(self.albums_with_matches)
    
    def find_albums_with_matches(self, use_cache=False):
        """Pre-process to find which albums have reasonable matches"""
        print(f"Finding albums with matches (threshold: {self.confidence_threshold}%)...")
        
        if use_cache and hasattr(self, '_all_matches_cache'):
            # Re-filter existing cached matches with new threshold
            self.albums_with_matches = []
            for album_data in self._all_matches_cache:
                match = album_data.get('cached_match')
                if match and match['confidence'] >= self.confidence_threshold:
                    self.albums_with_matches.append(album_data)
        else:
            # Initial load - fetch all matches
            self.albums_with_matches = []
            self._all_matches_cache = []
            
            total = len(self.failed_albums)
            for i, album_data in enumerate(self.failed_albums):
                if i % 50 == 0:
                    print(f"Processing {i}/{total} albums...")
                
                match = self.find_closest_match(album_data)
                if match:
                    # Store the match with the album data
                    album_data['cached_match'] = match
                    self._all_matches_cache.append(album_data)
                    
                    if match['confidence'] >= self.confidence_threshold:
                        self.albums_with_matches.append(album_data)
        
        print(f"Found {len(self.albums_with_matches)} albums with matches above {self.confidence_threshold}%")
        self.current_index = 0
    
    def set_confidence_threshold(self, threshold: float):
        """Update confidence threshold and re-filter albums"""
        self.confidence_threshold = threshold
        self.find_albums_with_matches(use_cache=True)
    
    def find_closest_match(self, album_data: Dict) -> Optional[Dict]:
        """Find the closest match for an album using the hybrid fetcher"""
        artist = album_data['local']['artist']
        album = album_data['local']['album']
        
        # Try to fetch with hybrid fetcher
        result = self.hybrid_fetcher.fetch_all_sources(artist, album)
        
        # Find the best individual source match
        best_match = None
        best_score = 0
        best_source = None
        
        for source_name, source_data in result.source_breakdown.items():
            if hasattr(source_data, 'match_quality') and source_data.match_quality > best_score:
                best_score = source_data.match_quality
                best_source = source_name
                
                # Extract match details based on source type
                if source_name == 'spotify' and hasattr(source_data, 'raw_data'):
                    raw = source_data.raw_data
                    best_match = {
                        'source': 'Spotify',
                        'confidence': best_score * 100,
                        'artist': raw.get('artists', [{}])[0].get('name', ''),
                        'album': raw.get('name', ''),
                        'year': raw.get('release_date', '')[:4] if raw.get('release_date') else '',
                        'track_count': raw.get('total_tracks', 0),
                        'genres': source_data.genres,
                        'album_type': raw.get('album_type', ''),
                        'spotify_id': raw.get('id', ''),
                        'url': raw.get('external_urls', {}).get('spotify', '')
                    }
                elif source_name == 'musicbrainz' and hasattr(source_data, 'raw_data'):
                    raw = source_data.raw_data
                    best_match = {
                        'source': 'MusicBrainz',
                        'confidence': best_score * 100,
                        'artist': raw.get('artist-credit', [{}])[0].get('name', ''),
                        'album': raw.get('title', ''),
                        'year': raw.get('date', '')[:4] if raw.get('date') else '',
                        'track_count': raw.get('track-count', 0),
                        'genres': source_data.genres,
                        'album_type': raw.get('primary-type', ''),
                        'musicbrainz_id': raw.get('id', ''),
                        'url': f"https://musicbrainz.org/release/{raw.get('id', '')}"
                    }
                elif source_name == 'lastfm' and hasattr(source_data, 'raw_data'):
                    raw = source_data.raw_data
                    best_match = {
                        'source': 'Last.fm',
                        'confidence': best_score * 100,
                        'artist': raw.get('artist', ''),
                        'album': raw.get('name', ''),
                        'year': '',  # Last.fm doesn't provide year in basic info
                        'track_count': 0,  # Last.fm doesn't provide track count in basic info
                        'genres': source_data.genres,
                        'album_type': '',
                        'lastfm_url': raw.get('url', '')
                    }
        
        # Only return if we have a match above the threshold
        if best_match and best_score * 100 >= self.confidence_threshold:
            # Calculate string similarity for visual diff
            artist_similarity = fuzz.ratio(
                album_data['local']['artist'].lower(), 
                best_match['artist'].lower()
            )
            album_similarity = fuzz.ratio(
                album_data['local']['album'].lower(), 
                best_match['album'].lower()
            )
            
            best_match['artist_similarity'] = artist_similarity
            best_match['album_similarity'] = album_similarity
            best_match['overall_similarity'] = (artist_similarity + album_similarity) / 2
            
            return best_match
        
        return None
    
    def get_current_album_with_match(self) -> Dict:
        """Get current album with its closest match"""
        if not self.albums_with_matches or self.current_index >= len(self.albums_with_matches):
            return None
        
        album_data = self.albums_with_matches[self.current_index]
        # Use cached match
        closest_match = album_data.get('cached_match')
        
        return {
            'index': self.current_index + 1,
            'total': len(self.albums_with_matches),
            'album_data': album_data,
            'closest_match': closest_match,
            'confidence_threshold': self.confidence_threshold
        }

# Initialize viewer
viewer = AlbumMatchViewer()

@app.route('/')
def index():
    """Main page"""
    return render_template('album_match_viewer.html')

@app.route('/api/load_albums')
def load_albums():
    """Load failed albums from database"""
    count = viewer.load_failed_albums()
    return jsonify({
        'success': True,
        'count': count,
        'message': f'Loaded {count} albums that need review'
    })

@app.route('/api/current_album')
def get_current_album():
    """Get current album with match data"""
    data = viewer.get_current_album_with_match()
    if data:
        return jsonify(data)
    else:
        return jsonify({'error': 'No albums to review'}), 404

@app.route('/api/navigate/<direction>')
def navigate(direction):
    """Navigate to next/previous album"""
    if direction == 'next' and viewer.current_index < len(viewer.albums_with_matches) - 1:
        viewer.current_index += 1
    elif direction == 'prev' and viewer.current_index > 0:
        viewer.current_index -= 1
    
    data = viewer.get_current_album_with_match()
    if data:
        return jsonify(data)
    else:
        return jsonify({'error': 'No more albums'}), 404

@app.route('/api/set_threshold/<threshold>')
def set_threshold(threshold):
    """Update confidence threshold and reload albums"""
    try:
        threshold_float = float(threshold)
        viewer.set_confidence_threshold(threshold_float)
        viewer.current_index = 0
        return jsonify({
            'success': True,
            'count': len(viewer.albums_with_matches),
            'threshold': threshold_float,
            'message': f'Found {len(viewer.albums_with_matches)} albums with matches above {threshold_float}%'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("🎵 Album Match Viewer")
    print("=" * 50)
    print("Loading failed albums from database...")
    
    # Don't load albums on startup - do it via API call instead
    print(f"🌐 Starting web interface at http://localhost:5003")
    print("🔍 Use arrow keys to navigate between albums")
    print()
    
    app.run(host='127.0.0.1', port=5003, debug=False)