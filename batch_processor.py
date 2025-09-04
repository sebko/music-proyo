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

from album_scanner import AlbumScanner
from matcher import Matcher
from genre_standardizer import GenreStandardizer
from smart_genre_assignment import SmartGenreAssignment
from quality_control import QualityControlSystem
from tag_writer import TagWriter
from process_cleanup import ProcessCleanup

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
    # Enhanced information from new matching system
    genre_reasoning: Optional[str] = None
    source_breakdown: Optional[Dict] = None
    overall_confidence: Optional[float] = None

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
        self.scanner = AlbumScanner(music_path)
        self.matcher = Matcher()
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
        if not self.scanner.albums:
            self.scanner.scan_filesystem()
        
        analysis = {
            'total_albums': len(self.scanner.albums),
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
        for album_key, album_info in self.scanner.albums.items():
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
            # Get match results using new multi-source system
            match_result = self.matcher.match_album(artist, album)
            suggested_genres = match_result.genres
            confidence = match_result.genre_confidence
            sources_used = match_result.genre_sources_used
            
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
                manual_review_reason=manual_review_reason,
                genre_reasoning=match_result.genre_reasoning,
                source_breakdown=match_result.sources_breakdown,
                overall_confidence=match_result.overall_confidence
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
                processing_time=processing_time,
                genre_reasoning=None,
                source_breakdown=None,
                overall_confidence=0.0
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
            if album_key not in self.scanner.albums:
                self.logger.warning(f"Album {album_key} not found in library")
                continue
            
            album_info = self.scanner.albums[album_key]
            
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

class MusicLibraryProcessor:
    """Main application class that coordinates batch processing operations"""
    
    def __init__(self, music_path: str, config_file: str = "tagger_config.json"):
        self.music_path = music_path
        self.config_file = config_file
        self.config = self._load_config()
        
        print(f"🎵 Music Library Processor v3.0")
        print(f"📁 Music Path: {music_path}")
        print("=" * 60)
        
        # Initialize core components
        self.scanner = AlbumScanner(music_path)
        self.matcher = Matcher()
        self.batch_processor = BatchProcessor(music_path)
        self.standardizer = GenreStandardizer()
        self.smart_assignment = SmartGenreAssignment(music_path)
        self.quality_control = QualityControlSystem(music_path)
        self.tag_writer = TagWriter(music_path)
        
        self._initialized = False
    
    def _load_config(self) -> dict:
        """Load or create configuration file"""
        config_path = Path(self.config_file)
        
        default_config = {
            "confidence_threshold": 95.0,
            "auto_update_high_confidence": False,
            "max_genres_per_album": 5,
            "api_rate_limit": 1.0,
            "batch_size": 100
        }
        
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = json.load(f)
                return {**default_config, **config}
        else:
            with open(config_path, 'w') as f:
                json.dump(default_config, f, indent=2)
            print(f"Created config file: {config_path}")
            return default_config
    
    def initialize(self):
        """Initialize the system by scanning the music library"""
        if self._initialized:
            return
        
        print("🔍 Scanning music library...")
        self.scanner.scan_filesystem()
        
        print("🧠 Initializing smart genre assignment...")
        self.smart_assignment.initialize(self.scanner.albums)
        
        print("✓ System initialized successfully!")
        print(f"📊 Found {len(self.scanner.albums)} albums with {sum(len(a['tracks']) for a in self.scanner.albums.values())} tracks")
        
        self._initialized = True
    
    def cmd_analyze(self, args):
        """Analyze the music library"""
        self.initialize()
        
        print("\n📈 LIBRARY ANALYSIS")
        print("=" * 50)
        
        # Basic statistics
        stats = self.scanner.get_album_stats()
        print(f"Total Albums: {stats['total_albums']:,}")
        print(f"Total Tracks: {stats['total_tracks']:,}")
        print(f"Albums with Genres: {stats['albums_with_genres']:,} ({stats['albums_with_genres']/stats['total_albums']*100:.1f}%)")
        print(f"Unique Genres: {len(stats['unique_genres'])}")
        
        # Batch processing analysis
        batch_analysis = self.batch_processor.analyze_library_for_processing()
        print(f"\nAlbums without genres: {batch_analysis['albums_without_genres']:,}")
        print(f"Albums with poor genres: {batch_analysis['albums_with_poor_genres']:,}")
        print(f"Genre inconsistencies: {batch_analysis['genre_inconsistencies']:,}")
        
        # Smart assignment analysis
        if args.detailed:
            print(f"\n🧠 Smart Genre Assignment Analysis (limited to {args.limit}):")
            suggestions = self.smart_assignment.get_suggestions(
                list(self.scanner.albums.keys())[:args.limit]
            )
            for suggestion in suggestions[:args.limit]:
                print(f"  {suggestion['artist']} - {suggestion['album']}: {suggestion['suggested_genres']}")
        
        # Quality control analysis
        if args.quality:
            print(f"\n📊 Quality Control Analysis:")
            qc_stats = self.quality_control.get_quality_report()
            print(f"Genre validation issues: {qc_stats.get('genre_issues', 0)}")
            print(f"Metadata completeness: {qc_stats.get('completeness_score', 0.0):.1%}")
    
    def cmd_batch(self, args):
        """Run batch processing"""
        self.initialize()
        
        print(f"\n🚀 BATCH PROCESSING")
        print("=" * 50)
        
        # Determine albums to process
        album_keys = []
        
        # Handle specific album filtering first
        if args.specific_album:
            try:
                target_artist, target_album = args.specific_album.split(',', 1)
                target_artist = target_artist.strip()
                target_album = target_album.strip()
                
                # Find matching album
                for key, album_data in self.scanner.albums.items():
                    if (album_data['artist'].lower() == target_artist.lower() and 
                        album_data['album'].lower() == target_album.lower()):
                        album_keys = [key]
                        break
                
                if album_keys:
                    print(f"Processing specific album: {target_artist} - {target_album}")
                else:
                    print(f"❌ Album not found: {target_artist} - {target_album}")
                    return
                    
            except ValueError:
                print("❌ Invalid --specific-album format. Use: 'Artist,Album'")
                return
        else:
            # Get processing candidates
            analysis = self.batch_processor.analyze_library_for_processing()
            candidates = analysis['processing_candidates']
            
            if args.filter == "no_genres":
                album_keys = candidates['high_priority']
            elif args.filter == "poor_genres":
                album_keys = candidates['medium_priority']
            elif args.filter == "all":
                album_keys = (candidates['high_priority'] + 
                             candidates['medium_priority'] + 
                             candidates['low_priority'])
            
            # Apply artist range filter
            if args.artist_range and not args.specific_album:
                album_keys = self._filter_by_artist_range(album_keys, args.artist_range)
            
            # Limit processing
            if args.limit and len(album_keys) > args.limit:
                album_keys = album_keys[:args.limit]
                print(f"⚠ Limiting processing to {args.limit} albums")
        
        if not album_keys:
            print("No albums to process with current filters.")
            return
        
        print(f"📋 Processing {len(album_keys)} albums...")
        if args.dry_run:
            print("🔒 DRY RUN MODE - No files will be modified")
        
        # Create and run batch job
        job_name = f"Batch Processing - {args.filter} (threshold: {args.confidence}%)"
        if args.specific_album:
            job_name = f"Single Album - {args.specific_album}"
        
        job_id = self.batch_processor.create_processing_job(
            job_name,
            album_keys,
            confidence_threshold=args.confidence,
            dry_run=args.dry_run
        )
        
        print(f"🚀 Created batch job: {job_id}")
        
        # Run the job
        try:
            result = self.batch_processor.run_batch_job(job_id, album_keys)
            summary = self.batch_processor.get_job_summary(job_id)
            
            print(f"\n📊 JOB COMPLETED")
            print("=" * 30)
            print(f"Success Rate: {summary['progress_percentage']:.1f}%")
            print(f"Processed: {summary['processed']}/{summary['total_albums']}")
            print(f"Successful: {summary['successful']}")
            print(f"Failed: {summary['failed']}")
            print(f"Needs Review: {summary['needs_review']}")
            print(f"Skipped: {summary['skipped']}")
            
        except KeyboardInterrupt:
            print("\n⚠ Processing interrupted by user")
        except Exception as e:
            print(f"\n❌ Processing failed: {e}")
    
    def cmd_review(self, args):
        """Manual review interface"""
        self.initialize()
        
        print("\n📋 MANUAL REVIEW QUEUE")
        print("=" * 50)
        
        # Get review queue
        db = self.batch_processor.db
        queue_items = db.get_review_queue(limit=args.limit)
        
        if not queue_items:
            print("No items in review queue!")
            return
        
        print(f"Found {len(queue_items)} items needing review:")
        print()
        
        for i, item in enumerate(queue_items, 1):
            print(f"{i}. {item['artist']} - {item['album']}")
            print(f"   Suggested: {item['suggested_genres']}")
            print(f"   Confidence: {item['confidence']:.1f}%")
            print(f"   Sources: {item['sources_used']}")
            print(f"   Reasoning: {item.get('reasoning', 'N/A')[:100]}...")
            print()
        
        if args.interactive:
            print("Interactive review mode not yet implemented.")
            print("Use the web interface for manual review: python3 music_dashboard.py")
    
    def cmd_test(self, args):
        """Run tests on the system"""
        self.initialize()
        
        print("\n🧪 SYSTEM TESTS")
        print("=" * 50)
        
        # Test components
        test_results = {
            'album_scanning': False,
            'genre_standardization': False,
            'api_connectivity': False,
            'tag_writing': False,
            'batch_processing': False
        }
        
        # Test 1: Album scanning
        try:
            if len(self.scanner.albums) > 0:
                test_results['album_scanning'] = True
                print("✓ Album scanning working")
            else:
                print("❌ No albums found in library")
        except Exception as e:
            print(f"❌ Album scanning failed: {e}")
        
        # Test 2: Genre standardization
        try:
            test_genres = ["rock", "hip-hop", "electronic"]
            standardized = [self.standardizer.standardize_genre(g) for g in test_genres]
            if standardized:
                test_results['genre_standardization'] = True
                print("✓ Genre standardization working")
            else:
                print("❌ Genre standardization failed")
        except Exception as e:
            print(f"❌ Genre standardization error: {e}")
        
        # Test 3: API connectivity
        try:
            # Test with a well-known album
            result = self.matcher.match_album("The Beatles", "Abbey Road")
            if result and len(result.genres) > 0:
                test_results['api_connectivity'] = True
                print("✓ API connectivity working")
            else:
                print("❌ API connectivity failed - no genres returned")
        except Exception as e:
            print(f"❌ API connectivity error: {e}")
        
        # Test 4: Tag writing (dry run)
        try:
            # Just test that tag writer can be initialized
            if self.tag_writer:
                test_results['tag_writing'] = True
                print("✓ Tag writing system ready")
        except Exception as e:
            print(f"❌ Tag writing error: {e}")
        
        # Test 5: Batch processing
        try:
            # Test job creation
            analysis = self.batch_processor.analyze_library_for_processing()
            if analysis['total_albums'] > 0:
                test_results['batch_processing'] = True
                print("✓ Batch processing ready")
            else:
                print("❌ Batch processing failed - no albums analyzed")
        except Exception as e:
            print(f"❌ Batch processing error: {e}")
        
        # Summary
        passed = sum(test_results.values())
        total = len(test_results)
        print(f"\nTest Results: {passed}/{total} passed")
        
        if passed == total:
            print("🎉 All tests passed! System is ready for use.")
        elif passed >= total * 0.7:
            print("⚠ Most tests passed. System is mostly functional.")
        else:
            print("❌ Multiple test failures. Check configuration and dependencies.")
    
    def _filter_by_artist_range(self, album_keys: List[str], artist_range: str) -> List[str]:
        """Filter albums by artist name range (e.g., 'a-c', 's-s')"""
        try:
            start_char, end_char = artist_range.lower().split('-')
            
            filtered_keys = []
            for key in album_keys:
                album = self.scanner.albums[key]
                first_char = album['artist'].lower()[0]
                if start_char <= first_char <= end_char:
                    filtered_keys.append(key)
            
            print(f"🔍 Filtered to {len(filtered_keys)} albums in range '{artist_range}'")
            return filtered_keys
        except (ValueError, IndexError):
            print(f"⚠ Invalid artist range format: {artist_range}. Using all albums.")
            return album_keys


def main():
    """Main command-line interface"""
    import argparse
    import sys
    
    # Clean up any existing instances before starting
    print("🧹 Checking for existing batch processor instances...")
    ProcessCleanup.cleanup_script_processes('batch_processor.py')
    
    parser = argparse.ArgumentParser(description="Music Library Processor - Batch Genre Processing System")
    parser.add_argument("music_path", help="Path to music library")
    parser.add_argument("--config", default="tagger_config.json", help="Configuration file")
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Analyze command
    analyze_parser = subparsers.add_parser("analyze", help="Analyze music library")
    analyze_parser.add_argument("--detailed", action="store_true", help="Include detailed analysis")
    analyze_parser.add_argument("--quality", action="store_true", help="Include quality analysis")
    analyze_parser.add_argument("--limit", type=int, default=20, help="Limit for detailed analysis")
    
    # Batch command
    batch_parser = subparsers.add_parser("batch", help="Run batch processing")
    batch_parser.add_argument("--filter", choices=["no_genres", "poor_genres", "all"], 
                             default="no_genres", help="Filter for albums to process")
    batch_parser.add_argument("--confidence", type=float, default=95.0, help="Confidence threshold")
    batch_parser.add_argument("--limit", type=int, default=100, help="Maximum albums to process")
    batch_parser.add_argument("--dry-run", action="store_true", help="Test mode (no file changes)")
    batch_parser.add_argument("--artist-range", help="Artist range filter (e.g., 'a-c', 'd-f', 's-s')")
    batch_parser.add_argument("--specific-album", help="Process specific album (format: 'Artist,Album')")
    batch_parser.add_argument("--batch-size", type=int, default=50, help="Process albums in batches of N (default: 50)")
    
    # Review command
    review_parser = subparsers.add_parser("review", help="Manual review interface")
    review_parser.add_argument("--limit", type=int, default=20, help="Number of items to show")
    review_parser.add_argument("--interactive", action="store_true", help="Interactive mode")
    
    # Test command
    test_parser = subparsers.add_parser("test", help="Run system tests")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Check if music path exists
    if not Path(args.music_path).exists():
        print(f"Error: Music path does not exist: {args.music_path}")
        sys.exit(1)
    
    # Initialize application
    try:
        app = MusicLibraryProcessor(args.music_path, args.config)
        
        # Route to appropriate command
        if args.command == "analyze":
            app.cmd_analyze(args)
        elif args.command == "batch":
            app.cmd_batch(args)
        elif args.command == "review":
            app.cmd_review(args)
        elif args.command == "test":
            app.cmd_test(args)
        else:
            print(f"Unknown command: {args.command}")
            
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user.")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()