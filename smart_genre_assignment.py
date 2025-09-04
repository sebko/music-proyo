#!/usr/bin/env python3
"""
Smart Genre Assignment System
Provides intelligent genre suggestions based on artist patterns, directory names, and contextual clues
"""

import re
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set
from collections import defaultdict, Counter
from dataclasses import dataclass
import logging

from genre_standardizer import GenreStandardizer

@dataclass
class GenreSuggestion:
    """Container for genre suggestions with confidence and reasoning"""
    genres: List[str]
    confidence: float
    reasoning: str
    source: str

class ArtistGenreAnalyzer:
    """Analyzes artist genre patterns across discography"""
    
    def __init__(self, genre_standardizer: GenreStandardizer):
        self.standardizer = genre_standardizer
        self.artist_profiles = {}
        self.logger = logging.getLogger(__name__)
    
    def build_artist_profiles(self, albums: Dict[str, Dict]) -> None:
        """Build genre profiles for all artists"""
        self.logger.info("Building artist genre profiles...")
        
        artist_albums = defaultdict(list)
        
        # Group albums by artist
        for album_key, album_info in albums.items():
            artist = album_info['artist'].strip()
            if artist:
                artist_albums[artist].append(album_info)
        
        # Analyze each artist
        for artist, artist_album_list in artist_albums.items():
            self.artist_profiles[artist] = self._analyze_artist_genres(artist_album_list)
        
        self.logger.info(f"Built profiles for {len(self.artist_profiles)} artists")
    
    def _analyze_artist_genres(self, albums: List[Dict]) -> Dict:
        """Analyze genre patterns for a single artist"""
        all_genres = []
        albums_with_genres = 0
        
        # Collect all genres from this artist's albums
        for album in albums:
            if album['genres']:
                albums_with_genres += 1
                normalized_genres = self.standardizer.normalize_genre_list(list(album['genres']))
                all_genres.extend(normalized_genres)
        
        # Count genre frequencies
        genre_counts = Counter(all_genres)
        total_albums = len(albums)
        
        # Calculate genre consistency and confidence
        primary_genres = []
        secondary_genres = []
        
        for genre, count in genre_counts.most_common():
            percentage = (count / albums_with_genres) * 100 if albums_with_genres > 0 else 0
            
            if percentage >= 60:  # Appears in 60%+ of albums
                primary_genres.append(genre)
            elif percentage >= 30:  # Appears in 30%+ of albums
                secondary_genres.append(genre)
        
        # Calculate overall confidence
        coverage = albums_with_genres / total_albums if total_albums > 0 else 0
        consistency = len(primary_genres) / len(genre_counts) if genre_counts else 0
        confidence = (coverage * 0.7 + consistency * 0.3) * 100
        
        return {
            'total_albums': total_albums,
            'albums_with_genres': albums_with_genres,
            'primary_genres': primary_genres,
            'secondary_genres': secondary_genres,
            'all_genres': list(genre_counts.keys()),
            'genre_distribution': dict(genre_counts),
            'confidence': confidence,
            'coverage': coverage
        }
    
    def suggest_genres_for_artist(self, artist: str) -> Optional[GenreSuggestion]:
        """Suggest genres for an album based on artist's profile"""
        if artist not in self.artist_profiles:
            return None
        
        profile = self.artist_profiles[artist]
        
        if profile['confidence'] < 30:
            return None
        
        # Build suggestion
        suggested_genres = profile['primary_genres'][:3]  # Top 3 primary genres
        
        if len(suggested_genres) < 2 and profile['secondary_genres']:
            suggested_genres.extend(profile['secondary_genres'][:2])
        
        if not suggested_genres:
            return None
        
        reasoning = (f"Based on {profile['albums_with_genres']}/{profile['total_albums']} "
                    f"albums by this artist. Primary genres: {', '.join(profile['primary_genres'])}")
        
        return GenreSuggestion(
            genres=suggested_genres,
            confidence=profile['confidence'],
            reasoning=reasoning,
            source="artist_analysis"
        )

