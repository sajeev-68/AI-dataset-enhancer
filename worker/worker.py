"""
Worker script for distributed vulnerability description enhancement with checkpointing

This script:
1. Uses a bash script to start Ollama and pull models
2. Processes a fragment of the dataset assigned by the master
3. Uses Ollama Python library to enhance vulnerability descriptions
4. Saves progress every 100 entries and can resume from checkpoints
5. Saves results back to a shared volume
"""

import json
import time
import os
import subprocess
import logging
import ollama
from tqdm import tqdm

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f"/results/fragments/worker_{os.environ.get('WORKER_ID', 'unknown')}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(f"worker-{os.environ.get('WORKER_ID', 'unknown')}")

# Configuration from environment variables
WORKER_ID = int(os.environ.get('WORKER_ID', 1))
MODEL_NAME = os.environ.get('MODEL_NAME', 'phi:mini')
FRAGMENT_DIR = "/data/fragments"
RESULT_DIR = "/results/fragments"
GPU_MEMORY_LIMIT = int(os.environ.get('GPU_MEMORY_LIMIT', 2048))  # In MB
CHECKPOINT_INTERVAL = 100  # Save checkpoint every 100 entries

# Input and output files
INPUT_FILE = f"{FRAGMENT_DIR}/fragment_{WORKER_ID}.json"
OUTPUT_FILE = f"{RESULT_DIR}/result_{WORKER_ID}.json"
CHECKPOINT_FILE = f"{RESULT_DIR}/checkpoint_{WORKER_ID}.json"
PROGRESS_FILE = f"{RESULT_DIR}/progress_{WORKER_ID}.json"

def save_progress(processed_count, total_count, stage="processing"):
    """Save current progress to file for monitoring."""
    try:
        progress_data = {
            "worker_id": WORKER_ID,
            "processed": processed_count,
            "total": total_count,
            "percentage": (processed_count / total_count * 100) if total_count > 0 else 0,
            "stage": stage,
            "timestamp": time.time()
        }
        with open(PROGRESS_FILE, 'w') as f:
            json.dump(progress_data, f)
    except Exception as e:
        logger.warning(f"Failed to save progress: {e}")

def load_checkpoint():
    """Load checkpoint data if it exists."""
    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, 'r') as f:
                checkpoint = json.load(f)
            logger.info(f"Loaded checkpoint: {checkpoint['processed']}/{checkpoint['total']} entries processed")
            return checkpoint
        except Exception as e:
            logger.warning(f"Failed to load checkpoint: {e}")
    return None

def save_checkpoint(processed_entries, total_entries, data_structure, original_data, list_field_name=None):
    """Save checkpoint with current progress."""
    try:
        checkpoint_data = {
            "processed": len(processed_entries),
            "total": total_entries,
            "data_structure": data_structure,
            "list_field_name": list_field_name,
            "timestamp": time.time(),
            "processed_entries": processed_entries
        }
        
        # Save checkpoint
        with open(CHECKPOINT_FILE, 'w') as f:
            json.dump(checkpoint_data, f, indent=2)
        
        # Also save current results
        if data_structure == "list":
            result_data = processed_entries
        elif data_structure == "dict_with_data":
            result_data = original_data.copy()
            result_data["data"] = processed_entries
        elif data_structure == "dict_with_list":
            result_data = original_data.copy()
            result_data[list_field_name] = processed_entries
        else:  # single_object
            result_data = processed_entries[0] if processed_entries else {}

        with open(f"{OUTPUT_FILE}.checkpoint", 'w') as f:
            json.dump(result_data, f, indent=2)
            
        logger.info(f"Checkpoint saved: {len(processed_entries)}/{total_entries} entries")
        
    except Exception as e:
        logger.error(f"Failed to save checkpoint: {e}")

def enhance_description(entry):
    """Enhance a vulnerability(or any) description using the Ollama Python library."""
    #change the fields to be selected here
    original_output = entry.get("output", "")
    code_sample = entry.get("input", "")

    # change this if you want a different prompt
    prompt = f"""You are a cybersecurity expert. Improve the following vulnerability explanation by:
1. Fixing grammar and sentence structure
2. Making the description more clear and descriptive
3. Ensuring proper technical explanations while keeping the same structure
4. Maintaining all technical details (CWE numbers, line numbers, function names)
5. Not deviating from the original description
6. Provide only the description no fluff or other things like intro

The vulnerability relates to this code:
```c/cpp
{code_sample}
```

Original vulnerability description:
{original_output}

Enhanced description:"""

    max_retries = 3
    for retry in range(max_retries):
        try:
            # Use the ollama.chat function to get a response
            response = ollama.chat(
                model="gemma3:1b-it-qat",  # Use the pulled model name
                messages=[
                    {"role": "user", "content": prompt}
                ],
                options={
                    "temperature": 0.2, # change temprature for more creative responses
                    "num_predict": 256 # change number of tokens for more/less detailed explanations/responses
                }
            )

            # Extract the enhanced description
            enhanced_output = response["message"]["content"].strip()

            # Create a new entry with the enhanced output
            updated_entry = entry.copy()
            updated_entry["output"] = enhanced_output
            return updated_entry

        except Exception as e:
            logger.warning(f"Exception in ollama.chat: {e} (Retry {retry+1}/{max_retries})")
            time.sleep(2)

    # If all retries fail, keep the original entry
    logger.error(f"Failed to process entry after {max_retries} attempts - keeping original")
    return entry

