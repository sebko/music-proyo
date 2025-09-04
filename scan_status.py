#!/usr/bin/env python3
"""
Scan Status - Comprehensive tool to check album scanning and matching progress
Shows current status across all databases (albums.db, album_registry.db, batch_processing.db)
"""

import sqlite3
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from album_registry import AlbumRegistry

class ScanStatusChecker:
    def __init__(self):
        self.registry_db = "album_registry.db"
        self.batch_db = "batch_processing.db"
        self.albums_db = "albums.db"
    
    def check_databases(self) -> Dict[str, bool]:
        """Check which databases exist"""
        status = {}
        status['album_registry'] = Path(self.registry_db).exists()
        status['batch_processing'] = Path(self.batch_db).exists()
        status['albums'] = Path(self.albums_db).exists()
        return status
    
    def get_registry_summary(self) -> Optional[Dict]:
        """Get summary from album_registry.db"""
        if not Path(self.registry_db).exists():
            return None
        
        conn = sqlite3.connect(self.registry_db)
        
        try:
            # Total albums
            total = conn.execute('SELECT COUNT(*) FROM album_registry').fetchone()[0]
            
            # Scan status breakdown
            scan_status = {}
            for row in conn.execute('SELECT scan_status, COUNT(*) FROM album_registry GROUP BY scan_status'):
                scan_status[row[0] if row[0] else 'unknown'] = row[1]
            
            # Match status breakdown
            match_status = {}
            for row in conn.execute('SELECT match_status, COUNT(*) FROM album_registry GROUP BY match_status'):
                match_status[row[0] if row[0] else 'unknown'] = row[1]
            
            # Albums with high confidence
            high_confidence = conn.execute(
                'SELECT COUNT(*) FROM album_registry WHERE confidence >= 95'
            ).fetchone()[0]
            
            # Recent activity
            last_scan = conn.execute(
                'SELECT MAX(last_scanned) FROM album_registry'
            ).fetchone()[0]
            
            last_match = conn.execute(
                'SELECT MAX(api_match_date) FROM album_registry'
            ).fetchone()[0]
            
            return {
                'total_albums': total,
                'scan_status': scan_status,
                'match_status': match_status,
                'high_confidence_count': high_confidence,
                'last_scan_date': last_scan,
                'last_match_date': last_match
            }
        finally:
            conn.close()
    
    def get_batch_summary(self) -> Optional[Dict]:
        """Get summary from batch_processing.db"""
        if not Path(self.batch_db).exists():
            return None
        
        conn = sqlite3.connect(self.batch_db)
        
        try:
            # Check if table exists
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='batch_jobs'"
            ).fetchall()
            
            if not tables:
                return {'error': 'No batch_jobs table found'}
            
            # Total jobs
            total_jobs = conn.execute('SELECT COUNT(*) FROM batch_jobs').fetchone()[0]
            
            # Status breakdown
            status_counts = {}
            for row in conn.execute('SELECT status, COUNT(*) FROM batch_jobs GROUP BY status'):
                status_counts[row[0] if row[0] else 'unknown'] = row[1]
            
            # Albums needing review
            needs_review = conn.execute(
                "SELECT COUNT(*) FROM batch_jobs WHERE status = 'needs_review'"
            ).fetchone()[0]
            
            # Recently approved
            approved = conn.execute(
                "SELECT COUNT(*) FROM batch_jobs WHERE status = 'approved'"
            ).fetchone()[0]
            
            # Failed jobs
            failed = conn.execute(
                "SELECT COUNT(*) FROM batch_jobs WHERE status = 'failed'"
            ).fetchone()[0]
            
            return {
                'total_jobs': total_jobs,
                'status_counts': status_counts,
                'needs_review': needs_review,
                'approved': approved,
                'failed': failed
            }
        finally:
            conn.close()
    
    def get_albums_summary(self) -> Optional[Dict]:
        """Get summary from albums.db"""
        if not Path(self.albums_db).exists():
            return None
        
        conn = sqlite3.connect(self.albums_db)
        
        try:
            # Total albums
            total = conn.execute('SELECT COUNT(*) FROM albums').fetchone()[0]
            
            # Albums with genres
            with_genres = conn.execute(
                "SELECT COUNT(*) FROM albums WHERE genre IS NOT NULL AND genre != ''"
            ).fetchone()[0]
            
            # Albums with artwork
            with_artwork = conn.execute(
                'SELECT COUNT(*) FROM albums WHERE artwork_data IS NOT NULL'
            ).fetchone()[0]
            
            # Total tracks
            total_tracks = conn.execute('SELECT COUNT(*) FROM tracks').fetchone()[0]
            
            return {
                'total_albums': total,
                'albums_with_genres': with_genres,
                'albums_with_artwork': with_artwork,
                'total_tracks': total_tracks
            }
        finally:
            conn.close()
    
    def get_recent_activity(self, limit: int = 10) -> List[Dict]:
        """Get recent processing activity"""
        activity = []
        
        if Path(self.batch_db).exists():
            conn = sqlite3.connect(self.batch_db)
            try:
                # Check if columns exist
                cursor = conn.execute('PRAGMA table_info(batch_jobs)')
                columns = [row[1] for row in cursor.fetchall()]
                
                if 'updated_at' in columns:
                    recent = conn.execute('''
                        SELECT album_key, status, confidence, updated_at
                        FROM batch_jobs
                        ORDER BY updated_at DESC
                        LIMIT ?
                    ''', (limit,)).fetchall()
                    
                    for row in recent:
                        activity.append({
                            'album_key': row[0],
                            'status': row[1],
                            'confidence': row[2],
                            'updated_at': row[3],
                            'source': 'batch_processing'
                        })
            finally:
                conn.close()
        
        return activity
    
    def print_summary(self):
        """Print comprehensive status summary"""
        print("=" * 80)
        print(" MUSIC LIBRARY SCAN STATUS REPORT")
        print("=" * 80)
        
        # Check databases
        db_status = self.check_databases()
        print("\n📁 Database Status:")
        for db_name, exists in db_status.items():
            status = "✅ Found" if exists else "❌ Not found"
            print(f"  {db_name:20}: {status}")
        
        # Albums.db summary
        albums_summary = self.get_albums_summary()
        if albums_summary:
            print("\n📀 Albums Database (ID3 Metadata):")
            print(f"  Total Albums:        {albums_summary['total_albums']:,}")
            print(f"  Albums with Genres:  {albums_summary['albums_with_genres']:,} ({albums_summary['albums_with_genres']/albums_summary['total_albums']*100:.1f}%)")
            print(f"  Albums with Artwork: {albums_summary['albums_with_artwork']:,} ({albums_summary['albums_with_artwork']/albums_summary['total_albums']*100:.1f}%)")
            print(f"  Total Tracks:        {albums_summary['total_tracks']:,}")
        
        # Registry summary
        registry = self.get_registry_summary()
        if registry:
            print("\n📊 Album Registry (Scan Tracking):")
            print(f"  Total Albums:        {registry['total_albums']:,}")
            
            if registry['scan_status']:
                print("\n  Scan Status:")
                for status, count in registry['scan_status'].items():
                    percentage = (count / registry['total_albums'] * 100) if registry['total_albums'] > 0 else 0
                    print(f"    {status:15}: {count:4} ({percentage:5.1f}%)")
            
            if registry['match_status']:
                print("\n  Match Status:")
                for status, count in registry['match_status'].items():
                    percentage = (count / registry['total_albums'] * 100) if registry['total_albums'] > 0 else 0
                    print(f"    {status:15}: {count:4} ({percentage:5.1f}%)")
            
            print(f"\n  High Confidence (≥95%): {registry['high_confidence_count']:,}")
            
            if registry['last_scan_date']:
                print(f"  Last Scan:              {registry['last_scan_date'][:19]}")
            if registry['last_match_date']:
                print(f"  Last API Match:         {registry['last_match_date'][:19]}")
        
        # Batch processing summary
        batch = self.get_batch_summary()
        if batch and 'error' not in batch:
            print("\n🔄 Batch Processing (API Matching):")
            print(f"  Total Jobs:          {batch['total_jobs']:,}")
            
            if batch['status_counts']:
                print("\n  Job Status:")
                for status, count in batch['status_counts'].items():
                    print(f"    {status:15}: {count:4}")
            
            if batch['needs_review'] > 0:
                print(f"\n  ⚠️  Albums Needing Review: {batch['needs_review']}")
        
        # Recent activity
        recent = self.get_recent_activity(5)
        if recent:
            print("\n📝 Recent Activity:")
            for item in recent:
                status_emoji = {
                    'approved': '✅',
                    'needs_review': '⚠️',
                    'failed': '❌',
                    'matched': '✔️'
                }.get(item['status'], '•')
                
                conf_str = f" ({item['confidence']:.1f}%)" if item['confidence'] else ""
                time_str = item['updated_at'][:19] if item['updated_at'] else "N/A"
                
                print(f"  {status_emoji} {item['album_key'][:50]:50} {item['status']:12}{conf_str}")
        
        print("\n" + "=" * 80)
        
        # Recommendations
        self.print_recommendations(registry, batch, albums_summary)
    
    def print_recommendations(self, registry: Optional[Dict], batch: Optional[Dict], 
                            albums: Optional[Dict]):
        """Print actionable recommendations"""
        print("\n💡 Recommendations:")
        
        if registry:
            unmatched = registry['match_status'].get('unmatched', 0)
            if unmatched > 0:
                print(f"  • {unmatched:,} albums haven't been matched with APIs yet")
                print(f"    Run: python3 hybrid_batch_processor.py")
        
        if batch and batch.get('needs_review', 0) > 0:
            print(f"  • {batch['needs_review']} albums need manual review")
            print(f"    Visit: http://localhost:5002/albums?filter_matched=review")
        
        if albums and albums['total_albums'] > 0:
            genre_coverage = albums['albums_with_genres'] / albums['total_albums'] * 100
            if genre_coverage < 80:
                print(f"  • Only {genre_coverage:.1f}% of albums have genres")
                print(f"    Consider running the API matcher to improve coverage")
        
        if not Path(self.registry_db).exists():
            print("  • Album registry not found - run initial scan:")
            print("    python3 album_registry.py")
        
        print("\n" + "=" * 80)


