#!/usr/bin/env python3
"""
Quality Control and Consistency Checking System
Validates genre data, detects inconsistencies, and ensures library quality
"""

import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, asdict
from collections import defaultdict, Counter
from datetime import datetime
import logging
import statistics

from genre_standardizer import GenreStandardizer
from album_scanner import AlbumScanner

@dataclass
class QualityIssue:
    """Container for quality control issues"""
    issue_type: str
    severity: str  # 'critical', 'warning', 'info'
    album_key: str
    artist: str
    album: str
    description: str
    suggested_fix: Optional[str] = None
    confidence: float = 0.0
    
@dataclass
class ConsistencyReport:
    """Container for consistency analysis results"""
    total_albums: int
    total_issues: int
    critical_issues: int
    warning_issues: int
    info_issues: int
    genre_quality_score: float
    consistency_score: float
    issues_by_type: Dict[str, int]
    top_issues: List[QualityIssue]

class GenreValidator:
    """Validates individual genre entries"""
    
    def __init__(self, genre_standardizer: GenreStandardizer):
        self.standardizer = genre_standardizer
        
        # Define validation rules
        self.validation_rules = {
            'empty_genre': self._check_empty_genre,
            'invalid_characters': self._check_invalid_characters,
            'too_long': self._check_too_long,
            'numeric_only': self._check_numeric_only,
            'duplicate_words': self._check_duplicate_words,
            'invalid_format': self._check_invalid_format,
            'unknown_genre': self._check_unknown_genre
        }
    
    def validate_genre(self, genre: str) -> List[QualityIssue]:
        """Validate a single genre string"""
        issues = []
        
        for rule_name, rule_func in self.validation_rules.items():
            issue = rule_func(genre)
            if issue:
                issues.append(issue)
        
        return issues
    
    def _check_empty_genre(self, genre: str) -> Optional[QualityIssue]:
        """Check for empty or whitespace-only genres"""
        if not genre or not genre.strip():
            return QualityIssue(
                issue_type='empty_genre',
                severity='warning',
                album_key='',
                artist='',
                album='',
                description='Empty or whitespace-only genre',
                suggested_fix='Remove empty genre or replace with valid genre'
            )
        return None
    
    def _check_invalid_characters(self, genre: str) -> Optional[QualityIssue]:
        """Check for invalid characters in genre"""
        import re
        if re.search(r'[^\w\s\-&/().]', genre):
            return QualityIssue(
                issue_type='invalid_characters',
                severity='warning',
                album_key='',
                artist='',
                album='',
                description=f'Genre contains invalid characters: "{genre}"',
                suggested_fix='Remove special characters and normalize'
            )
        return None
    
    def _check_too_long(self, genre: str) -> Optional[QualityIssue]:
        """Check for excessively long genre names"""
        if len(genre) > 50:
            return QualityIssue(
                issue_type='too_long',
                severity='info',
                album_key='',
                artist='',
                album='',
                description=f'Genre name is very long ({len(genre)} chars): "{genre[:30]}..."',
                suggested_fix='Use shorter, more standard genre name'
            )
        return None
    
    def _check_numeric_only(self, genre: str) -> Optional[QualityIssue]:
        """Check for numeric-only genres"""
        if genre.strip().isdigit():
            return QualityIssue(
                issue_type='numeric_only',
                severity='critical',
                album_key='',
                artist='',
                album='',
                description=f'Genre is numeric only: "{genre}"',
                suggested_fix='Replace with proper genre name'
            )
        return None
    
    def _check_duplicate_words(self, genre: str) -> Optional[QualityIssue]:
        """Check for duplicate words in genre"""
        words = genre.lower().split()
        if len(words) != len(set(words)):
            return QualityIssue(
                issue_type='duplicate_words',
                severity='info',
                album_key='',
                artist='',
                album='',
                description=f'Genre has duplicate words: "{genre}"',
                suggested_fix='Remove duplicate words'
            )
        return None
    
    def _check_invalid_format(self, genre: str) -> Optional[QualityIssue]:
        """Check for invalid genre formats"""
        # Check for multiple slashes, excessive punctuation, etc.
        import re
        if re.search(r'/{2,}|&{2,}|\s{3,}', genre):
            return QualityIssue(
                issue_type='invalid_format',
                severity='warning',
                album_key='',
                artist='',
                album='',
                description=f'Genre has formatting issues: "{genre}"',
                suggested_fix='Clean up spacing and punctuation'
            )
        return None
    
    def _check_unknown_genre(self, genre: str) -> Optional[QualityIssue]:
        """Check if genre is unknown/non-standard"""
        normalized = self.standardizer.normalize_genre(genre)
        if normalized not in self.standardizer.valid_genres:
            return QualityIssue(
                issue_type='unknown_genre',
                severity='info',
                album_key='',
                artist='',
                album='',
                description=f'Unknown genre: "{genre}"',
                suggested_fix=f'Consider mapping to: {", ".join(self.standardizer.suggest_genres(genre, limit=3))}',
                confidence=50.0
            )
        return None

