#!/usr/bin/env python3
"""
Update Local Albums - Apply enhanced genre tags to Music/Albums directory
Preserves existing genres and adds new ones based on album analysis
"""

from tag_writer import TagWriter
from pathlib import Path
from typing import Dict, List

def get_enhanced_genres_for_album(artist: str, album: str, existing_genres: List[str]) -> List[str]:
    """Get enhanced genre tags based on artist/album analysis"""
    
    artist_lower = artist.lower()
    album_lower = album.lower()
    
    # Enhanced genre mapping based on musical knowledge
    new_genres = []
    
    # Classic Jamaican Dub/Reggae Artists
    if any(word in artist_lower for word in ['ranking dread', 'dread']):
        new_genres.extend(["Reggae", "Dub", "Roots Reggae", "Jamaican"])
    elif any(word in artist_lower for word in ['errol brown', 'brown, errol']):
        new_genres.extend(["Dub", "Reggae", "Jamaican", "70s Dub", "Roots Dub"])
    elif any(word in artist_lower for word in ['derrick harriott', 'harriott']):
        new_genres.extend(["Dub", "Reggae", "Jamaican", "70s Dub", "Pioneer Dub"])
    elif any(word in artist_lower for word in ['iration steppas', 'steppas']):
        new_genres.extend(["Dub", "UK Dub", "Steppers", "Modern Dub", "Sound System"])
    elif any(word in artist_lower for word in ['annette brissett', 'brissett']):
        new_genres.extend(["Reggae", "Dancehall", "Caribbean", "Soul"])
    
    # Psychedelic/Rock
    elif any(word in artist_lower for word in ['tomorrow']):
        new_genres.extend(["Psychedelic Rock", "Rock", "1960s", "British Psychedelia"])
    
    # Album-specific additions based on title
    if 'dub' in album_lower:
        if "Dub" not in new_genres:
            new_genres.append("Dub")
    
    if 'pleasure dub' in album_lower:
        new_genres.extend(["Instrumental Dub", "Studio One"])
    
    if 'scrubbing' in album_lower:
        new_genres.extend(["Producer Dub", "Roots Dub"])
        
    if 'higher regionz' in album_lower or 'dubz' in album_lower:
        new_genres.extend(["Conscious Dub", "Steppers Dub"])
    
    if 'love power' in album_lower:
        if "Soul" not in new_genres:
            new_genres.append("Soul")
    
    # Year-based additions for classic dub
    if any(year in album_lower for year in ['1975', '1976']) and 'dub' in album_lower:
        new_genres.append("Classic Dub")
    
    # Remove duplicates while preserving order
    unique_genres = []
    seen = set()
    for genre in new_genres:
        if genre.lower() not in seen:
            seen.add(genre.lower())
            unique_genres.append(genre)
    
    # Return new genres (existing will be merged automatically)
    return unique_genres if unique_genres else ["Alternative", "World Music"]

def parse_album_directory(album_dir: str) -> tuple[str, str]:
    """Parse artist and album from various directory name formats"""
    
    # Strategy 1: Standard "Artist - Album" format
    if " - " in album_dir:
        parts = album_dir.split(" - ", 1)
        artist = parts[0].strip()
        album = parts[1].strip()
        
        # Clean up album name
        album = album.split(" (")[0].strip()
        album = album.split(" [")[0].strip()
        
        return artist, album
    
    # Strategy 2: "LastName, FirstName (Year) [Details] Album [Format]" format
    # Example: "Brown, Errol (1976) [002 Dub Series] Pleasure Dub [flac 16-48]"
    if ", " in album_dir and "(" in album_dir:
        # Extract artist from "LastName, FirstName" pattern
        comma_parts = album_dir.split(", ", 1)
        last_name = comma_parts[0].strip()
        
        # Find the first name and year
        remaining = comma_parts[1]
        if "(" in remaining:
            first_name = remaining.split("(")[0].strip()
            artist = f"{first_name} {last_name}"
            
            # Extract album name after the year and series info
            # Look for pattern after "] " which should be the album name
            if "] " in remaining:
                after_bracket = remaining.split("] ", 1)[1]
                album = after_bracket.split(" [")[0].strip()  # Remove format info
                
                return artist, album
    
    # Strategy 3: Try to extract from other patterns as needed
    # Can add more strategies here for other complex formats
    
    return "", ""