class DirectoryGenreExtractor:
    """Extracts genre hints from directory and file names"""
    
    def __init__(self, genre_standardizer: GenreStandardizer):
        self.standardizer = genre_standardizer
        
        # Genre keywords that might appear in directory names
        self.genre_keywords = {
            'metal': ['metal', 'doom', 'black', 'death', 'thrash', 'heavy'],
            'electronic': ['electronic', 'techno', 'house', 'ambient', 'edm', 'synth'],
            'rock': ['rock', 'indie', 'alternative', 'punk', 'grunge'],
            'jazz': ['jazz', 'bebop', 'fusion', 'swing'],
            'classical': ['classical', 'baroque', 'romantic', 'symphony', 'opera'],
            'folk': ['folk', 'acoustic', 'singer-songwriter'],
            'country': ['country', 'bluegrass', 'americana'],
            'hip hop': ['hip-hop', 'hiphop', 'rap', 'hip hop'],
            'reggae': ['reggae', 'dub', 'ska', 'dancehall'],
            'latin': ['latin', 'salsa', 'cumbia', 'bachata'],
            'world': ['world', 'ethnic', 'traditional'],
            'blues': ['blues', 'delta', 'chicago']
        }
        
        # Year patterns for era-based suggestions
        self.era_genres = {
            (1950, 1959): ['Rock', 'Blues', 'Country', 'Jazz'],
            (1960, 1969): ['Rock', 'Folk', 'Psychedelic Rock', 'Motown'],
            (1970, 1979): ['Rock', 'Punk', 'Funk', 'Disco'],
            (1980, 1989): ['New Wave', 'Electronic', 'Metal', 'Pop'],
            (1990, 1999): ['Alternative', 'Grunge', 'Hip Hop', 'Electronic'],
            (2000, 2009): ['Indie', 'Electronic', 'Pop', 'Alternative'],
            (2010, 2024): ['Indie', 'Electronic', 'Hip Hop', 'Pop']
        }
    
    def extract_from_path(self, file_path: str) -> Optional[GenreSuggestion]:
        """Extract genre hints from file path"""
        path = Path(file_path)
        
        # Check all directory components
        path_parts = [part.lower() for part in path.parts]
        full_path = ' '.join(path_parts)
        
        suggested_genres = []
        reasoning_parts = []
        
        # Look for genre keywords
        for genre, keywords in self.genre_keywords.items():
            for keyword in keywords:
                if keyword in full_path:
                    suggested_genres.append(genre)
                    reasoning_parts.append(f"'{keyword}' found in path")
                    break
        
        # Extract year and suggest era-appropriate genres
        year = self._extract_year_from_path(str(path))
        if year:
            era_suggestions = self._get_era_genres(year)
            if era_suggestions:
                suggested_genres.extend(era_suggestions[:2])
                reasoning_parts.append(f"era-based ({year})")
        
        if not suggested_genres:
            return None
        
        # Normalize and deduplicate
        normalized = self.standardizer.normalize_genre_list(suggested_genres)
        unique_genres = list(dict.fromkeys(normalized))[:3]
        
        confidence = min(70, len(unique_genres) * 20 + 30)
        reasoning = f"Directory analysis: {', '.join(reasoning_parts)}"
        
        return GenreSuggestion(
            genres=unique_genres,
            confidence=confidence,
            reasoning=reasoning,
            source="directory_analysis"
        )
    
    def _extract_year_from_path(self, path: str) -> Optional[int]:
        """Extract year from file path"""
        # Look for 4-digit years
        year_pattern = r'\b(19[5-9]\d|20[0-4]\d)\b'
        matches = re.findall(year_pattern, path)
        
        if matches:
            return int(matches[0])
        return None
    
    def _get_era_genres(self, year: int) -> List[str]:
        """Get era-appropriate genre suggestions"""
        for (start, end), genres in self.era_genres.items():
            if start <= year <= end:
                return genres
        return []

