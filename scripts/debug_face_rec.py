import os
import face_recognition
import numpy as np
import pickle
from PIL import Image, ImageDraw, ImageFont
import sys

# Configuration
FACES_DIR = os.path.abspath("../faces")
ENCODINGS_FILE = os.path.abspath("../face_encodings.pickle")
INPUT_FILE = "./IMG_3012.JPG"
OUTPUT_FILE = INPUT_FILE.replace(".JPG", "_output.JPG")

# Target Dimensions (Same as server.py)
TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920

def load_known_faces():
    """Loads face encodings from pickle file."""
    print("[Debug] Loading known faces...", flush=True)
    encodings = []
    names = []
    
    if os.path.exists(ENCODINGS_FILE):
        try:
            with open(ENCODINGS_FILE, "rb") as f:
                data = pickle.load(f)
            encodings = data["encodings"]
            names = data["names"]
            print(f"[Debug] Loaded {len(names)} faces from cache.", flush=True)
        except Exception as e:
            print(f"[Debug] Failed to load cache: {e}", flush=True)
    else:
        print("[Debug] No cache found. Please run 'python train_faces.py'.", flush=True)

    return encodings, names

def process_image():
    if not os.path.exists(INPUT_FILE):
        print(f"Error: Input file '{INPUT_FILE}' not found. Please place a snapshot there.")
        return

    known_encodings, known_names = load_known_faces()
    
    print(f"[Debug] Processing {INPUT_FILE}...", flush=True)
    try:
        img = Image.open(INPUT_FILE)
        
        # 1. Resize to fill height
        original_width, original_height = img.size
        ratio = TARGET_HEIGHT / original_height
        new_width = int(original_width * ratio)
        new_height = TARGET_HEIGHT
        
        print(f"[Debug] Resizing from {original_width}x{original_height} to {new_width}x{new_height}")
        img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # 2. Crop to 1080 width, aligned center
        print(f"[Debug] Cropping to {TARGET_WIDTH}x{TARGET_HEIGHT} (Center)")
        left_offset = (new_width - TARGET_WIDTH) // 2
        img_cropped = img_resized.crop((left_offset, 0, left_offset + TARGET_WIDTH, TARGET_HEIGHT))
        
        # 3. Detect Faces
        print("[Debug] Detecting faces...")
        # Convert PIL to numpy array (RGB)
        img_np = np.array(img_cropped)
        
        # Optimization: Resize for detection (1/4 size)
        small_frame = np.ascontiguousarray(img_np[::4, ::4])
        
        # Find faces
        face_locations = face_recognition.face_locations(small_frame)
        face_encodings = face_recognition.face_encodings(small_frame, face_locations)
        
        print(f"[Debug] Found {len(face_locations)} faces.")
        
        # Draw on image
        draw = ImageDraw.Draw(img_cropped)
        try:
            font = ImageFont.truetype("./fonts/Inter-Regular.otf", 40)
        except:
            font = ImageFont.load_default()

        for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
            # Check matches
            matches = face_recognition.compare_faces(known_encodings, face_encoding, tolerance=0.6)
            name = "Unknown"
            
            if True in matches:
                first_match_index = matches.index(True)
                name = known_names[first_match_index]
                print(f"[Debug] Recognized: {name}")
            else:
                print(f"[Debug] Face detected but unknown")

            # Scale back up by 4
            top *= 4
            right *= 4
            bottom *= 4
            left *= 4
            
            # Draw box
            color = (0, 255, 0) if name != "Unknown" else (255, 0, 0)
            draw.rectangle(((left, top), (right, bottom)), outline=color, width=5)
            
            # Draw text
            text_bbox = draw.textbbox((left, bottom), name, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]
            draw.rectangle(((left, bottom), (left + text_width + 10, bottom + text_height + 10)), fill=color, outline=color)
            draw.text((left + 5, bottom + 5), name, fill=(255, 255, 255, 255), font=font)

        # Save
        img_cropped.save(OUTPUT_FILE)
        print(f"[Debug] Saved result to {OUTPUT_FILE}")
        
    except Exception as e:
        print(f"[Debug] Error processing image: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    process_image()
