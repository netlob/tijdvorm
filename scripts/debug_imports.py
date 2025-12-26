import sys
import os

print(f"Python executable: {sys.executable}")
print(f"Python version: {sys.version}")
print(f"Sys path: {sys.path}")

print("\n--- Attempting to import face_recognition_models ---")
try:
    import face_recognition_models
    print(f"SUCCESS: face_recognition_models is imported from {face_recognition_models.__file__}")
except Exception as e:
    print(f"FAILURE: Could not import face_recognition_models. Error: {e}")

print("\n--- Attempting to import face_recognition ---")
try:
    import face_recognition
    print("SUCCESS: face_recognition imported.")
except SystemExit:
    print("FAILURE: face_recognition called quit() or sys.exit(). This likely means it couldn't find the models.")
except Exception as e:
    print(f"FAILURE: Could not import face_recognition. Error: {e}")

