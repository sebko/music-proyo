#!/usr/bin/env python3
"""
Hybrid Genre Fetcher - Multi-Source Genre Aggregation System
Combines multiple APIs for maximum coverage and accuracy
"""

import time
import json
import hashlib
import sqlite3
import requests
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from collections import Counter, defaultdict

try:
    import musicbrainzngs
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials
except ImportError:
    print("Required packages missing. Run: pip install musicbrainzngs spotipy requests")
    exit(1)

@dataclass
class GenreSource:
    """Container for genre data from a specific source"""
    source: str
    genres: List[str]
    confidence: float
    weight: float  # Source reliability weight
    raw_data: Dict = field(default_factory=dict)
    api_confidence: float = 0.0  # API-reported confidence
    match_quality: float = 0.0   # Our calculated match quality

@dataclass
class AggregatedGenres:
    """Final aggregated genre results"""
    final_genres: List[str]
    confidence: float
    sources_used: List[str]
    source_breakdown: Dict[str, GenreSource]
    reasoning: str

class HybridGenreFetcher:
    """Multi-source genre fetcher with intelligent aggregation"""
    
    def __init__(self, config_file: str = "api_config.json"):
        self.config_file = config_file
        self.config = self._load_config()
        
        # Source weights (higher = more reliable)
        self.source_weights = {
            'spotify': 1.0,      # Best coverage + professional curation - GOLD STANDARD
            'musicbrainz': 0.85, # Community-driven but high quality when found
            'lastfm': 0.7,       # Community driven, variable quality
            'discogs': 0.8,      # Good for detailed styles and rare releases
            'deezer': 0.75,      # Good European coverage
            'allmusic': 0.9      # Professional curation but limited API access
        }
        
        # Initialize APIs
        self._init_apis()
        
        # Setup caching
        self.cache = self._init_cache()
    
    def _load_config(self) -> Dict:
        """Load API configuration"""
        config_path = Path(self.config_file)
        if config_path.exists():
            with open(config_path, 'r') as f:
                return json.load(f)
        else:
            # Create default config
            default_config = {
                "spotify": {
                    "client_id": "",
                    "client_secret": "",
                    "enabled": False
                },
                "musicbrainz": {
                    "user_agent": "MusicGenreTagger/2.0",
                    "enabled": True
                },
                "lastfm": {
                    "api_key": "",
                    "enabled": False
                },
                "discogs": {
                    "token": "",
                    "enabled": False
                },
                "deezer": {
                    "enabled": True  # No key required for basic access
                },
                "allmusic": {
                    "api_key": "",
                    "enabled": False
                }
            }
            
            with open(config_path, 'w') as f:
                json.dump(default_config, f, indent=2)
            
            print(f"Created {config_path} - please add your API keys")
            return default_config
    
    def _init_apis(self):
        """Initialize API clients"""
        self.apis = {}
        
        # Spotify
        if self.config.get('spotify', {}).get('enabled'):
            try:
                client_credentials = SpotifyClientCredentials(
                    client_id=self.config['spotify']['client_id'],
                    client_secret=self.config['spotify']['client_secret']
                )
                self.apis['spotify'] = spotipy.Spotify(client_credentials_manager=client_credentials)
                logging.info("Spotify API initialized")
            except Exception as e:
                logging.error(f"Failed to initialize Spotify API: {e}")
        
        # MusicBrainz
        if self.config.get('musicbrainz', {}).get('enabled'):
            try:
                musicbrainzngs.set_useragent(
                    self.config['musicbrainz']['user_agent'],
                    "2.0"
                )
                self.apis['musicbrainz'] = musicbrainzngs
                logging.info("MusicBrainz API initialized")
            except Exception as e:
                logging.error(f"Failed to initialize MusicBrainz API: {e}")
    
    def _init_cache(self) -> sqlite3.Connection:
        """Initialize SQLite cache"""
        cache_db = sqlite3.connect("hybrid_genre_cache.db")
        cursor = cache_db.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS genre_cache (
                cache_key TEXT PRIMARY KEY,
                artist TEXT,
                album TEXT,
                source TEXT,
                genres TEXT,
                confidence REAL,
                weight REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_artist_album 
            ON genre_cache(artist, album)
        ''')
        
        cache_db.commit()
        return cache_db
    
    def get_cache_key(self, artist: str, album: str, source: str) -> str:
        """Generate cache key"""
        key_string = f"{artist.lower()}|{album.lower()}|{source}"
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def get_cached_result(self, artist: str, album: str, source: str) -> Optional[GenreSource]:
        """Get cached genre result"""
        cache_key = self.get_cache_key(artist, album, source)
        cursor = self.cache.cursor()
        
        cursor.execute('''
            SELECT genres, confidence, weight, created_at 
            FROM genre_cache 
            WHERE cache_key = ? AND (expires_at IS NULL OR expires_at > datetime('now'))
        ''', (cache_key,))
        
        result = cursor.fetchone()
        if result:
            genres = json.loads(result[0])
            return GenreSource(
                source=source,
                genres=genres,
                confidence=result[1],
                weight=result[2]
            )
        return None
    
    def cache_result(self, artist: str, album: str, genre_source: GenreSource, ttl_hours: int = 24):
        """Cache genre result"""
        cache_key = self.get_cache_key(artist, album, genre_source.source)
        expires_at = datetime.now() + timedelta(hours=ttl_hours)
        
        cursor = self.cache.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO genre_cache 
            (cache_key, artist, album, source, genres, confidence, weight, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            cache_key, artist, album, genre_source.source,
            json.dumps(genre_source.genres), genre_source.confidence,
            genre_source.weight, expires_at
        ))
        self.cache.commit()
    
    def fetch_spotify_genres(self, artist: str, album: str) -> Optional[GenreSource]:
        """Fetch genres from Spotify"""
        if 'spotify' not in self.apis:
            return None
        
        # Check cache first
        cached = self.get_cached_result(artist, album, 'spotify')
        if cached:
            return cached
        
        try:
            # Search for album
            query = f'artist:"{artist}" album:"{album}"'
            results = self.apis['spotify'].search(q=query, type='album', limit=10)
            
            if not results['albums']['items']:
                return None
            
            # Find best match
            best_match = None
            best_score = 0
            
            for album_item in results['albums']['items']:
                # Calculate match score
                artist_match = self._calculate_string_similarity(
                    artist.lower(), 
                    album_item['artists'][0]['name'].lower()
                )
                album_match = self._calculate_string_similarity(
                    album.lower(),
                    album_item['name'].lower()
                )
                
                score = (artist_match + album_match) / 2
                
                # Debug logging disabled for production
                # if len(results['albums']['items']) == 10:  # Only log first search
                #     print(f"    SPOTIFY: '{artist}' vs '{album_item['artists'][0]['name']}' = {artist_match:.2f}")
                #     print(f"    SPOTIFY: '{album}' vs '{album_item['name']}' = {album_match:.2f}")
                #     print(f"    SPOTIFY: Combined score = {score:.2f}")
                
                if score > best_score:
                    best_score = score
                    best_match = album_item
            
            if not best_match or best_score < 0.7:
                print(f"    SPOTIFY: No match found (best score: {best_score:.2f})")
                return None
            
            # Get artist details for genres
            artist_id = best_match['artists'][0]['id']
            artist_details = self.apis['spotify'].artist(artist_id)
            
            genres = artist_details.get('genres', [])
            
            if not genres:
                return None
            
            genre_source = GenreSource(
                source='spotify',
                genres=genres,
                confidence=best_score * 100,
                weight=self.source_weights['spotify'],
                api_confidence=best_score * 100,
                match_quality=best_score,
                raw_data={
                    'album_id': best_match['id'],
                    'artist_id': artist_id,
                    'popularity': artist_details.get('popularity', 0)
                }
            )
            
            # Cache result
            self.cache_result(artist, album, genre_source)
            
            return genre_source
            
        except Exception as e:
            logging.error(f"Spotify API error for {artist} - {album}: {e}")
            return None
    
    def fetch_musicbrainz_genres(self, artist: str, album: str) -> Optional[GenreSource]:
        """Fetch genres from MusicBrainz"""
        if 'musicbrainz' not in self.apis:
            return None
        
        # Check cache first
        cached = self.get_cached_result(artist, album, 'musicbrainz')
        if cached:
            return cached
        
        try:
            # Rate limiting
            time.sleep(1)
            
            # Search for release
            result = self.apis['musicbrainz'].search_releases(
                artist=artist,
                release=album,
                limit=10,
                strict=False
            )
            
            if not result['release-list']:
                return None
            
            # Find best match
            best_match = None
            best_score = 0
            
            for release in result['release-list']:
                if 'artist-credit' not in release:
                    continue
                
                release_artist = release['artist-credit'][0]['artist']['name']
                
                artist_match = self._calculate_string_similarity(
                    artist.lower(),
                    release_artist.lower()
                )
                album_match = self._calculate_string_similarity(
                    album.lower(),
                    release['title'].lower()
                )
                
                score = (artist_match + album_match) / 2
                if score > best_score:
                    best_score = score
                    best_match = release
            
            if not best_match or best_score < 0.7:
                return None
            
            # Get detailed release info
            release_id = best_match['id']
            detailed_release = self.apis['musicbrainz'].get_release_by_id(
                release_id,
                includes=['artists', 'release-groups', 'tags']
            )
            
            # Extract genres from tags
            genres = []
            if 'tag-list' in detailed_release['release']:
                for tag in detailed_release['release']['tag-list']:
                    try:
                        count = int(tag.get('count', 0))
                        if count >= 2:  # Only tags with some votes
                            genres.append(tag['name'].title())
                    except (ValueError, TypeError):
                        # Skip tags with invalid count data
                        continue
            
            # Also check artist tags
            if 'artist-credit' in detailed_release['release']:
                artist_id = detailed_release['release']['artist-credit'][0]['artist']['id']
                try:
                    artist_details = self.apis['musicbrainz'].get_artist_by_id(
                        artist_id,
                        includes=['tags']
                    )
                    
                    if 'tag-list' in artist_details['artist']:
                        for tag in artist_details['artist']['tag-list']:
                            try:
                                count = int(tag.get('count', 0))
                                if count >= 3:  # Higher threshold for artist tags
                                    genre = tag['name'].title()
                                    if genre not in genres:
                                        genres.append(genre)
                            except (ValueError, TypeError):
                                # Skip tags with invalid count data
                                continue
                except:
                    pass  # Artist lookup failed, continue with release tags
            
            if not genres:
                return None
            
            genre_source = GenreSource(
                source='musicbrainz',
                genres=genres[:10],  # Limit to top 10 genres
                confidence=best_score * 100,
                weight=self.source_weights['musicbrainz'],
                api_confidence=best_score * 100,
                match_quality=best_score,
                raw_data={
                    'release_id': release_id,
                    'mbid': best_match['id']
                }
            )
            
            # Cache result
            self.cache_result(artist, album, genre_source)
            
            return genre_source
            
        except Exception as e:
            logging.error(f"MusicBrainz API error for {artist} - {album}: {e}")
            return None
    
    def fetch_deezer_genres(self, artist: str, album: str) -> Optional[GenreSource]:
        """Fetch genres from Deezer (free API)"""
        # Check cache first
        cached = self.get_cached_result(artist, album, 'deezer')
        if cached:
            return cached
        
        try:
            # Search for album on Deezer
            search_url = "https://api.deezer.com/search/album"
            params = {
                'q': f'artist:"{artist}" album:"{album}"',
                'limit': 10
            }
            
            response = requests.get(search_url, params=params, timeout=10)
            if response.status_code != 200:
                return None
            
            data = response.json()
            if not data.get('data'):
                return None
            
            # Find best match
            best_match = None
            best_score = 0
            
            for album_item in data['data']:
                artist_match = self._calculate_string_similarity(
                    artist.lower(),
                    album_item['artist']['name'].lower()
                )
                album_match = self._calculate_string_similarity(
                    album.lower(),
                    album_item['title'].lower()
                )
                
                score = (artist_match + album_match) / 2
                if score > best_score:
                    best_score = score
                    best_match = album_item
            
            if not best_match or best_score < 0.7:
                return None
            
            # Get genre from album
            genres = []
            if 'genre_id' in best_match:
                # Get genre details
                genre_url = f"https://api.deezer.com/genre/{best_match['genre_id']}"
                genre_response = requests.get(genre_url, timeout=10)
                if genre_response.status_code == 200:
                    genre_data = genre_response.json()
                    if 'name' in genre_data:
                        genres.append(genre_data['name'])
            
            if not genres:
                return None
            
            genre_source = GenreSource(
                source='deezer',
                genres=genres,
                confidence=best_score * 100,
                weight=self.source_weights['deezer'],
                api_confidence=best_score * 100,
                match_quality=best_score,
                raw_data={
                    'album_id': best_match['id'],
                    'artist_id': best_match['artist']['id']
                }
            )
            
            # Cache result
            self.cache_result(artist, album, genre_source)
            
            return genre_source
            
        except Exception as e:
            logging.error(f"Deezer API error for {artist} - {album}: {e}")
            return None
    
    def _calculate_string_similarity(self, str1: str, str2: str) -> float:
        """Calculate similarity between two strings"""
        from difflib import SequenceMatcher
        return SequenceMatcher(None, str1, str2).ratio()
    
    def aggregate_genres(self, genre_sources: List[GenreSource]) -> AggregatedGenres:
        """Aggregate genres from multiple sources intelligently"""
        if not genre_sources:
            return AggregatedGenres(
                final_genres=[],
                confidence=0.0,
                sources_used=[],
                source_breakdown={},
                reasoning="No sources returned genres"
            )
        
        # Normalize all genres
        genre_scores = defaultdict(float)
        genre_sources_map = defaultdict(list)
        
        for source in genre_sources:
            source_multiplier = source.weight * (source.confidence / 100)
            
            for genre in source.genres:
                normalized_genre = self._normalize_genre_name(genre)
                genre_scores[normalized_genre] += source_multiplier
                genre_sources_map[normalized_genre].append(source.source)
        
        # Sort genres by score
        sorted_genres = sorted(genre_scores.items(), key=lambda x: x[1], reverse=True)
        
        # Select top genres with minimum threshold
        final_genres = []
        min_score = 0.3  # Minimum score to include a genre
        
        for genre, score in sorted_genres:
            if score >= min_score and len(final_genres) < 10:
                final_genres.append(genre)
        
        # Calculate overall confidence - PURE MATCH QUALITY FOCUS
        if not genre_sources:
            final_confidence = 0
        else:
            # Focus purely on string matching quality
            source_confidences = []
            for source in genre_sources:
                # Use actual match quality (string similarity) as primary factor
                match_confidence = getattr(source, 'match_quality', 0.7)  # Default if missing
                # print(f"      DEBUG: {source.source} match_quality = {match_confidence}")  # Disabled
                weighted_confidence = match_confidence * source.weight * 100
                source_confidences.append(weighted_confidence)
            
            # Average confidence from all sources
            avg_confidence = sum(source_confidences) / len(source_confidences)
            
            # Moderate boost for multiple sources agreeing on same album
            source_count_bonus = min(15, (len(genre_sources) - 1) * 10)  # Up to +15% for multiple sources
            
            # REMOVED: Genre coverage bonus - focus purely on match quality
            
            final_confidence = min(100, avg_confidence + source_count_bonus)
        
        # Create reasoning
        sources_used = [source.source for source in genre_sources]
        reasoning_parts = []
        
        for genre in final_genres[:3]:  # Top 3 genres
            sources = genre_sources_map[genre]
            reasoning_parts.append(f"{genre} ({', '.join(sources)})")
        
        reasoning = f"Aggregated from {len(sources_used)} sources: " + "; ".join(reasoning_parts)
        
        source_breakdown = {source.source: source for source in genre_sources}
        
        return AggregatedGenres(
            final_genres=final_genres,
            confidence=final_confidence,
            sources_used=sources_used,
            source_breakdown=source_breakdown,
            reasoning=reasoning
        )
    
    def _normalize_genre_name(self, genre: str) -> str:
        """Normalize genre name for comparison"""
        # Basic normalization
        normalized = genre.strip().title()
        
        # Common mappings
        mappings = {
            'Hip-Hop': 'Hip Hop',
            'R&B': 'R&B',
            'Electronic/Dance': 'Electronic',
            'Rock/Pop': 'Rock',
            'Alternative Rock': 'Alternative Rock'
        }
        
        return mappings.get(normalized, normalized)
    
    def fetch_all_sources(self, artist: str, album: str) -> AggregatedGenres:
        """Fetch genres from all available sources and aggregate"""
        genre_sources = []
        
        # Fetch from each enabled source
        fetchers = [
            ('spotify', self.fetch_spotify_genres),
            ('musicbrainz', self.fetch_musicbrainz_genres),
            ('deezer', self.fetch_deezer_genres),
        ]
        
        for source_name, fetcher_func in fetchers:
            try:
                result = fetcher_func(artist, album)
                if result:
                    genre_sources.append(result)
                    logging.info(f"Got {len(result.genres)} genres from {source_name}: {result.genres}")
            except Exception as e:
                logging.error(f"Failed to fetch from {source_name}: {e}")
        
        # Aggregate results
        return self.aggregate_genres(genre_sources)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    fetcher = HybridGenreFetcher()
    
    # Test with some well-known albums
    test_albums = [
        ("Pink Floyd", "The Dark Side of the Moon"),
        ("The Beatles", "Abbey Road"),
        ("Radiohead", "OK Computer"),
        ("Miles Davis", "Kind of Blue"),
        ("Daft Punk", "Random Access Memories")
    ]
    
    print("🎵 HYBRID GENRE FETCHER TEST")
    print("=" * 60)
    
    for artist, album in test_albums:
        print(f"\n🎯 Testing: {artist} - {album}")
        print("-" * 40)
        
        result = fetcher.fetch_all_sources(artist, album)
        
        print(f"Confidence: {result.confidence:.1f}%")
        print(f"Sources: {', '.join(result.sources_used)}")
        print(f"Genres: {'; '.join(result.final_genres)}")
        print(f"Reasoning: {result.reasoning}")
        
        # Show source breakdown
        for source_name, source_data in result.source_breakdown.items():
            print(f"  {source_name}: {'; '.join(source_data.genres)} ({source_data.confidence:.1f}%)")