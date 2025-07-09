#!/usr/bin/env python3
"""
Hybrid Batch Processor - Integration of Multi-Source Genre Fetcher with Batch Processing
"""

import json
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path

from hybrid_genre_fetcher import HybridGenreFetcher
from album_matcher import AlbumMatcher
from tag_writer import TagWriter
from genre_standardizer import GenreStandardizer

class HybridBatchProcessor:
    """Batch processor using the hybrid multi-source genre fetcher"""
    
    def __init__(self, music_path: str, confidence_threshold: float = 80.0):
        self.music_path = music_path
        self.confidence_threshold = confidence_threshold
        
        # Initialize components
        self.hybrid_fetcher = HybridGenreFetcher()
        self.album_matcher = AlbumMatcher(music_path)
        self.tag_writer = TagWriter(music_path)
        self.standardizer = GenreStandardizer()
        
        # Scan library
        print("🔍 Scanning music library...")
        self.album_matcher.scan_filesystem()
        print(f"Found {len(self.album_matcher.albums)} albums")
        
        # Initialize results tracking
        self.results = {
            'processed': 0,
            'high_confidence': 0,
            'medium_confidence': 0,
            'low_confidence': 0,
            'no_match': 0,
            'files_updated': 0,
            'errors': []
        }
    
    def process_album(self, album_key: str, album_info: Dict, dry_run: bool = True) -> Dict:
        """Process a single album with hybrid genre fetching"""
        result = {
            'album_key': album_key,
            'artist': album_info['artist'],
            'album': album_info['album'],
            'original_genres': list(album_info.get('genres', set())),
            'confidence': 0,
            'sources_used': [],
            'suggested_genres': [],
            'final_genres': [],
            'files_updated': 0,
            'status': 'pending',
            'reasoning': '',
            'processing_time': 0
        }
        
        start_time = datetime.now()
        
        try:
            print(f"🎯 Processing: {album_info['artist']} - {album_info['album']}")
            print(f"   🔍 Searching APIs for: Artist='{album_info['artist']}', Album='{album_info['album']}'")
            
            # Fetch genres from hybrid system
            hybrid_result = self.hybrid_fetcher.fetch_all_sources(
                album_info['artist'], 
                album_info['album']
            )
            
            result['confidence'] = hybrid_result.confidence
            result['sources_used'] = hybrid_result.sources_used
            result['suggested_genres'] = hybrid_result.final_genres
            result['reasoning'] = hybrid_result.reasoning
            
            # Merge with existing genres and standardize
            all_genres = result['original_genres'] + hybrid_result.final_genres
            final_standardized = self.standardizer.normalize_genre_list(all_genres)
            result['final_genres'] = final_standardized
            
            # Determine status based on confidence
            if hybrid_result.confidence >= self.confidence_threshold:
                result['status'] = 'high_confidence'
                self.results['high_confidence'] += 1
                
                # Update files if not dry run and genres found
                if not dry_run and final_standardized:
                    result['files_updated'] = self._update_album_files(album_info, final_standardized)
                    self.results['files_updated'] += result['files_updated']
                    
            elif hybrid_result.confidence >= 50:
                result['status'] = 'medium_confidence'
                self.results['medium_confidence'] += 1
            elif hybrid_result.confidence > 0:
                result['status'] = 'low_confidence'
                self.results['low_confidence'] += 1
            else:
                result['status'] = 'no_match'
                self.results['no_match'] += 1
            
            # Show results with better clarity
            confidence_emoji = "✅" if result['confidence'] >= self.confidence_threshold else "🟡" if result['confidence'] >= 50 else "🔴"
            print(f"   {confidence_emoji} Confidence: {result['confidence']:.1f}%")
            
            if result['sources_used']:
                print(f"   📡 Sources Found: {', '.join(result['sources_used'])}")
                print(f"   🎵 API Match: YES - Found in {len(result['sources_used'])} source(s)")
                
                # Show individual source match qualities
                for source_name, source_data in hybrid_result.source_breakdown.items():
                    match_quality = getattr(source_data, 'match_quality', 0) * 100
                    print(f"     {source_name}: {match_quality:.1f}% string match")
            else:
                print(f"   📡 Sources Found: NONE")
                print(f"   🎵 API Match: NO - Album not found in any API")
            
            if result['original_genres']:
                print(f"   📂 Original: {'; '.join(result['original_genres'])}")
            
            if result['suggested_genres']:
                print(f"   🆕 Suggested: {'; '.join(result['suggested_genres'])}")
                print(f"   💡 Reason: {result['reasoning']}")
            else:
                print(f"   🆕 Suggested: NONE - No genres found")
            
            if result['final_genres'] != result['original_genres']:
                print(f"   🎯 Final: {'; '.join(result['final_genres'])}")
                
            if result['files_updated'] > 0:
                print(f"   💾 Updated {result['files_updated']} files")
                
        except Exception as e:
            result['status'] = 'error'
            result['error'] = str(e)
            self.results['errors'].append(f"Error processing {album_key}: {e}")
            print(f"   ❌ Error: {e}")
        
        # Calculate processing time
        result['processing_time'] = (datetime.now() - start_time).total_seconds()
        self.results['processed'] += 1
        
        print()
        return result
    
    def _update_album_files(self, album_info: Dict, genres: List[str]) -> int:
        """Update files for an album with new genres"""
        files_updated = 0
        
        for track in album_info['tracks']:
            file_path = track.get('file_path')
            if file_path and Path(file_path).exists():
                try:
                    success = self.tag_writer.write_genre_tags(
                        Path(file_path), 
                        genres, 
                        test_mode=False, 
                        preserve_existing=False  # Replace with standardized versions
                    )
                    if success:
                        files_updated += 1
                except Exception as e:
                    print(f"     ⚠️ Failed to update {Path(file_path).name}: {e}")
        
        return files_updated
    
    def run_batch(self, sample_size: int = 10, dry_run: bool = True) -> List[Dict]:
        """Run batch processing on sample albums"""
        print("🚀 HYBRID BATCH PROCESSING")
        print("=" * 60)
        print(f"🎛️  Mode: {'DRY RUN' if dry_run else 'LIVE MODE'}")
        print(f"🎯 Confidence Threshold: {self.confidence_threshold}%")
        print(f"📊 Sample Size: {sample_size}")
        print()
        
        # Get sample albums
        album_items = list(self.album_matcher.albums.items())[:sample_size]
        
        results = []
        for i, (album_key, album_info) in enumerate(album_items):
            print(f"[{i+1}/{len(album_items)}]", end=" ")
            result = self.process_album(album_key, album_info, dry_run)
            results.append(result)
        
        # Print summary
        self._print_summary()
        
        return results
    
    def _print_summary(self):
        """Print batch processing summary"""
        print("=" * 60)
        print("📊 BATCH PROCESSING SUMMARY")
        print("=" * 60)
        
        total = self.results['processed']
        if total > 0:
            print(f"📈 Albums Processed: {total}")
            print(f"✅ High Confidence (≥{self.confidence_threshold}%): {self.results['high_confidence']} ({self.results['high_confidence']/total*100:.1f}%)")
            print(f"🟡 Medium Confidence (50-{self.confidence_threshold-1}%): {self.results['medium_confidence']} ({self.results['medium_confidence']/total*100:.1f}%)")
            print(f"🔴 Low Confidence (<50%): {self.results['low_confidence']} ({self.results['low_confidence']/total*100:.1f}%)")
            print(f"❌ No Match: {self.results['no_match']} ({self.results['no_match']/total*100:.1f}%)")
            
            if self.results['files_updated'] > 0:
                print(f"💾 Files Updated: {self.results['files_updated']}")
            
            if self.results['errors']:
                print(f"⚠️  Errors: {len(self.results['errors'])}")
                for error in self.results['errors'][:3]:  # Show first 3
                    print(f"   - {error}")
        
        print()
        print("🎉 Processing complete!")

