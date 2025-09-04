#!/usr/bin/env python3
"""
Matcher - Top-level Music Metadata Matching System
Orchestrates all matching operations: genres, artwork, and future metadata
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from difflib import SequenceMatcher
from hybrid_genre_fetcher import HybridGenreFetcher, AggregatedGenres

class ProcessingStatus(Enum):
    """Status for processing operations - shared across all matching types"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress" 
    COMPLETED = "completed"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"
    SKIPPED = "skipped"

@dataclass
class AlbumMatch:
    """Container for a single album match from an API"""
    source: str
    artist: str
    album: str
    match_score: float
    raw_data: Dict = None

@dataclass
class MatchResult:
    """Container for comprehensive match results"""
    # Required fields (no defaults)
    genres: List[str]
    genre_confidence: float
    genre_sources_used: List[str]
    genre_reasoning: str
    overall_confidence: float
    sources_breakdown: Dict
    
    # New: Best match info
    matched_artist: Optional[str] = None
    matched_album: Optional[str] = None  
    match_confidence: Optional[float] = None
    match_source: Optional[str] = None
    
    # Optional fields (with defaults)
    corrected_artist: Optional[str] = None
    corrected_album: Optional[str] = None
    artist_confidence: Optional[float] = None
    album_confidence: Optional[float] = None
    metadata_reasoning: Optional[str] = None
    processing_status: ProcessingStatus = ProcessingStatus.PENDING
    processing_time: float = 0.0
    
    # Future: artwork, year, label, etc.
    # artwork_url: Optional[str] = None
    # year: Optional[int] = None
    # label: Optional[str] = None

