import os

# Monkey-patch face_recognition_models to avoid pkg_resources dependency
# which is missing/broken in some Python 3.13 environments
try:
    import face_recognition_models
except ImportError:
    pass
except Exception:
    pass

# We create a fake module if it doesn't exist or is broken
import sys
import types

if "face_recognition_models" not in sys.modules:
    # Try to find where it is installed on disk manually if possible
    # This is a best-effort fallback
    pass

# Function to patch into the module
def _resource_filename(package_or_requirement, resource_name):
    # Assume the models are located relative to the site-packages/face_recognition_models directory
    # We find the module path from the already imported module or try to guess
    if "face_recognition_models" in sys.modules:
        mod = sys.modules["face_recognition_models"]
        if hasattr(mod, "__file__") and mod.__file__:
            base_dir = os.path.dirname(mod.__file__)
            return os.path.join(base_dir, resource_name)
    
    # Fallback: try to find in site-packages
    for path in sys.path:
        candidate = os.path.join(path, "face_recognition_models")
        if os.path.isdir(candidate):
            return os.path.join(candidate, resource_name)
            
    return resource_name

# Apply the patch if face_recognition_models failed to load due to pkg_resources
# or if we want to preemptively fix it.
try:
    import face_recognition_models
except ImportError as e:
    if "pkg_resources" in str(e) or "No module named 'pkg_resources'" in str(e):
        # Create a dummy module
        m = types.ModuleType("face_recognition_models")
        
        def pose_predictor_model_location():
            return _resource_filename("face_recognition_models", "models/shape_predictor_68_face_landmarks.dat")

        def pose_predictor_five_point_model_location():
            return _resource_filename("face_recognition_models", "models/shape_predictor_5_face_landmarks.dat")

        def face_recognition_model_location():
            return _resource_filename("face_recognition_models", "models/dlib_face_recognition_resnet_model_v1.dat")

        def cnn_face_detector_model_location():
            return _resource_filename("face_recognition_models", "models/mmod_human_face_detector.dat")
            
        m.pose_predictor_model_location = pose_predictor_model_location
        m.pose_predictor_five_point_model_location = pose_predictor_five_point_model_location
        m.face_recognition_model_location = face_recognition_model_location
        m.cnn_face_detector_model_location = cnn_face_detector_model_location
        
        sys.modules["face_recognition_models"] = m
        print("[Face Rec Patch] Patched face_recognition_models to bypass pkg_resources.", flush=True)

