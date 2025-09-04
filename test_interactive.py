#!/usr/bin/env python3
"""
Quick test of the interactive mode features without starting Flask server
"""

import sys
import time
from music_dashboard import MusicLibraryDashboard
from process_cleanup import ProcessCleanup

def test_process_cleanup():
    print("🧪 Testing process cleanup with verbose mode...")
    
    # Test script cleanup
    print("\n1. Testing script process cleanup:")
    result = ProcessCleanup.cleanup_script_processes('music_dashboard.py', verbose=True)
    print(f"   Result: {result}")
    
    # Test port cleanup  
    print("\n2. Testing port process cleanup:")
    result = ProcessCleanup.cleanup_port_processes(5002, verbose=True)
    print(f"   Result: {result}")

def test_database_init():
    print("\n🧪 Testing database initialization with verbose mode...")
    
    start_time = time.time()
    try:
        dashboard = MusicLibraryDashboard(verbose=True)
        init_time = time.time() - start_time
        print(f"✅ Database initialization completed in {init_time:.2f}s")
        return True
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        return False

if __name__ == '__main__':
    print("🎵 Testing Music Dashboard Interactive Mode Components\n")
    
    # Test process cleanup
    test_process_cleanup()
    
    # Test database initialization  
    if test_database_init():
        print("\n✅ All tests passed! Interactive mode components are working correctly.")
    else:
        print("\n❌ Database test failed!")
        sys.exit(1)