class Matcher:
    """
    Top-level matching system that coordinates all metadata matching operations.
    Currently handles genre matching, designed to be extended for artwork, year, etc.
    """
    
    def __init__(self, config_file: str = "api_config.json"):
        """Initialize the matcher with all necessary components"""
        # Initialize genre fetching system
        self.genre_fetcher = HybridGenreFetcher(config_file)
        
        # Confidence thresholds (lifted from batch_processor.py)
        self.high_confidence_threshold = 95.0    # Auto-update
        self.review_threshold = 70.0             # Manual review
        self.skip_threshold = 40.0               # Skip entirely
        
        # Future: Initialize other metadata fetchers
        # self.artwork_fetcher = ArtworkFetcher()
        # self.metadata_fetcher = MetadataFetcher()
    
    def find_best_album_match(self, artist: str, album: str) -> Optional[AlbumMatch]:
        """
        Find the best album match across all available APIs.
        
        Args:
            artist: Artist name
            album: Album name
            
        Returns:
            AlbumMatch with best match, or None if no matches found
        """
        all_matches = []
        
        # Search Spotify
        spotify_matches = self._search_spotify_albums(artist, album)
        all_matches.extend(spotify_matches)
        
        # Search MusicBrainz  
        mb_matches = self._search_musicbrainz_albums(artist, album)
        all_matches.extend(mb_matches)
        
        # Search Deezer
        deezer_matches = self._search_deezer_albums(artist, album)
        all_matches.extend(deezer_matches)
        
        if not all_matches:
            return None
            
        # Find best match by score
        best_match = max(all_matches, key=lambda x: x.match_score)
        
        print(f"    BEST MATCH: {best_match.source} - '{best_match.artist} - {best_match.album}' ({best_match.match_score:.1%})")
        
        return best_match

    def match_album(self, artist: str, album: str) -> MatchResult:
        """
        NEW FLOW: Find best album match first, then fetch genres for that match.
        
        Args:
            artist: Artist name
            album: Album name
            
        Returns:
            MatchResult containing matched album and genres
        """
        import time
        start_time = time.time()
        
        print(f"\nMATCHING: {artist} - {album}")
        print("-" * 50)
        
        # STEP 1: Find best album match across all APIs
        best_match = self.find_best_album_match(artist, album)
        
        if not best_match:
            # No match found anywhere
            return MatchResult(
                genres=[],
                genre_confidence=0.0,
                genre_sources_used=[],
                genre_reasoning="No album match found in any API",
                overall_confidence=0.0,
                sources_breakdown={},
                processing_status=ProcessingStatus.SKIPPED,
                processing_time=time.time() - start_time,
                matched_artist=None,
                matched_album=None,
                match_confidence=0.0,
                match_source="none"
            )
        
        # STEP 2: Fetch genres using the matched album info
        print(f"Fetching genres for matched album: {best_match.artist} - {best_match.album}")
        genre_result = self.genre_fetcher.fetch_all_sources(best_match.artist, best_match.album)
        
        # STEP 3: Build comprehensive result
        result = MatchResult(
            genres=genre_result.final_genres,
            genre_confidence=genre_result.confidence,
            genre_sources_used=genre_result.sources_used,
            genre_reasoning=genre_result.reasoning,
            overall_confidence=best_match.match_score * 100,  # Use match confidence as overall
            sources_breakdown=genre_result.source_breakdown,
            processing_status=self.evaluate_confidence(best_match.match_score * 100),
            processing_time=time.time() - start_time,
            matched_artist=best_match.artist,
            matched_album=best_match.album,
            match_confidence=best_match.match_score * 100,
            match_source=best_match.source
        )
        
        return result
    
    def match_album_metadata(self, artist: str, album: str, exclude_genres: bool = True) -> MatchResult:
        """
        Match album metadata (artist name, album name) while excluding genre information.
        Uses same APIs as genre fetcher but focuses on metadata correction.
        
        Args:
            artist: Local artist name
            album: Local album name  
            exclude_genres: If True, preserves existing genre information
            
        Returns:
            MatchResult with metadata corrections and confidence scores
        """
        import time
        start_time = time.time()
        
        # Initialize result with empty values
        result = MatchResult(
            genres=[],  # Will be empty if exclude_genres=True
            genre_confidence=0.0,
            genre_sources_used=[],
            genre_reasoning="Genres excluded from metadata matching",
            overall_confidence=0.0,
            sources_breakdown={},
            processing_status=ProcessingStatus.PENDING,
            processing_time=0.0
        )
        
        # Fetch metadata from Spotify (reusing existing API integration)
        try:
            metadata_result = self._fetch_spotify_metadata(artist, album)
            
            if metadata_result:
                # Calculate confidence scores for artist and album corrections
                artist_confidence = self.calculate_string_similarity(
                    artist.lower(), metadata_result['artist'].lower()
                ) * 100
                
                album_confidence = self.calculate_string_similarity(
                    album.lower(), metadata_result['album'].lower()
                ) * 100
                
                # Overall confidence is average of both
                overall_confidence = (artist_confidence + album_confidence) / 2
                
                # Determine if corrections are needed (only if significantly different)
                corrected_artist = metadata_result['artist'] if artist_confidence < 98.0 else None
                corrected_album = metadata_result['album'] if album_confidence < 98.0 else None
                
                # Build reasoning
                reasoning_parts = []
                if corrected_artist:
                    reasoning_parts.append(f"Artist: '{artist}' → '{corrected_artist}' ({artist_confidence:.1f}%)")
                if corrected_album:
                    reasoning_parts.append(f"Album: '{album}' → '{corrected_album}' ({album_confidence:.1f}%)")
                
                reasoning = "; ".join(reasoning_parts) if reasoning_parts else "No corrections needed"
                
                # Update result
                result.corrected_artist = corrected_artist
                result.corrected_album = corrected_album
                result.artist_confidence = artist_confidence
                result.album_confidence = album_confidence
                result.metadata_reasoning = reasoning
                result.overall_confidence = overall_confidence
                result.processing_status = self.evaluate_confidence(overall_confidence)
                result.sources_breakdown = {'spotify': metadata_result}
                
            else:
                result.metadata_reasoning = "No metadata found in Spotify API"
                result.processing_status = ProcessingStatus.SKIPPED
                
        except Exception as e:
            result.metadata_reasoning = f"Error fetching metadata: {str(e)}"
            result.processing_status = ProcessingStatus.FAILED
        
        result.processing_time = time.time() - start_time
        return result
    
    def _fetch_spotify_metadata(self, artist: str, album: str) -> Optional[Dict]:
        """
        Fetch metadata from Spotify API (reusing genre fetcher's Spotify integration).
        Returns dict with artist, album, and other metadata fields.
        """
        if 'spotify' not in self.genre_fetcher.apis:
            return None
        
        try:
            # Try multiple search strategies for better matching
            search_queries = [
                f'artist:"{artist}" album:"{album}"',  # Exact search first
                f'"{artist}" "{album}"',                # Quoted search
                f'{artist} {album}',                    # Broad search
                f'album:"{album}" {artist}'             # Album-focused search
            ]
            
            results = None
            for query in search_queries:
                results = self.genre_fetcher.apis['spotify'].search(q=query, type='album', limit=10)
                if results['albums']['items']:
                    break  # Found results, stop trying other queries
            
            if not results['albums']['items']:
                return None
            
            # Find best match using same logic as genre fetcher
            best_match = None
            best_score = 0
            
            for album_item in results['albums']['items']:
                artist_match = self.calculate_string_similarity(
                    artist.lower(), 
                    album_item['artists'][0]['name'].lower()
                )
                album_match = self.calculate_string_similarity(
                    album.lower(),
                    album_item['name'].lower()
                )
                
                score = (artist_match + album_match) / 2
                
                if score > best_score:
                    best_score = score
                    best_match = album_item
            
            # Use same threshold as genre fetcher  
            if not best_match or best_score < 0.7:
                return None
            
            # Extract metadata (not genres)
            return {
                'artist': best_match['artists'][0]['name'],
                'album': best_match['name'],
                'release_date': best_match.get('release_date', ''),
                'total_tracks': best_match.get('total_tracks', 0),
                'match_score': best_score,
                'spotify_id': best_match.get('id', '')
            }
            
        except Exception as e:
            print(f"Error fetching Spotify metadata: {e}")
            return None

    def match_genres_only(self, artist: str, album: str) -> AggregatedGenres:
        """
        Direct access to genre matching for backward compatibility.
        Use match_album() for comprehensive matching.
        """
        return self.genre_fetcher.fetch_all_sources(artist, album)
    
    def get_available_sources(self) -> List[str]:
        """Get list of available API sources for matching"""
        return list(self.genre_fetcher.source_weights.keys())
    
    def get_source_weights(self) -> Dict[str, float]:
        """Get reliability weights for each source"""
        return self.genre_fetcher.source_weights.copy()
    
    def calculate_string_similarity(self, str1: str, str2: str) -> float:
        """
        Calculate similarity between two strings using sequence matching.
        Lifted from hybrid_genre_fetcher.py for reuse across all matching.
        """
        return SequenceMatcher(None, str1, str2).ratio()
    
    def evaluate_confidence(self, confidence: float) -> ProcessingStatus:
        """
        Evaluate confidence score and return appropriate processing status.
        Currently configured for full manual review - all matches go to NEEDS_REVIEW.
        """
        if confidence >= self.skip_threshold:
            return ProcessingStatus.NEEDS_REVIEW  # All matches need manual review
        else:
            return ProcessingStatus.SKIPPED  # Return to unmatched state
    
    def _search_spotify_albums(self, artist: str, album: str) -> List[AlbumMatch]:
        """Search Spotify for album matches"""
        matches = []
        if 'spotify' not in self.genre_fetcher.apis:
            return matches
            
        try:
            # Try multiple search strategies
            search_queries = [
                f'artist:"{artist}" album:"{album}"',
                f'"{artist}" "{album}"',
                f'{artist} {album}',
                f'album:"{album}" {artist}'
            ]
            
            for query in search_queries:
                try:
                    results = self.genre_fetcher.apis['spotify'].search(q=query, type='album', limit=10)
                    if results['albums']['items']:
                        break
                except:
                    continue
            else:
                return matches
                
            # Process results
            for album_item in results['albums']['items']:
                artist_similarity = self.calculate_string_similarity(
                    artist.lower(),
                    album_item['artists'][0]['name'].lower()
                )
                album_similarity = self.calculate_string_similarity(
                    album.lower(),
                    album_item['name'].lower()
                )
                
                match_score = (artist_similarity + album_similarity) / 2
                
                if match_score >= 0.7:  # Minimum threshold
                    matches.append(AlbumMatch(
                        source='spotify',
                        artist=album_item['artists'][0]['name'],
                        album=album_item['name'],
                        match_score=match_score,
                        raw_data=album_item
                    ))
                    
        except Exception as e:
            print(f"Spotify search error: {e}")
            
        return matches
    
    def _search_musicbrainz_albums(self, artist: str, album: str) -> List[AlbumMatch]:
        """Search MusicBrainz for album matches"""
        matches = []
        if 'musicbrainz' not in self.genre_fetcher.apis:
            return matches
            
        try:
            # Search for releases in MusicBrainz
            results = self.genre_fetcher.apis['musicbrainz'].search_releases(
                artist=artist,
                release=album,
                limit=10
            )
            
            for release in results['release-list']:
                # Get primary artist
                if 'artist-credit' in release and release['artist-credit']:
                    mb_artist = release['artist-credit'][0]['artist']['name']
                else:
                    continue
                    
                mb_album = release['title']
                
                artist_similarity = self.calculate_string_similarity(
                    artist.lower(),
                    mb_artist.lower()
                )
                album_similarity = self.calculate_string_similarity(
                    album.lower(),
                    mb_album.lower()
                )
                
                match_score = (artist_similarity + album_similarity) / 2
                
                if match_score >= 0.7:  # Minimum threshold
                    matches.append(AlbumMatch(
                        source='musicbrainz',
                        artist=mb_artist,
                        album=mb_album,
                        match_score=match_score,
                        raw_data=release
                    ))
                    
        except Exception as e:
            print(f"MusicBrainz search error: {e}")
            
        return matches
    
    def _search_deezer_albums(self, artist: str, album: str) -> List[AlbumMatch]:
        """Search Deezer for album matches"""
        matches = []
        # Note: Deezer API integration needs to be implemented in genre_fetcher
        # For now, return empty list until deezer is properly integrated
        
        # TODO: Implement when deezer API is added to genre_fetcher
        # The logic would be similar to spotify/musicbrainz:
        # 1. Search deezer API for albums
        # 2. Calculate similarity scores
        # 3. Return AlbumMatch objects for good matches
        
        return matches
    
    def clear_cache(self):
        """Clear all cached results"""
        self.genre_fetcher.cache.execute("DELETE FROM genre_cache")
        self.genre_fetcher.cache.commit()
        
    def get_cache_stats(self) -> Dict:
        """Get cache statistics"""
        cursor = self.genre_fetcher.cache.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM genre_cache")
        total_entries = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT source, COUNT(*) 
            FROM genre_cache 
            WHERE expires_at > datetime('now') OR expires_at IS NULL
            GROUP BY source
        """)
        by_source = dict(cursor.fetchall())
        
        return {
            'total_cached_entries': total_entries,
            'entries_by_source': by_source
        }

# Example usage and testing
if __name__ == "__main__":
    matcher = Matcher()
    
    # Test comprehensive matching
    print("Testing comprehensive album matching...")
    result = matcher.match_album("Pink Floyd", "The Dark Side of the Moon")
    
    print(f"\nMatch Results:")
    print(f"Genres: {result.genres}")
    print(f"Confidence: {result.genre_confidence:.1f}%")
    print(f"Sources: {result.genre_sources_used}")
    print(f"Processing time: {result.processing_time:.2f}s")
    print(f"Reasoning: {result.genre_reasoning}")
    
    # Show cache stats
    cache_stats = matcher.get_cache_stats()
    print(f"\nCache Stats: {cache_stats}")