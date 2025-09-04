#!/usr/bin/env python3
"""
Music Library Dashboard - Comprehensive Music Management Interface
Shows live progress, job history, and genre modifications
"""

from flask import Flask, render_template, request, jsonify
import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Tuple, Optional
import difflib
import re
import os
import time
from pathlib import Path
from process_cleanup import ProcessCleanup

app = Flask(__name__)

class MusicLibraryDashboard:
    def __init__(self, db_path: str = "batch_processing.db", albums_db_path: str = "albums.db", verbose: bool = False):
        self.db_path = db_path
        self.albums_db_path = albums_db_path
        self.verbose = verbose
        self.init_albums_database()
    
    def get_connection(self):
        """Get database connection"""
        return sqlite3.connect(self.db_path)
    
    def get_albums_connection(self):
        """Get albums database connection with proper timeout and threading support"""
        conn = sqlite3.connect(self.albums_db_path, timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        # Set WAL mode for better concurrency
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA synchronous=NORMAL')
        conn.execute('PRAGMA cache_size=10000')
        conn.execute('PRAGMA temp_store=MEMORY')
        # Attach batch processing database for cross-database queries
        conn.execute(f'ATTACH DATABASE "{self.db_path}" AS batch_processing')
        return conn
    
    def parse_genres(self, genre_string: str) -> List[str]:
        """Parse genre string into list"""
        if not genre_string or genre_string == 'null':
            return []
        
        try:
            # Try JSON parsing first
            if genre_string.startswith('['):
                return json.loads(genre_string)
            else:
                # Split on semicolon
                return [g.strip() for g in genre_string.split(';') if g.strip()]
        except:
            return [genre_string] if genre_string else []
    
    def create_genre_diff(self, original: List[str], suggested: List[str], final: List[str]) -> Dict:
        """Create detailed diff between genre lists"""
        original_set = set([g.lower() for g in original])
        suggested_set = set([g.lower() for g in suggested])
        final_set = set([g.lower() for g in final])
        
        # Map back to proper case for display
        original_map = {g.lower(): g for g in original}
        suggested_map = {g.lower(): g for g in suggested}
        final_map = {g.lower(): g for g in final}
        
        return {
            'original': original,
            'suggested': suggested,
            'final': final,
            'added': [final_map[g] for g in final_set - original_set],
            'removed': [original_map[g] for g in original_set - final_set],
            'kept': [final_map[g] for g in final_set & original_set],
            'suggested_only': [suggested_map[g] for g in suggested_set - final_set],
            'has_changes': len(final_set - original_set) > 0 or len(original_set - final_set) > 0
        }
    
    def get_batch_jobs(self) -> List[Dict]:
        """Get all batch jobs"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT job_id, name, created_at, total_albums, processed, 
                       successful, failed, needs_review, skipped, status, 
                       confidence_threshold, dry_run
                FROM batch_jobs 
                ORDER BY created_at DESC
            ''')
            
            jobs = []
            for row in cursor.fetchall():
                jobs.append({
                    'job_id': row[0],
                    'name': row[1],
                    'created_at': row[2],
                    'total_albums': row[3],
                    'processed': row[4],
                    'successful': row[5],
                    'failed': row[6],
                    'needs_review': row[7],
                    'skipped': row[8],
                    'status': row[9],
                    'confidence_threshold': row[10],
                    'dry_run': row[11]
                })
            
            return jobs
    
    def get_album_results(self, job_id: str, status_filter: str = None, 
                         changes_only: bool = False, page: int = 1, 
                         per_page: int = 50) -> Tuple[List[Dict], int]:
        """Get album results with pagination"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Build query
            where_clause = "WHERE job_id = ?"
            params = [job_id]
            
            if status_filter and status_filter != 'all':
                where_clause += " AND status = ?"
                params.append(status_filter)
            
            # Count total
            count_query = f"SELECT COUNT(*) FROM album_results {where_clause}"
            cursor.execute(count_query, params)
            total = cursor.fetchone()[0]
            
            # Get results
            offset = (page - 1) * per_page
            query = f'''
                SELECT album_key, artist, album, original_genres, 
                       suggested_genres, final_genres, confidence, 
                       sources_used, files_updated, status, 
                       error_message, processing_time, created_at
                FROM album_results 
                {where_clause}
                ORDER BY confidence DESC, created_at DESC
                LIMIT ? OFFSET ?
            '''
            params.extend([per_page, offset])
            
            cursor.execute(query, params)
            
            results = []
            for row in cursor.fetchall():
                original = self.parse_genres(row[3])
                suggested = self.parse_genres(row[4])
                final = self.parse_genres(row[5])
                
                diff = self.create_genre_diff(original, suggested, final)
                
                # Filter changes only if requested
                if changes_only and not diff['has_changes']:
                    continue
                
                results.append({
                    'album_key': row[0],
                    'artist': row[1],
                    'album': row[2],
                    'original_genres': original,
                    'suggested_genres': suggested,
                    'final_genres': final,
                    'confidence': row[6],
                    'sources_used': row[7],
                    'files_updated': row[8],
                    'status': row[9],
                    'error_message': row[10],
                    'processing_time': row[11],
                    'created_at': row[12],
                    'diff': diff
                })
            
            return results, total
    
    def get_statistics(self, job_id: str) -> Dict:
        """Get statistics for a job"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Basic stats
            cursor.execute('''
                SELECT status, COUNT(*) 
                FROM album_results 
                WHERE job_id = ? 
                GROUP BY status
            ''', (job_id,))
            status_counts = dict(cursor.fetchall())
            
            # Confidence distribution
            cursor.execute('''
                SELECT 
                    CASE 
                        WHEN confidence >= 90 THEN '90%+'
                        WHEN confidence >= 80 THEN '80-89%'
                        WHEN confidence >= 70 THEN '70-79%'
                        WHEN confidence >= 50 THEN '50-69%'
                        ELSE '<50%'
                    END as conf_range,
                    COUNT(*)
                FROM album_results 
                WHERE job_id = ?
                GROUP BY conf_range
            ''', (job_id,))
            confidence_dist = dict(cursor.fetchall())
            
            # Genre addition stats
            cursor.execute('''
                SELECT album_key, original_genres, final_genres
                FROM album_results 
                WHERE job_id = ? AND final_genres IS NOT NULL
            ''', (job_id,))
            
            total_additions = 0
            albums_with_additions = 0
            
            for row in cursor.fetchall():
                original = len(self.parse_genres(row[1]))
                final = len(self.parse_genres(row[2]))
                if final > original:
                    albums_with_additions += 1
                    total_additions += (final - original)
            
            return {
                'status_counts': status_counts,
                'confidence_distribution': confidence_dist,
                'total_additions': total_additions,
                'albums_with_additions': albums_with_additions
            }
    
    def get_live_progress(self) -> Dict:
        """Get live progress information for currently running jobs"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get running jobs
            cursor.execute('''
                SELECT job_id, name, created_at, total_albums, processed, 
                       successful, failed, needs_review, skipped, status
                FROM batch_jobs 
                WHERE status IN ('running', 'pending', 'processing')
                ORDER BY created_at DESC
            ''')
            
            running_jobs = []
            for row in cursor.fetchall():
                job_progress = {
                    'job_id': row[0],
                    'name': row[1],
                    'created_at': row[2],
                    'total_albums': row[3],
                    'processed': row[4],
                    'successful': row[5],
                    'failed': row[6],
                    'needs_review': row[7],
                    'skipped': row[8],
                    'status': row[9],
                    'progress_percent': (row[4] / row[3] * 100) if row[3] > 0 else 0
                }
                
                # Get latest processed album for this job
                cursor.execute('''
                    SELECT artist, album, created_at 
                    FROM album_results 
                    WHERE job_id = ? 
                    ORDER BY created_at DESC 
                    LIMIT 1
                ''', (row[0],))
                
                latest = cursor.fetchone()
                if latest:
                    job_progress['latest_album'] = {
                        'artist': latest[0],
                        'album': latest[1],
                        'processed_at': latest[2]
                    }
                
                # Calculate processing rate (albums per minute in last 5 minutes)
                cursor.execute('''
                    SELECT COUNT(*) 
                    FROM album_results 
                    WHERE job_id = ? AND created_at > datetime('now', '-5 minutes')
                ''', (row[0],))
                
                recent_count = cursor.fetchone()[0]
                job_progress['processing_rate'] = recent_count  # albums in last 5 minutes
                
                # Estimate remaining time
                if job_progress['processing_rate'] > 0 and row[3] > row[4]:
                    remaining_albums = row[3] - row[4]
                    estimated_minutes = (remaining_albums / job_progress['processing_rate']) * 5
                    job_progress['eta_minutes'] = int(estimated_minutes)
                else:
                    job_progress['eta_minutes'] = None
                
                running_jobs.append(job_progress)
            
            return {
                'running_jobs': running_jobs,
                'has_active_jobs': len(running_jobs) > 0,
                'total_active_jobs': len(running_jobs)
            }
    
    def init_albums_database(self):
        """Initialize albums database with clean ID3-only schema"""
        if self.verbose:
            print("├── Initializing albums database schema...")
            
        try:
            with self.get_albums_connection() as conn:
                cursor = conn.cursor()
                
                if self.verbose:
                    print("├── ├── Creating albums table...")
                # Create albums table with clean ID3 data only
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS albums (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        album_key TEXT UNIQUE NOT NULL,
                        artist TEXT,
                        album TEXT,
                        year INTEGER,
                        genre TEXT,
                        track_count INTEGER DEFAULT 0,
                        total_duration REAL DEFAULT 0.0,
                        file_path TEXT,
                        raw_metadata_json TEXT,
                        artwork_data BLOB,
                        artwork_format TEXT
                    )
                ''')
                
                if self.verbose:
                    print("├── ├── Creating tracks table...")
                # Create tracks table (clean ID3 data only)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS tracks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        album_id INTEGER NOT NULL,
                        track_number INTEGER,
                        title TEXT,
                        artist TEXT,
                        duration REAL,
                        file_path TEXT NOT NULL,
                        file_format TEXT,
                        file_size INTEGER,
                        raw_metadata_json TEXT,
                        FOREIGN KEY (album_id) REFERENCES albums (id)
                    )
                ''')
                
                if self.verbose:
                    print("├── ├── Creating database indexes...")
                # Create performance indexes (clean ID3 only)
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_albums_artist ON albums(artist)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_albums_album ON albums(album)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_albums_genre ON albums(genre)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_albums_album_key ON albums(album_key)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_albums_search ON albums(artist, album)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_tracks_album ON tracks(album_id)')
                
                if self.verbose:
                    print("├── ├── Committing database changes...")
                conn.commit()
                
                if self.verbose:
                    print("├── ✅ Database schema initialized successfully")
                    
        except Exception as e:
            if self.verbose:
                print(f"├── ❌ Database initialization error: {e}")
            raise
    
    def get_album_status(self, album_key: str) -> Dict:
        """Get scan and processing status from proper databases"""
        status = {
            'scan_status': 'never_scanned',
            'last_scanned': None,
            'match_status': 'never_matched',
            'last_matched': None,
            'match_confidence': None,
            'scan_error': None,
            'batch_status': None
        }
        
        # Check album registry for scan status
        try:
            registry_conn = sqlite3.connect('album_registry.db', timeout=5.0)
            cursor = registry_conn.execute(
                'SELECT last_scanned, scan_status FROM album_registry WHERE album_key = ?',
                (album_key,)
            )
            registry_result = cursor.fetchone()
            if registry_result:
                status['last_scanned'] = registry_result[0] 
                status['scan_status'] = registry_result[1] or 'scanned'
            registry_conn.close()
        except sqlite3.Error:
            pass  # Registry may not exist yet
        
        # Check batch processing for match status
        try:
            batch_conn = sqlite3.connect(self.db_path, timeout=5.0)
            cursor = batch_conn.execute(
                'SELECT status, confidence, created_at FROM album_results WHERE album_key = ? ORDER BY created_at DESC LIMIT 1',
                (album_key,)
            )
            batch_result = cursor.fetchone()
            if batch_result:
                status['batch_status'] = batch_result[0]
                status['match_confidence'] = batch_result[1]
                status['last_matched'] = batch_result[2]
                if batch_result[0] in ['matched', 'approved']:
                    status['match_status'] = 'matched'
            batch_conn.close()
        except sqlite3.Error:
            pass  # Batch processing may not exist yet
            
        return status
    
    def extract_hybrid_metadata(self, file_path: str) -> Dict:
        """Extract both structured fields and complete raw metadata JSON"""
        from mutagen import File as MutagenFile
        import os
        
        try:
            mutagen_file = MutagenFile(file_path)
            if not mutagen_file:
                return self._empty_metadata(file_path)
            
            tags = mutagen_file.tags or {}
            info = mutagen_file.info
            
            # Extract key fields for database columns (performance)
            # Support multiple tag formats: ID3 (MP3), Vorbis (FLAC/OGG), MP4, APE
            extracted = {
                'title': self._get_tag_value(tags, ['TIT2', 'TITLE', 'Title', 'title', '©nam']),
                'artist': self._get_tag_value(tags, ['TPE1', 'ARTIST', 'Artist', 'artist', '©ART']),
                'album': self._get_tag_value(tags, ['TALB', 'ALBUM', 'Album', 'album', '©alb']),
                'album_artist': self._get_tag_value(tags, ['TPE2', 'ALBUMARTIST', 'AlbumArtist', 'albumartist', 'aART']),
                'year': self._extract_year(tags),
                'genre': self._get_tag_value(tags, ['TCON', 'GENRE', 'Genre', 'genre', '©gen']),
                'track_number': self._extract_track_number(tags),
                'duration': getattr(info, 'length', 0) or 0
            }
            
            # Check if this is a compilation
            compilation = self._get_tag_value(tags, ['TCMP', 'COMPILATION', 'Compilation', 'compilation'])
            is_compilation = compilation.lower() in ['1', 'true', 'yes'] if compilation else False
            
            # For compilations, use "Various Artists" as album artist
            if is_compilation and not extracted['album_artist']:
                extracted['album_artist'] = 'Various Artists'
            elif not extracted['album_artist'] and extracted['artist']:
                extracted['album_artist'] = extracted['artist']
            
            # Build complete raw metadata JSON
            raw_metadata = {
                'format': self._get_format_info(mutagen_file),
                'tags': self._convert_tags_to_dict(tags),
                'technical': {
                    'bitrate': getattr(info, 'bitrate', 0),
                    'sample_rate': getattr(info, 'sample_rate', 0),
                    'channels': getattr(info, 'channels', 0),
                    'duration': getattr(info, 'length', 0),
                    'file_size': os.path.getsize(file_path) if os.path.exists(file_path) else 0
                }
            }
            
            # Extract artwork if available
            artwork_data, artwork_format = self._extract_artwork(mutagen_file)
            
            return {
                'extracted': extracted,
                'raw_json': json.dumps(raw_metadata, default=str),
                'file_format': os.path.splitext(file_path)[1].lower().lstrip('.'),
                'file_size': os.path.getsize(file_path) if os.path.exists(file_path) else 0,
                'artwork_data': artwork_data,
                'artwork_format': artwork_format
            }
            
        except Exception as e:
            print(f"Warning: Could not extract metadata from {file_path}: {e}")
            return self._empty_metadata(file_path)
    
    def _empty_metadata(self, file_path: str) -> Dict:
        """Return empty metadata structure"""
        import os
        return {
            'extracted': {
                'title': '', 'artist': '', 'album': '', 'album_artist': '',
                'year': None, 'genre': '', 'track_number': None, 'duration': 0
            },
            'raw_json': json.dumps({'format': 'unknown', 'tags': {}, 'technical': {}}),
            'file_format': os.path.splitext(file_path)[1].lower().lstrip('.'),
            'file_size': os.path.getsize(file_path) if os.path.exists(file_path) else 0,
            'artwork_data': None,
            'artwork_format': None
        }
    
    def _get_tag_value(self, tags, tag_names: List[str]) -> str:
        """Get tag value from multiple possible tag names"""
        for tag_name in tag_names:
            try:
                if tag_name in tags:
                    value = tags[tag_name]
                    if isinstance(value, list) and value:
                        return str(value[0])
                    elif value:
                        return str(value)
            except (ValueError, TypeError, KeyError):
                # Handle mutagen FLAC tag checking issues
                continue
        return ''
    
    def _extract_year(self, tags) -> Optional[int]:
        """Extract year from various date formats"""
        year_str = self._get_tag_value(tags, ['TDRC', 'TYER', 'DATE', 'Year', 'date', '©day'])
        if year_str:
            # Extract year from formats like "2023", "2023-01-01", etc.
            import re
            match = re.search(r'(\d{4})', year_str)
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    pass
        return None
    
    def _extract_track_number(self, tags) -> Optional[int]:
        """Extract track number from various formats"""
        track_str = self._get_tag_value(tags, ['TRCK', 'TRACKNUMBER', 'TrackNumber', 'tracknumber', 'trkn'])
        if track_str:
            # Handle formats like "1", "1/12", "01"
            import re
            match = re.search(r'^(\d+)', track_str)
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    pass
        return None
    
    def _get_format_info(self, mutagen_file) -> str:
        """Get audio format information"""
        if hasattr(mutagen_file, 'mime'):
            mime_type = mutagen_file.mime[0] if isinstance(mutagen_file.mime, list) else mutagen_file.mime
            return mime_type.split('/')[-1].upper()
        elif hasattr(mutagen_file, 'info'):
            return type(mutagen_file.info).__name__.replace('Info', '').upper()
        return 'Unknown'
    
    def _convert_tags_to_dict(self, tags) -> Dict:
        """Convert all tags to serializable dictionary"""
        tag_dict = {}
        for key, value in tags.items():
            if isinstance(value, list):
                tag_dict[key] = [str(v) for v in value]
            else:
                tag_dict[key] = str(value)
        return tag_dict
    
    def _extract_artwork(self, mutagen_file) -> tuple:
        """Extract album artwork from audio file"""
        try:
            if not mutagen_file:
                return None, None
            
            # Handle different file formats
            file_type = type(mutagen_file).__name__.lower()
            
            if 'flac' in file_type:
                # FLAC files
                if hasattr(mutagen_file, 'pictures') and mutagen_file.pictures:
                    picture = mutagen_file.pictures[0]
                    return picture.data, picture.mime.split('/')[-1]
            
            elif 'mp3' in file_type or 'id3' in file_type:
                # MP3 files with ID3 tags
                if hasattr(mutagen_file, 'tags') and mutagen_file.tags:
                    # Try APIC (ID3v2.3/2.4)
                    if 'APIC:' in mutagen_file.tags:
                        apic = mutagen_file.tags['APIC:']
                        return apic.data, apic.mime.split('/')[-1]
                    # Try other APIC variants
                    for key in mutagen_file.tags.keys():
                        if key.startswith('APIC'):
                            apic = mutagen_file.tags[key]
                            return apic.data, apic.mime.split('/')[-1]
            
            elif 'mp4' in file_type:
                # MP4/M4A files
                if hasattr(mutagen_file, 'tags') and mutagen_file.tags and 'covr' in mutagen_file.tags:
                    cover = mutagen_file.tags['covr'][0]
                    # MP4 covers are usually JPEG or PNG
                    format_type = 'png' if cover.imageformat == cover.FORMAT_PNG else 'jpeg'
                    return bytes(cover), format_type
                    
        except Exception as e:
            print(f"Warning: Could not extract artwork: {e}")
            
        return None, None
    
    def scan_and_store_library(self, music_path: str = "/Volumes/T7/Albums") -> Dict:
        """Scan music library and store all metadata including artwork in database (fully idempotent)"""
        from album_scanner import AlbumScanner
        
        print("🔍 Scanning music library...")
        
        # Use AlbumScanner to scan filesystem
        scanner = AlbumScanner(music_path)
        scanner.scan_filesystem()
        
        stats = {
            'albums_processed': 0,
            'albums_updated': 0,
            'tracks_processed': 0,
            'artwork_extracted': 0,
            'errors': []
        }
        
        with self.get_albums_connection() as conn:
            cursor = conn.cursor()
            
            for album_key, album_info in scanner.albums.items():
                try:
                    # Get representative track for album-level metadata
                    representative_track = album_info['tracks'][0] if album_info['tracks'] else None
                    if not representative_track:
                        continue
                    
                    # Extract metadata from representative track
                    album_metadata = self.extract_hybrid_metadata(representative_track['file_path'])
                    extracted = album_metadata['extracted']
                    
                    # Calculate album totals
                    total_duration = 0
                    track_count = len(album_info['tracks'])
                    
                    # Store or update album with artwork (fully idempotent - overwrite everything)
                    cursor.execute('''
                        INSERT INTO albums (
                            album_key, artist, album, year, genre, track_count, 
                            total_duration, file_path, raw_metadata_json, 
                            artwork_data, artwork_format
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(album_key) DO UPDATE SET
                            artist = excluded.artist,
                            album = excluded.album,
                            year = excluded.year,
                            genre = excluded.genre,
                            track_count = excluded.track_count,
                            total_duration = excluded.total_duration,
                            file_path = excluded.file_path,
                            raw_metadata_json = excluded.raw_metadata_json,
                            artwork_data = excluded.artwork_data,
                            artwork_format = excluded.artwork_format
                    ''', (
                        album_key,
                        extracted['album_artist'] or extracted['artist'],
                        extracted['album'],
                        extracted['year'],
                        extracted['genre'],
                        track_count,
                        0,  # Will calculate after processing tracks
                        os.path.dirname(representative_track['file_path']),
                        album_metadata['raw_json'],
                        album_metadata['artwork_data'],
                        album_metadata['artwork_format']
                    ))
                    
                    # Get album ID
                    album_id = cursor.lastrowid
                    
                    # Delete existing tracks for this album
                    cursor.execute('DELETE FROM tracks WHERE album_id = ?', (album_id,))
                    
                    # Process all tracks
                    for track_info in album_info['tracks']:
                        try:
                            track_metadata = self.extract_hybrid_metadata(track_info['file_path'])
                            track_extracted = track_metadata['extracted']
                            
                            cursor.execute('''
                                INSERT INTO tracks (
                                    album_id, track_number, title, artist, duration,
                                    file_path, file_format, file_size, raw_metadata_json
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (
                                album_id,
                                track_extracted['track_number'],
                                track_extracted['title'],
                                track_extracted['artist'],
                                track_extracted['duration'],
                                track_info['file_path'],
                                track_metadata['file_format'],
                                track_metadata['file_size'],
                                track_metadata['raw_json']
                            ))
                            
                            total_duration += track_extracted['duration']
                            stats['tracks_processed'] += 1
                            
                        except Exception as e:
                            error_msg = f"Error processing track {track_info['file_path']}: {e}"
                            print(f"Warning: {error_msg}")
                            stats['errors'].append(error_msg)
                    
                    # Update album with total duration
                    cursor.execute('''
                        UPDATE albums SET total_duration = ? WHERE id = ?
                    ''', (total_duration, album_id))
                    
                    # Track artwork extraction
                    if album_metadata['artwork_data']:
                        stats['artwork_extracted'] += 1
                    
                    stats['albums_processed'] += 1
                    
                    if stats['albums_processed'] % 100 == 0:
                        print(f"Processed {stats['albums_processed']} albums...")
                        
                except Exception as e:
                    error_msg = f"Error processing album {album_key}: {e}"
                    print(f"Warning: {error_msg}")
                    stats['errors'].append(error_msg)
            
            conn.commit()
        
        print(f"✅ Library scan complete!")
        print(f"📊 Processed {stats['albums_processed']} albums, {stats['tracks_processed']} tracks")
        print(f"🎨 Extracted artwork for {stats['artwork_extracted']} albums")
        if stats['errors']:
            print(f"⚠️  {len(stats['errors'])} errors occurred")
            
        return stats

    def rescan_single_album(self, album_id: int) -> Dict:
        """Rescan a specific album by ID and update its metadata and artwork"""
        print(f"🔍 Rescanning album ID {album_id}...")
        
        with self.get_albums_connection() as conn:
            cursor = conn.cursor()
            
            # Get the album's file path
            cursor.execute('SELECT file_path, album_key FROM albums WHERE id = ?', (album_id,))
            result = cursor.fetchone()
            
            if not result:
                raise ValueError(f"Album with ID {album_id} not found")
            
            file_path, album_key = result
            
            if not os.path.exists(file_path) or not os.path.isdir(file_path):
                raise ValueError(f"Album directory not found: {file_path}")
            
            # Find audio files in the album directory
            audio_extensions = ['.flac', '.mp3', '.m4a', '.ogg', '.wav', '.aiff', '.wma']
            audio_files = []
            
            try:
                for filename in os.listdir(file_path):
                    if any(filename.lower().endswith(ext) for ext in audio_extensions):
                        audio_files.append(os.path.join(file_path, filename))
            except Exception as e:
                raise ValueError(f"Could not read album directory: {e}")
            
            if not audio_files:
                raise ValueError(f"No audio files found in {file_path}")
            
            # Use first audio file as representative track for album metadata
            representative_file = audio_files[0]
            album_metadata = self.extract_hybrid_metadata(representative_file)
            extracted = album_metadata['extracted']
            
            # Calculate album totals
            total_duration = 0
            track_count = len(audio_files)
            
            # Update album with new metadata and artwork
            cursor.execute('''
                UPDATE albums SET 
                    artist = ?, album = ?, year = ?, genre = ?, track_count = ?,
                    total_duration = ?, raw_metadata_json = ?, last_scanned = CURRENT_TIMESTAMP,
                    artwork_data = ?, artwork_format = ?, scan_error = NULL
                WHERE id = ?
            ''', (
                extracted['album_artist'] or extracted['artist'],
                extracted['album'],
                extracted['year'],
                extracted['genre'],
                track_count,
                0,  # Will update after processing tracks
                album_metadata['raw_json'],
                album_metadata['artwork_data'],
                album_metadata['artwork_format'],
                album_id
            ))
            
            # Delete and re-insert tracks
            cursor.execute('DELETE FROM tracks WHERE album_id = ?', (album_id,))
            
            # Process all tracks
            tracks_processed = 0
            for audio_file in audio_files:
                try:
                    track_metadata = self.extract_hybrid_metadata(audio_file)
                    track_extracted = track_metadata['extracted']
                    
                    cursor.execute('''
                        INSERT INTO tracks (
                            album_id, track_number, title, artist, duration,
                            file_path, file_format, file_size, raw_metadata_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        album_id,
                        track_extracted['track_number'],
                        track_extracted['title'],
                        track_extracted['artist'],
                        track_extracted['duration'],
                        audio_file,
                        track_metadata['file_format'],
                        track_metadata['file_size'],
                        track_metadata['raw_json']
                    ))
                    
                    total_duration += track_extracted['duration']
                    tracks_processed += 1
                    
                except Exception as e:
                    print(f"Warning: Could not process track {audio_file}: {e}")
            
            # Update total duration
            cursor.execute('UPDATE albums SET total_duration = ? WHERE id = ?', (total_duration, album_id))
            
            conn.commit()
        
        result = {
            'metadata_updated': True,
            'artwork_extracted': bool(album_metadata['artwork_data']),
            'tracks_processed': tracks_processed
        }
        
        print(f"✅ Album {album_id} rescanned successfully!")
        print(f"📊 Processed {tracks_processed} tracks, artwork: {'extracted' if result['artwork_extracted'] else 'not found'}")
        
        return result

    def consolidate_compilation_albums(self) -> Dict:
        """Find and consolidate albums that should be treated as compilations"""
        print("🎵 Consolidating compilation albums...")
        
        stats = {
            'compilations_found': 0,
            'albums_consolidated': 0,
            'tracks_moved': 0
        }
        
        with self.get_albums_connection() as conn:
            cursor = conn.cursor()
            
            # Find potential compilation albums by checking raw metadata for compilation tags
            cursor.execute('''
                SELECT id, artist, album, raw_metadata_json, file_path
                FROM albums 
                WHERE raw_metadata_json LIKE '%"compilation"%' 
                   OR raw_metadata_json LIKE '%"COMPILATION"%'
                   OR raw_metadata_json LIKE '%"Compilation"%'
                ORDER BY album, artist
            ''')
            
            potential_compilations = cursor.fetchall()
            compilation_groups = {}
            
            # Group albums by album name
            for album_id, artist, album, raw_json, file_path in potential_compilations:
                try:
                    raw_data = json.loads(raw_json)
                    compilation_tag = None
                    
                    # Check for compilation tag in various formats
                    if 'tags' in raw_data:
                        tags = raw_data['tags']
                        for key in ['compilation', 'COMPILATION', 'Compilation', 'TCMP']:
                            if key in tags:
                                compilation_tag = tags[key]
                                if isinstance(compilation_tag, list):
                                    compilation_tag = compilation_tag[0] if compilation_tag else None
                                break
                    
                    # Check if it's marked as compilation
                    if compilation_tag and str(compilation_tag).lower() in ['1', 'true', 'yes']:
                        if album not in compilation_groups:
                            compilation_groups[album] = []
                        compilation_groups[album].append((album_id, artist, file_path))
                        stats['compilations_found'] += 1
                        
                except Exception as e:
                    print(f"Warning: Could not parse metadata for album {album_id}: {e}")
            
            # Process each compilation group
            for album_name, album_entries in compilation_groups.items():
                if len(album_entries) > 1:  # Only consolidate if there are multiple entries
                    print(f"Consolidating compilation: {album_name} ({len(album_entries)} entries)")
                    
                    # Keep the first entry as the master, consolidate others into it
                    master_id, _, master_path = album_entries[0]
                    
                    # Update master album to "Various Artists"
                    cursor.execute('''
                        UPDATE albums SET artist = 'Various Artists' WHERE id = ?
                    ''', (master_id,))
                    
                    # Move all tracks from other albums to the master
                    for album_id, artist, file_path in album_entries[1:]:
                        # Move tracks to master album
                        cursor.execute('''
                            UPDATE tracks SET album_id = ? WHERE album_id = ?
                        ''', (master_id, album_id))
                        
                        # Count moved tracks
                        cursor.execute('SELECT COUNT(*) FROM tracks WHERE album_id = ? AND id IN (SELECT id FROM tracks WHERE album_id = ? LIMIT 1000)', (master_id, master_id))
                        
                        # Delete the duplicate album entry
                        cursor.execute('DELETE FROM albums WHERE id = ?', (album_id,))
                        
                        stats['albums_consolidated'] += 1
                    
                    # Recalculate track count and duration for master album
                    cursor.execute('''
                        SELECT COUNT(*), COALESCE(SUM(duration), 0) 
                        FROM tracks WHERE album_id = ?
                    ''', (master_id,))
                    track_count, total_duration = cursor.fetchone()
                    
                    cursor.execute('''
                        UPDATE albums SET track_count = ?, total_duration = ? WHERE id = ?
                    ''', (track_count, total_duration, master_id))
                    
                    stats['tracks_moved'] += track_count
            
            conn.commit()
        
        print(f"✅ Consolidation complete!")
        print(f"📊 Found {stats['compilations_found']} compilation tracks")
        print(f"🔗 Consolidated {stats['albums_consolidated']} duplicate albums")
        print(f"🎵 Moved {stats['tracks_moved']} tracks")
        
        return stats

    def extract_artwork_for_all_albums(self) -> Dict:
        """Extract artwork for all albums that don't have it"""
        print("🎨 Extracting artwork for all albums...")
        
        stats = {
            'albums_processed': 0,
            'artwork_extracted': 0,
            'errors': []
        }
        
        with self.get_albums_connection() as conn:
            cursor = conn.cursor()
            
            # Get albums without artwork
            cursor.execute('''
                SELECT id, file_path FROM albums 
                WHERE artwork_data IS NULL 
                ORDER BY id
            ''')
            albums = cursor.fetchall()
            
            print(f"Found {len(albums)} albums without artwork")
            
            for album_id, file_path in albums:
                try:
                    stats['albums_processed'] += 1
                    
                    # Find a representative track file
                    import os
                    from pathlib import Path
                    
                    audio_files = []
                    audio_extensions = ['.flac', '.mp3', '.m4a', '.ogg', '.wav', '.aiff', '.wma']
                    
                    try:
                        if os.path.exists(file_path) and os.path.isdir(file_path):
                            for filename in os.listdir(file_path):
                                if any(filename.lower().endswith(ext) for ext in audio_extensions):
                                    audio_files.append(os.path.join(file_path, filename))
                                    break  # Just need one file for artwork
                    except Exception:
                        continue
                    
                    if not audio_files:
                        continue
                    
                    # Try to extract artwork
                    from mutagen import File as MutagenFile
                    mutagen_file = MutagenFile(audio_files[0])
                    
                    if mutagen_file:
                        artwork_data, artwork_format = self._extract_artwork(mutagen_file)
                        
                        if artwork_data:
                            cursor.execute('''
                                UPDATE albums SET artwork_data = ?, artwork_format = ? 
                                WHERE id = ?
                            ''', (artwork_data, artwork_format, album_id))
                            
                            stats['artwork_extracted'] += 1
                            
                            if stats['albums_processed'] % 10 == 0:
                                print(f"Processed {stats['albums_processed']} albums, extracted {stats['artwork_extracted']} artworks")
                    
                except Exception as e:
                    error_msg = f"Error extracting artwork for album {album_id}: {e}"
                    print(f"Warning: {error_msg}")
                    stats['errors'].append(error_msg)
            
            conn.commit()
        
        print(f"✅ Artwork extraction complete! Extracted artwork for {stats['artwork_extracted']} of {stats['albums_processed']} albums.")
        return stats

    def rescan_failed_albums(self) -> Dict:
        """Re-scan albums that had scan errors with improved extraction"""
        print("🔄 Re-scanning albums with scan errors...")
        
        stats = {
            'albums_rescanned': 0,
            'albums_fixed': 0,
            'still_failed': 0,
            'errors': []
        }
        
        with self.get_albums_connection() as conn:
            cursor = conn.cursor()
            
            # Get albums with scan errors
            cursor.execute('SELECT id, file_path FROM albums WHERE scan_error IS NOT NULL')
            failed_albums = cursor.fetchall()
            
            print(f"Found {len(failed_albums)} albums with scan errors")
            
            for album_id, file_path in failed_albums:
                try:
                    stats['albums_rescanned'] += 1
                    
                    # Find audio files using robust directory scanning (handles Unicode/special chars)
                    import os
                    from pathlib import Path
                    
                    audio_files = []
                    audio_extensions = ['.flac', '.mp3', '.m4a', '.ogg', '.wav', '.aiff', '.wma']
                    
                    try:
                        # Use os.listdir for immediate directory
                        if os.path.exists(file_path) and os.path.isdir(file_path):
                            for filename in os.listdir(file_path):
                                if any(filename.lower().endswith(ext) for ext in audio_extensions):
                                    audio_files.append(os.path.join(file_path, filename))
                        
                        # Also check subdirectories using pathlib (handles Unicode better)
                        if not audio_files:
                            path_obj = Path(file_path)
                            for ext in audio_extensions:
                                audio_files.extend(list(path_obj.rglob(f'*{ext}')))
                                audio_files.extend(list(path_obj.rglob(f'*{ext.upper()}')))
                        
                        # Convert Path objects to strings
                        audio_files = [str(f) for f in audio_files]
                        
                    except (OSError, UnicodeError, PermissionError) as e:
                        print(f"⚠️ Error accessing directory {file_path}: {e}")
                        continue
                    
                    if not audio_files:
                        print(f"⚠️ No audio files found in {file_path}")
                        continue
                    
                    # Try the first audio file
                    representative_file = audio_files[0]
                    album_metadata = self.extract_hybrid_metadata(representative_file)
                    
                    # Check if extraction was successful
                    extracted = album_metadata['extracted']
                    if extracted['artist'] or extracted['album'] or extracted['title']:
                        # Success! Update the album
                        cursor.execute('''
                            UPDATE albums SET 
                                artist = ?, album = ?, year = ?, genre = ?, 
                                raw_metadata_json = ?, scan_error = NULL,
                                artwork_data = ?, artwork_format = ?,
                                last_scanned = CURRENT_TIMESTAMP
                            WHERE id = ?
                        ''', (
                            extracted['album_artist'] or extracted['artist'],
                            extracted['album'],
                            extracted['year'],
                            extracted['genre'],
                            album_metadata['raw_json'],
                            album_metadata['artwork_data'],
                            album_metadata['artwork_format'],
                            album_id
                        ))
                        
                        # Also update tracks if any exist
                        cursor.execute('DELETE FROM tracks WHERE album_id = ?', (album_id,))
                        
                        # Re-process tracks
                        total_duration = 0
                        for track_file in audio_files:
                            try:
                                track_metadata = self.extract_hybrid_metadata(track_file)
                                track_extracted = track_metadata['extracted']
                                
                                cursor.execute('''
                                    INSERT INTO tracks (
                                        album_id, track_number, title, artist, duration,
                                        file_path, file_format, file_size, raw_metadata_json
                                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                                ''', (
                                    album_id,
                                    track_extracted['track_number'],
                                    track_extracted['title'],
                                    track_extracted['artist'],
                                    track_extracted['duration'],
                                    track_file,
                                    track_metadata['file_format'],
                                    track_metadata['file_size'],
                                    track_metadata['raw_json']
                                ))
                                
                                total_duration += track_extracted['duration']
                                
                            except Exception as e:
                                print(f"Warning: Could not process track {track_file}: {e}")
                        
                        # Update total duration and track count
                        cursor.execute('''
                            UPDATE albums SET total_duration = ?, track_count = ? WHERE id = ?
                        ''', (total_duration, len(audio_files), album_id))
                        
                        stats['albums_fixed'] += 1
                        print(f"✅ Fixed: {extracted['artist']} - {extracted['album']}")
                        
                    else:
                        # Still failed
                        stats['still_failed'] += 1
                        # Note: Clean database doesn't store scan errors
                        # Scan errors should be tracked in album_registry.db if needed
                        
                        print(f"⚠️ Still failed: {file_path}")
                        
                except Exception as e:
                    error_msg = f"Error re-scanning album {file_path}: {e}"
                    print(f"Warning: {error_msg}")
                    stats['errors'].append(error_msg)
                    stats['still_failed'] += 1
            
            conn.commit()
        
        print(f"✅ Re-scan complete! Fixed {stats['albums_fixed']} of {stats['albums_rescanned']} albums.")
        return stats
    
    def get_albums_paginated(self, page: int = 1, per_page: int = 50, search: str = "", 
                           filter_matched: str = "all", sort_by: str = "artist") -> Dict:
        """Get paginated albums with search and filtering from clean database architecture"""
        with self.get_albums_connection() as conn:
            cursor = conn.cursor()
            
            # Build WHERE clause for clean albums table
            where_conditions = []
            params = []
            
            if search:
                where_conditions.append("(artist LIKE ? OR album LIKE ?)")
                params.extend([f"%{search}%", f"%{search}%"])
            
            # For status filtering, we need to check external databases
            album_keys_for_status = None
            
            if filter_matched == "review":
                # Get albums that need review from batch processing
                try:
                    batch_conn = sqlite3.connect(self.db_path, timeout=5.0)
                    batch_cursor = batch_conn.execute('SELECT album_key FROM album_results WHERE status = "needs_review"')
                    album_keys_for_status = [row[0] for row in batch_cursor.fetchall()]
                    batch_conn.close()
                    
                    if album_keys_for_status:
                        placeholders = ','.join(['?' for _ in album_keys_for_status])
                        where_conditions.append(f"album_key IN ({placeholders})")
                        params.extend(album_keys_for_status)
                    else:
                        # No albums need review
                        where_conditions.append("1=0")  # Return no results
                except sqlite3.Error:
                    where_conditions.append("1=0")  # Return no results if batch DB doesn't exist
                    
            elif filter_matched == "no_artwork":
                where_conditions.append("artwork_data IS NULL")
            
            elif filter_matched == "matched":
                # Get albums that have been matched/approved from batch processing
                try:
                    batch_conn = sqlite3.connect(self.db_path, timeout=5.0)
                    batch_cursor = batch_conn.execute('SELECT album_key FROM album_results WHERE status IN ("matched", "approved")')
                    album_keys_for_status = [row[0] for row in batch_cursor.fetchall()]
                    batch_conn.close()
                    
                    if album_keys_for_status:
                        placeholders = ','.join(['?' for _ in album_keys_for_status])
                        where_conditions.append(f"album_key IN ({placeholders})")
                        params.extend(album_keys_for_status)
                    else:
                        # No albums matched
                        where_conditions.append("1=0")  # Return no results
                except sqlite3.Error:
                    where_conditions.append("1=0")  # Return no results if batch DB doesn't exist
            
            elif filter_matched == "never":
                # Get albums that have never been processed by batch matching
                try:
                    batch_conn = sqlite3.connect(self.db_path, timeout=5.0)
                    batch_cursor = batch_conn.execute('SELECT DISTINCT album_key FROM album_results')
                    processed_album_keys = [row[0] for row in batch_cursor.fetchall()]
                    batch_conn.close()
                    
                    if processed_album_keys:
                        placeholders = ','.join(['?' for _ in processed_album_keys])
                        where_conditions.append(f"album_key NOT IN ({placeholders})")
                        params.extend(processed_album_keys)
                    # If no albums have been processed, all albums are "never matched"
                except sqlite3.Error:
                    # If batch DB doesn't exist, all albums are "never matched"
                    pass
            
            where_clause = " AND ".join(where_conditions)
            if where_clause:
                where_clause = "WHERE " + where_clause
            
            # Build ORDER BY clause (handle NULL values properly)
            order_by_map = {
                "artist": "CASE WHEN artist IS NULL OR artist = '' THEN 1 ELSE 0 END, artist, album",
                "album": "CASE WHEN album IS NULL OR album = '' THEN 1 ELSE 0 END, album, artist", 
                "year": "CASE WHEN year IS NULL THEN 1 ELSE 0 END, year DESC, artist"
            }
            order_clause = f"ORDER BY {order_by_map.get(sort_by, order_by_map['artist'])}"
            
            # Count total results
            count_query = f"SELECT COUNT(*) FROM albums {where_clause}"
            cursor.execute(count_query, params)
            total = cursor.fetchone()[0]
            
            # Get paginated results from clean albums table
            offset = (page - 1) * per_page
            query = f"""
                SELECT id, album_key, artist, album, year, genre, track_count, 
                       total_duration, file_path
                FROM albums 
                {where_clause}
                {order_clause}
                LIMIT ? OFFSET ?
            """
            
            cursor.execute(query, params + [per_page, offset])
            albums = []
            
            for row in cursor.fetchall():
                album_key = row[1]
                
                # Get status from proper external databases
                status = self.get_album_status(album_key)
                
                albums.append({
                    'id': row[0],
                    'album_key': album_key,
                    'artist': row[2],
                    'album': row[3],
                    'year': row[4],
                    'genre': row[5],
                    'track_count': row[6],
                    'total_duration': row[7],
                    'file_path': row[8],
                    'batch_status': status['batch_status'],
                    'match_status': self._get_match_status_clean(status)
                })
            
            return {
                'albums': albums,
                'total': total,
                'page': page,
                'per_page': per_page,
                'total_pages': (total + per_page - 1) // per_page,
                'has_prev': page > 1,
                'has_next': page * per_page < total
            }
    
    def _get_match_status(self, last_matched, confidence, scan_error=None):
        """Get match status indicator (legacy method for compatibility)"""
        if scan_error:
            return {"type": "error", "text": "Scan Error", "class": "danger"}
        elif not last_matched:
            return {"type": "never", "text": "Never Matched", "class": "secondary"}
        elif confidence and confidence >= 80:
            return {"type": "matched", "text": f"Matched {last_matched[:10]}", "class": "success"}
        else:
            return {"type": "review", "text": "Needs Review", "class": "warning"}
    
    def _get_match_status_clean(self, status: Dict):
        """Get album match status for display using clean status data"""
        if status['scan_error']:
            return {"type": "error", "text": "Scan Error", "class": "danger"}
        elif status['batch_status'] == 'needs_review':
            return {"type": "review", "text": "Needs Review", "class": "warning"}
        elif status['batch_status'] in ['matched', 'approved']:
            return {"type": "matched", "text": "Matched", "class": "success"}
        else:
            return {"type": "never", "text": "Never Matched", "class": "secondary"}