def process_fragment():
    """Process the assigned fragment of the dataset with checkpointing."""
    logger.info(f"Worker {WORKER_ID} starting to process fragment {INPUT_FILE}")
    save_progress(0, 0, "loading")

    try:
        # Load fragment data
        with open(INPUT_FILE, 'r') as f:
            data = json.load(f)

        # Determine data structure
        list_field_name = None
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

        total_entries = len(entries)
        logger.info(f"Loaded {total_entries} entries, detected structure: {data_structure}")
        save_progress(0, total_entries, "loaded")

        # Check for existing checkpoint
        checkpoint = load_checkpoint()
        start_index = 0
        result_entries = []
        
        if checkpoint and checkpoint["total"] == total_entries:
            start_index = checkpoint["processed"]
            result_entries = checkpoint["processed_entries"]
            logger.info(f"Resuming from checkpoint at entry {start_index}")
            save_progress(start_index, total_entries, "resumed")
        else:
            logger.info("Starting fresh processing")
            save_progress(0, total_entries, "processing")

        # Process entries from start_index
        for i in range(start_index, total_entries):
            try:
                # Process single entry
                processed_entry = enhance_description(entries[i])
                result_entries.append(processed_entry)
                
                # Brief pause to avoid overwhelming Ollama
                time.sleep(0.1)
                
                processed_count = len(result_entries)
                
                # Save checkpoint every CHECKPOINT_INTERVAL entries
                if processed_count % CHECKPOINT_INTERVAL == 0:
                    save_checkpoint(result_entries, total_entries, data_structure, data, list_field_name)
                    save_progress(processed_count, total_entries, "processing")
                    logger.info(f"Processed {processed_count}/{total_entries} entries ({processed_count/total_entries*100:.1f}%)")
                
                # Update progress more frequently for monitoring
                if processed_count % 10 == 0:
                    save_progress(processed_count, total_entries, "processing")
                    
            except Exception as e:
                logger.error(f"Error processing entry {i}: {e}")
                # Save original entry on error
                result_entries.append(entries[i])

        # Save final results
        if data_structure == "list":
            final_data = result_entries
        elif data_structure == "dict_with_data":
            final_data = data.copy()
            final_data["data"] = result_entries
        elif data_structure == "dict_with_list":
            final_data = data.copy()
            final_data[list_field_name] = result_entries
        else:  # single_object
            final_data = result_entries[0] if result_entries else {}

        with open(OUTPUT_FILE, 'w') as f:
            json.dump(final_data, f, indent=2)

        # Clean up checkpoint files after successful completion
        try:
            if os.path.exists(CHECKPOINT_FILE):
                os.remove(CHECKPOINT_FILE)
            if os.path.exists(f"{OUTPUT_FILE}.checkpoint"):
                os.remove(f"{OUTPUT_FILE}.checkpoint")
        except:
            pass

        save_progress(total_entries, total_entries, "completed")
        logger.info(f"Processing completed. Results saved to {OUTPUT_FILE}")

    except Exception as e:
        logger.error(f"Error processing fragment: {e}")
        save_progress(0, 0, "error")
        raise

def start_ollama_with_bash():
    """Start Ollama using the bash script."""
    logger.info("Starting Ollama using the bash script")
    save_progress(0, 0, "starting_ollama")

    try:
        # Run the bash script with environment variables
        result = subprocess.run(
            ["/app/start-ollama.sh"],
            env={
                **os.environ,
                "WORKER_ID": str(WORKER_ID),
                "MODEL_NAME": MODEL_NAME,
                "GPU_MEMORY_LIMIT": str(GPU_MEMORY_LIMIT)
            },
            check=True
        )

        if result.returncode == 0:
            logger.info("Ollama started successfully via bash script")
            save_progress(0, 0, "ollama_ready")
            # Verify we can connect using the Python library
            try:
                models = ollama.list()
                logger.info(f"Successfully connected to Ollama using Python library")
                return True
            except Exception as e:
                logger.warning(f"Bash script succeeded but Python library connection failed: {e}")
                save_progress(0, 0, "ollama_connection_failed")
                return False
        else:
            logger.error(f"Bash script failed with return code {result.returncode}")
            save_progress(0, 0, "ollama_start_failed")
            return False

    except subprocess.CalledProcessError as e:
        logger.error(f"Error running bash script: {e}")
        save_progress(0, 0, "ollama_start_failed")
        return False
    except Exception as e:
        logger.error(f"Unexpected error starting Ollama: {e}")
        save_progress(0, 0, "ollama_start_failed")
        return False

def main():
    # Start Ollama service using bash script
    if not start_ollama_with_bash():
        logger.error("Cannot proceed without Ollama service")
        return

    # Process the fragment
    process_fragment()

if __name__ == "__main__":
    main()
