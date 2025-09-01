#!/usr/bin/env python3
"""
Web Interface for Manual Review and Bulk Operations
Flask-based web UI for managing genre updates and manual review
"""

import json
import os
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_from_directory
from datetime import datetime
from typing import Dict, List, Optional

from album_matcher import AlbumMatcher
from batch_processor import BatchProcessor, BatchDatabase
from enhanced_api_client import EnhancedAPIClient
from genre_standardizer import GenreStandardizer
from smart_genre_assignment import SmartGenreAssignment
from quality_control import QualityControlSystem
from process_cleanup import ProcessCleanup

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'

# Global instances (in production, use proper dependency injection)
music_path = "/Volumes/T7/Albums"
matcher = None
batch_processor = None
api_client = None
standardizer = None
smart_assignment = None
quality_control = None

def initialize_components():
    """Initialize all components"""
    global matcher, batch_processor, api_client, standardizer, smart_assignment, quality_control
    
    print("Initializing components...")
    
    matcher = AlbumMatcher(music_path)
    batch_processor = BatchProcessor(music_path)
    api_client = EnhancedAPIClient()
    standardizer = GenreStandardizer()
    smart_assignment = SmartGenreAssignment(music_path)
    quality_control = QualityControlSystem(music_path)
    
    # Load album data if not already loaded
    if not matcher.albums:
        print("Loading album data...")
        matcher.scan_filesystem()
        smart_assignment.initialize(matcher.albums)
    
    print("Components initialized!")

@app.route('/')
def dashboard():
    """Main dashboard"""
    if not matcher or not matcher.albums:
        return render_template('loading.html', message="Loading album data...")
    
    # Basic statistics
    total_albums = len(matcher.albums)
    albums_with_genres = sum(1 for album in matcher.albums.values() if album['genres'])
    albums_without_genres = total_albums - albums_with_genres
    
    # Recent jobs
    db = BatchDatabase()
    recent_jobs = []  # Would get from database
    
    stats = {
        'total_albums': total_albums,
        'albums_with_genres': albums_with_genres,
        'albums_without_genres': albums_without_genres,
        'genre_coverage': (albums_with_genres / total_albums * 100) if total_albums > 0 else 0
    }
    
    return render_template('dashboard.html', stats=stats, recent_jobs=recent_jobs)

@app.route('/api/albums')
def api_albums():
    """API endpoint to get albums with pagination"""
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 50))
    filter_type = request.args.get('filter', 'all')
    search = request.args.get('search', '')
    
    if not matcher:
        return jsonify({'error': 'System not initialized'}), 500
    
    # Filter albums
    filtered_albums = []
    
    for album_key, album_info in matcher.albums.items():
        # Apply search filter
        if search:
            search_lower = search.lower()
            if (search_lower not in album_info['artist'].lower() and 
                search_lower not in album_info['album'].lower()):
                continue
        
        # Apply type filter
        has_genres = bool(album_info['genres'])
        
        if filter_type == 'with_genres' and not has_genres:
            continue
        elif filter_type == 'without_genres' and has_genres:
            continue
        elif filter_type == 'needs_review':
            # Add logic for albums that need review
            pass
        
        album_data = {
            'key': album_key,
            'artist': album_info['artist'],
            'album': album_info['album'],
            'genres': list(album_info['genres']),
            'track_count': len(album_info['tracks']),
            'has_genres': has_genres
        }
        
        # Add suggestions if no genres
        if not has_genres and smart_assignment:
            suggestions = smart_assignment.get_smart_suggestions(album_key, album_info)
            album_data['suggestions'] = [
                {
                    'genres': s.genres,
                    'confidence': s.confidence,
                    'source': s.source,
                    'reasoning': s.reasoning
                } for s in suggestions
            ]
        
        filtered_albums.append(album_data)
    
    # Pagination
    total = len(filtered_albums)
    start = (page - 1) * per_page
    end = start + per_page
    albums_page = filtered_albums[start:end]
    
    return jsonify({
        'albums': albums_page,
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': (total + per_page - 1) // per_page
    })

