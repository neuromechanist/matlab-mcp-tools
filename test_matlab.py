import os
import sys
import traceback

print("=== MATLAB Test Script ===")
print(f"MATLAB_PATH: {os.getenv('MATLAB_PATH', 'Not set')}")
print(f"Python executable: {sys.executable}")
print(f"Python path: {sys.path}")
print("\nAttempting to import matlab.engine...")

try:
    import matlab.engine
    print(f"matlab.engine imported successfully")
    print(f"matlab.engine path: {matlab.engine.__file__}")
except Exception as e:
    print(f"Error importing matlab.engine: {str(e)}")
    print("\nFull traceback:")
    traceback.print_exc()
    sys.exit(1)

try:
    print("\nChecking MATLAB installation...")
    matlab_root = os.getenv('MATLAB_PATH', '/Applications/MATLAB_R2024b.app')
    print(f"MATLAB root directory exists: {os.path.exists(matlab_root)}")

    engine_dir = os.path.join(matlab_root, 'extern/engines/python')
    print(f"MATLAB engine directory exists: {os.path.exists(engine_dir)}")

    print("\nSearching for MATLAB sessions...")
    try:
        sessions = matlab.engine.find_matlab()
        print(f"Found sessions: {sessions}")
    except Exception as e:
        print(f"Error finding MATLAB sessions: {str(e)}")
        sessions = []

    print("\nStarting MATLAB engine...")
    try:
        eng = matlab.engine.start_matlab()
    except Exception as e:
        print(f"Error starting MATLAB engine: {str(e)}")
        print("\nFull traceback:")
        traceback.print_exc()
        sys.exit(1)

    if eng is not None:
        print("MATLAB engine started successfully")
        ver = eng.version()
        print(f"MATLAB version: {ver}")

        print("\nTesting basic computation...")
        result = eng.sqrt(4.0)
        print(f"sqrt(4) = {result}")

        print("\nClosing MATLAB engine...")
        eng.quit()
        print("Engine closed successfully")
    else:
        print("Failed to start MATLAB engine (returned None)")
except Exception as e:
    print(f"\nError: {str(e)}")
    raise
