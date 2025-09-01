#!/usr/bin/env python3
"""
Music Genre Tagger - Complete Genre Management System
Main integration script that provides command-line interface to all functionality
"""

import argparse
import sys
import json
from pathlib import Path
from datetime import datetime

from album_matcher import AlbumMatcher
from batch_processor import BatchProcessor
from enhanced_api_client import EnhancedAPIClient
from genre_standardizer import GenreStandardizer
from smart_genre_assignment import SmartGenreAssignment
from quality_control import QualityControlSystem
from tag_writer import TagWriter

class MusicGenreTagger:
    """Main application class that integrates all components"""
    
    def __init__(self, music_path: str, config_file: str = "tagger_config.json"):
        self.music_path = music_path
        self.config_file = config_file
        self.config = self._load_config()
        
        print(f"🎵 Music Genre Tagger v2.0")
        print(f"📁 Music Path: {music_path}")
        print("=" * 60)
        
        # Initialize all components
        self.matcher = AlbumMatcher(music_path)
        self.batch_processor = BatchProcessor(music_path)
        self.api_client = EnhancedAPIClient()
        self.standardizer = GenreStandardizer()
        self.smart_assignment = SmartGenreAssignment(music_path)
        self.quality_control = QualityControlSystem(music_path)
        self.tag_writer = TagWriter(music_path)
        
        # Load library data
        self._initialized = False
    
    def _load_config(self) -> dict:
        """Load or create configuration file"""
        config_path = Path(self.config_file)
        
        default_config = {
            "confidence_threshold": 95.0,
            "auto_update_high_confidence": False,
            "max_genres_per_album": 5,
            "api_rate_limit": 1.0,
            "batch_size": 100,
            "web_interface_enabled": True,
            "web_interface_port": 5000
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
        self.matcher.scan_filesystem()
        
        print("🧠 Initializing smart genre assignment...")
        self.smart_assignment.initialize(self.matcher.albums)
        
        print("✓ System initialized successfully!")
        print(f"📊 Found {len(self.matcher.albums)} albums with {sum(len(a['tracks']) for a in self.matcher.albums.values())} tracks")
        
        self._initialized = True
    
    def cmd_analyze(self, args):
        """Analyze the music library"""
        self.initialize()
        
        print("\n📈 LIBRARY ANALYSIS")
        print("=" * 50)
        
        # Basic statistics
        stats = self.matcher.get_album_stats()
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
            print("\n🧠 SMART GENRE ASSIGNMENT ANALYSIS")
            self.smart_assignment.generate_suggestion_report(self.matcher.albums, limit=args.limit)
        
        # Quality control analysis
        if args.quality:
            print("\n🔍 QUALITY CONTROL ANALYSIS")
            sample_size = min(100, len(self.matcher.albums))
            sample_albums = dict(list(self.matcher.albums.items())[:sample_size])
            report = self.quality_control.run_comprehensive_analysis(sample_albums)
            self.quality_control.print_quality_report(report)
    
    def cmd_batch(self, args):
        """Run batch processing"""
        self.initialize()
        
        print(f"\n🚀 BATCH PROCESSING")
        print("=" * 50)
        
        # Determine albums to process
        if args.filter == 'no_genres':
            analysis = self.batch_processor.analyze_library_for_processing()
            album_keys = analysis['processing_candidates']['high_priority']
            print(f"Processing {len(album_keys)} albums without genres...")
        elif args.filter == 'poor_genres':
            analysis = self.batch_processor.analyze_library_for_processing()
            album_keys = analysis['processing_candidates']['medium_priority']
            print(f"Processing {len(album_keys)} albums with poor genres...")
        elif args.filter == 'all':
            album_keys = list(self.matcher.albums.keys())[:args.limit]
            print(f"Processing {len(album_keys)} albums (limited to {args.limit})...")
        else:
            print(f"Unknown filter: {args.filter}")
            return
        
        if not album_keys:
            print("No albums to process!")
            return
        
        # Create and run batch job
        job_name = f"Batch_{args.filter}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        job_id = self.batch_processor.create_processing_job(
            job_name,
            album_keys,
            confidence_threshold=args.confidence,
            dry_run=args.dry_run
        )
        
        print(f"Created job: {job_id}")
        print(f"Confidence threshold: {args.confidence}%")
        print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
        
        # Run the job
        result = self.batch_processor.run_batch_job(job_id, album_keys)
        
        # Print results
        print(f"\n✓ Job completed!")
        print(f"Processed: {result.processed}")
        print(f"Successful: {result.successful}")
        print(f"Failed: {result.failed}")
        print(f"Needs Review: {result.needs_review}")
        print(f"Skipped: {result.skipped}")
        
        if result.needs_review > 0:
            print(f"\n📋 {result.needs_review} albums added to manual review queue")
    
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
            print(f"   Reason: {item['reason']}")
            
            if args.interactive:
                response = input("   Action (a)ccept, (r)eject, (m)odify, (s)kip: ").lower()
                
                if response == 'a':
                    # Accept suggestion
                    album_key = item['album_key']
                    if album_key in self.matcher.albums:
                        suggested_genres = json.loads(item['suggested_genres'])
                        self._update_album_genres(album_key, suggested_genres)
                        print("   ✓ Genres updated")
                elif response == 'm':
                    # Modify genres
                    print("   Enter genres (comma-separated):")
                    new_genres = input("   > ").split(',')
                    new_genres = [g.strip() for g in new_genres if g.strip()]
                    if new_genres:
                        album_key = item['album_key']
                        self._update_album_genres(album_key, new_genres)
                        print("   ✓ Custom genres applied")
                elif response == 's':
                    break
                
                print()
    
    def _update_album_genres(self, album_key: str, genres: list):
        """Update genres for an album"""
        if album_key not in self.matcher.albums:
            return False
        
        album_info = self.matcher.albums[album_key]
        normalized_genres = self.standardizer.normalize_genre_list(genres)
        
        # Update album info
        album_info['genres'] = set(normalized_genres)
        
        # Update files
        files_updated = 0
        for track in album_info['tracks']:
            file_path = track.get('file_path')
            if file_path and Path(file_path).exists():
                try:
                    success = self.tag_writer.write_genre_tags(
                        Path(file_path), normalized_genres, test_mode=False, preserve_existing=False
                    )
                    if success:
                        files_updated += 1
                except Exception as e:
                    print(f"   Error updating {file_path}: {e}")
        
        return files_updated > 0
    
    def cmd_web(self, args):
        """Start web interface"""
        try:
            from web_interface import app, initialize_components
            from process_cleanup import ProcessCleanup
            
            print("🌐 Starting web interface...")
            
            # Clean up any existing processes first
            ProcessCleanup.cleanup_script_processes('web_interface.py')
            port = args.port or self.config['web_interface_port']
            ProcessCleanup.cleanup_port_processes(port)
            
            initialize_components()
            
            print(f"Web interface available at: http://localhost:{port}")
            
            app.run(debug=args.debug, host='0.0.0.0', port=port)
            
        except ImportError:
            print("Web interface dependencies not available. Run: pip install flask")
        except Exception as e:
            print(f"Error starting web interface: {e}")
    
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
            if len(self.matcher.albums) > 0:
                test_results['album_scanning'] = True
                print("✓ Album scanning working")
            else:
                print("✗ No albums found")
        except Exception as e:
            print(f"✗ Album scanning failed: {e}")
        
        # Test 2: Genre standardization
        try:
            test_genres = ["Hip-Hop", "Rock & Roll", "Electronic"]
            normalized = self.standardizer.normalize_genre_list(test_genres)
            if len(normalized) == 3:
                test_results['genre_standardization'] = True
                print("✓ Genre standardization working")
            else:
                print("✗ Genre standardization failed")
        except Exception as e:
            print(f"✗ Genre standardization failed: {e}")
        
        # Test 3: API connectivity (basic test)
        try:
            # Test with a well-known album
            api_results = self.api_client.get_comprehensive_genres("The Beatles", "Abbey Road")
            test_results['api_connectivity'] = True
            print("✓ API connectivity working")
        except Exception as e:
            print(f"⚠ API connectivity issue (may need API keys): {e}")
        
        # Test 4: Tag writing (test mode)
        try:
            if self.matcher.albums:
                first_album = next(iter(self.matcher.albums.values()))
                if first_album['tracks']:
                    first_track = first_album['tracks'][0]
                    file_path = first_track.get('file_path')
                    if file_path and Path(file_path).exists():
                        success = self.tag_writer.write_genre_tags(
                            Path(file_path), ["Test"], test_mode=True
                        )
                        if success:
                            test_results['tag_writing'] = True
                            print("✓ Tag writing working")
                        else:
                            print("✗ Tag writing test failed")
                    else:
                        print("⚠ No valid file found for tag writing test")
                else:
                    print("⚠ No tracks found for tag writing test")
            else:
                print("⚠ No albums found for tag writing test")
        except Exception as e:
            print(f"✗ Tag writing failed: {e}")
        
        # Test 5: Batch processing
        try:
            if self.matcher.albums:
                test_albums = list(self.matcher.albums.keys())[:2]
                job_id = self.batch_processor.create_processing_job(
                    "Test Job", test_albums, dry_run=True
                )
                if job_id:
                    test_results['batch_processing'] = True
                    print("✓ Batch processing working")
                else:
                    print("✗ Batch processing failed")
            else:
                print("⚠ No albums for batch processing test")
        except Exception as e:
            print(f"✗ Batch processing failed: {e}")
        
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

def main():
    """Main command-line interface"""
    parser = argparse.ArgumentParser(description="Music Genre Tagger - Complete Genre Management System")
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
    
    # Review command
    review_parser = subparsers.add_parser("review", help="Manual review interface")
    review_parser.add_argument("--limit", type=int, default=20, help="Number of items to show")
    review_parser.add_argument("--interactive", action="store_true", help="Interactive mode")
    
    # Web command
    web_parser = subparsers.add_parser("web", help="Start web interface")
    web_parser.add_argument("--port", type=int, help="Port for web interface")
    web_parser.add_argument("--debug", action="store_true", help="Debug mode")
    
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
        app = MusicGenreTagger(args.music_path, args.config)
        
        # Route to appropriate command
        if args.command == "analyze":
            app.cmd_analyze(args)
        elif args.command == "batch":
            app.cmd_batch(args)
        elif args.command == "review":
            app.cmd_review(args)
        elif args.command == "web":
            app.cmd_web(args)
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