class ArtistConsistencyChecker:
    """Checks for consistency across an artist's discography"""
    
    def __init__(self, genre_standardizer: GenreStandardizer):
        self.standardizer = genre_standardizer
    
    def check_artist_consistency(self, artist: str, albums: List[Dict]) -> List[QualityIssue]:
        """Check consistency across an artist's albums"""
        issues = []
        
        if len(albums) < 2:
            return issues
        
        # Collect all genres for this artist
        all_genres = []
        albums_with_genres = 0
        
        for album in albums:
            if album['genres']:
                albums_with_genres += 1
                normalized_genres = self.standardizer.normalize_genre_list(list(album['genres']))
                all_genres.extend(normalized_genres)
        
        if albums_with_genres < 2:
            return issues
        
        # Calculate genre consistency
        genre_counts = Counter(all_genres)
        total_genre_instances = len(all_genres)
        
        # Check for highly inconsistent artists (too many unique genres)
        unique_genres = len(genre_counts)
        if unique_genres > 10 and albums_with_genres > 5:
            issues.append(QualityIssue(
                issue_type='artist_inconsistency',
                severity='warning',
                album_key='',
                artist=artist,
                album='',
                description=f'Artist has {unique_genres} different genres across {albums_with_genres} albums',
                suggested_fix='Review and standardize artist\'s primary genres',
                confidence=70.0
            ))
        
        # Check for missing genres in discography
        albums_without_genres = len(albums) - albums_with_genres
        if albums_without_genres > 0 and albums_with_genres > 0:
            percentage_missing = (albums_without_genres / len(albums)) * 100
            if percentage_missing > 30:
                issues.append(QualityIssue(
                    issue_type='missing_genres',
                    severity='info',
                    album_key='',
                    artist=artist,
                    album='',
                    description=f'{albums_without_genres}/{len(albums)} albums missing genres ({percentage_missing:.0f}%)',
                    suggested_fix='Add genres to albums based on artist\'s common genres',
                    confidence=80.0
                ))
        
        return issues

class DuplicateDetector:
    """Detects potential duplicate albums"""
    
    def __init__(self):
        self.similarity_threshold = 0.85
    
    def find_potential_duplicates(self, albums: Dict[str, Dict]) -> List[QualityIssue]:
        """Find albums that might be duplicates"""
        issues = []
        checked_pairs = set()
        
        albums_list = list(albums.items())
        
        for i, (key1, album1) in enumerate(albums_list):
            for j, (key2, album2) in enumerate(albums_list[i+1:], i+1):
                pair_key = tuple(sorted([key1, key2]))
                if pair_key in checked_pairs:
                    continue
                checked_pairs.add(pair_key)
                
                similarity = self._calculate_album_similarity(album1, album2)
                
                if similarity >= self.similarity_threshold:
                    issues.append(QualityIssue(
                        issue_type='potential_duplicate',
                        severity='warning',
                        album_key=key1,
                        artist=album1['artist'],
                        album=album1['album'],
                        description=f'Potential duplicate: "{album2["artist"]} - {album2["album"]}" (similarity: {similarity:.0%})',
                        suggested_fix='Review and remove duplicate or mark as different edition',
                        confidence=similarity * 100
                    ))
        
        return issues
    
    def _calculate_album_similarity(self, album1: Dict, album2: Dict) -> float:
        """Calculate similarity between two albums"""
        # Artist similarity
        artist_sim = self._string_similarity(album1['artist'], album2['artist'])
        
        # Album title similarity  
        album_sim = self._string_similarity(album1['album'], album2['album'])
        
        # Track count similarity
        track_count1 = len(album1['tracks'])
        track_count2 = len(album2['tracks'])
        if track_count1 > 0 and track_count2 > 0:
            track_sim = 1 - abs(track_count1 - track_count2) / max(track_count1, track_count2)
        else:
            track_sim = 0.5
        
        # Weighted average
        return (artist_sim * 0.4 + album_sim * 0.5 + track_sim * 0.1)
    
    def _string_similarity(self, str1: str, str2: str) -> float:
        """Calculate string similarity using Levenshtein distance"""
        def levenshtein_distance(s1, s2):
            if len(s1) < len(s2):
                return levenshtein_distance(s2, s1)
            
            if len(s2) == 0:
                return len(s1)
            
            previous_row = list(range(len(s2) + 1))
            for i, c1 in enumerate(s1):
                current_row = [i + 1]
                for j, c2 in enumerate(s2):
                    insertions = previous_row[j + 1] + 1
                    deletions = current_row[j] + 1
                    substitutions = previous_row[j] + (c1 != c2)
                    current_row.append(min(insertions, deletions, substitutions))
                previous_row = current_row
            
            return previous_row[-1]
        
        s1, s2 = str1.lower(), str2.lower()
        distance = levenshtein_distance(s1, s2)
        max_len = max(len(s1), len(s2))
        
        if max_len == 0:
            return 1.0
        
        return 1 - (distance / max_len)

