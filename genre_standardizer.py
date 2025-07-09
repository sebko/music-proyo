#!/usr/bin/env python3
"""
Genre Standardization and Hierarchy System
Normalizes, validates, and provides hierarchical relationships for music genres
"""

import json
import re
from typing import Dict, List, Set, Optional, Tuple
from pathlib import Path
from collections import defaultdict

class GenreStandardizer:
    def __init__(self, config_path: str = "genre_config.json"):
        self.config_path = config_path
        self.genre_mappings = {}
        self.genre_hierarchy = {}
        self.valid_genres = set()
        self.load_or_create_config()
    
    def load_or_create_config(self):
        """Load existing config or create default genre mappings"""
        config_file = Path(self.config_path)
        
        if config_file.exists():
            with open(config_file, 'r') as f:
                config = json.load(f)
                self.genre_mappings = config.get('mappings', {})
                self.genre_hierarchy = config.get('hierarchy', {})
                self.valid_genres = set(config.get('valid_genres', []))
        else:
            self._create_default_config()
            self.save_config()
    
    def _create_default_config(self):
        """Create comprehensive default genre mappings and hierarchy"""
        
        # Genre normalization mappings
        self.genre_mappings = {
            # Hip-Hop variations
            "Hip-Hop": "Hip Hop",
            "Hip Hop": "Hip Hop",
            "Hiphop": "Hip Hop",
            "Rap": "Hip Hop",
            "Hip-hop": "Hip Hop",
            
            # Electronic variations
            "Electronic": "Electronic",
            "Electronica": "Electronic",
            "IDM": "IDM",
            "Ambient": "Ambient",
            "Techno": "Techno", 
            "House": "House",
            "Drum & Bass": "Drum & Bass",
            "Drum and Bass": "Drum & Bass",
            "DnB": "Drum & Bass",
            "Dubstep": "Dubstep",
            "Synthpop": "Synthpop",
            "Synth-pop": "Synthpop",
            "New Wave": "New Wave",
            
            # Rock variations
            "Rock": "Rock",
            "Rock & Roll": "Rock",
            "Rock and Roll": "Rock",
            "Rock/Blues": "Rock",
            "Hard Rock": "Rock",
            "Soft Rock": "Rock",
            "Classic Rock": "Rock",
            "Progressive Rock": "Rock",
            "Prog Rock": "Rock",
            "Psychedelic Rock": "Rock",
            "Psych Rock": "Rock",
            "Indie Rock": "Indie Rock",
            "Alternative Rock": "Alternative Rock", 
            "Punk Rock": "Punk Rock",
            "Post-Rock": "Post-Rock",
            "Art Rock": "Art Rock",
            "Garage Rock": "Garage Rock",
            "Glam Rock": "Glam Rock",
            
            # Alternative variations
            "Alternative": "Alternative",
            "Alt": "Alternative",
            "Indie": "Alternative",
            "Independent": "Alternative",
            "Alternative Rock": "Alternative",
            
            # Jazz variations
            "Jazz": "Jazz",
            "Bebop": "Jazz",
            "Cool Jazz": "Jazz",
            "Free Jazz": "Jazz",
            "Fusion": "Jazz",
            "Jazz Fusion": "Jazz",
            "Smooth Jazz": "Jazz",
            "Contemporary Jazz": "Jazz",
            
            # Blues variations
            "Blues": "Blues",
            "Delta Blues": "Blues",
            "Chicago Blues": "Blues",
            "Electric Blues": "Blues",
            "Blues Rock": "Blues",
            
            # Country variations
            "Country": "Country",
            "Country Music": "Country",
            "Country Rock": "Country",
            "Alt-Country": "Country",
            "Alternative Country": "Country",
            "Americana": "Country",
            "Folk Country": "Country",
            
            # Folk variations
            "Folk": "Folk",
            "Folk Music": "Folk",
            "Traditional Folk": "Folk",
            "Contemporary Folk": "Folk",
            "Folk Rock": "Folk",
            "Singer-Songwriter": "Folk",
            
            # Reggae variations
            "Reggae": "Reggae",
            "Dub": "Reggae",
            "Ska": "Reggae",
            "Rocksteady": "Reggae",
            "Dancehall": "Reggae",
            "Roots Reggae": "Reggae",
            
            # Latin variations
            "Latin": "Latin",
            "Latin Music": "Latin",
            "Salsa": "Latin",
            "Cumbia": "Latin",
            "Bachata": "Latin",
            "Merengue": "Latin",
            "Reggaeton": "Latin",
            "Bossa Nova": "Latin",
            
            # Pop variations
            "Pop": "Pop",
            "Pop Music": "Pop",
            "Dance Pop": "Pop",
            "Electropop": "Pop",
            "Synth Pop": "Pop",
            "Teen Pop": "Pop",
            "Adult Contemporary": "Pop",
            
            # Classical variations
            "Classical": "Classical",
            "Classical Music": "Classical",
            "Baroque": "Classical",
            "Romantic": "Classical",
            "Contemporary Classical": "Classical",
            "Opera": "Classical",
            "Symphony": "Classical",
            
            # R&B/Soul variations
            "R&B": "R&B",
            "Soul": "R&B",
            "Rhythm and Blues": "R&B",
            "Neo-Soul": "R&B",
            "Contemporary R&B": "R&B",
            "Motown": "R&B",
            "Funk": "R&B",
            
            # Metal variations
            "Metal": "Metal",
            "Heavy Metal": "Heavy Metal",
            "Death Metal": "Death Metal",
            "Black Metal": "Black Metal",
            "Thrash Metal": "Thrash Metal", 
            "Progressive Metal": "Progressive Metal",
            "Doom Metal": "Doom Metal",
            "Power Metal": "Power Metal",
            
            # Punk variations
            "Punk": "Punk",
            "Punk Rock": "Punk",
            "Post-Punk": "Punk",
            "Hardcore Punk": "Punk",
            "Pop Punk": "Punk",
            
            # World Music variations
            "World": "World",
            "World Music": "World",
            "African": "World",
            "Celtic": "World",
            "Indian": "World",
            "Middle Eastern": "World",
            "Asian": "World",
            
            # Other common variations
            "Other": "Other",
            "Unknown": "Other",
            "Unclassified": "Other",
            "Various": "Other",
            "Soundtrack": "Soundtrack",
            "Film Score": "Soundtrack",
            "Game Music": "Soundtrack",
            "Easy Listening": "Easy Listening",
            "Vocal": "Vocal",
            "Instrumental": "Instrumental",
            "Experimental": "Experimental",
            "Avant-Garde": "Experimental",
            "Noise": "Experimental"
        }
        
        # Genre hierarchy (child -> parents)
        self.genre_hierarchy = {
            # Electronic subgenres
            "Ambient": ["Electronic"],
            "Techno": ["Electronic"],
            "House": ["Electronic"],
            "Drum & Bass": ["Electronic"],
            "Dubstep": ["Electronic"],
            "IDM": ["Electronic"],
            "Synthpop": ["Electronic", "Pop"],
            "New Wave": ["Electronic", "Rock"],
            
            # Rock subgenres
            "Hard Rock": ["Rock"],
            "Progressive Rock": ["Rock"],
            "Psychedelic Rock": ["Rock"],
            "Punk Rock": ["Rock", "Punk"],
            "Alternative Rock": ["Rock", "Alternative"],
            "Indie Rock": ["Rock", "Alternative"],
            "Post-Rock": ["Rock"],
            "Art Rock": ["Rock"],
            "Garage Rock": ["Rock"],
            "Glam Rock": ["Rock"],
            
            # Jazz subgenres
            "Bebop": ["Jazz"],
            "Cool Jazz": ["Jazz"],
            "Free Jazz": ["Jazz"],
            "Fusion": ["Jazz"],
            "Smooth Jazz": ["Jazz"],
            
            # Blues subgenres
            "Delta Blues": ["Blues"],
            "Chicago Blues": ["Blues"],
            "Electric Blues": ["Blues"],
            "Blues Rock": ["Blues", "Rock"],
            
            # Country subgenres
            "Country Rock": ["Country", "Rock"],
            "Alt-Country": ["Country", "Alternative"],
            "Americana": ["Country", "Folk"],
            
            # Folk subgenres
            "Folk Rock": ["Folk", "Rock"],
            "Contemporary Folk": ["Folk"],
            "Singer-Songwriter": ["Folk"],
            
            # Reggae subgenres
            "Dub": ["Reggae"],
            "Ska": ["Reggae"],
            "Rocksteady": ["Reggae"],
            "Dancehall": ["Reggae"],
            "Roots Reggae": ["Reggae"],
            
            # Latin subgenres
            "Salsa": ["Latin"],
            "Cumbia": ["Latin"],
            "Bachata": ["Latin"],
            "Merengue": ["Latin"],
            "Reggaeton": ["Latin"],
            "Bossa Nova": ["Latin", "Jazz"],
            
            # Pop subgenres
            "Dance Pop": ["Pop"],
            "Electropop": ["Pop", "Electronic"],
            "Teen Pop": ["Pop"],
            
            # R&B/Soul subgenres
            "Neo-Soul": ["R&B"],
            "Funk": ["R&B"],
            "Motown": ["R&B"],
            
            # Metal subgenres
            "Heavy Metal": ["Metal"],
            "Death Metal": ["Metal"],
            "Black Metal": ["Metal"],
            "Thrash Metal": ["Metal"],
            "Progressive Metal": ["Metal"],
            "Doom Metal": ["Metal"],
            "Power Metal": ["Metal"],
            
            # Punk subgenres
            "Post-Punk": ["Punk"],
            "Hardcore Punk": ["Punk"],
            "Pop Punk": ["Punk", "Pop"],
            
            # Classical subgenres
            "Baroque": ["Classical"],
            "Romantic": ["Classical"],
            "Contemporary Classical": ["Classical"],
            "Opera": ["Classical"],
            
            # World subgenres
            "African": ["World"],
            "Celtic": ["World"],
            "Indian": ["World"],
            "Middle Eastern": ["World"],
            "Asian": ["World"]
        }
        
        # Extract valid genres from mappings
        self.valid_genres = set(self.genre_mappings.values())
        
        # Add hierarchical genres
        for genre, parents in self.genre_hierarchy.items():
            self.valid_genres.add(genre)
            self.valid_genres.update(parents)
    
    def save_config(self):
        """Save current configuration to file"""
        config = {
            'mappings': self.genre_mappings,
            'hierarchy': self.genre_hierarchy,
            'valid_genres': list(self.valid_genres)
        }
        
        with open(self.config_path, 'w') as f:
            json.dump(config, f, indent=2)
    
    def normalize_genre(self, genre: str) -> str:
        """Normalize a single genre string"""
        if not genre:
            return ""
        
        # Clean the genre string
        cleaned = self._clean_genre_string(genre)
        
        # Apply direct mapping if exists
        if cleaned in self.genre_mappings:
            return self.genre_mappings[cleaned]
        
        # Try case-insensitive lookup
        for mapping_key, mapping_value in self.genre_mappings.items():
            if cleaned.lower() == mapping_key.lower():
                return mapping_value
        
        # Try partial matching for compound genres
        normalized = self._partial_match_genre(cleaned)
        if normalized:
            return normalized
        
        # Return cleaned version if no mapping found
        return cleaned
    
    def _clean_genre_string(self, genre: str) -> str:
        """Clean and standardize genre string format"""
        # Remove extra whitespace and normalize
        cleaned = re.sub(r'\s+', ' ', genre.strip())
        
        # Remove common prefixes/suffixes
        cleaned = re.sub(r'^(The|A|An)\s+', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s+(Music|Genre)$', '', cleaned, flags=re.IGNORECASE)
        
        # Handle special characters
        cleaned = cleaned.replace('&', 'and')
        cleaned = cleaned.replace('/', ' ')
        cleaned = re.sub(r'[^\w\s-]', '', cleaned)
        
        # Proper case
        return cleaned.title()
    
    def _partial_match_genre(self, genre: str) -> Optional[str]:
        """Try to match genre using partial string matching"""
        genre_lower = genre.lower()
        
        # Check if any known genre is contained in the input
        for known_genre in self.valid_genres:
            if known_genre.lower() in genre_lower or genre_lower in known_genre.lower():
                return known_genre
        
        return None
    
    def normalize_genre_list(self, genres: List[str]) -> List[str]:
        """Normalize a list of genres, expand hierarchies, and remove duplicates"""
        all_genres = set()
        
        for genre in genres:
            if not genre:
                continue
            
            # Handle semicolon-separated genres in single string
            if ';' in genre:
                sub_genres = [g.strip() for g in genre.split(';') if g.strip()]
                for sub_genre in sub_genres:
                    all_genres.add(sub_genre)
            else:
                all_genres.add(genre)
        
        # Normalize each genre
        normalized_genres = set()
        for genre in all_genres:
            norm_genre = self.normalize_genre(genre)
            if norm_genre:
                normalized_genres.add(norm_genre)
        
        # Expand with hierarchical parents
        expanded_genres = set(normalized_genres)
        for genre in normalized_genres:
            parents = self.get_genre_hierarchy(genre)
            expanded_genres.update(parents)
        
        # Convert to sorted list (parents typically come first)
        result = []
        seen = set()
        
        # Add all genres, avoiding duplicates (case-insensitive)
        for genre in sorted(expanded_genres):
            if genre.lower() not in seen:
                result.append(genre)
                seen.add(genre.lower())
        
        return result
    
    def get_genre_hierarchy(self, genre: str) -> List[str]:
        """Get all parent genres for a given genre"""
        parents = []
        if genre in self.genre_hierarchy:
            parents.extend(self.genre_hierarchy[genre])
        return parents
    
    def expand_genres_with_hierarchy(self, genres: List[str]) -> List[str]:
        """Expand genre list to include hierarchical parents"""
        expanded = set(genres)
        
        for genre in genres:
            parents = self.get_genre_hierarchy(genre)
            expanded.update(parents)
        
        return list(expanded)
    
    def validate_genres(self, genres: List[str]) -> Tuple[List[str], List[str]]:
        """Validate genres and return valid/invalid lists"""
        valid = []
        invalid = []
        
        for genre in genres:
            normalized = self.normalize_genre(genre)
            if normalized in self.valid_genres:
                valid.append(normalized)
            else:
                invalid.append(genre)
        
        return valid, invalid
    
    def suggest_genres(self, partial_genre: str, limit: int = 5) -> List[str]:
        """Suggest valid genres based on partial input"""
        partial_lower = partial_genre.lower()
        suggestions = []
        
        for genre in sorted(self.valid_genres):
            if partial_lower in genre.lower():
                suggestions.append(genre)
                if len(suggestions) >= limit:
                    break
        
        return suggestions
    
    def analyze_genre_inconsistencies(self, album_genres: Dict[str, List[str]]) -> Dict:
        """Analyze genre inconsistencies across albums"""
        analysis = {
            'unmapped_genres': set(),
            'inconsistent_formats': defaultdict(set),
            'hierarchy_opportunities': defaultdict(list),
            'statistics': {}
        }
        
        all_genres = []
        for genres in album_genres.values():
            all_genres.extend(genres)
        
        # Find unmapped genres
        for genre in all_genres:
            normalized = self.normalize_genre(genre)
            if normalized not in self.valid_genres:
                analysis['unmapped_genres'].add(genre)
        
        # Find format inconsistencies
        genre_variants = defaultdict(set)
        for genre in all_genres:
            normalized = self.normalize_genre(genre)
            genre_variants[normalized].add(genre)
        
        for normalized, variants in genre_variants.items():
            if len(variants) > 1:
                analysis['inconsistent_formats'][normalized] = variants
        
        # Find hierarchy opportunities
        for album, genres in album_genres.items():
            for genre in genres:
                parents = self.get_genre_hierarchy(genre)
                if parents:
                    missing_parents = [p for p in parents if p not in genres]
                    if missing_parents:
                        analysis['hierarchy_opportunities'][album].extend(missing_parents)
        
        # Generate statistics
        total_genres = len(all_genres)
        unique_genres = len(set(all_genres))
        valid_genres = len([g for g in all_genres if self.normalize_genre(g) in self.valid_genres])
        
        analysis['statistics'] = {
            'total_genre_instances': total_genres,
            'unique_genres': unique_genres,
            'valid_genres': valid_genres,
            'invalid_genres': total_genres - valid_genres,
            'consistency_rate': (valid_genres / total_genres) * 100 if total_genres > 0 else 0
        }
        
        return analysis
    
    def add_custom_mapping(self, original: str, normalized: str):
        """Add a custom genre mapping"""
        self.genre_mappings[original] = normalized
        self.valid_genres.add(normalized)
        self.save_config()
    
    def add_genre_hierarchy(self, child: str, parents: List[str]):
        """Add a genre hierarchy relationship"""
        self.genre_hierarchy[child] = parents
        self.valid_genres.add(child)
        self.valid_genres.update(parents)
        self.save_config()

if __name__ == "__main__":
    # Test the genre standardizer
    standardizer = GenreStandardizer()
    
    # Test some normalizations
    test_genres = [
        "Hip-Hop", "Rock & Roll", "Electronic", "Folk Music",
        "Progressive Rock", "Drum and Bass", "Alt-Country",
        "Unknown", "Rock/Blues", "Synthpop"
    ]
    
    print("Genre Normalization Test:")
    print("=" * 50)
    for genre in test_genres:
        normalized = standardizer.normalize_genre(genre)
        hierarchy = standardizer.get_genre_hierarchy(normalized)
        print(f"{genre:<20} -> {normalized:<15} {f'[Parents: {hierarchy}]' if hierarchy else ''}")
    
    print(f"\nTotal valid genres: {len(standardizer.valid_genres)}")