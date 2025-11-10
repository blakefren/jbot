import sys
import os
import runpy

# Add the 'src' directory to the Python path
src_dir = os.path.join(os.path.dirname(__file__), "src")
sys.path.insert(0, src_dir)

if __name__ == "__main__":
    # Run the main module from the src directory
    runpy.run_module("main", run_name="__main__")
