#!/usr/bin/env python3
"""
Batch Processor for Confidence-Based Genre Updates
Handles large-scale genre updates with safety checks
"""

import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, asdict
from datetime import datetime
import logging
from enum import Enum

from album_matcher import AlbumMatcher
from enhanced_api_client import EnhancedAPIClient
from genre_standardizer import GenreStandardizer
from tag_writer import TagWriter

class ProcessingStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress" 
    COMPLETED = "completed"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"
    SKIPPED = "skipped"

@dataclass
class BatchJob:
    """Container for batch processing job"""
    job_id: str
    name: str
    created_at: datetime
    total_albums: int
    processed: int = 0
    successful: int = 0
    failed: int = 0
    needs_review: int = 0
    skipped: int = 0
    status: ProcessingStatus = ProcessingStatus.PENDING
    confidence_threshold: float = 95.0
    dry_run: bool = True

@dataclass
class AlbumProcessingResult:
    """Result of processing a single album"""
    album_key: str
    artist: str
    album: str
    original_genres: List[str]
    suggested_genres: List[str]
    final_genres: List[str]
    confidence: float
    sources_used: List[str]
    files_updated: int
    status: ProcessingStatus
    error_message: Optional[str] = None
    processing_time: float = 0.0
    manual_review_reason: Optional[str] = None

