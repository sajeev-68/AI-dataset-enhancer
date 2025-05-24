#!/usr/bin/env python3
"""
Improved master script for distributed vulnerability description enhancement

This script:
1. Splits a JSON dataset into multiple fragments
2. Assigns each fragment to a worker container
3. Monitors progress of workers with a clear, consolidated display
4. Combines results when all workers are done
"""

import json
import time
import os
import subprocess
import logging
import sys
import threading
from datetime import datetime
from collections import defaultdict

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("/results/master.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("master")

# Configuration from environment variables
NUM_WORKERS = int(os.environ.get('NUM_WORKERS', 4))
INPUT_FILE = os.environ.get('INPUT_FILE', '/data/vulnerability_dataset.json')
OUTPUT_FILE = os.environ.get('OUTPUT_FILE', '/results/vulnerability_dataset.enhanced.json')
FRAGMENT_DIR = "/data/fragments"
RESULT_DIR = "/results/fragments"

# Create necessary directories
os.makedirs(FRAGMENT_DIR, exist_ok=True)
os.makedirs(RESULT_DIR, exist_ok=True)

# Store progress info for each worker
worker_status = {}
worker_logs = defaultdict(list)
status_lock = threading.Lock()

def load_and_split_data():
    """Load the JSON dataset and split it into fragments."""
    logger.info(f"Loading data from {INPUT_FILE}")
    
    try:
        with open(INPUT_FILE, 'r') as f:
            data = json.load(f)
        
        # Determine data structure
        if isinstance(data, list):
            entries = data
            data_structure = "list"
        elif isinstance(data, dict) and "data" in data:
            entries = data["data"]
            data_structure = "dict_with_data"
        else:
            # Try to find any list field in the JSON
            list_fields = [k for k, v in data.items() if isinstance(v, list)]
            if list_fields:
                entries = data[list_fields[0]]
                data_structure = "dict_with_list"
                list_field_name = list_fields[0]
            else:
                entries = [data]  # Treat the whole JSON as a single entry
                data_structure = "single_object"
        
        logger.info(f"Loaded {len(entries)} entries, detected structure: {data_structure}")
        
        # Calculate fragment sizes
        total_entries = len(entries)
        base_size = total_entries // NUM_WORKERS
        remainder = total_entries % NUM_WORKERS
        
        fragment_sizes = [base_size + (1 if i < remainder else 0) for i in range(NUM_WORKERS)]
        logger.info(f"Fragment sizes: {fragment_sizes}")
        
        # Create fragments
        start_idx = 0
        fragments = []
        
        for worker_id in range(NUM_WORKERS):
            size = fragment_sizes[worker_id]
            end_idx = start_idx + size
            fragment = entries[start_idx:end_idx]
            fragment_file = f"{FRAGMENT_DIR}/fragment_{worker_id+1}.json"
            
            # Save fragment with original structure
            if data_structure == "list":
                with open(fragment_file, 'w') as f:
                    json.dump(fragment, f)
            elif data_structure == "dict_with_data":
                fragment_data = data.copy()
                fragment_data["data"] = fragment
                with open(fragment_file, 'w') as f:
                    json.dump(fragment_data, f)
            elif data_structure == "dict_with_list":
                fragment_data = data.copy()
                fragment_data[list_field_name] = fragment
                with open(fragment_file, 'w') as f:
                    json.dump(fragment_data, f)
            else:  # single_object
                with open(fragment_file, 'w') as f:
                    json.dump(fragment[0] if fragment else {}, f)
            
            logger.info(f"Created fragment {worker_id+1} with {size} entries at {fragment_file}")
            fragments.append({
                "worker_id": worker_id + 1,
                "file": fragment_file,
                "size": size,
                "start_idx": start_idx,
                "end_idx": end_idx
            })
            
            # Initialize worker status
            worker_status[worker_id + 1] = {
                "status": "Ready",
                "progress": 0,
                "total": size,
                "stage": "Not started",
                "last_update": time.time()
            }
            
            start_idx = end_idx
        
        return fragments, data_structure, data
    
    except Exception as e:
        logger.error(f"Error loading data: {e}")
        raise

def monitor_worker_log(worker_id):
    """Monitor the log file of a specific worker and update its status."""
    log_file = f"{RESULT_DIR}/worker_{worker_id}.log"
    last_position = 0
    
    while not worker_status[worker_id].get("completed", False):
        try:
            if os.path.exists(log_file):
                with open(log_file, 'r') as f:
                    f.seek(last_position)
                    new_lines = f.readlines()
                    if new_lines:
                        last_position = f.tell()
                        for line in new_lines:
                            with status_lock:
                                worker_logs[worker_id].append(line.strip())
                                
                                # Update status based on log content
                                if "Starting Ollama" in line:
                                    worker_status[worker_id]["stage"] = "Starting Ollama"
                                elif "Pulling model" in line:
                                    worker_status[worker_id]["stage"] = "Pulling model"
                                elif "Ollama service is running" in line:
                                    worker_status[worker_id]["stage"] = "Ollama ready"
                                elif "processing fragment" in line:
                                    worker_status[worker_id]["stage"] = "Processing"
                                elif "Processed " in line and "entries" in line:
                                    # Extract progress information
                                    try:
                                        parts = line.split("Processed ")[1].split()
                                        if "/" in parts[0]:
                                            current, total = map(int, parts[0].split("/"))
                                            worker_status[worker_id]["progress"] = current
                                            worker_status[worker_id]["total"] = total
                                            worker_status[worker_id]["status"] = "Processing"
                                    except:
                                        pass
                                elif "Processing completed" in line:
                                    worker_status[worker_id]["status"] = "Completed"
                                    worker_status[worker_id]["progress"] = worker_status[worker_id]["total"]
                                    worker_status[worker_id]["completed"] = True
                                
                                worker_status[worker_id]["last_update"] = time.time()
            
            time.sleep(1)
        except Exception as e:
            logger.error(f"Error monitoring worker {worker_id} log: {e}")
            time.sleep(5)

def display_status():
    """Display the status of all workers in a clear format."""
    while not all(worker.get("completed", False) for worker in worker_status.values()):
        # Clear screen
        os.system('cls' if os.name == 'nt' else 'clear')
        
        print("\n" + "="*80)
        print(f"VULNERABILITY ENHANCEMENT PROCESSING - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*80)
        
        # Display overall progress
        total_entries = sum(worker["total"] for worker in worker_status.values())
        processed_entries = sum(worker["progress"] for worker in worker_status.values())
        overall_percentage = (processed_entries / total_entries * 100) if total_entries > 0 else 0
        
        print(f"\nOVERALL PROGRESS: {processed_entries}/{total_entries} entries ({overall_percentage:.1f}%)")
        print("-"*80)
        
        # Display status for each worker
        print("\nWORKER STATUS:")
        for worker_id, status in sorted(worker_status.items()):
            stage = status["stage"]
            progress = status["progress"]
            total = status["total"]
            percentage = (progress / total * 100) if total > 0 else 0
            
            # Calculate time since last update
            idle_time = time.time() - status["last_update"]
            idle_indicator = " (!)" if idle_time > 60 else ""
            
            # Create a progress bar
            bar_length = 30
            filled_length = int(bar_length * percentage / 100)
            bar = '█' * filled_length + '░' * (bar_length - filled_length)
            
            print(f"Worker {worker_id}: [{bar}] {percentage:.1f}% - {stage} ({progress}/{total}){idle_indicator}")
        
        print("\nLATEST LOGS:")
        for worker_id in sorted(worker_logs.keys()):
            # Show the last 2 log entries for each worker
            logs = worker_logs[worker_id][-2:] if worker_logs[worker_id] else []
            if logs:
                print(f"Worker {worker_id}:", end=" ")
                print(logs[-1] if len(logs) == 1 else f"{logs[-2]} → {logs[-1]}")
        
        print("\nPress Ctrl+C to exit monitoring (processing will continue)")
        print("="*80)
        
        time.sleep(2)
    
    # Final status after completion
    os.system('cls' if os.name == 'nt' else 'clear')
    print("\n" + "="*80)
    print(f"PROCESSING COMPLETED - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    print("\nAll workers have completed processing!")
    print(f"Enhanced data saved to {OUTPUT_FILE}")
    print("="*80 + "\n")

def monitor_workers(fragments):
    """Monitor the progress of worker containers."""
    logger.info("Starting worker monitoring")
    
    # Create monitoring threads for each worker
    threads = []
    for fragment in fragments:
        worker_id = fragment["worker_id"]
        thread = threading.Thread(target=monitor_worker_log, args=(worker_id,))
        thread.daemon = True
        thread.start()
        threads.append(thread)
    
    # Start the display thread
    display_thread = threading.Thread(target=display_status)
    display_thread.daemon = True
    display_thread.start()
    
    # Wait for all workers to complete
    try:
        while not all(worker.get("completed", False) for worker in worker_status.values()):
            # Check for result files as a backup completion indicator
            for fragment in fragments:
                worker_id = fragment["worker_id"]
                result_file = f"{RESULT_DIR}/result_{worker_id}.json"
                
                if os.path.exists(result_file) and not worker_status[worker_id].get("completed", False):
                    logger.info(f"Worker {worker_id} completed (detected by result file)")
                    with status_lock:
                        worker_status[worker_id]["status"] = "Completed"
                        worker_status[worker_id]["progress"] = worker_status[worker_id]["total"]
                        worker_status[worker_id]["completed"] = True
            
            time.sleep(5)
    except KeyboardInterrupt:
        logger.info("Monitoring interrupted by user")
    
    logger.info("All workers have completed processing")
    
    # Wait for display thread to complete
    display_thread.join(timeout=2)
    
    return True

def combine_results(fragments, data_structure, original_data):
    """Combine results from all workers into a single output file."""
    logger.info("Combining results from all workers")
    
    try:
        combined_entries = []
        
        for fragment in fragments:
            worker_id = fragment["worker_id"]
            result_file = f"{RESULT_DIR}/result_{worker_id}.json"
            
            with open(result_file, 'r') as f:
                result_data = json.load(f)
            
            # Extract entries based on data structure
            if data_structure == "list":
                entries = result_data
            elif data_structure == "dict_with_data":
                entries = result_data["data"]
            elif data_structure == "dict_with_list":
                list_fields = [k for k, v in result_data.items() if isinstance(v, list)]
                if list_fields:
                    entries = result_data[list_fields[0]]
                else:
                    entries = []
            else:  # single_object
                entries = [result_data]
            
            logger.info(f"Adding {len(entries)} entries from worker {worker_id}")
            combined_entries.extend(entries)
        
        # Sort entries by their original order if needed
        # This assumes entries have some index or identifier to restore original order
        
        # Create final output with original structure
        if data_structure == "list":
            final_data = combined_entries
        elif data_structure == "dict_with_data":
            final_data = original_data.copy()
            final_data["data"] = combined_entries
        elif data_structure == "dict_with_list":
            final_data = original_data.copy()
            list_fields = [k for k, v in original_data.items() if isinstance(v, list)]
            if list_fields:
                final_data[list_fields[0]] = combined_entries
        else:  # single_object
            final_data = combined_entries[0] if combined_entries else {}
        
        # Save combined results
        with open(OUTPUT_FILE, 'w') as f:
            json.dump(final_data, f, indent=2)
        
        logger.info(f"Combined results saved to {OUTPUT_FILE}")
        
    except Exception as e:
        logger.error(f"Error combining results: {e}")
        raise

def main():
    start_time = datetime.now()
    logger.info(f"Starting distributed processing at {start_time}")
    
    try:
        # Split data into fragments
        fragments, data_structure, original_data = load_and_split_data()
        
        # Monitor workers until completion
        monitor_workers(fragments)
        
        # Combine results
        combine_results(fragments, data_structure, original_data)
        
        end_time = datetime.now()
        duration = end_time - start_time
        logger.info(f"Processing completed at {end_time}")
        logger.info(f"Total processing time: {duration}")
        
    except Exception as e:
        logger.error(f"Error in main process: {e}")
        raise

if __name__ == "__main__":
    main()
