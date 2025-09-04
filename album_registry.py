#!/usr/bin/env python3
"""
Album Registry - Local database to track all albums and their scan/match status
Maintains a complete mirror of the music library with scan tracking
"""

import sqlite3
import os
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from album_scanner import AlbumScanner

class AlbumRegistry:
    def __init__(self, db_path: str = "album_registry.db"):
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """Initialize the album registry database"""
        conn = sqlite3.connect(self.db_path)
        conn.execute('PRAGMA foreign_keys = ON')
        
        # Main album registry table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS album_registry (
                album_key TEXT PRIMARY KEY,
                artist TEXT NOT NULL,
                album TEXT NOT NULL,
                track_count INTEGER,
                file_paths TEXT,  -- JSON array of file paths
                first_discovered TEXT,
                last_scanned TEXT,
                scan_status TEXT DEFAULT 'never_scanned',  -- never_scanned, scanned, matched, failed, manual_review
                match_status TEXT DEFAULT 'unmatched',     -- unmatched, matched, manual, failed
                api_match_date TEXT,
                confidence REAL,
                original_genres TEXT,  -- JSON array
                matched_genres TEXT,   -- JSON array  
                api_sources TEXT,      -- JSON array of sources used
                error_message TEXT,
                manual_review_reason TEXT,
                notes TEXT,
                file_hash TEXT,  -- Hash of file paths for change detection
                updated_at TEXT
            )
        ''')
        
        # Track individual scan sessions
        conn.execute('''
            CREATE TABLE IF NOT EXISTS scan_sessions (
                session_id TEXT PRIMARY KEY,
                started_at TEXT,
                completed_at TEXT,
                music_path TEXT,
                albums_discovered INTEGER DEFAULT 0,
                albums_updated INTEGER DEFAULT 0,
                status TEXT DEFAULT 'running'  -- running, completed, failed
            )
        ''')
        
        # Track API matching sessions
        conn.execute('''
            CREATE TABLE IF NOT EXISTS match_sessions (
                session_id TEXT PRIMARY KEY,
                started_at TEXT,
                completed_at TEXT,
                albums_processed INTEGER DEFAULT 0,
                albums_matched INTEGER DEFAULT 0,
                albums_failed INTEGER DEFAULT 0,
                confidence_threshold REAL,
                api_sources TEXT,  -- JSON array
                dry_run BOOLEAN DEFAULT 0,
                status TEXT DEFAULT 'running'
            )
        ''')
        
        # Create indexes for performance
        conn.execute('CREATE INDEX IF NOT EXISTS idx_scan_status ON album_registry (scan_status)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_match_status ON album_registry (match_status)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_last_scanned ON album_registry (last_scanned)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_artist ON album_registry (artist)')
        
        conn.commit()
        conn.close()
    
    def start_scan_session(self, music_path: str) -> str:
        """Start a new filesystem scan session"""
        session_id = f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        conn = sqlite3.connect(self.db_path)
        conn.execute('''
            INSERT INTO scan_sessions (session_id, started_at, music_path, status)
            VALUES (?, ?, ?, 'running')
        ''', (session_id, datetime.now().isoformat(), music_path))
        conn.commit()
        conn.close()
        
        return session_id
    
    def complete_scan_session(self, session_id: str, albums_discovered: int, albums_updated: int):
        """Mark scan session as completed"""
        conn = sqlite3.connect(self.db_path)
        conn.execute('''
            UPDATE scan_sessions 
            SET completed_at = ?, albums_discovered = ?, albums_updated = ?, status = 'completed'
            WHERE session_id = ?
        ''', (datetime.now().isoformat(), albums_discovered, albums_updated, session_id))
        conn.commit()
        conn.close()
    
    def scan_and_register_albums(self, music_path: str) -> Dict:
        """Scan filesystem and register all albums in the database"""
        print(f"Starting album registry scan of {music_path}")
        session_id = self.start_scan_session(music_path)
        
        # Use existing AlbumScanner to scan filesystem
        scanner = AlbumScanner(music_path)
        scanner.scan_filesystem()
        
        albums_discovered = 0
        albums_updated = 0
        current_time = datetime.now().isoformat()
        
        conn = sqlite3.connect(self.db_path)
        
        for album_key, album_data in scanner.albums.items():
            # Get file paths for this album
            file_paths = [track['file_path'] for track in album_data['tracks'] if track.get('file_path')]
            file_hash = self._calculate_file_hash(file_paths)
            
            # Check if album already exists
            existing = conn.execute(
                'SELECT album_key, file_hash, first_discovered FROM album_registry WHERE album_key = ?',
                (album_key,)
            ).fetchone()
            
            if existing:
                # Album exists - check if files changed
                if existing[1] != file_hash:
                    # Files changed - update registry
                    conn.execute('''
                        UPDATE album_registry 
                        SET track_count = ?, file_paths = ?, last_scanned = ?, 
                            file_hash = ?, updated_at = ?, original_genres = ?
                        WHERE album_key = ?
                    ''', (
                        len(album_data['tracks']),
                        json.dumps(file_paths),
                        current_time,
                        file_hash,
                        current_time,
                        json.dumps(list(album_data['genres'])),
                        album_key
                    ))
                    albums_updated += 1
                else:
                    # Just update last_scanned timestamp
                    conn.execute('''
                        UPDATE album_registry 
                        SET last_scanned = ?, updated_at = ?
                        WHERE album_key = ?
                    ''', (current_time, current_time, album_key))
            else:
                # New album - insert
                conn.execute('''
                    INSERT INTO album_registry (
                        album_key, artist, album, track_count, file_paths,
                        first_discovered, last_scanned, original_genres,
                        file_hash, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    album_key,
                    album_data['artist'],
                    album_data['album'],
                    len(album_data['tracks']),
                    json.dumps(file_paths),
                    current_time,
                    current_time,
                    json.dumps(list(album_data['genres'])),
                    file_hash,
                    current_time
                ))
                albums_discovered += 1
        
        conn.commit()
        conn.close()
        
        self.complete_scan_session(session_id, albums_discovered, albums_updated)
        
        return {
            'session_id': session_id,
            'albums_discovered': albums_discovered,
            'albums_updated': albums_updated,
            'total_albums': len(scanner.albums)
        }
    
    def _calculate_file_hash(self, file_paths: List[str]) -> str:
        """Calculate simple hash of file paths for change detection"""
        import hashlib
        paths_str = '|'.join(sorted(file_paths))
        return hashlib.md5(paths_str.encode()).hexdigest()
    
    def get_scan_status_summary(self) -> Dict:
        """Get summary of album scan statuses"""
        conn = sqlite3.connect(self.db_path)
        
        # Get status counts
        status_counts = {}
        for row in conn.execute('SELECT scan_status, COUNT(*) FROM album_registry GROUP BY scan_status'):
            status_counts[row[0]] = row[1]
        
        match_counts = {}
        for row in conn.execute('SELECT match_status, COUNT(*) FROM album_registry GROUP BY match_status'):
            match_counts[row[0]] = row[1]
        
        # Get total counts
        total_albums = conn.execute('SELECT COUNT(*) FROM album_registry').fetchone()[0]
        
        # Get recent scan activity
        recent_scans = conn.execute('''
            SELECT session_id, started_at, completed_at, albums_discovered, albums_updated
            FROM scan_sessions 
            ORDER BY started_at DESC 
            LIMIT 5
        ''').fetchall()
        
        conn.close()
        
        return {
            'total_albums': total_albums,
            'scan_status_counts': status_counts,
            'match_status_counts': match_counts,
            'recent_scan_sessions': [
                {
                    'session_id': row[0],
                    'started_at': row[1],
                    'completed_at': row[2],
                    'albums_discovered': row[3],
                    'albums_updated': row[4]
                }
                for row in recent_scans
            ]
        }
    
    def get_albums_by_status(self, scan_status: Optional[str] = None, 
                            match_status: Optional[str] = None, 
                            limit: int = 100) -> List[Dict]:
        """Get albums filtered by scan/match status"""
        conn = sqlite3.connect(self.db_path)
        
        query = 'SELECT * FROM album_registry WHERE 1=1'
        params = []
        
        if scan_status:
            query += ' AND scan_status = ?'
            params.append(scan_status)
        
        if match_status:
            query += ' AND match_status = ?'
            params.append(match_status)
        
        query += ' ORDER BY last_scanned DESC LIMIT ?'
        params.append(limit)
        
        cursor = conn.execute(query, params)
        columns = [desc[0] for desc in cursor.description]
        
        albums = []
        for row in cursor.fetchall():
            album = dict(zip(columns, row))
            # Parse JSON fields
            if album['file_paths']:
                album['file_paths'] = json.loads(album['file_paths'])
            if album['original_genres']:
                album['original_genres'] = json.loads(album['original_genres'])
            if album['matched_genres']:
                album['matched_genres'] = json.loads(album['matched_genres'])
            if album['api_sources']:
                album['api_sources'] = json.loads(album['api_sources'])
            albums.append(album)
        
        conn.close()
        return albums
    
    def update_album_match_status(self, album_key: str, match_status: str, 
                                 matched_genres: List[str] = None, 
                                 confidence: float = None,
                                 api_sources: List[str] = None,
                                 error_message: str = None):
        """Update album match status after API processing"""
        conn = sqlite3.connect(self.db_path)
        
        current_time = datetime.now().isoformat()
        
        conn.execute('''
            UPDATE album_registry 
            SET match_status = ?, 
                matched_genres = ?,
                confidence = ?,
                api_sources = ?,
                api_match_date = ?,
                error_message = ?,
                updated_at = ?
            WHERE album_key = ?
        ''', (
            match_status,
            json.dumps(matched_genres) if matched_genres else None,
            confidence,
            json.dumps(api_sources) if api_sources else None,
            current_time,
            error_message,
            current_time,
            album_key
        ))
        
        conn.commit()
        conn.close()
    
    def get_unscanned_albums(self, limit: int = 100) -> List[Dict]:
        """Get albums that haven't been scanned by API matching yet"""
        return self.get_albums_by_status(match_status='unmatched', limit=limit)
    
    def get_album_details(self, album_key: str) -> Optional[Dict]:
        """Get detailed information for a specific album"""
        albums = self.get_albums_by_status(limit=1)
        conn = sqlite3.connect(self.db_path)
        
        cursor = conn.execute('SELECT * FROM album_registry WHERE album_key = ?', (album_key,))
        row = cursor.fetchone()
        
        if not row:
            conn.close()
            return None
        
        columns = [desc[0] for desc in cursor.description]
        album = dict(zip(columns, row))
        
        # Parse JSON fields
        if album['file_paths']:
            album['file_paths'] = json.loads(album['file_paths'])
        if album['original_genres']:
            album['original_genres'] = json.loads(album['original_genres'])
        if album['matched_genres']:
            album['matched_genres'] = json.loads(album['matched_genres'])
        if album['api_sources']:
            album['api_sources'] = json.loads(album['api_sources'])
        
        conn.close()
        return album
    
    def print_status_report(self):
        """Print comprehensive status report"""
        summary = self.get_scan_status_summary()
        
        print("=" * 70)
        print("ALBUM REGISTRY STATUS REPORT")
        print("=" * 70)
        print(f"Total Albums in Registry: {summary['total_albums']}")
        
        print("\nScan Status Breakdown:")
        for status, count in summary['scan_status_counts'].items():
            percentage = (count / summary['total_albums'] * 100) if summary['total_albums'] > 0 else 0
            print(f"  {status:15}: {count:4} ({percentage:5.1f}%)")
        
        print("\nMatch Status Breakdown:")
        for status, count in summary['match_status_counts'].items():
            percentage = (count / summary['total_albums'] * 100) if summary['total_albums'] > 0 else 0
            print(f"  {status:15}: {count:4} ({percentage:5.1f}%)")
        
        print("\nRecent Scan Sessions:")
        for session in summary['recent_scan_sessions']:
            status = "✓" if session['completed_at'] else "⏳"
            print(f"  {status} {session['session_id']:20} | Discovered: {session['albums_discovered']:3} | Updated: {session['albums_updated']:3}")
        
        # Show some sample unscanned albums
        unscanned = self.get_unscanned_albums(5)
        if unscanned:
            print(f"\nSample Unscanned Albums ({len(unscanned)} shown):")
            for album in unscanned:
                genres = album['original_genres'] if album['original_genres'] else []
                genre_str = ', '.join(genres) if genres else 'No genres'
                print(f"  {album['artist']} - {album['album']}")
                print(f"    Tracks: {album['track_count']} | Current genres: {genre_str}")


if __name__ == "__main__":
    # Example usage
    registry = AlbumRegistry()
    
    # Scan and register albums
    results = registry.scan_and_register_albums("/Volumes/T7/Albums")
    print(f"Scan completed: {results}")
    
    # Print status report
    registry.print_status_report()