#!/usr/bin/env python3
"""
Apply Updates - Actually update the Music/Albums directory
"""

from update_local_albums import update_local_albums

if __name__ == "__main__":
    print("🎵 APPLYING ENHANCED GENRE TAGS TO MUSIC/ALBUMS")
    print("=" * 60)
    print("✅ Preserving existing genres")
    print("✅ Creating backups of all modified files")
    print("✅ Adding enhanced genre classifications")
    print()
    
    # Apply the changes
    update_local_albums(test_mode=False)