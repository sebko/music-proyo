#!/usr/bin/env python3
"""
Simple progress checker for batch processing
Run this anytime to see current progress
"""

import sqlite3
import sys
from datetime import datetime, timedelta

def get_processing_stats():
    """Get current processing statistics from database"""
    try:
        db = sqlite3.connect('batch_processing.db')
        cursor = db.cursor()
        
        # Get total albums processed
        cursor.execute('SELECT COUNT(*) FROM album_results')
        total_processed = cursor.fetchone()[0]
        
        # Get completed albums (with files updated)
        cursor.execute('SELECT COUNT(*) FROM album_results WHERE status = "completed" AND files_updated > 0')
        completed = cursor.fetchone()[0]
        
        # Get albums by confidence level
        cursor.execute('SELECT COUNT(*) FROM album_results WHERE confidence >= 75 AND status = "completed"')
        high_conf = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM album_results WHERE confidence < 75 AND confidence >= 50')
        med_conf = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM album_results WHERE confidence < 50')
        low_conf = cursor.fetchone()[0]
        
        # Get recent albums (last 5 processed)
        cursor.execute('''
            SELECT artist, album, confidence, status, created_at 
            FROM album_results 
            ORDER BY created_at DESC 
            LIMIT 5
        ''')
        recent = cursor.fetchall()
        
        # Get processing rate (albums per hour)
        cursor.execute('''
            SELECT COUNT(*), MIN(created_at), MAX(created_at)
            FROM album_results
            WHERE created_at > datetime('now', '-1 hour')
        ''')
        hour_data = cursor.fetchone()
        
        db.close()
        return {
            'total_processed': total_processed,
            'completed': completed,
            'high_conf': high_conf,
            'med_conf': med_conf,
            'low_conf': low_conf,
            'recent': recent,
            'hour_count': hour_data[0] if hour_data else 0
        }
    except Exception as e:
        print(f"Error reading database: {e}")
        sys.exit(1)

def format_time_ago(timestamp_str):
    """Format timestamp as 'X minutes ago'"""
    try:
        timestamp = datetime.fromisoformat(timestamp_str)
        now = datetime.now()
        diff = now - timestamp
        
        if diff < timedelta(minutes=1):
            return "just now"
        elif diff < timedelta(hours=1):
            mins = int(diff.total_seconds() / 60)
            return f"{mins} min{'s' if mins != 1 else ''} ago"
        else:
            hours = int(diff.total_seconds() / 3600)
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
    except:
        return timestamp_str

def main():
    """Display progress information"""
    stats = get_processing_stats()
    
    # Total albums in library
    TOTAL_ALBUMS = 2146
    
    # Calculate percentages
    pct_complete = (stats['completed'] / TOTAL_ALBUMS) * 100
    pct_processed = (stats['total_processed'] / TOTAL_ALBUMS) * 100
    
    # Create progress bar
    bar_length = 50
    filled = int(bar_length * pct_complete / 100)
    bar = '█' * filled + '░' * (bar_length - filled)
    
    # Display header
    print("\n🎵 MUSIC LIBRARY GENRE TAGGING PROGRESS")
    print("=" * 70)
    
    # Display progress bar
    print(f"\nProgress: [{bar}] {pct_complete:.1f}%")
    print(f"Albums updated: {stats['completed']:,} / {TOTAL_ALBUMS:,}")
    
    # Display statistics
    print(f"\n📊 Statistics:")
    print(f"  • Total processed: {stats['total_processed']:,} ({pct_processed:.1f}%)")
    print(f"  • ✅ High confidence (≥75%): {stats['high_conf']:,}")
    print(f"  • 🟡 Medium confidence (50-74%): {stats['med_conf']:,}")
    print(f"  • 🔴 Low confidence (<50%): {stats['low_conf']:,}")
    print(f"  • ⚡ Processing rate: ~{stats['hour_count']} albums/hour")
    
    # Estimate completion time
    if stats['hour_count'] > 0 and stats['completed'] < TOTAL_ALBUMS:
        remaining = TOTAL_ALBUMS - stats['completed']
        hours_left = remaining / stats['hour_count']
        print(f"  • ⏱️  Estimated time remaining: {hours_left:.1f} hours")
    
    # Show recent albums
    if stats['recent']:
        print(f"\n📝 Recently Processed:")
        for artist, album, confidence, status, created_at in stats['recent']:
            time_ago = format_time_ago(created_at)
            conf_emoji = "✅" if confidence >= 75 else "🟡" if confidence >= 50 else "🔴"
            print(f"  {conf_emoji} {artist} - {album} ({confidence:.1f}%) - {time_ago}")
    
    print("\n" + "=" * 70)
    print("💡 Tip: Run 'python3 hybrid_batch_processor.py' if processing has stopped")
    print()

if __name__ == "__main__":
    main()