#!/usr/bin/env python3
"""
Enhanced API Client with Real Genre Fetching
Integrates MusicBrainz, Last.fm, and Discogs APIs with rate limiting and caching
"""

import time
import json
import hashlib
import sqlite3
import requests
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

try:
    import musicbrainzngs
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError:
    print("Required packages missing. Run: pip install musicbrainzngs requests")
    exit(1)

@dataclass
class GenreResult:
    """Container for genre API results"""
    genres: List[str]
    confidence: float
    source: str
    raw_data: Dict

@dataclass
class AlbumMatch:
    """Container for album match results"""
    artist: str
    album: str
    mbid: Optional[str]
    confidence: float
    genres: List[str]
    year: Optional[int]
    country: Optional[str]
    label: Optional[str]
    raw_data: Dict

class APICache:
    """SQLite-based cache for API results"""
    
    def __init__(self, cache_file: str = "api_cache.db"):
        self.cache_file = cache_file
        self.init_cache()
    
    def init_cache(self):
        """Initialize cache database"""
        conn = sqlite3.connect(self.cache_file)
        cursor = conn.cursor()
        
        # Create tables
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS api_cache (
                key TEXT PRIMARY KEY,
                response TEXT,
                timestamp REAL,
                source TEXT,
                expires_at REAL
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS rate_limit_log (
                api_name TEXT,
                timestamp REAL,
                request_count INTEGER DEFAULT 1
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def get(self, key: str) -> Optional[Dict]:
        """Get cached result if not expired"""
        conn = sqlite3.connect(self.cache_file)
        cursor = conn.cursor()
        
        current_time = time.time()
        cursor.execute(
            'SELECT response, expires_at FROM api_cache WHERE key = ? AND expires_at > ?',
            (key, current_time)
        )
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return json.loads(result[0])
        return None
    
    def set(self, key: str, data: Dict, source: str, ttl_hours: int = 24):
        """Cache result with TTL"""
        conn = sqlite3.connect(self.cache_file)
        cursor = conn.cursor()
        
        expires_at = time.time() + (ttl_hours * 3600)
        
        cursor.execute('''
            INSERT OR REPLACE INTO api_cache (key, response, timestamp, source, expires_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (key, json.dumps(data), time.time(), source, expires_at))
        
        conn.commit()
        conn.close()
    
    def log_request(self, api_name: str):
        """Log API request for rate limiting"""
        conn = sqlite3.connect(self.cache_file)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO rate_limit_log (api_name, timestamp) VALUES (?, ?)
        ''', (api_name, time.time()))
        
        conn.commit()
        conn.close()
    
    def get_request_count(self, api_name: str, window_seconds: int) -> int:
        """Get request count within time window"""
        conn = sqlite3.connect(self.cache_file)
        cursor = conn.cursor()
        
        cutoff_time = time.time() - window_seconds
        cursor.execute(
            'SELECT COUNT(*) FROM rate_limit_log WHERE api_name = ? AND timestamp > ?',
            (api_name, cutoff_time)
        )
        
        result = cursor.fetchone()[0]
        conn.close()
        return result
    
    def cleanup_expired(self):
        """Remove expired cache entries"""
        conn = sqlite3.connect(self.cache_file)
        cursor = conn.cursor()
        
        current_time = time.time()
        cursor.execute('DELETE FROM api_cache WHERE expires_at < ?', (current_time,))
        cursor.execute('DELETE FROM rate_limit_log WHERE timestamp < ?', (current_time - 86400,))  # Keep 24 hours
        
        conn.commit()
        conn.close()

class RateLimiter:
    """Rate limiter for API requests"""
    
    def __init__(self, cache: APICache):
        self.cache = cache
        self.limits = {
            'musicbrainz': {'requests': 50, 'window': 60},  # 50 requests per minute
            'lastfm': {'requests': 300, 'window': 60},      # 5 requests per second
            'discogs': {'requests': 60, 'window': 60}       # 60 requests per minute
        }
    
    def wait_if_needed(self, api_name: str):
        """Wait if rate limit would be exceeded"""
        if api_name not in self.limits:
            return
        
        limit_config = self.limits[api_name]
        current_count = self.cache.get_request_count(api_name, limit_config['window'])
        
        if current_count >= limit_config['requests']:
            sleep_time = limit_config['window']
            logging.info(f"Rate limit reached for {api_name}, sleeping for {sleep_time} seconds")
            time.sleep(sleep_time)
        
        # Add small delay between requests
        time.sleep(0.1 if api_name == 'lastfm' else 1.0)
    
    def log_request(self, api_name: str):
        """Log request for rate limiting"""
        self.cache.log_request(api_name)

class EnhancedAPIClient:
    """Enhanced API client with real genre fetching capabilities"""
    
    def __init__(self, config_file: str = "api_config.json"):
        self.cache = APICache()
        self.rate_limiter = RateLimiter(self.cache)
        self.session = self._create_session()
        
        # Load API credentials
        self.config = self._load_config(config_file)
        
        # Initialize MusicBrainz
        musicbrainzngs.set_useragent("MusicLibraryTagger", "2.0", "https://github.com/user/music-tagger")
        
        # Set up logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
    
    def _create_session(self) -> requests.Session:
        """Create session with retry strategy"""
        session = requests.Session()
        
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        return session
    
    def _load_config(self, config_file: str) -> Dict:
        """Load API configuration"""
        config_path = Path(config_file)
        
        default_config = {
            "lastfm_api_key": "",
            "discogs_token": "",
            "musicbrainz_user": "",
            "musicbrainz_password": ""
        }
        
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = json.load(f)
                return {**default_config, **config}
        else:
            with open(config_path, 'w') as f:
                json.dump(default_config, f, indent=2)
            print(f"Created {config_file}. Please add your API credentials.")
            return default_config
    
    def _cache_key(self, *args) -> str:
        """Generate cache key from arguments"""
        key_string = "|".join(str(arg) for arg in args)
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def search_musicbrainz_release(self, artist: str, album: str) -> Optional[AlbumMatch]:
        """Search MusicBrainz for release with genre information"""
        cache_key = self._cache_key("mb_release", artist, album)
        cached = self.cache.get(cache_key)
        
        if cached:
            return AlbumMatch(**cached) if cached.get('success') else None
        
        self.rate_limiter.wait_if_needed('musicbrainz')
        
        try:
            # Search for releases
            query = f'artist:"{artist}" AND release:"{album}"'
            result = musicbrainzngs.search_releases(query=query, limit=5)
            
            self.rate_limiter.log_request('musicbrainz')
            
            if not result.get('release-list'):
                self.cache.set(cache_key, {'success': False}, 'musicbrainz')
                return None
            
            # Get the best match
            best_release = result['release-list'][0]
            
            # Get detailed release information including genre
            detailed_release = self._get_musicbrainz_release_details(best_release['id'])
            
            if detailed_release:
                self.cache.set(cache_key, detailed_release.__dict__, 'musicbrainz')
                return detailed_release
            
        except Exception as e:
            self.logger.error(f"MusicBrainz search error: {e}")
        
        self.cache.set(cache_key, {'success': False}, 'musicbrainz')
        return None
    
    def _get_musicbrainz_release_details(self, mbid: str) -> Optional[AlbumMatch]:
        """Get detailed release information from MusicBrainz"""
        try:
            self.rate_limiter.wait_if_needed('musicbrainz')
            
            # Get release with all possible includes
            result = musicbrainzngs.get_release_by_id(
                mbid, 
                includes=['artists', 'release-groups', 'tags', 'labels']
            )
            
            self.rate_limiter.log_request('musicbrainz')
            
            release = result['release']
            
            # Extract basic information
            artist = self._extract_artist_name(release.get('artist-credit', []))
            album = release.get('title', '')
            year = self._extract_year(release.get('date'))
            country = release.get('country')
            label = self._extract_label(release.get('label-info-list', []))
            
            # Extract genres from various sources
            genres = set()
            
            # From release genres
            if 'genre-list' in release:
                for genre in release['genre-list']:
                    genres.add(genre['name'])
            
            # From release tags
            if 'tag-list' in release:
                for tag in release['tag-list']:
                    if tag.get('count', 0) > 0:  # Only include tags with votes
                        genres.add(tag['name'])
            
            # From release group if available
            if 'release-group' in release:
                rg = release['release-group']
                if 'genre-list' in rg:
                    for genre in rg['genre-list']:
                        genres.add(genre['name'])
                if 'tag-list' in rg:
                    for tag in rg['tag-list']:
                        if tag.get('count', 0) > 0:
                            genres.add(tag['name'])
            
            # Calculate confidence based on data completeness
            confidence = self._calculate_mb_confidence(release, len(genres))
            
            return AlbumMatch(
                artist=artist,
                album=album,
                mbid=mbid,
                confidence=confidence,
                genres=list(genres),
                year=year,
                country=country,
                label=label,
                raw_data=release
            )
            
        except Exception as e:
            self.logger.error(f"MusicBrainz detail fetch error: {e}")
            return None
    
    def search_lastfm_genres(self, artist: str, album: str) -> Optional[GenreResult]:
        """Get genre information from Last.fm"""
        if not self.config.get('lastfm_api_key'):
            return None
        
        cache_key = self._cache_key("lastfm", artist, album)
        cached = self.cache.get(cache_key)
        
        if cached:
            return GenreResult(**cached) if cached.get('success') else None
        
        self.rate_limiter.wait_if_needed('lastfm')
        
        try:
            # Search for album
            url = "http://ws.audioscrobbler.com/2.0/"
            params = {
                'method': 'album.getinfo',
                'api_key': self.config['lastfm_api_key'],
                'artist': artist,
                'album': album,
                'format': 'json'
            }
            
            response = self.session.get(url, params=params)
            self.rate_limiter.log_request('lastfm')
            
            if response.status_code == 200:
                data = response.json()
                
                if 'album' in data:
                    album_data = data['album']
                    genres = []
                    
                    # Extract genres from tags
                    if 'tags' in album_data and 'tag' in album_data['tags']:
                        tags = album_data['tags']['tag']
                        if isinstance(tags, dict):  # Single tag
                            tags = [tags]
                        
                        for tag in tags:
                            genres.append(tag['name'])
                    
                    # Calculate confidence based on listener count and tag count
                    listeners = int(album_data.get('listeners', 0))
                    confidence = min(90, (listeners / 1000) + (len(genres) * 10))
                    
                    result = GenreResult(
                        genres=genres,
                        confidence=confidence,
                        source='lastfm',
                        raw_data=album_data
                    )
                    
                    self.cache.set(cache_key, result.__dict__, 'lastfm')
                    return result
            
        except Exception as e:
            self.logger.error(f"Last.fm search error: {e}")
        
        self.cache.set(cache_key, {'success': False}, 'lastfm')
        return None
    
    def search_discogs_genres(self, artist: str, album: str) -> Optional[GenreResult]:
        """Get genre information from Discogs"""
        if not self.config.get('discogs_token'):
            return None
        
        cache_key = self._cache_key("discogs", artist, album)
        cached = self.cache.get(cache_key)
        
        if cached:
            return GenreResult(**cached) if cached.get('success') else None
        
        self.rate_limiter.wait_if_needed('discogs')
        
        try:
            url = "https://api.discogs.com/database/search"
            headers = {'Authorization': f'Discogs token={self.config["discogs_token"]}'}
            params = {
                'q': f'{artist} {album}',
                'type': 'release',
                'per_page': 5
            }
            
            response = self.session.get(url, headers=headers, params=params)
            self.rate_limiter.log_request('discogs')
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get('results'):
                    # Get the first result
                    result = data['results'][0]
                    
                    genres = result.get('genre', [])
                    styles = result.get('style', [])
                    all_genres = genres + styles
                    
                    # Calculate confidence based on data availability
                    confidence = min(85, len(all_genres) * 15 + 40)
                    
                    genre_result = GenreResult(
                        genres=all_genres,
                        confidence=confidence,
                        source='discogs',
                        raw_data=result
                    )
                    
                    self.cache.set(cache_key, genre_result.__dict__, 'discogs')
                    return genre_result
            
        except Exception as e:
            self.logger.error(f"Discogs search error: {e}")
        
        self.cache.set(cache_key, {'success': False}, 'discogs')
        return None
    
    def get_comprehensive_genres(self, artist: str, album: str) -> Dict:
        """Get genres from all available sources and combine results"""
        results = {
            'musicbrainz': None,
            'lastfm': None,
            'discogs': None,
            'combined_genres': [],
            'confidence': 0,
            'sources_used': []
        }
        
        # Get results from all sources
        mb_result = self.search_musicbrainz_release(artist, album)
        if mb_result:
            results['musicbrainz'] = mb_result
            results['sources_used'].append('musicbrainz')
        
        lastfm_result = self.search_lastfm_genres(artist, album)
        if lastfm_result:
            results['lastfm'] = lastfm_result
            results['sources_used'].append('lastfm')
        
        discogs_result = self.search_discogs_genres(artist, album)
        if discogs_result:
            results['discogs'] = discogs_result
            results['sources_used'].append('discogs')
        
        # Combine and rank genres
        genre_scores = {}
        
        # Weight genres by source reliability and confidence
        weights = {'musicbrainz': 1.0, 'lastfm': 0.8, 'discogs': 0.9}
        
        for source, weight in weights.items():
            source_data = results[source]
            if source_data:
                confidence_multiplier = (source_data.confidence if hasattr(source_data, 'confidence') else source_data.get('confidence', 50)) / 100
                for genre in (source_data.genres if hasattr(source_data, 'genres') else source_data.get('genres', [])):
                    if genre not in genre_scores:
                        genre_scores[genre] = 0
                    genre_scores[genre] += weight * confidence_multiplier
        
        # Sort genres by score and take top ones
        sorted_genres = sorted(genre_scores.items(), key=lambda x: x[1], reverse=True)
        results['combined_genres'] = [genre for genre, score in sorted_genres[:5]]
        
        # Calculate overall confidence
        if results['sources_used']:
            confidences = []
            if mb_result:
                confidences.append(mb_result.confidence)
            if lastfm_result:
                confidences.append(lastfm_result.confidence)
            if discogs_result:
                confidences.append(discogs_result.confidence)
            
            results['confidence'] = sum(confidences) / len(confidences) if confidences else 0
        
        return results
    
    def _extract_artist_name(self, artist_credit: List) -> str:
        """Extract artist name from MusicBrainz artist credit"""
        if not artist_credit:
            return ""
        
        if isinstance(artist_credit[0], dict) and 'artist' in artist_credit[0]:
            return artist_credit[0]['artist']['name']
        return str(artist_credit[0])
    
    def _extract_year(self, date_str: Optional[str]) -> Optional[int]:
        """Extract year from date string"""
        if not date_str:
            return None
        try:
            return int(date_str[:4])
        except (ValueError, TypeError):
            return None
    
    def _extract_label(self, label_info_list: List) -> Optional[str]:
        """Extract label name from label info list"""
        if not label_info_list:
            return None
        
        for label_info in label_info_list:
            if 'label' in label_info and 'name' in label_info['label']:
                return label_info['label']['name']
        
        return None
    
    def _calculate_mb_confidence(self, release: Dict, genre_count: int) -> float:
        """Calculate confidence score for MusicBrainz result"""
        score = 50  # Base score
        
        # Boost for having genres/tags
        score += min(30, genre_count * 5)
        
        # Boost for having complete metadata
        if release.get('date'):
            score += 5
        if release.get('country'):
            score += 5
        if release.get('label-info-list'):
            score += 5
        if release.get('barcode'):
            score += 5
        
        return min(95, score)
    
    def cleanup_cache(self):
        """Clean up expired cache entries"""
        self.cache.cleanup_expired()

if __name__ == "__main__":
    # Test the enhanced API client
    client = EnhancedAPIClient()
    
    # Test album search
    test_artist = "Pink Floyd"
    test_album = "The Dark Side of the Moon"
    
    print(f"Testing API search for: {test_artist} - {test_album}")
    print("=" * 60)
    
    results = client.get_comprehensive_genres(test_artist, test_album)
    
    print(f"Sources used: {results['sources_used']}")
    print(f"Overall confidence: {results['confidence']:.1f}%")
    print(f"Combined genres: {results['combined_genres']}")
    
    if results['musicbrainz']:
        print(f"\nMusicBrainz: {results['musicbrainz'].genres} (confidence: {results['musicbrainz'].confidence:.1f}%)")
    
    if results['lastfm']:
        print(f"Last.fm: {results['lastfm'].genres} (confidence: {results['lastfm'].confidence:.1f}%)")
    
    if results['discogs']:
        print(f"Discogs: {results['discogs'].genres} (confidence: {results['discogs'].confidence:.1f}%)")