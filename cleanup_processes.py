#!/usr/bin/env python3
"""
Cleanup All Music System Processes
Standalone script to clean up all running music system instances
"""

from process_cleanup import ProcessCleanup
import sys

def main():
    """Clean up all music system processes"""
    print("🧹 Music System Process Cleanup")
    print("=" * 40)
    
    music_scripts = [
        'music_dashboard.py',
 
        'batch_processor.py',
        'album_match_viewer.py',
    ]
    
    total_cleaned = 0
    
    # Clean up script processes
    for script in music_scripts:
        try:
            result = ProcessCleanup.cleanup_script_processes(script, verbose=True)
            if result['killed']:
                total_cleaned += len(result['killed'])
                print(f"✅ {script}: Cleaned {len(result['killed'])} processes")
            else:
                print(f"✅ {script}: No processes running")
        except Exception as e:
            print(f"⚠️  {script}: Error - {e}")
    
    # Clean up common ports
    ports = [5000, 5001, 5002, 5003]
    for port in ports:
        try:
            result = ProcessCleanup.cleanup_port_processes(port, verbose=True)
            if result['killed']:
                total_cleaned += len(result['killed'])
                print(f"✅ Port {port}: Freed by cleaning {len(result['killed'])} processes")
        except Exception as e:
            print(f"⚠️  Port {port}: Error - {e}")
    
    print("=" * 40)
    if total_cleaned > 0:
        print(f"🎉 Cleanup complete! Terminated {total_cleaned} processes.")
    else:
        print("✅ All clean! No processes were running.")
    
    return total_cleaned

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n🛑 Cleanup interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Cleanup failed: {e}")
        sys.exit(1)