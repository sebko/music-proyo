#!/usr/bin/env python3
"""
Live progress monitor for batch processing
Shows real-time updates with progress bar
"""

import sqlite3
import time
import sys
from datetime import datetime

def get_stats():
    """Get current processing statistics"""
    db = sqlite3.connect('batch_processing.db')
    cursor = db.cursor()
    
    # Get completed albums
    cursor.execute('SELECT COUNT(*) FROM album_results WHERE status = "completed" AND files_updated > 0')
    completed = cursor.fetchone()[0]
    
    # Get by confidence
    cursor.execute('SELECT COUNT(*) FROM album_results WHERE confidence >= 75 AND status = "completed"')
    high = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM album_results WHERE confidence < 75 AND confidence >= 50')
    med = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM album_results WHERE confidence < 50')
    low = cursor.fetchone()[0]
    
    # Get last processed album
    cursor.execute('''
        SELECT artist, album, confidence 
        FROM album_results 
        ORDER BY created_at DESC 
        LIMIT 1
    ''')
    last = cursor.fetchone()
    
    # Get processing rate (last 5 minutes)
    cursor.execute('''
        SELECT COUNT(*)
        FROM album_results
        WHERE created_at > datetime('now', '-5 minutes')
    ''')
    recent_count = cursor.fetchone()[0]
    
    db.close()
    return completed, high, med, low, last, recent_count

def main():
    """Display live progress"""
    print("\n🎵 LIVE PROGRESS MONITOR - Music Library Genre Tagging")
    print("Press Ctrl+C to stop monitoring\n")
    
    TOTAL = 2146
    last_completed = 0
    start_time = time.time()
    
    try:
        while True:
            completed, high, med, low, last, recent_rate = get_stats()
            
            # Calculate percentage
            pct = (completed / TOTAL) * 100
            
            # Create progress bar
            bar_length = 50
            filled = int(bar_length * pct / 100)
            bar = '█' * filled + '░' * (bar_length - filled)
            
            # Calculate rate
            rate_per_min = recent_rate / 5 if recent_rate > 0 else 0
            
            # Estimate time remaining
            if rate_per_min > 0:
                remaining = TOTAL - completed
                mins_left = remaining / rate_per_min
                hours_left = mins_left / 60
                time_str = f"{hours_left:.1f}h" if hours_left > 1 else f"{mins_left:.0f}m"
            else:
                time_str = "---"
            
            # Clear line and print progress
            sys.stdout.write('\r' + ' ' * 100 + '\r')  # Clear line
            
            # Main progress line
            progress_line = f"[{bar}] {pct:.1f}% | {completed}/{TOTAL}"
            
            # Stats line
            stats_line = f"✅ {high} 🟡 {med} 🔴 {low} | ⚡ {rate_per_min:.1f}/min | ⏱️  {time_str}"
            
            # Last album line
            if last:
                artist, album, conf = last
                # Truncate if too long
                if len(artist) > 20: artist = artist[:17] + "..."
                if len(album) > 25: album = album[:22] + "..."
                last_line = f"📀 {artist} - {album} ({conf:.0f}%)"
            else:
                last_line = "📀 Starting..."
            
            # Print all on one line
            output = f"{progress_line} | {stats_line} | {last_line}"
            sys.stdout.write(output)
            sys.stdout.flush()
            
            # Show new albums processed
            if completed > last_completed:
                diff = completed - last_completed
                sys.stdout.write(f" [+{diff}]")
                sys.stdout.flush()
                last_completed = completed
            
            time.sleep(2)  # Update every 2 seconds
            
    except KeyboardInterrupt:
        print("\n\n✅ Monitoring stopped")
        print(f"Final progress: {completed}/{TOTAL} albums processed ({pct:.1f}%)")

if __name__ == "__main__":
    main()