class MetadataQualityChecker:
    """Checks overall metadata quality"""
    
    def check_metadata_completeness(self, albums: Dict[str, Dict]) -> List[QualityIssue]:
        """Check for metadata completeness issues"""
        issues = []
        
        for album_key, album_info in albums.items():
            # Check for missing basic metadata
            if not album_info.get('artist') or not album_info['artist'].strip():
                issues.append(QualityIssue(
                    issue_type='missing_artist',
                    severity='critical',
                    album_key=album_key,
                    artist='',
                    album=album_info.get('album', ''),
                    description='Missing artist name',
                    suggested_fix='Add artist name from file metadata or directory'
                ))
            
            if not album_info.get('album') or not album_info['album'].strip():
                issues.append(QualityIssue(
                    issue_type='missing_album',
                    severity='critical',
                    album_key=album_key,
                    artist=album_info.get('artist', ''),
                    album='',
                    description='Missing album title',
                    suggested_fix='Add album title from file metadata or directory'
                ))
            
            # Check for suspicious metadata
            if album_info.get('artist') == album_info.get('album'):
                issues.append(QualityIssue(
                    issue_type='suspicious_metadata',
                    severity='warning',
                    album_key=album_key,
                    artist=album_info['artist'],
                    album=album_info['album'],
                    description='Artist and album names are identical',
                    suggested_fix='Verify metadata is correct'
                ))
            
            # Check track metadata consistency
            if album_info.get('tracks'):
                self._check_track_metadata_consistency(album_key, album_info, issues)
        
        return issues
    
    def _check_track_metadata_consistency(self, album_key: str, album_info: Dict, issues: List[QualityIssue]):
        """Check consistency of track metadata within an album"""
        tracks = album_info['tracks']
        
        if len(tracks) < 2:
            return
        
        # Check for missing track names
        unnamed_tracks = sum(1 for track in tracks if not track.get('name', '').strip())
        if unnamed_tracks > 0:
            issues.append(QualityIssue(
                issue_type='missing_track_names',
                severity='warning',
                album_key=album_key,
                artist=album_info['artist'],
                album=album_info['album'],
                description=f'{unnamed_tracks}/{len(tracks)} tracks missing names',
                suggested_fix='Add track names from file metadata'
            ))
        
        # Check for inconsistent artists within album
        track_artists = {track.get('artist', '') for track in tracks if track.get('artist')}
        if len(track_artists) > 3:  # More than 3 different artists might indicate compilation
            issues.append(QualityIssue(
                issue_type='multiple_artists',
                severity='info',
                album_key=album_key,
                artist=album_info['artist'],
                album=album_info['album'],
                description=f'Album has {len(track_artists)} different track artists',
                suggested_fix='Consider if this is a compilation album'
            ))

