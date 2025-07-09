#!/usr/bin/env python3
"""
Genre Diff Viewer - Web App for Visualizing Genre Modifications
Shows before/after genre comparisons with visual diffs
"""

from flask import Flask, render_template, request, jsonify
import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Tuple
import difflib
import re

app = Flask(__name__)

class GenreDiffViewer:
    def __init__(self, db_path: str = "batch_processing.db"):
        self.db_path = db_path
    
    def get_connection(self):
        """Get database connection"""
        return sqlite3.connect(self.db_path)
    
    def parse_genres(self, genre_string: str) -> List[str]:
        """Parse genre string into list"""
        if not genre_string or genre_string == 'null':
            return []
        
        try:
            # Try JSON parsing first
            if genre_string.startswith('['):
                return json.loads(genre_string)
            else:
                # Split on semicolon
                return [g.strip() for g in genre_string.split(';') if g.strip()]
        except:
            return [genre_string] if genre_string else []
    
    def create_genre_diff(self, original: List[str], suggested: List[str], final: List[str]) -> Dict:
        """Create detailed diff between genre lists"""
        original_set = set([g.lower() for g in original])
        suggested_set = set([g.lower() for g in suggested])
        final_set = set([g.lower() for g in final])
        
        # Map back to proper case for display
        original_map = {g.lower(): g for g in original}
        suggested_map = {g.lower(): g for g in suggested}
        final_map = {g.lower(): g for g in final}
        
        return {
            'original': original,
            'suggested': suggested,
            'final': final,
            'added': [final_map[g] for g in final_set - original_set],
            'removed': [original_map[g] for g in original_set - final_set],
            'kept': [final_map[g] for g in final_set & original_set],
            'suggested_only': [suggested_map[g] for g in suggested_set - final_set],
            'has_changes': len(final_set - original_set) > 0 or len(original_set - final_set) > 0
        }
    
    def get_batch_jobs(self) -> List[Dict]:
        """Get all batch jobs"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT job_id, name, created_at, total_albums, processed, 
                       successful, failed, needs_review, skipped, status, 
                       confidence_threshold, dry_run
                FROM batch_jobs 
                ORDER BY created_at DESC
            ''')
            
            jobs = []
            for row in cursor.fetchall():
                jobs.append({
                    'job_id': row[0],
                    'name': row[1],
                    'created_at': row[2],
                    'total_albums': row[3],
                    'processed': row[4],
                    'successful': row[5],
                    'failed': row[6],
                    'needs_review': row[7],
                    'skipped': row[8],
                    'status': row[9],
                    'confidence_threshold': row[10],
                    'dry_run': row[11]
                })
            
            return jobs
    
    def get_album_results(self, job_id: str, status_filter: str = None, 
                         changes_only: bool = False, page: int = 1, 
                         per_page: int = 50) -> Tuple[List[Dict], int]:
        """Get album results with pagination"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Build query
            where_clause = "WHERE job_id = ?"
            params = [job_id]
            
            if status_filter and status_filter != 'all':
                where_clause += " AND status = ?"
                params.append(status_filter)
            
            # Count total
            count_query = f"SELECT COUNT(*) FROM album_results {where_clause}"
            cursor.execute(count_query, params)
            total = cursor.fetchone()[0]
            
            # Get results
            offset = (page - 1) * per_page
            query = f'''
                SELECT album_key, artist, album, original_genres, 
                       suggested_genres, final_genres, confidence, 
                       sources_used, files_updated, status, 
                       error_message, processing_time, created_at
                FROM album_results 
                {where_clause}
                ORDER BY confidence DESC, created_at DESC
                LIMIT ? OFFSET ?
            '''
            params.extend([per_page, offset])
            
            cursor.execute(query, params)
            
            results = []
            for row in cursor.fetchall():
                original = self.parse_genres(row[3])
                suggested = self.parse_genres(row[4])
                final = self.parse_genres(row[5])
                
                diff = self.create_genre_diff(original, suggested, final)
                
                # Filter changes only if requested
                if changes_only and not diff['has_changes']:
                    continue
                
                results.append({
                    'album_key': row[0],
                    'artist': row[1],
                    'album': row[2],
                    'original_genres': original,
                    'suggested_genres': suggested,
                    'final_genres': final,
                    'confidence': row[6],
                    'sources_used': row[7],
                    'files_updated': row[8],
                    'status': row[9],
                    'error_message': row[10],
                    'processing_time': row[11],
                    'created_at': row[12],
                    'diff': diff
                })
            
            return results, total
    
    def get_statistics(self, job_id: str) -> Dict:
        """Get statistics for a job"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Basic stats
            cursor.execute('''
                SELECT status, COUNT(*) 
                FROM album_results 
                WHERE job_id = ? 
                GROUP BY status
            ''', (job_id,))
            status_counts = dict(cursor.fetchall())
            
            # Confidence distribution
            cursor.execute('''
                SELECT 
                    CASE 
                        WHEN confidence >= 90 THEN '90%+'
                        WHEN confidence >= 80 THEN '80-89%'
                        WHEN confidence >= 70 THEN '70-79%'
                        WHEN confidence >= 50 THEN '50-69%'
                        ELSE '<50%'
                    END as conf_range,
                    COUNT(*)
                FROM album_results 
                WHERE job_id = ?
                GROUP BY conf_range
            ''', (job_id,))
            confidence_dist = dict(cursor.fetchall())
            
            # Genre addition stats
            cursor.execute('''
                SELECT album_key, original_genres, final_genres
                FROM album_results 
                WHERE job_id = ? AND final_genres IS NOT NULL
            ''', (job_id,))
            
            total_additions = 0
            albums_with_additions = 0
            
            for row in cursor.fetchall():
                original = len(self.parse_genres(row[1]))
                final = len(self.parse_genres(row[2]))
                if final > original:
                    albums_with_additions += 1
                    total_additions += (final - original)
            
            return {
                'status_counts': status_counts,
                'confidence_distribution': confidence_dist,
                'total_additions': total_additions,
                'albums_with_additions': albums_with_additions
            }

# Initialize viewer
viewer = GenreDiffViewer()

@app.route('/')
def index():
    """Main dashboard"""
    jobs = viewer.get_batch_jobs()
    return render_template('index.html', jobs=jobs)

@app.route('/job/<job_id>')
def view_job(job_id):
    """View specific job results"""
    status_filter = request.args.get('status', 'all')
    changes_only = request.args.get('changes_only', 'false').lower() == 'true'
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 50))
    
    # Get job details
    jobs = viewer.get_batch_jobs()
    job = next((j for j in jobs if j['job_id'] == job_id), None)
    
    if not job:
        return "Job not found", 404
    
    # Get results
    results, total = viewer.get_album_results(job_id, status_filter, changes_only, page, per_page)
    
    # Get statistics
    stats = viewer.get_statistics(job_id)
    
    # Pagination info
    total_pages = (total + per_page - 1) // per_page
    
    return render_template('job_results.html', 
                         job=job, 
                         results=results, 
                         stats=stats,
                         status_filter=status_filter,
                         changes_only=changes_only,
                         page=page,
                         per_page=per_page,
                         total=total,
                         total_pages=total_pages)

@app.route('/api/album/<job_id>/<path:album_key>')
def get_album_detail(job_id, album_key):
    """Get detailed album information"""
    with viewer.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM album_results 
            WHERE job_id = ? AND album_key = ?
        ''', (job_id, album_key))
        
        row = cursor.fetchone()
        if not row:
            return jsonify({'error': 'Album not found'}), 404
        
        # Parse and create diff
        original = viewer.parse_genres(row[4])  # original_genres
        suggested = viewer.parse_genres(row[5])  # suggested_genres  
        final = viewer.parse_genres(row[6])  # final_genres
        
        diff = viewer.create_genre_diff(original, suggested, final)
        
        return jsonify({
            'album_key': row[1],
            'artist': row[2],
            'album': row[3],
            'diff': diff,
            'confidence': row[7],
            'sources_used': row[8],
            'processing_time': row[12]
        })

if __name__ == '__main__':
    print("🎵 Starting Genre Diff Viewer Web App...")
    print("📊 Available at: http://localhost:5001")
    print("🔍 Visualizing genre modifications and diffs")
    app.run(debug=True, host='0.0.0.0', port=5001)