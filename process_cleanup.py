#!/usr/bin/env python3
"""
Process Cleanup Utility
Handles termination of rogue processes before starting new instances
"""

import os
import sys
import signal
import psutil
from typing import List, Dict, Optional


class ProcessCleanup:
    """Utility class for cleaning up rogue processes"""
    
    @staticmethod
    def find_processes_by_script(script_name: str) -> List[Dict]:
        """Find processes running a specific Python script"""
        processes = []
        
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                # Check if it's a Python process
                if proc.info['name'] and 'python' in proc.info['name'].lower():
                    cmdline = proc.info['cmdline']
                    if cmdline and any(script_name in arg for arg in cmdline):
                        processes.append({
                            'pid': proc.info['pid'],
                            'cmdline': ' '.join(cmdline),
                            'process': proc
                        })
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        
        return processes
    
    @staticmethod
    def find_processes_by_port(port: int) -> List[Dict]:
        """Find processes using a specific port"""
        processes = []
        
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                # Check network connections
                try:
                    connections = proc.net_connections(kind='inet')
                except AttributeError:
                    # Fallback for older psutil versions
                    connections = proc.connections(kind='inet')
                for conn in connections:
                    if conn.laddr.port == port and conn.status == 'LISTEN':
                        processes.append({
                            'pid': proc.info['pid'],
                            'name': proc.info['name'],
                            'port': port,
                            'process': proc
                        })
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        
        return processes
    
    @staticmethod
    def kill_processes(processes: List[Dict], force: bool = False, verbose: bool = False) -> Dict:
        """Kill a list of processes"""
        results = {
            'killed': [],
            'failed': [],
            'total': len(processes)
        }
        
        for proc_info in processes:
            try:
                proc = proc_info['process']
                pid = proc_info['pid']
                
                # Skip current process
                if pid == os.getpid():
                    continue
                
                if verbose:
                    method = "SIGKILL" if force else "SIGTERM->SIGKILL"
                    print(f"    │   ├── Terminating PID {pid} ({method})...")
                
                # Try graceful termination first
                if not force:
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                        results['killed'].append(pid)
                        if verbose:
                            print(f"    │   │   └── ✅ Gracefully terminated")
                        continue
                    except psutil.TimeoutExpired:
                        if verbose:
                            print(f"    │   │   ├── Timeout, forcing kill...")
                        pass
                
                # Force kill if graceful termination failed
                proc.kill()
                try:
                    proc.wait(timeout=1)
                    results['killed'].append(pid)
                    if verbose:
                        print(f"    │   │   └── ✅ Force killed")
                except psutil.TimeoutExpired:
                    results['failed'].append(pid)
                    if verbose:
                        print(f"    │   │   └── ❌ Kill timeout")
                    
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                # Process already gone or no permission
                results['killed'].append(proc_info['pid'])
                if verbose:
                    print(f"    │   │   └── ✅ Already terminated")
            except Exception as e:
                results['failed'].append(proc_info['pid'])
                if verbose:
                    print(f"    │   │   └── ❌ Error: {e}")
        
        return results
    
    @staticmethod
    def cleanup_script_processes(script_name: str, exclude_current: bool = True, force_kill: bool = False, verbose: bool = False) -> Dict:
        """Clean up all processes running a specific script"""
        processes = ProcessCleanup.find_processes_by_script(script_name)
        
        if exclude_current:
            # Filter out current process
            current_pid = os.getpid()
            processes = [p for p in processes if p['pid'] != current_pid]
        
        if not processes:
            if verbose:
                print(f"    No existing {script_name} processes found")
            return {'killed': [], 'failed': [], 'total': 0}
        
        if verbose:
            print(f"    Found {len(processes)} existing {script_name} processes")
            for proc in processes:
                print(f"    ├── PID {proc['pid']}: {proc['cmdline'][:80]}{'...' if len(proc['cmdline']) > 80 else ''}")
        else:
            print(f"🧹 Found {len(processes)} existing {script_name} processes")
            for proc in processes:
                print(f"  - PID {proc['pid']}: {proc['cmdline']}")
        
        results = ProcessCleanup.kill_processes(processes, force=force_kill, verbose=verbose)
        
        if verbose:
            if results['killed']:
                print(f"    ├── ✅ Terminated {len(results['killed'])} processes")
            if results['failed']:
                print(f"    ├── ❌ Failed to terminate {len(results['failed'])} processes")
        else:
            if results['killed']:
                print(f"✅ Terminated {len(results['killed'])} processes: {results['killed']}")
            if results['failed']:
                print(f"❌ Failed to terminate {len(results['failed'])} processes: {results['failed']}")
        
        return results
    
    @staticmethod
    def cleanup_port_processes(port: int, force_kill: bool = False, verbose: bool = False) -> Dict:
        """Clean up all processes using a specific port"""
        processes = ProcessCleanup.find_processes_by_port(port)
        
        if not processes:
            if verbose:
                print(f"    No processes using port {port}")
            return {'killed': [], 'failed': [], 'total': 0}
        
        if verbose:
            print(f"    Found {len(processes)} processes using port {port}")
            for proc in processes:
                print(f"    ├── PID {proc['pid']}: {proc['name']}")
        else:
            print(f"🧹 Found {len(processes)} processes using port {port}")
            for proc in processes:
                print(f"  - PID {proc['pid']}: {proc['name']}")
        
        results = ProcessCleanup.kill_processes(processes, force=force_kill, verbose=verbose)
        
        if verbose:
            if results['killed']:
                print(f"    ├── ✅ Freed port {port} by terminating {len(results['killed'])} processes")
            if results['failed']:
                print(f"    ├── ❌ Failed to terminate {len(results['failed'])} processes")
        else:
            if results['killed']:
                print(f"✅ Freed port {port} by terminating {len(results['killed'])} processes")
            if results['failed']:
                print(f"❌ Failed to terminate {len(results['failed'])} processes on port {port}")
        
        return results
    
    @staticmethod
    def cleanup_music_system_processes() -> Dict:
        """Clean up all known music system processes"""
        scripts_to_cleanup = [
            'music_dashboard.py',
            'genre_diff_viewer.py',
            'web_interface.py',
            'music_genre_tagger.py',
            'batch_processor.py'
        ]
        
        ports_to_cleanup = [5000, 5002]
        
        total_results = {'killed': [], 'failed': [], 'total': 0}
        
        print("🧹 Cleaning up music system processes...")
        
        # Clean up by script name
        for script in scripts_to_cleanup:
            results = ProcessCleanup.cleanup_script_processes(script)
            total_results['killed'].extend(results['killed'])
            total_results['failed'].extend(results['failed'])
            total_results['total'] += results['total']
        
        # Clean up by port
        for port in ports_to_cleanup:
            results = ProcessCleanup.cleanup_port_processes(port)
            # Avoid double counting if already killed by script cleanup
            new_kills = [pid for pid in results['killed'] if pid not in total_results['killed']]
            new_fails = [pid for pid in results['failed'] if pid not in total_results['failed']]
            total_results['killed'].extend(new_kills)
            total_results['failed'].extend(new_fails)
            total_results['total'] += len(new_kills) + len(new_fails)
        
        if total_results['total'] == 0:
            print("✅ No rogue processes found")
        else:
            print(f"🧹 Cleanup complete: {len(total_results['killed'])} killed, {len(total_results['failed'])} failed")
        
        return total_results


def main():
    """Command-line interface for process cleanup"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Clean up rogue music system processes')
    parser.add_argument('--script', help='Clean up specific script processes')
    parser.add_argument('--port', type=int, help='Clean up processes using specific port')
    parser.add_argument('--all', action='store_true', help='Clean up all music system processes')
    parser.add_argument('--force', action='store_true', help='Force kill processes')
    
    args = parser.parse_args()
    
    if args.all:
        ProcessCleanup.cleanup_music_system_processes()
    elif args.script:
        ProcessCleanup.cleanup_script_processes(args.script)
    elif args.port:
        ProcessCleanup.cleanup_port_processes(args.port)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()