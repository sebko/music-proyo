#!/usr/bin/env python3
"""
Fast Album Match Viewer - Shows existing API matches from previous batch runs
"""

import sqlite3
import json
from flask import Flask, render_template, jsonify
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

from album_scanner import AlbumScanner
from fuzzywuzzy import fuzz

app = Flask(__name__)

class FastAlbumMatchViewer:
    """Fast viewer that uses existing batch processing results"""
    
    def __init__(self, music_path: str = "/Volumes/T7/Albums"):
        self.music_path = music_path
        self.album_matcher = AlbumMatcher(music_path)
        self.failed_albums = []
        self.current_index = 0
        self.confidence_threshold = 30.0  # Start with lower threshold
        
    def load_failed_albums_from_cache(self):
        """Load albums and their cached matches from hybrid_genre_cache.db"""
        print("Loading from cache databases...")
        
        # First get failed albums from batch processing
        batch_db = sqlite3.connect('batch_processing.db')
        cursor = batch_db.cursor()
        
        cursor.execute('''
            SELECT album_key, artist, album, confidence, final_genres
            FROM album_results 
            WHERE status IN ('failed', 'needs_review', 'no_match')
            ORDER BY confidence DESC
        ''')
        
        failed_albums = cursor.fetchall()
        batch_db.close()
        
        # Now check hybrid cache for these albums
        cache_db = sqlite3.connect('hybrid_genre_cache.db')
        cache_cursor = cache_db.cursor()
        
        # Load album info
        self.album_matcher.scan_filesystem()
        
        self.failed_albums = []
        albums_with_cache = 0
        seen_albums = set()  # Track seen albums to avoid duplicates
        
        for album_key, artist, album, confidence, genres_json in failed_albums:
            # Skip if we've already processed this album
            if album_key in seen_albums:
                continue
            seen_albums.add(album_key)
            album_info = self.album_matcher.albums.get(album_key)
            if not album_info:
                continue
                
            # Check cache for this artist/album
            cache_cursor.execute('''
                SELECT source, genres, confidence, weight
                FROM genre_cache
                WHERE LOWER(artist) = LOWER(?) AND LOWER(album) = LOWER(?)
                AND expires_at > datetime('now')
                ORDER BY weight DESC
            ''', (artist, album))
            
            cache_results = cache_cursor.fetchall()
            
            if cache_results:
                albums_with_cache += 1
                # Find best cached match
                best_match = None
                best_score = 0
                
                for source, genres_str, cache_conf, weight in cache_results:
                    try:
                        genres = json.loads(genres_str) if genres_str else []
                        score = (cache_conf or 0) * weight
                        
                        if score > best_score:
                            best_score = score
                            # Fix: cache_conf might already be in percentage form
                            conf_value = cache_conf if cache_conf <= 1.0 else cache_conf / 100.0
                            best_match = {
                                'source': source.title(),
                                'confidence': conf_value * 100 if conf_value <= 1.0 else conf_value,
                                'artist': artist,
                                'album': album,
                                'genres': genres,
                                'cached': True
                            }
                    except:
                        continue
                
                if best_match and best_match['confidence'] >= self.confidence_threshold:
                    # Calculate similarity
                    artist_similarity = fuzz.ratio(
                        album_info['artist'].lower(), 
                        best_match['artist'].lower()
                    )
                    album_similarity = fuzz.ratio(
                        album_info['album'].lower(), 
                        best_match['album'].lower()
                    )
                    
                    best_match['artist_similarity'] = artist_similarity
                    best_match['album_similarity'] = album_similarity
                    best_match['overall_similarity'] = (artist_similarity + album_similarity) / 2
                    
                    # Store album data with match
                    first_track = album_info['tracks'][0] if album_info['tracks'] else {}
                    album_data = {
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
                        'cached_match': best_match
                    }
                    
                    self.failed_albums.append(album_data)
        
        cache_db.close()
        
        print(f"Found {albums_with_cache} albums with cached API data")
        print(f"Showing {len(self.failed_albums)} albums with matches above {self.confidence_threshold}%")
        
        return len(self.failed_albums)
    
    def set_confidence_threshold(self, threshold: float):
        """Update threshold and reload"""
        self.confidence_threshold = threshold
        self.failed_albums = []
        return self.load_failed_albums_from_cache()
    
    def get_current_album(self) -> Optional[Dict]:
        """Get current album with its match"""
        if not self.failed_albums or self.current_index >= len(self.failed_albums):
            return None
            
        album_data = self.failed_albums[self.current_index]
        
        return {
            'index': self.current_index + 1,
            'total': len(self.failed_albums),
            'album_data': album_data,
            'closest_match': album_data.get('cached_match'),
            'confidence_threshold': self.confidence_threshold
        }

# Initialize viewer
viewer = FastAlbumMatchViewer()

@app.route('/')
def index():
    """Main page"""
    return render_template('album_match_viewer.html')

@app.route('/api/load_albums')
def load_albums():
    """Load albums from cache"""
    count = viewer.load_failed_albums_from_cache()
    return jsonify({
        'success': True,
        'count': count,
        'message': f'Loaded {count} albums with cached matches'
    })

@app.route('/api/current_album')
def get_current_album():
    """Get current album"""
    data = viewer.get_current_album()
    if data:
        return jsonify(data)
    else:
        return jsonify({'error': 'No albums to review'}), 404

@app.route('/api/navigate/<direction>')
def navigate(direction):
    """Navigate albums"""
    if direction == 'next' and viewer.current_index < len(viewer.failed_albums) - 1:
        viewer.current_index += 1
    elif direction == 'prev' and viewer.current_index > 0:
        viewer.current_index -= 1
    
    data = viewer.get_current_album()
    if data:
        return jsonify(data)
    else:
        return jsonify({'error': 'No more albums'}), 404

@app.route('/api/set_threshold/<threshold>')
def set_threshold(threshold):
    """Update confidence threshold"""
    try:
        threshold_float = float(threshold)
        count = viewer.set_confidence_threshold(threshold_float)
        return jsonify({
            'success': True,
            'count': count,
            'threshold': threshold_float,
            'message': f'Found {count} albums with cached matches above {threshold_float}%'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("🎵 Fast Album Match Viewer")
    print("=" * 50)
    print("Using cached API results for instant loading")
    print()
    
    app.run(host='127.0.0.1', port=5003, debug=False)