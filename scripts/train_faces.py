import os
import face_recognition
import pickle
import sys

# Hack: Append project root to sys.path if running as script
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tijdvorm.config import FACES_DIR, ENCODINGS_FILE

def train_faces():
    """Loads images from faces/ directory and saves encodings to a pickle file."""
    print("[Training] Starting...", flush=True)
    encodings = []
    names = []
    
    if not os.path.exists(FACES_DIR):
        print(f"[Training] Error: Faces directory not found: {FACES_DIR}")
        return

    # Walk through the directory structure
    for person_name in os.listdir(FACES_DIR):
        person_dir = os.path.join(FACES_DIR, person_name)
        if not os.path.isdir(person_dir):
            continue
        
        print(f"[Training] Processing {person_name}...", flush=True)
        count = 0
        
        for filename in os.listdir(person_dir):
            if not filename.lower().endswith(('.jpg', '.jpeg', '.png')):
                continue
            
            image_path = os.path.join(person_dir, filename)
            try:
                image = face_recognition.load_image_file(image_path)
                face_encodings = face_recognition.face_encodings(image)
                
                if len(face_encodings) > 0:
                    # We only take the first face found in the image
                    encodings.append(face_encodings[0])
                    names.append(person_name)
                    count += 1
                else:
                    print(f"  [Warning] No face found in {filename}", flush=True)
            except Exception as e:
                print(f"  [Error] Failed to process {filename}: {e}", flush=True)
        
        print(f"  -> Added {count} faces for {person_name}")

    # Save to pickle
    print(f"[Training] Saving {len(names)} encodings to {ENCODINGS_FILE}...", flush=True)
    data = {"encodings": encodings, "names": names}
    try:
        with open(ENCODINGS_FILE, "wb") as f:
            pickle.dump(data, f)
        print("[Training] Done.", flush=True)
    except Exception as e:
        print(f"[Training] Error saving encodings file: {e}")

if __name__ == "__main__":
    train_faces()
