#!/usr/bin/env python3
"""
Test real tag writing
"""

from tag_writer import TagWriter
from pathlib import Path

def test_real_write():
    writer = TagWriter("SwinsianLibrary.xml")
    
    # Find the Annette Brissett album (it probably has minimal genres)
    test_file = Path("Music/Albums/Annette Brissett - Love Power - (2018) [WEB-FLAC]/1 Forever Loving You.flac")
    
    if not test_file.exists():
        print(f"Test file not found: {test_file}")
        return
    
    print("🧪 TESTING REAL TAG WRITING")
    print("=" * 50)
    
    # Show current tags
    print("BEFORE:")
    current_tags = writer.read_current_tags(test_file)
    for key, value in current_tags.items():
        print(f"  {key}: {value}")
    
    # Write new genres
    test_genres = ["Reggae", "Dancehall", "Caribbean", "Soul"]
    print(f"\nWriting genres: {'; '.join(test_genres)}")
    
    success = writer.write_genre_tags(test_file, test_genres, test_mode=False)
    
    if success:
        print("✓ Tag writing successful!")
        
        # Show updated tags
        print("\nAFTER:")
        updated_tags = writer.read_current_tags(test_file)
        for key, value in updated_tags.items():
            print(f"  {key}: {value}")
        
        print("\n✓ Tags updated successfully")
    else:
        print("✗ Tag writing failed")

if __name__ == "__main__":
    test_real_write()