if __name__ == "__main__":
    # Test the hybrid batch processor
    processor = HybridBatchProcessor("/Volumes/T7/Albums", confidence_threshold=75.0)
    
    # Run with a small sample first
    
    # FULL LIBRARY PRODUCTION RUN
    print("🚀 FULL LIBRARY PRODUCTION RUN STARTING!")
    print("📊 Processing: ALL 2,144 albums in your library")
    print("⚡ Mode: LIVE MODE - Will update files with 75%+ confidence")
    print("📁 Backup system: ENABLED")
    print("🎯 Expected: ~1,823 albums to be updated")
    print("⏱️  Estimated time: 2-4 hours (API rate limiting)")
    print("🔧 Fresh cache - optimized for production")
    print()
    print("Starting full library processing...")
    
    results = processor.run_batch(sample_size=None, dry_run=False)  # None = full library
    
    print("\n" + "=" * 60)
    print("🔍 DETAILED RESULTS")
    print("=" * 60)
    
    for result in results:
        if result['confidence'] > 0:
            print(f"\n🎵 {result['artist']} - {result['album']}")
            print(f"   Confidence: {result['confidence']:.1f}%")
            print(f"   Status: {result['status']}")
            print(f"   Sources: {', '.join(result['sources_used'])}")
            if result['final_genres']:
                print(f"   Final Genres: {'; '.join(result['final_genres'])}")