class ContextualGenreAnalyzer:
    """Analyzes various contextual clues for genre suggestions"""
    
    def __init__(self, genre_standardizer: GenreStandardizer):
        self.standardizer = genre_standardizer
        
        # Label-based genre hints
        self.label_genres = {
            'sub pop': ['Alternative', 'Indie Rock'],
            'matador': ['Indie Rock', 'Alternative'],
            'merge': ['Indie', 'Electronic'],
            'xl recordings': ['Electronic', 'Alternative'],
            'ninja tune': ['Electronic', 'Hip Hop'],
            'warp': ['Electronic', 'IDM'],
            'kranky': ['Ambient', 'Post-Rock'],
            'constellation': ['Post-Rock', 'Experimental'],
            'sacred bones': ['Punk', 'Experimental'],
            'captured tracks': ['Indie', 'Pop'],
            'jagjaguwar': ['Indie Rock', 'Folk'],
            'epitaph': ['Punk', 'Alternative'],
            'metal blade': ['Metal'],
            'relapse': ['Metal', 'Death Metal'],
            'blue note': ['Jazz'],
            'ecm': ['Jazz', 'Classical'],
            'nonesuch': ['Classical', 'Contemporary'],
            'deutsche grammophon': ['Classical'],
            'def jam': ['Hip Hop'],
            'roc-a-fella': ['Hip Hop'],
            'young money': ['Hip Hop'],
            'island': ['Reggae', 'Rock'],
            'trojan': ['Reggae', 'Ska']
        }
        
        # Country-based genre hints
        self.country_genres = {
            'jamaica': ['Reggae', 'Dub', 'Ska'],
            'brazil': ['Bossa Nova', 'Samba', 'Latin'],
            'cuba': ['Salsa', 'Latin', 'Afro-Cuban'],
            'argentina': ['Tango', 'Latin'],
            'colombia': ['Cumbia', 'Latin'],
            'india': ['Indian Classical', 'World'],
            'japan': ['J-Pop', 'Noise', 'Electronic'],
            'germany': ['Electronic', 'Krautrock'],
            'uk': ['Britpop', 'Electronic', 'Punk'],
            'united kingdom': ['Britpop', 'Electronic', 'Punk'],
            'france': ['Chanson', 'Electronic'],
            'norway': ['Black Metal', 'Electronic'],
            'sweden': ['Death Metal', 'Pop'],
            'finland': ['Metal', 'Electronic']
        }
    
    def analyze_album_context(self, album_info: Dict) -> Optional[GenreSuggestion]:
        """Analyze album context for genre hints"""
        suggestions = []
        reasoning_parts = []
        
        # Analyze track count patterns
        track_count = len(album_info.get('tracks', []))
        if track_count >= 15:
            suggestions.extend(['Compilation', 'Various Artists'])
            reasoning_parts.append(f"high track count ({track_count})")
        elif track_count <= 4:
            suggestions.extend(['EP', 'Single'])
            reasoning_parts.append(f"short release ({track_count} tracks)")
        
        # Analyze artist name patterns
        artist = album_info.get('artist', '').lower()
        if any(keyword in artist for keyword in ['dj', 'mc', 'lil', 'young']):
            suggestions.extend(['Hip Hop', 'Electronic'])
            reasoning_parts.append("artist name pattern")
        
        # Analyze album title patterns
        album_title = album_info.get('album', '').lower()
        title_keywords = {
            'symphony': ['Classical'],
            'concerto': ['Classical'],
            'mass': ['Classical'],
            'requiem': ['Classical'],
            'remix': ['Electronic'],
            'live': ['Live Recording'],
            'unplugged': ['Acoustic', 'Folk'],
            'greatest hits': ['Compilation'],
            'best of': ['Compilation'],
            'collection': ['Compilation']
        }
        
        for keyword, genres in title_keywords.items():
            if keyword in album_title:
                suggestions.extend(genres)
                reasoning_parts.append(f"album title contains '{keyword}'")
        
        if not suggestions:
            return None
        
        # Normalize and prepare result
        normalized = self.standardizer.normalize_genre_list(suggestions)
        unique_genres = list(dict.fromkeys(normalized))[:3]
        
        confidence = min(60, len(reasoning_parts) * 15 + 20)
        reasoning = f"Contextual analysis: {', '.join(reasoning_parts)}"
        
        return GenreSuggestion(
            genres=unique_genres,
            confidence=confidence,
            reasoning=reasoning,
            source="contextual_analysis"
        )