def update_local_albums(test_mode: bool = True):
    """Update all albums in Music/Albums directory"""
    
    writer = TagWriter("SwinsianLibrary.xml")
    local_path = Path("Music/Albums")
    
    if not local_path.exists():
        print(f"Music/Albums directory not found")
        return
    
    print("🎵 UPDATING LOCAL ALBUMS WITH ENHANCED GENRES")
    print("=" * 60)
    print(f"Mode: {'TEST MODE' if test_mode else 'LIVE UPDATE'}")
    print(f"Preserving existing genres: YES")
    
    # Find all audio files
    audio_files = []
    for ext in ['*.flac', '*.mp3', '*.m4a']:
        audio_files.extend(local_path.rglob(ext))
    
    # Group by album directory
    albums = {}
    for file_path in audio_files:
        album_dir = file_path.parent.name
        if album_dir not in albums:
            albums[album_dir] = []
        albums[album_dir].append(file_path)
    
    print(f"Found {len(albums)} albums with {len(audio_files)} total tracks\n")
    
    # Process each album
    for album_dir, files in albums.items():
        print(f"📁 ALBUM: {album_dir}")
        print(f"   Tracks: {len(files)}")
        
        # Parse artist and album from directory name using multiple strategies
        artist, album = parse_album_directory(album_dir)
        
        if artist and album:
            print(f"   Artist: {artist}")
            print(f"   Album: {album}")
            
            # Check current genres from first file
            first_file = files[0]
            current_tags = writer.read_current_tags(first_file)
            current_genres = current_tags.get('genre', '')
            
            print(f"   Current Genres: {current_genres if current_genres else 'None'}")
            
            # Get enhanced genres
            existing_genre_list = [g.strip() for g in current_genres.split(';') if g.strip()] if current_genres else []
            new_genres = get_enhanced_genres_for_album(artist, album, existing_genre_list)
            
            if new_genres:
                print(f"   Adding Genres: {'; '.join(new_genres)}")
                
                # Update all files in the album
                updated_count = 0
                for file_path in files:
                    try:
                        success = writer.write_genre_tags(
                            file_path, new_genres, 
                            test_mode=test_mode, 
                            preserve_existing=True
                        )
                        if success:
                            updated_count += 1
                    except Exception as e:
                        print(f"   ✗ Error updating {file_path.name}: {e}")
                
                if not test_mode:
                    print(f"   ✓ Updated {updated_count}/{len(files)} files")
                else:
                    print(f"   ✓ Would update {updated_count}/{len(files)} files")
            else:
                print(f"   ⚠️  No additional genres to add")
        else:
            print(f"   ⚠️  Could not parse artist/album from directory name")
            print(f"   ⚠️  Directory format: {album_dir}")
        
        print()  # Empty line between albums
    
    print("=" * 60)
    if test_mode:
        print("TEST COMPLETE - No files were modified")
        print("Run with test_mode=False to apply changes")
    else:
        print("UPDATE COMPLETE - All files have been updated")

if __name__ == "__main__":
    # First run in test mode to see what would happen
    print("=== PREVIEW MODE ===")
    update_local_albums(test_mode=True)
    
    # Ask user if they want to proceed
    print("\n" + "="*60)
    response = input("Apply these changes? (y/N): ").strip().lower()
    
    if response == 'y':
        print("\n=== APPLYING CHANGES ===")
        update_local_albums(test_mode=False)
    else:
        print("No changes applied.")