class BatchDatabase:
    """Database for tracking batch processing jobs and results"""
    
    def __init__(self, db_path: str = "batch_processing.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize database tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Jobs table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS batch_jobs (
                job_id TEXT PRIMARY KEY,
                name TEXT,
                created_at TEXT,
                total_albums INTEGER,
                processed INTEGER DEFAULT 0,
                successful INTEGER DEFAULT 0,
                failed INTEGER DEFAULT 0,
                needs_review INTEGER DEFAULT 0,
                skipped INTEGER DEFAULT 0,
                status TEXT,
                confidence_threshold REAL,
                dry_run BOOLEAN,
                backup_path TEXT,
                config_json TEXT
            )
        ''')
        
        # Results table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS album_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT,
                album_key TEXT,
                artist TEXT,
                album TEXT,
                original_genres TEXT,
                suggested_genres TEXT,
                final_genres TEXT,
                confidence REAL,
                sources_used TEXT,
                files_updated INTEGER,
                status TEXT,
                error_message TEXT,
                processing_time REAL,
                manual_review_reason TEXT,
                created_at TEXT,
                FOREIGN KEY (job_id) REFERENCES batch_jobs (job_id)
            )
        ''')
        
        # Manual review queue
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS manual_review_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT,
                album_key TEXT,
                artist TEXT,
                album TEXT,
                suggested_genres TEXT,
                confidence REAL,
                reason TEXT,
                priority INTEGER DEFAULT 1,
                created_at TEXT,
                reviewed_at TEXT,
                reviewer_decision TEXT,
                reviewer_genres TEXT,
                FOREIGN KEY (job_id) REFERENCES batch_jobs (job_id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def create_job(self, job: BatchJob) -> str:
        """Create a new batch job"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO batch_jobs (
                job_id, name, created_at, total_albums, status, 
                confidence_threshold, dry_run
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            job.job_id, job.name, job.created_at.isoformat(), job.total_albums,
            job.status.value, job.confidence_threshold, job.dry_run
        ))
        
        conn.commit()
        conn.close()
        return job.job_id
    
    def update_job_progress(self, job_id: str, processed: int, successful: int, 
                           failed: int, needs_review: int, skipped: int):
        """Update job progress"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE batch_jobs 
            SET processed = ?, successful = ?, failed = ?, needs_review = ?, skipped = ?
            WHERE job_id = ?
        ''', (processed, successful, failed, needs_review, skipped, job_id))
        
        conn.commit()
        conn.close()
    
    def save_album_result(self, job_id: str, result: AlbumProcessingResult):
        """Save album processing result"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO album_results (
                job_id, album_key, artist, album, original_genres, suggested_genres,
                final_genres, confidence, sources_used, files_updated, status,
                error_message, processing_time, manual_review_reason, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            job_id, result.album_key, result.artist, result.album,
            json.dumps(result.original_genres), json.dumps(result.suggested_genres),
            json.dumps(result.final_genres), result.confidence,
            json.dumps(result.sources_used), result.files_updated,
            result.status.value, result.error_message, result.processing_time,
            result.manual_review_reason, datetime.now().isoformat()
        ))
        
        conn.commit()
        conn.close()
    
    def add_to_review_queue(self, job_id: str, album_key: str, artist: str, 
                           album: str, suggested_genres: List[str], confidence: float, 
                           reason: str, priority: int = 1):
        """Add album to manual review queue"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO manual_review_queue (
                job_id, album_key, artist, album, suggested_genres, 
                confidence, reason, priority, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            job_id, album_key, artist, album, json.dumps(suggested_genres),
            confidence, reason, priority, datetime.now().isoformat()
        ))
        
        conn.commit()
        conn.close()
    
    def get_job_status(self, job_id: str) -> Optional[BatchJob]:
        """Get current job status"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM batch_jobs WHERE job_id = ?', (job_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return BatchJob(
                job_id=row[0], name=row[1], 
                created_at=datetime.fromisoformat(row[2]),
                total_albums=row[3], processed=row[4], successful=row[5],
                failed=row[6], needs_review=row[7], skipped=row[8],
                status=ProcessingStatus(row[9]), confidence_threshold=row[10],
                dry_run=bool(row[11])
            )
        return None
    
    def get_review_queue(self, job_id: Optional[str] = None, limit: int = 50) -> List[Dict]:
        """Get items from manual review queue"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if job_id:
            cursor.execute('''
                SELECT * FROM manual_review_queue 
                WHERE job_id = ? AND reviewed_at IS NULL 
                ORDER BY priority DESC, created_at ASC 
                LIMIT ?
            ''', (job_id, limit))
        else:
            cursor.execute('''
                SELECT * FROM manual_review_queue 
                WHERE reviewed_at IS NULL 
                ORDER BY priority DESC, created_at ASC 
                LIMIT ?
            ''', (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(zip([col[0] for col in cursor.description], row)) for row in rows]

class BatchProcessor:
    """Main batch processor for genre updates"""
    
    def __init__(self, music_path: str):
        self.music_path = music_path
        
        # Initialize components
        self.matcher = AlbumMatcher(music_path)
        self.api_client = EnhancedAPIClient()
        self.genre_standardizer = GenreStandardizer()
        self.tag_writer = TagWriter(music_path)
        self.db = BatchDatabase()
        
        # Set up logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)
    
    
    def analyze_library_for_processing(self) -> Dict:
        """Analyze library to determine processing candidates"""
        self.logger.info("Analyzing library for batch processing...")
        
        # Scan filesystem if not already done
        if not self.matcher.albums:
            self.matcher.scan_filesystem()
        
        analysis = {
            'total_albums': len(self.matcher.albums),
            'albums_with_genres': 0,
            'albums_without_genres': 0,
            'albums_with_poor_genres': 0,
            'genre_inconsistencies': 0,
            'processing_candidates': {
                'high_priority': [],  # No genres
                'medium_priority': [],  # Poor genres
                'low_priority': []   # Genre inconsistencies
            }
        }
        
        # Analyze each album
        for album_key, album_info in self.matcher.albums.items():
            has_genres = bool(album_info['genres'])
            
            if not has_genres:
                analysis['albums_without_genres'] += 1
                analysis['processing_candidates']['high_priority'].append(album_key)
            else:
                analysis['albums_with_genres'] += 1
                
                # Check genre quality
                genres = list(album_info['genres'])
                normalized_genres = self.genre_standardizer.normalize_genre_list(genres)
                valid_genres, invalid_genres = self.genre_standardizer.validate_genres(normalized_genres)
                
                if len(invalid_genres) > len(valid_genres):
                    analysis['albums_with_poor_genres'] += 1
                    analysis['processing_candidates']['medium_priority'].append(album_key)
                elif invalid_genres:
                    analysis['genre_inconsistencies'] += 1
                    analysis['processing_candidates']['low_priority'].append(album_key)
        
        self.logger.info(f"Analysis complete: {analysis['total_albums']} albums analyzed")
        return analysis
    
    def create_processing_job(self, name: str, album_keys: List[str], 
                            confidence_threshold: float = 95.0, 
                            dry_run: bool = True) -> str:
        """Create a new batch processing job"""
        job_id = f"job_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        job = BatchJob(
            job_id=job_id,
            name=name,
            created_at=datetime.now(),
            total_albums=len(album_keys),
            confidence_threshold=confidence_threshold,
            dry_run=dry_run
        )
        
        self.db.create_job(job)
        self.logger.info(f"Created job {job_id}: {name} ({len(album_keys)} albums)")
        
        return job_id
    
    def process_album(self, album_key: str, album_info: Dict, 
                     confidence_threshold: float, dry_run: bool) -> AlbumProcessingResult:
        """Process a single album"""
        start_time = datetime.now()
        
        artist = album_info['artist']
        album = album_info['album']
        original_genres = list(album_info['genres'])
        
        try:
            # Get API results
            api_results = self.api_client.get_comprehensive_genres(artist, album)
            suggested_genres = api_results.get('combined_genres', [])
            confidence = api_results.get('confidence', 0)
            sources_used = api_results.get('sources_used', [])
            
            # Normalize suggested genres
            normalized_genres = self.genre_standardizer.normalize_genre_list(suggested_genres)
            
            # Determine action based on confidence
            status = ProcessingStatus.PENDING
            final_genres = original_genres
            files_updated = 0
            manual_review_reason = None
            
            if confidence >= confidence_threshold:
                # High confidence - proceed with update
                final_genres = self._merge_genres(original_genres, normalized_genres)
                
                if not dry_run:
                    files_updated = self._update_album_files(album_info, final_genres)
                
                status = ProcessingStatus.COMPLETED
                
            elif confidence >= 70:
                # Medium confidence - needs manual review
                status = ProcessingStatus.NEEDS_REVIEW
                manual_review_reason = f"Medium confidence ({confidence:.1f}%) - requires manual review"
                
            elif confidence >= 40:
                # Low confidence - different review reason
                status = ProcessingStatus.NEEDS_REVIEW
                manual_review_reason = f"Low confidence ({confidence:.1f}%) - uncertain match"
                
            else:
                # Very low confidence - skip
                status = ProcessingStatus.SKIPPED
                manual_review_reason = f"Very low confidence ({confidence:.1f}%) - no reliable match found"
            
            processing_time = (datetime.now() - start_time).total_seconds()
            
            return AlbumProcessingResult(
                album_key=album_key,
                artist=artist,
                album=album,
                original_genres=original_genres,
                suggested_genres=suggested_genres,
                final_genres=final_genres,
                confidence=confidence,
                sources_used=sources_used,
                files_updated=files_updated,
                status=status,
                processing_time=processing_time,
                manual_review_reason=manual_review_reason
            )
            
        except Exception as e:
            processing_time = (datetime.now() - start_time).total_seconds()
            self.logger.error(f"Error processing {artist} - {album}: {e}")
            
            return AlbumProcessingResult(
                album_key=album_key,
                artist=artist,
                album=album,
                original_genres=original_genres,
                suggested_genres=[],
                final_genres=original_genres,
                confidence=0,
                sources_used=[],
                files_updated=0,
                status=ProcessingStatus.FAILED,
                error_message=str(e),
                processing_time=processing_time
            )
    
    def _merge_genres(self, original: List[str], suggested: List[str]) -> List[str]:
        """Intelligently merge original and suggested genres"""
        # Normalize both lists
        normalized_original = self.genre_standardizer.normalize_genre_list(original)
        normalized_suggested = self.genre_standardizer.normalize_genre_list(suggested)
        
        # Combine and deduplicate
        combined = list(dict.fromkeys(normalized_original + normalized_suggested))
        
        # Expand with hierarchy if beneficial
        expanded = self.genre_standardizer.expand_genres_with_hierarchy(combined)
        
        # Return top 5 most relevant
        return expanded[:5]
    
    def _update_album_files(self, album_info: Dict, new_genres: List[str]) -> int:
        """Update all files in an album with new genres"""
        updated_count = 0
        
        for track in album_info['tracks']:
            file_path = track.get('file_path')
            if file_path and Path(file_path).exists():
                try:
                    success = self.tag_writer.write_genre_tags(
                        Path(file_path), new_genres, test_mode=False, preserve_existing=False
                    )
                    if success:
                        updated_count += 1
                except Exception as e:
                    self.logger.error(f"Failed to update {file_path}: {e}")
        
        return updated_count
    
    def run_batch_job(self, job_id: str, album_keys: List[str]) -> BatchJob:
        """Run a complete batch processing job"""
        job = self.db.get_job_status(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")
        
        self.logger.info(f"Starting batch job {job_id}: {job.name}")
        
        # Counters
        processed = 0
        successful = 0
        failed = 0
        needs_review = 0
        skipped = 0
        
        # Process each album
        for i, album_key in enumerate(album_keys):
            if album_key not in self.matcher.albums:
                self.logger.warning(f"Album {album_key} not found in library")
                continue
            
            album_info = self.matcher.albums[album_key]
            
            # Process album
            result = self.process_album(
                album_key, album_info, job.confidence_threshold, job.dry_run
            )
            
            # Update counters
            processed += 1
            
            if result.status == ProcessingStatus.COMPLETED:
                successful += 1
            elif result.status == ProcessingStatus.FAILED:
                failed += 1
            elif result.status == ProcessingStatus.NEEDS_REVIEW:
                needs_review += 1
                # Add to review queue
                self.db.add_to_review_queue(
                    job_id, album_key, result.artist, result.album,
                    result.suggested_genres, result.confidence,
                    result.manual_review_reason or "Needs review"
                )
            elif result.status == ProcessingStatus.SKIPPED:
                skipped += 1
            
            # Save result
            self.db.save_album_result(job_id, result)
            
            # Update job progress
            self.db.update_job_progress(job_id, processed, successful, failed, needs_review, skipped)
            
            # Log progress
            if (i + 1) % 10 == 0:
                self.logger.info(f"Processed {i + 1}/{len(album_keys)} albums")
        
        # Update final job status
        final_job = self.db.get_job_status(job_id)
        self.logger.info(f"Job {job_id} completed: {successful} successful, {failed} failed, {needs_review} need review, {skipped} skipped")
        
        return final_job
    
    def get_job_summary(self, job_id: str) -> Dict:
        """Get comprehensive job summary"""
        job = self.db.get_job_status(job_id)
        if not job:
            return {}
        
        # Get review queue count
        review_items = self.db.get_review_queue(job_id)
        
        return {
            'job': asdict(job),
            'progress_percentage': (job.processed / job.total_albums * 100) if job.total_albums > 0 else 0,
            'success_rate': (job.successful / job.processed * 100) if job.processed > 0 else 0,
            'review_queue_count': len(review_items),
            'estimated_completion': self._estimate_completion_time(job)
        }
    
    def _estimate_completion_time(self, job: BatchJob) -> Optional[str]:
        """Estimate job completion time"""
        if job.processed == 0:
            return None
        
        # Simple estimation based on current progress
        remaining = job.total_albums - job.processed
        if remaining <= 0:
            return "Completed"
        
        # Assume average processing time of 2 seconds per album
        estimated_seconds = remaining * 2
        hours = estimated_seconds // 3600
        minutes = (estimated_seconds % 3600) // 60
        
        if hours > 0:
            return f"~{hours}h {minutes}m remaining"
        else:
            return f"~{minutes}m remaining"

if __name__ == "__main__":
    # Test batch processor
    processor = BatchProcessor("/Volumes/T7/Albums")
    
    # Analyze library
    analysis = processor.analyze_library_for_processing()
    
    print("Library Analysis for Batch Processing:")
    print("=" * 50)
    print(f"Total albums: {analysis['total_albums']}")
    print(f"Albums with genres: {analysis['albums_with_genres']}")
    print(f"Albums without genres: {analysis['albums_without_genres']}")
    print(f"Albums with poor genres: {analysis['albums_with_poor_genres']}")
    print(f"Genre inconsistencies: {analysis['genre_inconsistencies']}")
    print()
    print("Processing Candidates:")
    print(f"  High priority (no genres): {len(analysis['processing_candidates']['high_priority'])}")
    print(f"  Medium priority (poor genres): {len(analysis['processing_candidates']['medium_priority'])}")
    print(f"  Low priority (inconsistencies): {len(analysis['processing_candidates']['low_priority'])}")
    
    # Create a small test job
    if analysis['processing_candidates']['high_priority']:
        test_albums = analysis['processing_candidates']['high_priority'][:5]
        job_id = processor.create_processing_job(
            "Test Genre Assignment",
            test_albums,
            confidence_threshold=80.0,
            dry_run=True
        )
        print(f"\nCreated test job: {job_id}")
        
        # Run the job
        result = processor.run_batch_job(job_id, test_albums)
        summary = processor.get_job_summary(job_id)
        
        print(f"Job completed with {summary['progress_percentage']:.1f}% success rate")