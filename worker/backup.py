#!/usr/bin/env python3
"""
Worker script for distributed vulnerability description enhancement

This script:
1. Uses a bash script to start Ollama and pull models
2. Processes a fragment of the dataset assigned by the master
3. Uses Ollama Python library to enhance vulnerability descriptions
4. Saves results back to a shared volume
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

# Input and output files
INPUT_FILE = f"{FRAGMENT_DIR}/fragment_{WORKER_ID}.json"
OUTPUT_FILE = f"{RESULT_DIR}/result_{WORKER_ID}.json"

def enhance_description(entry):
    """Enhance a vulnerability description using the Ollama Python library."""
    original_output = entry.get("output", "")
    code_sample = entry.get("input", "")

    # Create prompt for the model
    prompt = f"""You are a cybersecurity expert. Improve the following vulnerability explanation by:
1. Fixing grammar and sentence structure
2. Making the description more clear and descriptive
3. Ensuring proper technical explanations while keeping the same structure
4. Maintaining all technical details (CWE numbers, line numbers, function names)
5. The description should be a minimum of 2 lines

The vulnerability relates to this code:
```c
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
                model="gemma3:1b-it-qat",  # Use the preset model name
                messages=[
                    {"role": "user", "content": prompt}
                ],
                options={
                    "temperature": 0.3,
                    "num_predict": 512
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
            # On error, list available models for debugging
            try:
                models = ollama.list()
                logger.info(f"Available models: {models}")
            except Exception as list_err:
                logger.warning(f"Could not list models: {list_err}")
            time.sleep(2)

    # If all retries fail, keep the original entry
    logger.error(f"Failed to process entry after {max_retries} attempts - keeping original")
    return entry

def process_fragment():
    """Process the assigned fragment of the dataset."""
    logger.info(f"Worker {WORKER_ID} starting to process fragment {INPUT_FILE}")
    
    try:
        # Load fragment data
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
        
        # Process entries
        result_entries = []
        batch_size = 10  # Process in small batches and save progress
        
        for i in tqdm(range(0, len(entries), batch_size)):
            batch = entries[i:min(i+batch_size, len(entries))]
            batch_results = []
            
            for entry in batch:
                # Process each entry
                processed_entry = enhance_description(entry)
                batch_results.append(processed_entry)
                # Brief pause to avoid overwhelming Ollama
                time.sleep(0.1)
            
            # Add processed batch to results
            result_entries.extend(batch_results)
            
            # Save intermediate results
            if data_structure == "list":
                intermediate_data = result_entries
            elif data_structure == "dict_with_data":
                intermediate_data = data.copy()
                intermediate_data["data"] = result_entries
            elif data_structure == "dict_with_list":
                intermediate_data = data.copy()
                intermediate_data[list_field_name] = result_entries
            else:  # single_object
                intermediate_data = result_entries[0] if result_entries else {}
            
            with open(f"{OUTPUT_FILE}.temp", 'w') as f:
                json.dump(intermediate_data, f, indent=2)
            
            # Log progress
            processed = len(result_entries)
            total = len(entries)
            logger.info(f"Processed {processed}/{total} entries ({processed/total*100:.2f}%)")
        
        # Save final results with original structure
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
        
        logger.info(f"Processing completed. Results saved to {OUTPUT_FILE}")
        
    except Exception as e:
        logger.error(f"Error processing fragment: {e}")
        raise

def start_ollama_with_bash():
    """Start Ollama using the bash script."""
    logger.info("Starting Ollama using the bash script")
    
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
            # Verify we can connect using the Python library
            try:
                models = ollama.list()
                logger.info(f"Successfully connected to Ollama using Python library. Available models: {models}")
                return True
            except Exception as e:
                logger.warning(f"Bash script succeeded but Python library connection failed: {e}")
                return False
        else:
            logger.error(f"Bash script failed with return code {result.returncode}")
            return False
            
    except subprocess.CalledProcessError as e:
        logger.error(f"Error running bash script: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error starting Ollama: {e}")
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
