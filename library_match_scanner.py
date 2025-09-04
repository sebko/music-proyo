#!/usr/bin/env python3
"""
Library Match Scanner - Analyze match rates across entire music library
Shows what percentage of library can be enhanced with hybrid genre system
"""

import time
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional

from hybrid_genre_fetcher import HybridGenreFetcher
from album_scanner import AlbumScanner

class LibraryMatchScanner:
    """Scan entire library to analyze match rates and potential improvements"""
    
    def __init__(self, music_path: str):
        self.music_path = music_path
        self.hybrid_fetcher = HybridGenreFetcher()
        self.album_scanner = AlbumScanner(music_path)
        
        print("🔍 Scanning music library...")
        self.album_scanner.scan_filesystem()
        print(f"Found {len(self.album_scanner.albums)} albums to analyze")
        
        # Results tracking
        self.results = {
            'total_albums': len(self.album_scanner.albums),
            'processed': 0,
            'matched': 0,
            'no_match': 0,
            'errors': 0,
            'confidence_distribution': defaultdict(int),
            'source_usage': defaultdict(int),
            'genre_improvements': 0,
            'albums_with_existing_genres': 0,
            'albums_without_genres': 0
        }
        
        self.detailed_results = []
    
    def scan_library(self, sample_size: Optional[int] = None, confidence_threshold: float = 25.0) -> Dict:
        """Scan library for match rates"""
        print("🎯 LIBRARY MATCH ANALYSIS")
        print("=" * 60)
        print(f"📊 Total Albums: {self.results['total_albums']}")
        print(f"🎯 Confidence Threshold: {confidence_threshold}%")
        
        if sample_size:
            print(f"📦 Scanning Sample: {sample_size} albums")
            album_items = list(self.album_scanner.albums.items())[:sample_size]
        else:
            print(f"📦 Scanning Full Library: {self.results['total_albums']} albums")
            album_items = list(self.album_scanner.albums.items())
        
        print()
        
        start_time = datetime.now()
        
        for i, (album_key, album_info) in enumerate(album_items):
            if i % 50 == 0:  # Progress update every 50 albums
                elapsed = (datetime.now() - start_time).total_seconds()
                rate = i / elapsed if elapsed > 0 else 0
                remaining = len(album_items) - i
                eta = remaining / rate if rate > 0 else 0
                print(f"⏳ Progress: {i}/{len(album_items)} ({i/len(album_items)*100:.1f}%) - ETA: {eta/60:.1f}min")
            
            self._analyze_album(album_key, album_info, confidence_threshold)
        
        # Final analysis
        self._generate_report()
        return self.results
    
    def _analyze_album(self, album_key: str, album_info: Dict, confidence_threshold: float):
        """Analyze a single album for match potential"""
        try:
            # Track existing genres
            existing_genres = list(album_info.get('genres', set()))
            if existing_genres:
                self.results['albums_with_existing_genres'] += 1
            else:
                self.results['albums_without_genres'] += 1
            
            # Try to fetch genres
            hybrid_result = self.hybrid_fetcher.fetch_all_sources(
                album_info['artist'], 
                album_info['album']
            )
            
            self.results['processed'] += 1
            
            # Track confidence distribution
            confidence_bucket = int(hybrid_result.confidence // 10) * 10
            self.results['confidence_distribution'][f"{confidence_bucket}%"] += 1
            
            # Track source usage
            for source in hybrid_result.sources_used:
                self.results['source_usage'][source] += 1
            
            # Determine if this is a match
            if hybrid_result.confidence >= confidence_threshold and hybrid_result.final_genres:
                self.results['matched'] += 1
                
                # Check if this would improve genres
                new_genres = set(hybrid_result.final_genres)
                existing_set = set(existing_genres)
                
                if new_genres - existing_set:  # New genres found
                    self.results['genre_improvements'] += 1
            else:
                self.results['no_match'] += 1
            
            # Store detailed result for top matches
            if hybrid_result.confidence > 20:  # Only store promising matches
                self.detailed_results.append({
                    'artist': album_info['artist'],
                    'album': album_info['album'],
                    'confidence': hybrid_result.confidence,
                    'sources': hybrid_result.sources_used,
                    'existing_genres': existing_genres,
                    'suggested_genres': hybrid_result.final_genres,
                    'would_improve': len(set(hybrid_result.final_genres) - set(existing_genres)) > 0
                })
            
        except Exception as e:
            self.results['errors'] += 1
            if self.results['errors'] <= 5:  # Only log first 5 errors
                print(f"   ⚠️ Error analyzing {album_info['artist']} - {album_info['album']}: {e}")
    
    def _generate_report(self):
        """Generate comprehensive analysis report"""
        total = self.results['processed']
        matched = self.results['matched']
        
        print("\n" + "=" * 60)
        print("📊 LIBRARY MATCH ANALYSIS REPORT")
        print("=" * 60)
        
        # Overall statistics
        print(f"📈 OVERALL STATISTICS:")
        print(f"   Total Albums Processed: {total}")
        print(f"   Successful Matches: {matched} ({matched/total*100:.1f}%)")
        print(f"   No Matches: {self.results['no_match']} ({self.results['no_match']/total*100:.1f}%)")
        print(f"   Errors: {self.results['errors']}")
        print()
        
        # Genre improvement potential
        print(f"🎯 GENRE IMPROVEMENT POTENTIAL:")
        print(f"   Albums with Existing Genres: {self.results['albums_with_existing_genres']}")
        print(f"   Albums without Genres: {self.results['albums_without_genres']}")
        print(f"   Albums that would get NEW genres: {self.results['genre_improvements']} ({self.results['genre_improvements']/total*100:.1f}%)")
        print()
        
        # Confidence distribution
        print(f"📊 CONFIDENCE DISTRIBUTION:")
        for confidence_range in sorted(self.results['confidence_distribution'].keys()):
            count = self.results['confidence_distribution'][confidence_range]
            percentage = count / total * 100
            bar = "█" * int(percentage / 2)  # Visual bar
            print(f"   {confidence_range:>4}: {count:>4} albums ({percentage:>5.1f}%) {bar}")
        print()
        
        # Source usage
        print(f"📡 API SOURCE USAGE:")
        for source, count in sorted(self.results['source_usage'].items()):
            percentage = count / total * 100
            print(f"   {source:>12}: {count:>4} albums ({percentage:>5.1f}%)")
        print()
        
        # Top successful matches
        if self.detailed_results:
            top_matches = sorted(self.detailed_results, key=lambda x: x['confidence'], reverse=True)[:10]
            print(f"🏆 TOP 10 MATCHES (Highest Confidence):")
            for i, match in enumerate(top_matches, 1):
                improvement = "📈" if match['would_improve'] else "📊"
                print(f"   {i:>2}. {improvement} {match['confidence']:>5.1f}% - {match['artist']} - {match['album'][:40]}...")
                print(f"       Sources: {', '.join(match['sources'])}")
                if match['existing_genres']:
                    print(f"       Existing: {'; '.join(match['existing_genres'])}")
                print(f"       Suggested: {'; '.join(match['suggested_genres'])}")
                print()
        
        # Summary recommendations
        print("💡 RECOMMENDATIONS:")
        match_rate = matched / total * 100
        improvement_rate = self.results['genre_improvements'] / total * 100
        
        if match_rate >= 70:
            print(f"   ✅ Excellent match rate ({match_rate:.1f}%) - Ready for production!")
        elif match_rate >= 50:
            print(f"   🟡 Good match rate ({match_rate:.1f}%) - Consider running with current settings")
        else:
            print(f"   🔴 Low match rate ({match_rate:.1f}%) - Consider lowering confidence threshold")
        
        if improvement_rate >= 50:
            print(f"   🎯 High improvement potential ({improvement_rate:.1f}%) - Many albums will get better genres")
        elif improvement_rate >= 25:
            print(f"   📈 Moderate improvement potential ({improvement_rate:.1f}%) - Decent genre enhancements")
        else:
            print(f"   📊 Limited improvement potential ({improvement_rate:.1f}%) - Mostly validation of existing genres")

if __name__ == "__main__":
    scanner = LibraryMatchScanner("/Volumes/T7/Albums")
    
    print("Choose scan type:")
    print("1. Quick sample (50 albums)")
    print("2. Medium sample (200 albums)")  
    print("3. Large sample (500 albums)")
    print("4. Full library scan (2144 albums)")
    
    choice = input("Enter choice (1-4): ").strip()
    
    sample_sizes = {
        "1": 50,
        "2": 200,
        "3": 500,
        "4": None  # Full scan
    }
    
    sample_size = sample_sizes.get(choice, 50)
    
    # Run the scan
    scanner.scan_library(sample_size=sample_size, confidence_threshold=25.0)