def main():
    """Main entry point with command-line interface"""
    parser = argparse.ArgumentParser(description="Check album scan status and manage registry")
    parser.add_argument("--music-path", default="/Volumes/T7/Albums", 
                       help="Path to music library (default: /Volumes/T7/Albums)")
    parser.add_argument("--db-path", default="album_registry.db",
                       help="Path to registry database (default: album_registry.db)")
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Default status command
    status_parser = subparsers.add_parser('status', help='Show comprehensive status report (default)')
    
    # Scan command
    scan_parser = subparsers.add_parser('scan', help='Scan filesystem and update registry')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List albums by status')
    list_parser.add_argument('--scan-status', choices=['never_scanned', 'scanned', 'matched', 'failed', 'manual_review'],
                           help='Filter by scan status')
    list_parser.add_argument('--match-status', choices=['unmatched', 'matched', 'manual', 'failed'],
                           help='Filter by match status')
    list_parser.add_argument('--limit', type=int, default=50,
                           help='Maximum number of albums to show (default: 50)')
    
    # Details command
    details_parser = subparsers.add_parser('details', help='Show details for specific album')
    details_parser.add_argument('album_key', help='Album key (artist|album)')
    
    # Unscanned command
    unscanned_parser = subparsers.add_parser('unscanned', help='List unscanned albums')
    unscanned_parser.add_argument('--limit', type=int, default=20,
                                help='Maximum number to show (default: 20)')
    
    args = parser.parse_args()
    
    # Default to status command if no command specified
    if not args.command:
        checker = ScanStatusChecker()
        checker.print_summary()
        
        # Quick status line for scripting
        db_status = checker.check_databases()
        if all(db_status.values()):
            registry = checker.get_registry_summary()
            if registry:
                total = registry['total_albums']
                matched = total - registry['match_status'].get('unmatched', 0)
                print(f"\n✅ Quick Status: {matched}/{total} albums processed ({matched/total*100:.1f}%)")
        else:
            missing = [k for k, v in db_status.items() if not v]
            print(f"\n⚠️  Missing databases: {', '.join(missing)}")
        return
    
    # Handle registry-based commands
    registry = AlbumRegistry(args.db_path)
    
    if args.command == 'status':
        checker = ScanStatusChecker()
        checker.print_summary()
        
    elif args.command == 'scan':
        print(f"Scanning music library at {args.music_path}")
        results = registry.scan_and_register_albums(args.music_path)
        print(f"✓ Scan completed")
        print(f"  Albums discovered: {results['albums_discovered']}")
        print(f"  Albums updated: {results['albums_updated']}")
        print(f"  Total albums: {results['total_albums']}")
        
    elif args.command == 'list':
        albums = registry.get_albums_by_status(
            scan_status=args.scan_status,
            match_status=args.match_status,
            limit=args.limit
        )
        
        if not albums:
            print("No albums found matching criteria")
            return
        
        print(f"Found {len(albums)} albums:")
        print("=" * 80)
        
        for album in albums:
            genres = album['original_genres'] if album['original_genres'] else []
            matched_genres = album['matched_genres'] if album['matched_genres'] else []
            
            print(f"{album['artist']} - {album['album']}")
            print(f"  Tracks: {album['track_count']} | Scan: {album['scan_status']} | Match: {album['match_status']}")
            
            if genres:
                print(f"  Current genres: {', '.join(genres)}")
            if matched_genres:
                confidence_str = f" (confidence: {album['confidence']:.1f}%)" if album['confidence'] else ""
                print(f"  Matched genres: {', '.join(matched_genres)}{confidence_str}")
            
            if album['last_scanned']:
                print(f"  Last scanned: {album['last_scanned']}")
            
            print()
    
    elif args.command == 'details':
        album = registry.get_album_details(args.album_key)
        
        if not album:
            print(f"Album not found: {args.album_key}")
            return
        
        print("=" * 60)
        print(f"ALBUM DETAILS: {album['artist']} - {album['album']}")
        print("=" * 60)
        print(f"Album Key: {album['album_key']}")
        print(f"Track Count: {album['track_count']}")
        print(f"Scan Status: {album['scan_status']}")
        print(f"Match Status: {album['match_status']}")
        
        if album['original_genres']:
            print(f"Original Genres: {', '.join(album['original_genres'])}")
        
        if album['matched_genres']:
            confidence_str = f" (confidence: {album['confidence']:.1f}%)" if album['confidence'] else ""
            print(f"Matched Genres: {', '.join(album['matched_genres'])}{confidence_str}")
        
        if album['api_sources']:
            print(f"API Sources: {', '.join(album['api_sources'])}")
        
        print(f"First Discovered: {album['first_discovered']}")
        print(f"Last Scanned: {album['last_scanned']}")
        
        if album['api_match_date']:
            print(f"API Match Date: {album['api_match_date']}")
        
        if album['error_message']:
            print(f"Error: {album['error_message']}")
        
        if album['manual_review_reason']:
            print(f"Review Reason: {album['manual_review_reason']}")
        
        if album['file_paths']:
            print(f"\nFile Paths ({len(album['file_paths'])} files):")
            for i, path in enumerate(album['file_paths'][:5]):  # Show first 5
                print(f"  {i+1}. {path}")
            if len(album['file_paths']) > 5:
                print(f"  ... and {len(album['file_paths']) - 5} more files")
    
    elif args.command == 'unscanned':
        albums = registry.get_unscanned_albums(args.limit)
        
        if not albums:
            print("✓ All albums have been scanned!")
            return
        
        print(f"Found {len(albums)} unscanned albums:")
        print("=" * 60)
        
        for album in albums:
            genres = album['original_genres'] if album['original_genres'] else []
            genre_str = ', '.join(genres) if genres else 'No genres'
            
            print(f"{album['artist']} - {album['album']}")
            print(f"  Tracks: {album['track_count']} | Current genres: {genre_str}")
            print(f"  Last scanned: {album['last_scanned']}")
            print()


if __name__ == "__main__":
    main()