@app.route('/api/album/<album_key>')
def api_album_detail(album_key):
    """Get detailed album information"""
    if not matcher or album_key not in matcher.albums:
        return jsonify({'error': 'Album not found'}), 404
    
    album_info = matcher.albums[album_key]
    
    # Get API results
    api_results = api_client.get_comprehensive_genres(album_info['artist'], album_info['album'])
    
    # Get smart suggestions
    suggestions = smart_assignment.get_smart_suggestions(album_key, album_info)
    
    result = {
        'key': album_key,
        'artist': album_info['artist'],
        'album': album_info['album'],
        'genres': list(album_info['genres']),
        'tracks': album_info['tracks'],
        'api_results': api_results,
        'suggestions': [
            {
                'genres': s.genres,
                'confidence': s.confidence,
                'source': s.source,
                'reasoning': s.reasoning
            } for s in suggestions
        ]
    }
    
    return jsonify(result)

@app.route('/api/album/<album_key>/update_genres', methods=['POST'])
def api_update_album_genres(album_key):
    """Update genres for a specific album"""
    if not matcher or album_key not in matcher.albums:
        return jsonify({'error': 'Album not found'}), 404
    
    data = request.get_json()
    new_genres = data.get('genres', [])
    
    if not isinstance(new_genres, list):
        return jsonify({'error': 'Genres must be a list'}), 400
    
    # Normalize genres
    normalized_genres = standardizer.normalize_genre_list(new_genres)
    
    # Update album info
    album_info = matcher.albums[album_key]
    album_info['genres'] = set(normalized_genres)
    
    # Update files
    try:
        files_updated = 0
        for track in album_info['tracks']:
            file_path = track.get('file_path')
            if file_path and Path(file_path).exists():
                success = batch_processor.tag_writer.write_genre_tags(
                    Path(file_path), normalized_genres, test_mode=False, preserve_existing=False
                )
                if success:
                    files_updated += 1
        
        return jsonify({
            'success': True,
            'genres': normalized_genres,
            'files_updated': files_updated
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/genres/suggest')
def api_suggest_genres():
    """Get genre suggestions based on partial input"""
    partial = request.args.get('q', '')
    limit = int(request.args.get('limit', 10))
    
    suggestions = standardizer.suggest_genres(partial, limit)
    return jsonify({'suggestions': suggestions})

@app.route('/api/batch/create', methods=['POST'])
def api_create_batch_job():
    """Create a new batch processing job"""
    data = request.get_json()
    
    name = data.get('name', '')
    album_keys = data.get('album_keys', [])
    confidence_threshold = data.get('confidence_threshold', 95.0)
    dry_run = data.get('dry_run', True)
    
    if not name or not album_keys:
        return jsonify({'error': 'Name and album_keys are required'}), 400
    
    try:
        job_id = batch_processor.create_processing_job(
            name, album_keys, confidence_threshold, dry_run
        )
        
        return jsonify({
            'success': True,
            'job_id': job_id
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/batch/<job_id>/run', methods=['POST'])
def api_run_batch_job(job_id):
    """Run a batch processing job"""
    db = BatchDatabase()
    job = db.get_job_status(job_id)
    
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    
    try:
        # Get album keys (this would be stored in the job)
        # For now, use a subset for testing
        album_keys = list(matcher.albums.keys())[:10]
        
        # Run job in background (in production, use Celery or similar)
        result = batch_processor.run_batch_job(job_id, album_keys)
        
        return jsonify({
            'success': True,
            'job': {
                'job_id': result.job_id,
                'processed': result.processed,
                'successful': result.successful,
                'failed': result.failed,
                'needs_review': result.needs_review,
                'skipped': result.skipped
            }
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/batch/<job_id>/status')
def api_batch_job_status(job_id):
    """Get batch job status"""
    summary = batch_processor.get_job_summary(job_id)
    
    if not summary:
        return jsonify({'error': 'Job not found'}), 404
    
    return jsonify(summary)

@app.route('/api/review_queue')
def api_review_queue():
    """Get manual review queue"""
    limit = int(request.args.get('limit', 50))
    
    db = BatchDatabase()
    queue_items = db.get_review_queue(limit=limit)
    
    return jsonify({'items': queue_items})

@app.route('/albums/scan-status')
def scan_status():
    """Show album scan status view"""
    if not matcher or not matcher.albums:
        return render_template('loading.html', message="Loading album data...")
    
    return render_template('scan_status.html')

@app.route('/api/scan-status')
def api_scan_status():
    """API endpoint for scan status data"""
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 50))
    status_filter = request.args.get('status', 'all')
    search = request.args.get('search', '')
    
    if not matcher:
        return jsonify({'error': 'System not initialized'}), 500
    
    # Get processed albums from database
    db = BatchDatabase()
    processed_albums = {}
    
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT album_key, artist, album, status, confidence, 
                       files_updated, created_at, error_message
                FROM album_results
                ORDER BY created_at DESC
            ''')
            
            for row in cursor.fetchall():
                album_key = row[0]
                processed_albums[album_key] = {
                    'artist': row[1],
                    'album': row[2],
                    'status': row[3],
                    'confidence': row[4],
                    'files_updated': row[5],
                    'created_at': row[6],
                    'error_message': row[7]
                }
    except Exception as e:
        print(f"Warning: Could not query database: {e}")
    
    # Categorize all albums
    categorized_albums = []
    
    for album_key, album_info in matcher.albums.items():
        # Apply search filter
        if search:
            search_lower = search.lower()
            if (search_lower not in album_info['artist'].lower() and 
                search_lower not in album_info['album'].lower()):
                continue
        
        # Determine status
        if album_key in processed_albums:
            processed = processed_albums[album_key]
            if processed['status'] == 'completed' and processed['files_updated'] > 0:
                scan_status = 'updated'
                status_label = 'Updated'
                status_class = 'success'
            elif processed['status'] == 'needs_review':
                scan_status = 'needs_review'
                status_label = 'Needs Review'
                status_class = 'warning'
            elif processed['status'] == 'failed':
                scan_status = 'failed'
                status_label = 'Failed'
                status_class = 'danger'
            else:
                scan_status = 'needs_scan'
                status_label = 'Needs Scan'
                status_class = 'secondary'
        else:
            scan_status = 'needs_scan'
            status_label = 'Needs Scan'
            status_class = 'secondary'
            processed = None
        
        # Apply status filter
        if status_filter != 'all' and scan_status != status_filter:
            continue
        
        album_data = {
            'album_key': album_key,
            'artist': album_info['artist'],
            'album': album_info['album'],
            'scan_status': scan_status,
            'status_label': status_label,
            'status_class': status_class,
            'track_count': len(album_info['tracks']),
            'has_genres': bool(album_info['genres']),
            'current_genres': list(album_info['genres']) if album_info['genres'] else []
        }
        
        # Add processing info if available
        if processed:
            album_data.update({
                'confidence': processed['confidence'],
                'files_updated': processed['files_updated'],
                'processed_at': processed['created_at'],
                'error_message': processed['error_message']
            })
        
        categorized_albums.append(album_data)
    
    # Pagination
    total = len(categorized_albums)
    start = (page - 1) * per_page
    end = start + per_page
    albums_page = categorized_albums[start:end]
    
    # Calculate summary stats
    stats = {
        'total': len(matcher.albums),
        'updated': len([a for a in categorized_albums if a['scan_status'] == 'updated']),
        'needs_scan': len([a for a in categorized_albums if a['scan_status'] == 'needs_scan']),
        'needs_review': len([a for a in categorized_albums if a['scan_status'] == 'needs_review']),
        'failed': len([a for a in categorized_albums if a['scan_status'] == 'failed'])
    }
    
    return jsonify({
        'albums': albums_page,
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': (total + per_page - 1) // per_page,
        'stats': stats
    })

@app.route('/api/quality/analyze')
def api_quality_analyze():
    """Run quality control analysis"""
    try:
        # Run analysis on subset for demo
        sample_albums = dict(list(matcher.albums.items())[:100])
        report = quality_control.run_comprehensive_analysis(sample_albums)
        
        return jsonify({
            'total_albums': report.total_albums,
            'total_issues': report.total_issues,
            'quality_score': report.genre_quality_score,
            'consistency_score': report.consistency_score,
            'issues_by_type': report.issues_by_type,
            'top_issues': [
                {
                    'type': issue.issue_type,
                    'severity': issue.severity,
                    'artist': issue.artist,
                    'album': issue.album,
                    'description': issue.description,
                    'suggested_fix': issue.suggested_fix
                } for issue in report.top_issues[:10]
            ]
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Create templates directory and HTML templates
def create_templates():
    """Create HTML templates for the web interface"""
    templates_dir = Path("templates")
    templates_dir.mkdir(exist_ok=True)
    
    # Base template
    base_template = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Music Genre Tagger{% endblock %}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
        <div class="container">
            <a class="navbar-brand" href="/">🎵 Genre Tagger</a>
            <div class="navbar-nav">
                <a class="nav-link" href="/">Dashboard</a>
                <a class="nav-link" href="/albums">Albums</a>
                <a class="nav-link" href="/batch">Batch Processing</a>
                <a class="nav-link" href="/quality">Quality Control</a>
            </div>
        </div>
    </nav>
    
    <div class="container mt-4">
        {% block content %}{% endblock %}
    </div>
    
    {% block scripts %}{% endblock %}
</body>
</html>
"""
    
    # Dashboard template
    dashboard_template = """
{% extends "base.html" %}

{% block title %}Dashboard - Music Genre Tagger{% endblock %}

{% block content %}
<div class="row">
    <div class="col-md-12">
        <h1>Music Library Dashboard</h1>
    </div>
</div>

<div class="row mt-4">
    <div class="col-md-3">
        <div class="card text-center">
            <div class="card-body">
                <h5 class="card-title">Total Albums</h5>
                <h2 class="text-primary">{{ stats.total_albums }}</h2>
            </div>
        </div>
    </div>
    <div class="col-md-3">
        <div class="card text-center">
            <div class="card-body">
                <h5 class="card-title">With Genres</h5>
                <h2 class="text-success">{{ stats.albums_with_genres }}</h2>
            </div>
        </div>
    </div>
    <div class="col-md-3">
        <div class="card text-center">
            <div class="card-body">
                <h5 class="card-title">Without Genres</h5>
                <h2 class="text-warning">{{ stats.albums_without_genres }}</h2>
            </div>
        </div>
    </div>
    <div class="col-md-3">
        <div class="card text-center">
            <div class="card-body">
                <h5 class="card-title">Coverage</h5>
                <h2 class="text-info">{{ "%.1f"|format(stats.genre_coverage) }}%</h2>
            </div>
        </div>
    </div>
</div>

<div class="row mt-4">
    <div class="col-md-6">
        <div class="card">
            <div class="card-header">
                <h5>Quick Actions</h5>
            </div>
            <div class="card-body">
                <a href="/albums?filter=without_genres" class="btn btn-primary mb-2">
                    Review Albums Without Genres
                </a><br>
                <a href="/batch" class="btn btn-success mb-2">
                    Start Batch Processing
                </a><br>
                <a href="/quality" class="btn btn-info mb-2">
                    Run Quality Check
                </a>
            </div>
        </div>
    </div>
    <div class="col-md-6">
        <div class="card">
            <div class="card-header">
                <h5>Recent Jobs</h5>
            </div>
            <div class="card-body">
                {% if recent_jobs %}
                    {% for job in recent_jobs %}
                    <p>{{ job.name }} - {{ job.status }}</p>
                    {% endfor %}
                {% else %}
                    <p class="text-muted">No recent jobs</p>
                {% endif %}
            </div>
        </div>
    </div>
</div>
{% endblock %}
"""
    
    # Loading template
    loading_template = """
{% extends "base.html" %}

{% block content %}
<div class="d-flex justify-content-center align-items-center" style="height: 50vh;">
    <div class="text-center">
        <div class="spinner-border text-primary" role="status">
            <span class="visually-hidden">Loading...</span>
        </div>
        <h3 class="mt-3">{{ message }}</h3>
        <p class="text-muted">This may take a few minutes for large libraries...</p>
    </div>
</div>
{% endblock %}
"""
    
    # Write templates
    with open(templates_dir / "base.html", 'w') as f:
        f.write(base_template)
    
    with open(templates_dir / "dashboard.html", 'w') as f:
        f.write(dashboard_template)
    
    with open(templates_dir / "loading.html", 'w') as f:
        f.write(loading_template)

if __name__ == "__main__":
    create_templates()
    
    print("Starting Music Genre Tagger Web Interface...")
    
    # Clean up any existing processes first
    ProcessCleanup.cleanup_script_processes('web_interface.py')
    ProcessCleanup.cleanup_port_processes(5000)
    
    print("Initializing components (this may take a moment)...")
    
    try:
        initialize_components()
        print("✓ All components initialized successfully!")
        print("\nStarting web server...")
        print("Access the interface at: http://localhost:5000")
        
        app.run(debug=True, host='0.0.0.0', port=5000)
        
    except Exception as e:
        print(f"Error starting application: {e}")
        print("Make sure the music path is accessible and try again.")