# Initialize dashboard
dashboard = MusicLibraryDashboard()

@app.route('/')
def index():
    """Main dashboard with live progress"""
    jobs = dashboard.get_batch_jobs()
    live_progress = dashboard.get_live_progress()
    return render_template('index.html', jobs=jobs, live_progress=live_progress)

@app.route('/job/<job_id>')
def view_job(job_id):
    """View specific job results"""
    status_filter = request.args.get('status', 'all')
    changes_only = request.args.get('changes_only', 'false').lower() == 'true'
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 50))
    
    # Get job details
    jobs = dashboard.get_batch_jobs()
    job = next((j for j in jobs if j['job_id'] == job_id), None)
    
    if not job:
        return "Job not found", 404
    
    # Get results
    results, total = dashboard.get_album_results(job_id, status_filter, changes_only, page, per_page)
    
    # Get statistics
    stats = dashboard.get_statistics(job_id)
    
    # Pagination info
    total_pages = (total + per_page - 1) // per_page
    
    return render_template('job_results.html', 
                         job=job, 
                         results=results, 
                         stats=stats,
                         status_filter=status_filter,
                         changes_only=changes_only,
                         page=page,
                         per_page=per_page,
                         total=total,
                         total_pages=total_pages)

@app.route('/api/album/<job_id>/<path:album_key>')
def get_album_detail(job_id, album_key):
    """Get detailed album information"""
    with dashboard.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM album_results 
            WHERE job_id = ? AND album_key = ?
        ''', (job_id, album_key))
        
        row = cursor.fetchone()
        if not row:
            return jsonify({'error': 'Album not found'}), 404
        
        # Parse and create diff
        original = dashboard.parse_genres(row[4])  # original_genres
        suggested = dashboard.parse_genres(row[5])  # suggested_genres  
        final = dashboard.parse_genres(row[6])  # final_genres
        
        diff = dashboard.create_genre_diff(original, suggested, final)
        
        return jsonify({
            'album_key': row[1],
            'artist': row[2],
            'album': row[3],
            'diff': diff,
            'confidence': row[7],
            'sources_used': row[8],
            'processing_time': row[12]
        })

@app.route('/api/live-progress')
def api_live_progress():
    """API endpoint for live progress updates"""
    return jsonify(dashboard.get_live_progress())

@app.route('/albums')
def albums():
    """Albums library view"""
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 50))
    search = request.args.get('search', '').strip()
    filter_matched = request.args.get('filter', 'all')
    sort_by = request.args.get('sort', 'artist')
    
    # Validate per_page range
    if per_page < 10:
        per_page = 10
    elif per_page > 200:
        per_page = 200
    
    # Get paginated albums
    result = dashboard.get_albums_paginated(
        page=page,
        per_page=per_page,
        search=search,
        filter_matched=filter_matched,
        sort_by=sort_by
    )
    
    return render_template('albums.html', **result, search=search, 
                         filter_matched=filter_matched, sort_by=sort_by)

@app.route('/albums/<int:album_id>')
def album_detail(album_id):
    """Detailed album view with all metadata"""
    with dashboard.get_albums_connection() as conn:
        cursor = conn.cursor()
        
        # Get album details from clean database
        cursor.execute('''
            SELECT id, album_key, artist, album, year, genre, track_count,
                   total_duration, file_path
            FROM albums WHERE id = ?
        ''', (album_id,))
        
        album_row = cursor.fetchone()
        if not album_row:
            return "Album not found", 404
        
        # Get status from proper external databases
        album_key = album_row[1]
        status = dashboard.get_album_status(album_key)
        
        album = {
            'id': album_row[0],
            'album_key': album_key,
            'artist': album_row[2],
            'album': album_row[3],
            'year': album_row[4],
            'genre': album_row[5],
            'track_count': album_row[6],
            'total_duration': album_row[7],
            'file_path': album_row[8],
            'raw_metadata': {},  # Clean database doesn't store this
            'last_scanned': status['last_scanned'],
            'last_matched': status['last_matched'],
            'match_confidence': status['match_confidence'],
            'match_status': dashboard._get_match_status_clean(status)
        }
        
        # Get tracks from clean database
        cursor.execute('''
            SELECT id, track_number, title, artist, duration, file_path,
                   file_format, file_size
            FROM tracks WHERE album_id = ? ORDER BY track_number ASC, title ASC
        ''', (album_id,))
        
        tracks = []
        for track_row in cursor.fetchall():
            tracks.append({
                'id': track_row[0],
                'track_number': track_row[1],
                'title': track_row[2],
                'artist': track_row[3],
                'duration': track_row[4],
                'file_path': track_row[5],
                'file_format': track_row[6],
                'file_size': track_row[7],
                'raw_metadata': {}  # Clean database doesn't store this
            })
        
        return render_template('album_detail.html', album=album, tracks=tracks)

@app.route('/albums/<int:album_id>/review')
def album_metadata_review(album_id):
    """Metadata diff view for albums that need review"""
    with dashboard.get_albums_connection() as conn:
        cursor = conn.cursor()
        
        # Get album details from clean database
        cursor.execute('''
            SELECT id, album_key, artist, album, year, genre, track_count,
                   total_duration, file_path
            FROM albums WHERE id = ?
        ''', (album_id,))
        
        album_row = cursor.fetchone()
        if not album_row:
            return "Album not found", 404
        
        # Get status from proper external databases
        album_key = album_row[1]
        status = dashboard.get_album_status(album_key)
        
        album = {
            'id': album_row[0],
            'album_key': album_key,
            'artist': album_row[2],
            'album': album_row[3],
            'year': album_row[4],
            'genre': album_row[5],
            'track_count': album_row[6],
            'total_duration': album_row[7],
            'file_path': album_row[8]
        }
        
        # Get proposed changes from batch_processing.db
        cursor.execute('''
            SELECT confidence, manual_review_reason, status, suggested_genres, sources_used
            FROM batch_processing.album_results 
            WHERE album_key = ?
        ''', (album_row[1],))  # album_key
        
        batch_row = cursor.fetchone()
        proposed_changes = None
        
        if batch_row:
            import re
            # Parse the manual_review_reason to extract metadata corrections
            review_reason = batch_row[1] or ""
            corrected_artist = None
            corrected_album = None
            
            # Parse artist correction from "Artist: "Old" → "New" (confidence%)"
            if "Artist:" in review_reason:
                match = re.search(r'Artist:\s*"([^"]+)"\s*→\s*"([^"]+)"\s*\(([0-9.]+)%\)', review_reason)
                if match:
                    # Current artist is match.group(1), suggested is match.group(2)
                    corrected_artist = match.group(2)
                    
            # Parse album correction similarly
            if "Album:" in review_reason:
                match = re.search(r'Album:\s*"([^"]+)"\s*→\s*"([^"]+)"\s*\(([0-9.]+)%\)', review_reason)
                if match:
                    corrected_album = match.group(2)
            
            # Parse suggested genres from the string format "Genre1; Genre2; Genre3"
            suggested_genres_str = batch_row[3] or ""
            if suggested_genres_str:
                suggested_genres = [g.strip() for g in suggested_genres_str.split(';') if g.strip()]
            else:
                suggested_genres = []
            
            proposed_changes = {
                'confidence': batch_row[0],
                'status': batch_row[2],
                'corrected_artist': corrected_artist,
                'corrected_album': corrected_album,
                'suggested_genres': suggested_genres,
                'sources_used': json.loads(batch_row[4]) if batch_row[4] else [],
                'manual_review_reason': review_reason,
                'has_genre_changes': bool(suggested_genres)
            }
        
        return render_template('album_metadata_review.html', album=album, proposed_changes=proposed_changes)

@app.route('/api/approve-metadata/<int:album_id>', methods=['POST'])
def api_approve_metadata(album_id):
    """Approve and apply metadata changes"""
    try:
        with dashboard.get_albums_connection() as conn:
            cursor = conn.cursor()
            
            # Get album details
            cursor.execute('SELECT album_key FROM albums WHERE id = ?', (album_id,))
            result = cursor.fetchone()
            if not result:
                return jsonify({'success': False, 'error': 'Album not found'}), 404
            
            album_key = result[0]
            
            # Get proposed changes  
            cursor.execute('''
                SELECT manual_review_reason, suggested_genres FROM batch_processing.album_results 
                WHERE album_key = ? AND status = 'needs_review'
            ''', (album_key,))
            
            batch_row = cursor.fetchone()
            if not batch_row:
                return jsonify({'success': False, 'error': 'No pending changes found'}), 404
            
            # Parse corrections from manual_review_reason
            import re
            review_reason = batch_row[0] or ""
            suggested_genres = batch_row[1] or ""
            updates = {}
            
            # Parse artist correction
            if "Artist:" in review_reason:
                match = re.search(r'Artist:\s*"([^"]+)"\s*→\s*"([^"]+)"\s*\(([0-9.]+)%\)', review_reason)
                if match:
                    updates['artist'] = match.group(2)
                    
            # Parse album correction  
            if "Album:" in review_reason:
                match = re.search(r'Album:\s*"([^"]+)"\s*→\s*"([^"]+)"\s*\(([0-9.]+)%\)', review_reason)
                if match:
                    updates['album'] = match.group(2)
            
            # Apply suggested genres if available
            if suggested_genres:
                updates['genre'] = suggested_genres
            
            if updates:
                import json
                
                # Get current complete metadata state
                cursor.execute('''
                    SELECT artist, album, year, genre, track_count, total_duration, 
                           file_path, raw_metadata_json
                    FROM albums WHERE id = ?
                ''', (album_id,))
                current_row = cursor.fetchone()
                
                # Build current metadata snapshot
                current_metadata = {
                    'artist': current_row[0],
                    'album': current_row[1],
                    'year': current_row[2],
                    'genre': current_row[3],
                    'track_count': current_row[4],
                    'total_duration': current_row[5],
                    'file_path': current_row[6]
                }
                
                # Include raw ID3 metadata if available
                if current_row[7]:
                    try:
                        raw_meta = json.loads(current_row[7])
                        current_metadata['raw_metadata'] = raw_meta
                    except:
                        pass
                
                # Get next version number for v2 table
                cursor.execute('''
                    SELECT COALESCE(MAX(version_number), 0) + 1 
                    FROM album_versions_v2 WHERE album_id = ?
                ''', (album_id,))
                next_version = cursor.fetchone()[0]
                
                # Save current state as a version (if not first version)
                if next_version > 1:
                    cursor.execute('''
                        INSERT INTO album_versions_v2 
                        (album_id, version_number, metadata_snapshot, changed_fields,
                         changed_by, change_reason, is_current)
                        VALUES (?, ?, ?, NULL, 'preserved', 'Previous version before changes', 0)
                    ''', (album_id, next_version - 1, json.dumps(current_metadata)))
                
                # Apply updates to database
                update_sql = "UPDATE albums SET "
                update_sql += ", ".join([f"{k} = ?" for k in updates.keys()])
                update_sql += " WHERE id = ?"
                
                cursor.execute(update_sql, list(updates.values()) + [album_id])
                
                # Get new complete metadata state
                cursor.execute('''
                    SELECT artist, album, year, genre, track_count, total_duration, 
                           file_path, raw_metadata_json
                    FROM albums WHERE id = ?
                ''', (album_id,))
                new_row = cursor.fetchone()
                
                # Build new metadata snapshot
                new_metadata = {
                    'artist': new_row[0],
                    'album': new_row[1],
                    'year': new_row[2],
                    'genre': new_row[3],
                    'track_count': new_row[4],
                    'total_duration': new_row[5],
                    'file_path': new_row[6]
                }
                
                if new_row[7]:
                    try:
                        raw_meta = json.loads(new_row[7])
                        new_metadata['raw_metadata'] = raw_meta
                    except:
                        pass
                
                # Calculate what changed
                changed_fields = {}
                for key in updates.keys():
                    if key in current_metadata and key in new_metadata:
                        if current_metadata[key] != new_metadata[key]:
                            changed_fields[key] = {
                                'old': current_metadata[key],
                                'new': new_metadata[key]
                            }
                
                # Mark all previous versions as not current
                cursor.execute('''
                    UPDATE album_versions_v2 SET is_current = 0 
                    WHERE album_id = ?
                ''', (album_id,))
                
                # Also update old table for backward compatibility
                cursor.execute('''
                    UPDATE album_versions SET is_current = 0 
                    WHERE album_id = ?
                ''', (album_id,))
                
                # Insert new current version in v2 table
                cursor.execute('''
                    INSERT INTO album_versions_v2 
                    (album_id, version_number, metadata_snapshot, changed_fields,
                     changed_by, change_reason, is_current)
                    VALUES (?, ?, ?, ?, 'api_match', ?, 1)
                ''', (album_id, next_version, json.dumps(new_metadata), 
                      json.dumps(changed_fields), review_reason))
                
                # Write genre tags to actual audio files if genres were updated
                files_updated = 0
                if 'genre' in updates:
                    try:
                        from tag_writer import TagWriter
                        import os
                        
                        # Get album file path from database
                        cursor.execute('SELECT file_path FROM albums WHERE id = ?', (album_id,))
                        file_path_result = cursor.fetchone()
                        if file_path_result:
                            album_dir = file_path_result[0]
                            
                            # Initialize tag writer
                            tag_writer = TagWriter("/Volumes/T7/Albums")  # Use the music library path
                            
                            # Get all audio files in the album directory
                            if os.path.exists(album_dir):
                                for file_name in os.listdir(album_dir):
                                    if file_name.lower().endswith(('.flac', '.mp3', '.m4a', '.ogg')):
                                        file_path = os.path.join(album_dir, file_name)
                                        
                                        # Parse genres - handle both JSON array and semicolon formats
                                        genre_string = updates['genre']
                                        if genre_string.startswith('[') and genre_string.endswith(']'):
                                            # JSON array format
                                            genre_list = json.loads(genre_string)
                                        else:
                                            # Semicolon delimited format
                                            genre_list = [g.strip() for g in genre_string.split(';') if g.strip()]
                                        
                                        # Write genres to file (test_mode=False to actually write)
                                        success = tag_writer.write_genre_tags(
                                            Path(file_path), 
                                            genre_list, 
                                            test_mode=False, 
                                            preserve_existing=False
                                        )
                                        if success:
                                            files_updated += 1
                    except Exception as e:
                        print(f"Error writing tags: {e}")
                
                # Mark as approved in batch processing
                cursor.execute('''
                    UPDATE batch_processing.album_results 
                    SET status = 'approved', files_updated = ?
                    WHERE album_key = ?
                ''', (files_updated, album_key))
                
                conn.commit()
                
                return jsonify({'success': True, 'changes_applied': updates, 'version': next_version, 'files_updated': files_updated})
            else:
                return jsonify({'success': False, 'error': 'No changes to apply'})
                
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/reject-metadata/<int:album_id>', methods=['POST'])
def api_reject_metadata(album_id):
    """Reject proposed metadata changes"""
    try:
        with dashboard.get_albums_connection() as conn:
            cursor = conn.cursor()
            
            # Get album key
            cursor.execute('SELECT album_key FROM albums WHERE id = ?', (album_id,))
            result = cursor.fetchone()
            if not result:
                return jsonify({'success': False, 'error': 'Album not found'}), 404
            
            album_key = result[0]
            
            # Mark as rejected in batch processing
            cursor.execute('''
                UPDATE batch_processing.album_results 
                SET status = 'rejected'
                WHERE album_key = ? AND status = 'needs_review'
            ''', (album_key,))
            
            conn.commit()
            
            return jsonify({'success': True})
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/albums/<int:album_id>/history')
def album_version_history(album_id):
    """Display version history for an album"""
    import json
    with dashboard.get_albums_connection() as conn:
        cursor = conn.cursor()
        
        # Get current album details
        cursor.execute('''
            SELECT id, album_key, artist, album, year, genre, track_count
            FROM albums WHERE id = ?
        ''', (album_id,))
        
        album_row = cursor.fetchone()
        if not album_row:
            return "Album not found", 404
        
        album = {
            'id': album_row[0],
            'album_key': album_row[1],
            'artist': album_row[2],
            'album': album_row[3],
            'year': album_row[4],
            'genre': album_row[5],
            'track_count': album_row[6]
        }
        
        # Try to get version history from v2 table first (JSON-based)
        cursor.execute('''
            SELECT id, version_number, metadata_snapshot, changed_fields,
                   changed_by, change_reason, created_at, is_current
            FROM album_versions_v2
            WHERE album_id = ?
            ORDER BY version_number DESC
        ''', (album_id,))
        
        v2_rows = cursor.fetchall()
        versions = []
        
        if v2_rows:
            # Use v2 versions (JSON-based)
            for row in v2_rows:
                metadata = json.loads(row[2]) if row[2] else {}
                changed_fields = json.loads(row[3]) if row[3] else {}
                
                versions.append({
                    'id': row[0],
                    'version_number': row[1],
                    'artist': metadata.get('artist', ''),
                    'album': metadata.get('album', ''),
                    'year': metadata.get('year'),
                    'genre': metadata.get('genre', ''),
                    'metadata': metadata,  # Full metadata for display
                    'changed_fields': changed_fields,
                    'changed_by': row[4],
                    'change_reason': row[5],
                    'created_at': row[6],
                    'is_current': row[7]
                })
        else:
            # Fall back to old table if no v2 versions
            cursor.execute('''
                SELECT id, version_number, artist, album, year, genre,
                       changed_by, change_reason, created_at, is_current
                FROM album_versions
                WHERE album_id = ?
                ORDER BY version_number DESC
            ''', (album_id,))
            
            for row in cursor.fetchall():
                versions.append({
                    'id': row[0],
                    'version_number': row[1],
                    'artist': row[2],
                    'album': row[3],
                    'year': row[4],
                    'genre': row[5],
                    'metadata': {
                        'artist': row[2],
                        'album': row[3],
                        'year': row[4],
                        'genre': row[5]
                    },
                    'changed_fields': {},
                    'changed_by': row[6],
                    'change_reason': row[7],
                    'created_at': row[8],
                    'is_current': row[9]
                })
        
        return render_template('album_version_history.html', album=album, versions=versions)

@app.route('/api/revert-album/<int:album_id>/<int:version_id>', methods=['POST'])
def api_revert_album_version(album_id, version_id):
    """Revert album to a specific version"""
    try:
        import json
        with dashboard.get_albums_connection() as conn:
            cursor = conn.cursor()
            
            # First check if this is a v2 version
            cursor.execute('''
                SELECT metadata_snapshot, version_number
                FROM album_versions_v2
                WHERE id = ? AND album_id = ?
            ''', (version_id, album_id))
            
            v2_data = cursor.fetchone()
            
            if v2_data:
                # Handle v2 (JSON-based) revert
                metadata_to_restore = json.loads(v2_data[0])
                version_num = v2_data[1]
                
                # Save current state before reverting
                cursor.execute('''
                    SELECT artist, album, year, genre, track_count, total_duration, 
                           file_path, raw_metadata_json
                    FROM albums WHERE id = ?
                ''', (album_id,))
                current_row = cursor.fetchone()
                
                current_metadata = {
                    'artist': current_row[0],
                    'album': current_row[1],
                    'year': current_row[2],
                    'genre': current_row[3],
                    'track_count': current_row[4],
                    'total_duration': current_row[5],
                    'file_path': current_row[6]
                }
                
                if current_row[7]:
                    try:
                        current_metadata['raw_metadata'] = json.loads(current_row[7])
                    except:
                        pass
                
                # Get next version number
                cursor.execute('''
                    SELECT COALESCE(MAX(version_number), 0) + 1 
                    FROM album_versions_v2 WHERE album_id = ?
                ''', (album_id,))
                next_version = cursor.fetchone()[0]
                
                # Calculate what will change
                changed_fields = {}
                for key in ['artist', 'album', 'year', 'genre']:
                    if key in metadata_to_restore and key in current_metadata:
                        if metadata_to_restore[key] != current_metadata[key]:
                            changed_fields[key] = {
                                'old': current_metadata[key],
                                'new': metadata_to_restore[key]
                            }
                
                # Save current state as a new version
                cursor.execute('''
                    INSERT INTO album_versions_v2 
                    (album_id, version_number, metadata_snapshot, changed_fields,
                     changed_by, change_reason, is_current)
                    VALUES (?, ?, ?, ?, 'user_revert', ?, 0)
                ''', (album_id, next_version, json.dumps(current_metadata), 
                      json.dumps(changed_fields),
                      f'Reverted to version {version_num}'))
                
                # Apply the selected version to albums table
                # Build dynamic update based on available fields
                update_fields = []
                update_values = []
                
                for field in ['artist', 'album', 'year', 'genre']:
                    if field in metadata_to_restore:
                        update_fields.append(f"{field} = ?")
                        update_values.append(metadata_to_restore[field])
                
                # Update raw_metadata_json if present
                if 'raw_metadata' in metadata_to_restore:
                    update_fields.append("raw_metadata_json = ?")
                    update_values.append(json.dumps(metadata_to_restore['raw_metadata']))
                
                if update_fields:
                    update_values.append(album_id)
                    cursor.execute(f'''
                        UPDATE albums 
                        SET {', '.join(update_fields)}
                        WHERE id = ?
                    ''', update_values)
                
                # Mark all versions as not current
                cursor.execute('''
                    UPDATE album_versions_v2 SET is_current = 0 
                    WHERE album_id = ?
                ''', (album_id,))
                
                # Mark the reverted version as current
                cursor.execute('''
                    UPDATE album_versions_v2 SET is_current = 1 
                    WHERE id = ?
                ''', (version_id,))
                
                conn.commit()
                
                return jsonify({
                    'success': True, 
                    'message': f'Reverted to version {version_num}',
                    'version': version_num,
                    'fields_changed': list(changed_fields.keys())
                })
                
            else:
                # Fall back to old version table
                cursor.execute('''
                    SELECT artist, album, year, genre, version_number
                    FROM album_versions
                    WHERE id = ? AND album_id = ?
                ''', (version_id, album_id))
                
                version_data = cursor.fetchone()
                if not version_data:
                    return jsonify({'success': False, 'error': 'Version not found'}), 404
                
                # Apply old-style revert
                cursor.execute('''
                    UPDATE albums 
                    SET artist = ?, album = ?, year = ?, genre = ?
                    WHERE id = ?
                ''', (version_data[0], version_data[1], version_data[2], 
                      version_data[3], album_id))
                
                conn.commit()
                
                return jsonify({
                    'success': True, 
                    'message': f'Reverted to version {version_data[4]}',
                    'version': version_data[4]
                })
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/scan-library')
def api_scan_library():
    """Trigger library scan"""
    try:
        stats = dashboard.scan_and_store_library()
        return jsonify({'success': True, 'stats': stats})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/rescan-errors')
def api_rescan_errors():
    """Re-scan albums that had errors"""
    try:
        stats = dashboard.rescan_failed_albums()
        return jsonify({'success': True, 'stats': stats})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/extract-artwork')
def api_extract_artwork():
    """Extract artwork for all albums"""
    try:
        stats = dashboard.extract_artwork_for_all_albums()
        return jsonify({'success': True, 'stats': stats})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/rescan-album/<int:album_id>')
def api_rescan_album(album_id):
    """Rescan a specific album"""
    try:
        result = dashboard.rescan_single_album(album_id)
        return jsonify({'success': True, **result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/consolidate-compilations')
def api_consolidate_compilations():
    """Consolidate albums marked as compilations"""
    try:
        stats = dashboard.consolidate_compilation_albums()
        return jsonify({'success': True, 'stats': stats})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/artwork/<int:album_id>')
def api_artwork(album_id):
    """Serve album artwork"""
    try:
        with dashboard.get_albums_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT artwork_data, artwork_format FROM albums WHERE id = ?', (album_id,))
            result = cursor.fetchone()
            
            if result and result[0]:
                artwork_data, artwork_format = result
                mime_type = f'image/{artwork_format}' if artwork_format else 'image/jpeg'
                
                from flask import Response
                return Response(artwork_data, mimetype=mime_type)
            else:
                # Return a default placeholder image
                return '', 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    import argparse
    import logging
    import time
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Music Library Dashboard - Comprehensive Music Management Interface')
    parser.add_argument('-i', '--interactive', action='store_true', 
                       help='Run in interactive mode with verbose output and real-time logging')
    parser.add_argument('-d', '--daemon', action='store_true', 
                       help='Run in daemon mode (background) with minimal output')
    parser.add_argument('--force-kill', action='store_true', 
                       help='Aggressively kill existing processes (SIGKILL)')
    parser.add_argument('--debug', action='store_true', 
                       help='Enable Flask debug mode with auto-reload')
    parser.add_argument('--port', type=int, default=5002, 
                       help='Port to run server on (default: 5002)')
    
    args = parser.parse_args()
    
    # Configure logging based on mode
    if args.interactive:
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s [%(levelname)s] %(message)s',
            datefmt='%H:%M:%S'
        )
        print("🎵 Starting Music Library Dashboard in INTERACTIVE MODE...")
        print("📝 Verbose logging enabled - you'll see detailed startup progress")
    elif args.daemon:
        logging.basicConfig(level=logging.WARNING)
        print("🎵 Starting Music Library Dashboard in DAEMON MODE...")
    else:
        logging.basicConfig(level=logging.INFO)
        print("🎵 Starting Music Library Dashboard...")
    
    # Enhanced process cleanup with progress reporting
    start_time = time.time()
    
    if args.interactive:
        print("\n🔧 STARTUP PHASE 1: Process Cleanup")
        print("├── Checking for existing music system processes...")
    
    # Clean up all music system processes
    music_scripts = ['music_dashboard.py', 'batch_processor.py']
    
    for script in music_scripts:
        try:
            ProcessCleanup.cleanup_script_processes(script, force_kill=args.force_kill, verbose=args.interactive)
            if args.interactive:
                print(f"├── ✅ {script} processes cleaned")
        except Exception as e:
            if args.interactive:
                print(f"├── ⚠️  {script} cleanup warning: {e}")
            logging.warning(f"{script} cleanup issue: {e}")
    
    if args.interactive:
        print(f"├── Checking for processes using port {args.port}...")
    
    try:
        ProcessCleanup.cleanup_port_processes(args.port, force_kill=args.force_kill, verbose=args.interactive)
        if args.interactive:
            print(f"├── ✅ Port {args.port} cleaned")
    except Exception as e:
        if args.interactive:
            print(f"├── ⚠️  Port cleanup warning: {e}")
        logging.warning(f"Port cleanup issue: {e}")
    
    cleanup_time = time.time() - start_time
    if args.interactive:
        print(f"└── Process cleanup completed in {cleanup_time:.2f}s")
    
    # Database initialization with progress reporting
    if args.interactive:
        print("\n🗄️  STARTUP PHASE 2: Database Initialization")
        init_start = time.time()
    
    try:
        dashboard = MusicLibraryDashboard(verbose=args.interactive)
        if args.interactive:
            init_time = time.time() - init_start
            print(f"└── ✅ Database initialization completed in {init_time:.2f}s")
    except Exception as e:
        if args.interactive:
            print(f"└── ❌ Database initialization failed: {e}")
        logging.error(f"Database initialization failed: {e}")
        raise
    
    # Flask server startup
    total_startup_time = time.time() - start_time
    
    if args.interactive:
        print(f"\n🚀 STARTUP PHASE 3: Flask Server")
        print(f"├── Total startup time: {total_startup_time:.2f}s")
        print(f"├── Server starting on port {args.port}")
        print(f"├── Debug mode: {'ON' if args.debug else 'OFF'}")
        print(f"└── 📊 Available at: http://localhost:{args.port}")
        print("\n🎛️ Music library management and live progress monitoring")
        print("💡 Press Ctrl+C to stop the server")
        print("=" * 60)
    else:
        print(f"📊 Available at: http://localhost:{args.port}")
        print("🎛️ Music library management and live progress monitoring")
    
    # Start Flask application
    try:
        app.run(
            debug=args.debug, 
            host='0.0.0.0', 
            port=args.port,
            use_reloader=args.debug,  # Only reload in debug mode
            threaded=True  # Enable threading for better performance
        )
    except KeyboardInterrupt:
        if args.interactive:
            print("\n\n🛑 Server stopped by user (Ctrl+C)")
        else:
            print("Server stopped")
    except Exception as e:
        if args.interactive:
            print(f"\n❌ Server error: {e}")
        logging.error(f"Server startup failed: {e}")
        raise