class QualityControlSystem:
    """Main quality control system"""
    
    def __init__(self, music_path: str):
        self.music_path = music_path
        self.standardizer = GenreStandardizer()
        self.validator = GenreValidator(self.standardizer)
        self.consistency_checker = ArtistConsistencyChecker(self.standardizer)
        self.duplicate_detector = DuplicateDetector()
        self.metadata_checker = MetadataQualityChecker()
        
        self.logger = logging.getLogger(__name__)
        
        # Quality control database
        self.db_path = "quality_control.db"
        self._init_database()
    
    def _init_database(self):
        """Initialize quality control database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS quality_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_date TEXT,
                total_albums INTEGER,
                total_issues INTEGER,
                quality_score REAL,
                report_data TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS quality_issues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id INTEGER,
                issue_type TEXT,
                severity TEXT,
                album_key TEXT,
                artist TEXT,
                album TEXT,
                description TEXT,
                suggested_fix TEXT,
                confidence REAL,
                resolved BOOLEAN DEFAULT FALSE,
                FOREIGN KEY (report_id) REFERENCES quality_reports (id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def run_comprehensive_analysis(self, albums: Dict[str, Dict]) -> ConsistencyReport:
        """Run comprehensive quality control analysis"""
        self.logger.info("Starting comprehensive quality control analysis...")
        
        all_issues = []
        
        # 1. Validate individual genres
        self.logger.info("Validating individual genres...")
        genre_issues = self._validate_all_genres(albums)
        all_issues.extend(genre_issues)
        
        # 2. Check artist consistency
        self.logger.info("Checking artist consistency...")
        consistency_issues = self._check_all_artist_consistency(albums)
        all_issues.extend(consistency_issues)
        
        # 3. Find potential duplicates
        self.logger.info("Detecting potential duplicates...")
        duplicate_issues = self.duplicate_detector.find_potential_duplicates(albums)
        all_issues.extend(duplicate_issues)
        
        # 4. Check metadata quality
        self.logger.info("Checking metadata completeness...")
        metadata_issues = self.metadata_checker.check_metadata_completeness(albums)
        all_issues.extend(metadata_issues)
        
        # 5. Generate quality scores
        quality_score = self._calculate_quality_score(albums, all_issues)
        consistency_score = self._calculate_consistency_score(albums, all_issues)
        
        # Categorize issues
        critical_issues = [i for i in all_issues if i.severity == 'critical']
        warning_issues = [i for i in all_issues if i.severity == 'warning']
        info_issues = [i for i in all_issues if i.severity == 'info']
        
        # Count issues by type
        issues_by_type = defaultdict(int)
        for issue in all_issues:
            issues_by_type[issue.issue_type] += 1
        
        # Create report
        report = ConsistencyReport(
            total_albums=len(albums),
            total_issues=len(all_issues),
            critical_issues=len(critical_issues),
            warning_issues=len(warning_issues),
            info_issues=len(info_issues),
            genre_quality_score=quality_score,
            consistency_score=consistency_score,
            issues_by_type=dict(issues_by_type),
            top_issues=sorted(all_issues, key=lambda x: (
                {'critical': 3, 'warning': 2, 'info': 1}[x.severity],
                x.confidence
            ), reverse=True)[:20]
        )
        
        # Save report to database
        self._save_report(report, all_issues)
        
        self.logger.info(f"Quality control analysis complete: {len(all_issues)} issues found")
        return report
    
    def _validate_all_genres(self, albums: Dict[str, Dict]) -> List[QualityIssue]:
        """Validate all genres in the library"""
        issues = []
        
        for album_key, album_info in albums.items():
            if not album_info.get('genres'):
                continue
            
            for genre in album_info['genres']:
                genre_issues = self.validator.validate_genre(genre)
                for issue in genre_issues:
                    issue.album_key = album_key
                    issue.artist = album_info['artist']
                    issue.album = album_info['album']
                    issues.append(issue)
        
        return issues
    
    def _check_all_artist_consistency(self, albums: Dict[str, Dict]) -> List[QualityIssue]:
        """Check consistency for all artists"""
        issues = []
        
        # Group albums by artist
        artist_albums = defaultdict(list)
        for album_key, album_info in albums.items():
            artist = album_info['artist']
            artist_albums[artist].append(album_info)
        
        # Check each artist
        for artist, artist_album_list in artist_albums.items():
            artist_issues = self.consistency_checker.check_artist_consistency(artist, artist_album_list)
            issues.extend(artist_issues)
        
        return issues
    
    def _calculate_quality_score(self, albums: Dict[str, Dict], issues: List[QualityIssue]) -> float:
        """Calculate overall quality score (0-100)"""
        total_albums = len(albums)
        if total_albums == 0:
            return 100.0
        
        # Count different types of issues
        critical_count = sum(1 for i in issues if i.severity == 'critical')
        warning_count = sum(1 for i in issues if i.severity == 'warning')
        info_count = sum(1 for i in issues if i.severity == 'info')
        
        # Calculate penalty
        penalty = (critical_count * 5 + warning_count * 2 + info_count * 0.5) / total_albums
        
        # Score is 100 minus penalty, capped at 0
        score = max(0, 100 - penalty)
        
        return round(score, 1)
    
    def _calculate_consistency_score(self, albums: Dict[str, Dict], issues: List[QualityIssue]) -> float:
        """Calculate genre consistency score (0-100)"""
        total_albums = len(albums)
        if total_albums == 0:
            return 100.0
        
        # Count albums with genres
        albums_with_genres = sum(1 for album in albums.values() if album.get('genres'))
        
        # Count consistency-related issues
        consistency_issues = [i for i in issues if i.issue_type in [
            'artist_inconsistency', 'unknown_genre', 'invalid_format'
        ]]
        
        # Base score from genre coverage
        coverage_score = (albums_with_genres / total_albums) * 100
        
        # Penalty for consistency issues
        consistency_penalty = (len(consistency_issues) / total_albums) * 20
        
        score = max(0, coverage_score - consistency_penalty)
        return round(score, 1)
    
    def _save_report(self, report: ConsistencyReport, issues: List[QualityIssue]):
        """Save quality report to database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Save main report
        cursor.execute('''
            INSERT INTO quality_reports (
                report_date, total_albums, total_issues, quality_score, report_data
            ) VALUES (?, ?, ?, ?, ?)
        ''', (
            datetime.now().isoformat(),
            report.total_albums,
            report.total_issues,
            report.genre_quality_score,
            json.dumps(asdict(report))
        ))
        
        report_id = cursor.lastrowid
        
        # Save individual issues
        for issue in issues:
            cursor.execute('''
                INSERT INTO quality_issues (
                    report_id, issue_type, severity, album_key, artist, album,
                    description, suggested_fix, confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                report_id, issue.issue_type, issue.severity, issue.album_key,
                issue.artist, issue.album, issue.description,
                issue.suggested_fix, issue.confidence
            ))
        
        conn.commit()
        conn.close()
    
    def print_quality_report(self, report: ConsistencyReport):
        """Print formatted quality control report"""
        print("QUALITY CONTROL REPORT")
        print("=" * 60)
        print(f"Report Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Total Albums: {report.total_albums:,}")
        print(f"Total Issues: {report.total_issues:,}")
        print()
        
        print("QUALITY SCORES:")
        print(f"  Overall Quality: {report.genre_quality_score:.1f}/100")
        print(f"  Consistency: {report.consistency_score:.1f}/100")
        print()
        
        print("ISSUE BREAKDOWN:")
        print(f"  Critical: {report.critical_issues:,}")
        print(f"  Warning:  {report.warning_issues:,}")
        print(f"  Info:     {report.info_issues:,}")
        print()
        
        print("ISSUES BY TYPE:")
        for issue_type, count in sorted(report.issues_by_type.items(), key=lambda x: x[1], reverse=True):
            print(f"  {issue_type}: {count}")
        print()
        
        print("TOP 10 CRITICAL ISSUES:")
        print("-" * 60)
        critical_issues = [i for i in report.top_issues if i.severity == 'critical'][:10]
        for i, issue in enumerate(critical_issues, 1):
            print(f"{i}. {issue.artist} - {issue.album}")
            print(f"   Issue: {issue.description}")
            print(f"   Fix: {issue.suggested_fix}")
            print()
        
        if not critical_issues:
            print("No critical issues found!")

if __name__ == "__main__":
    # Test quality control system
    print("Testing Quality Control System")
    print("=" * 50)
    
    # Initialize with album data
    matcher = AlbumScanner("/Volumes/T7/Albums")
    matcher.scan_filesystem()
    
    qc_system = QualityControlSystem("/Volumes/T7/Albums")
    report = qc_system.run_comprehensive_analysis(matcher.albums)
    
    qc_system.print_quality_report(report)