class SmartGenreAssignment:
    """Main smart genre assignment system"""
    
    def __init__(self, music_path: str):
        self.music_path = music_path
        self.standardizer = GenreStandardizer()
        self.artist_analyzer = ArtistGenreAnalyzer(self.standardizer)
        self.directory_extractor = DirectoryGenreExtractor(self.standardizer)
        self.contextual_analyzer = ContextualGenreAnalyzer(self.standardizer)
        
        self.logger = logging.getLogger(__name__)
        
        # Cache for suggestions
        self.suggestion_cache = {}
    
    def initialize(self, albums: Dict[str, Dict]) -> None:
        """Initialize the system with album data"""
        self.logger.info("Initializing smart genre assignment system...")
        self.artist_analyzer.build_artist_profiles(albums)
        self.logger.info("Smart genre assignment system ready")
    
    def get_smart_suggestions(self, album_key: str, album_info: Dict) -> List[GenreSuggestion]:
        """Get comprehensive smart genre suggestions for an album"""
        if album_key in self.suggestion_cache:
            return self.suggestion_cache[album_key]
        
        suggestions = []
        
        # 1. Artist-based suggestions
        artist_suggestion = self.artist_analyzer.suggest_genres_for_artist(album_info['artist'])
        if artist_suggestion:
            suggestions.append(artist_suggestion)
        
        # 2. Directory-based suggestions
        if album_info.get('tracks'):
            first_track = album_info['tracks'][0]
            file_path = first_track.get('file_path')
            if file_path:
                dir_suggestion = self.directory_extractor.extract_from_path(file_path)
                if dir_suggestion:
                    suggestions.append(dir_suggestion)
        
        # 3. Contextual suggestions
        context_suggestion = self.contextual_analyzer.analyze_album_context(album_info)
        if context_suggestion:
            suggestions.append(context_suggestion)
        
        # Cache the results
        self.suggestion_cache[album_key] = suggestions
        
        return suggestions
    
    def get_best_suggestion(self, album_key: str, album_info: Dict) -> Optional[GenreSuggestion]:
        """Get the best single suggestion for an album"""
        suggestions = self.get_smart_suggestions(album_key, album_info)
        
        if not suggestions:
            return None
        
        # Weight suggestions by confidence and combine
        all_genres = []
        total_confidence = 0
        reasoning_parts = []
        sources = []
        
        for suggestion in suggestions:
            weight = suggestion.confidence / 100
            for genre in suggestion.genres:
                all_genres.extend([genre] * int(weight * 10))
            
            total_confidence += suggestion.confidence
            reasoning_parts.append(f"{suggestion.source} ({suggestion.confidence:.0f}%)")
            sources.append(suggestion.source)
        
        if not all_genres:
            return None
        
        # Count weighted genres
        genre_counts = Counter(all_genres)
        top_genres = [genre for genre, count in genre_counts.most_common(3)]
        
        avg_confidence = total_confidence / len(suggestions)
        combined_reasoning = f"Combined analysis: {', '.join(reasoning_parts)}"
        
        return GenreSuggestion(
            genres=top_genres,
            confidence=avg_confidence,
            reasoning=combined_reasoning,
            source="smart_combined"
        )
    
    def analyze_genre_gaps(self, albums: Dict[str, Dict]) -> Dict:
        """Analyze which albums could benefit from smart suggestions"""
        analysis = {
            'albums_without_genres': [],
            'albums_with_poor_genres': [],
            'albums_with_suggestions': 0,
            'suggestion_coverage': {},
            'source_statistics': defaultdict(int)
        }
        
        for album_key, album_info in albums.items():
            has_genres = bool(album_info['genres'])
            
            # Check if we can provide suggestions
            suggestions = self.get_smart_suggestions(album_key, album_info)
            
            if suggestions:
                analysis['albums_with_suggestions'] += 1
                
                for suggestion in suggestions:
                    analysis['source_statistics'][suggestion.source] += 1
                
                if not has_genres:
                    analysis['albums_without_genres'].append({
                        'album_key': album_key,
                        'artist': album_info['artist'],
                        'album': album_info['album'],
                        'suggestions': suggestions
                    })
                else:
                    # Check if current genres are poor quality
                    normalized = self.standardizer.normalize_genre_list(list(album_info['genres']))
                    valid, invalid = self.standardizer.validate_genres(normalized)
                    
                    if len(invalid) > len(valid):
                        analysis['albums_with_poor_genres'].append({
                            'album_key': album_key,
                            'artist': album_info['artist'],
                            'album': album_info['album'],
                            'current_genres': list(album_info['genres']),
                            'suggestions': suggestions
                        })
        
        # Calculate coverage statistics
        total_albums = len(albums)
        analysis['suggestion_coverage'] = {
            'total_albums': total_albums,
            'albums_with_suggestions': analysis['albums_with_suggestions'],
            'coverage_percentage': (analysis['albums_with_suggestions'] / total_albums * 100) if total_albums > 0 else 0
        }
        
        return analysis
    
    def generate_suggestion_report(self, albums: Dict[str, Dict], limit: int = 20) -> None:
        """Generate a detailed report of smart suggestions"""
        analysis = self.analyze_genre_gaps(albums)
        
        print("SMART GENRE ASSIGNMENT ANALYSIS")
        print("=" * 60)
        print(f"Total albums analyzed: {analysis['suggestion_coverage']['total_albums']}")
        print(f"Albums with suggestions: {analysis['suggestion_coverage']['albums_with_suggestions']}")
        print(f"Coverage: {analysis['suggestion_coverage']['coverage_percentage']:.1f}%")
        print()
        
        print("SUGGESTION SOURCES:")
        for source, count in analysis['source_statistics'].items():
            print(f"  {source}: {count} albums")
        print()
        
        print(f"TOP {limit} ALBUMS WITHOUT GENRES (with suggestions):")
        print("-" * 60)
        for i, album in enumerate(analysis['albums_without_genres'][:limit]):
            print(f"{i+1}. {album['artist']} - {album['album']}")
            for suggestion in album['suggestions']:
                print(f"   {suggestion.source}: {suggestion.genres} ({suggestion.confidence:.0f}%)")
                print(f"   Reasoning: {suggestion.reasoning}")
            print()
        
        if analysis['albums_with_poor_genres']:
            print(f"\nTOP {limit//2} ALBUMS WITH POOR GENRES (with suggestions):")
            print("-" * 60)
            for i, album in enumerate(analysis['albums_with_poor_genres'][:limit//2]):
                print(f"{i+1}. {album['artist']} - {album['album']}")
                print(f"   Current: {album['current_genres']}")
                best_suggestion = self.get_best_suggestion(album['album_key'], albums[album['album_key']])
                if best_suggestion:
                    print(f"   Suggested: {best_suggestion.genres} ({best_suggestion.confidence:.0f}%)")
                print()

if __name__ == "__main__":
    # Test smart genre assignment
    from album_scanner import AlbumScanner
    
    print("Testing Smart Genre Assignment System")
    print("=" * 50)
    
    # Initialize with album data
    matcher = AlbumScanner("/Volumes/T7/Albums")
    matcher.scan_filesystem()
    
    smart_assignment = SmartGenreAssignment("/Volumes/T7/Albums")
    smart_assignment.initialize(matcher.albums)
    
    # Generate analysis report
    smart_assignment.generate_suggestion_report(matcher.albums, limit=10)