import os
import sys
import cv2
import numpy as np

# Add the project root to Python's import path so backend/ can be imported.
# __file__ is 'test_phase2.py'. dirname(abspath(__file__)) gets the directory path.
# Appending this to sys.path lets us do 'from backend.xxx import yyy'.
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import embedding extraction and FAISS store helper classes
from backend.embedder import detect_faces, get_embedding
from backend.faiss_store import FAISSStore
from backend.config import DB_PATH

def main():
    """
    Main entrypoint to verify FAISS vector storage, persistence, and similarity matching.
    """
    # 1. Parse command-line arguments to obtain image paths
    # We require two command-line arguments: image1 (reference) and image2 (probe of a different person)
    if len(sys.argv) < 3:
        print("Usage: python test_phase2.py <path_to_image_1> <path_to_image_2>")
        print("Please provide paths to two image files (representing two different people).")
        sys.exit(1)

    img1_path = sys.argv[1]
    img2_path = sys.argv[2]

    # 2. Check if the provided image files exist
    if not os.path.exists(img1_path):
        print(f"Error: Image 1 file does not exist at: {img1_path}")
        sys.exit(1)
    if not os.path.exists(img2_path):
        print(f"Error: Image 2 file does not exist at: {img2_path}")
        sys.exit(1)

    # 3. Read image files using OpenCV
    # OpenCV imread loads images in BGR format, which is the exact format expected by detect_faces()
    print(f"Loading Image 1 from: {img1_path}")
    img1 = cv2.imread(img1_path)
    if img1 is None:
        print(f"Error: Failed to read image from {img1_path}")
        sys.exit(1)

    print(f"Loading Image 2 from: {img2_path}")
    img2 = cv2.imread(img2_path)
    if img2 is None:
        print(f"Error: Failed to read image from {img2_path}")
        sys.exit(1)

    # 4. Detect faces and extract 512-d embedding for Image 1 (Reference Person)
    print("\nDetecting faces in Image 1...")
    faces1 = detect_faces(img1)
    if not faces1:
        print("Error: No faces detected in Image 1. Please use an image containing a clear face.")
        sys.exit(1)
    
    # We take the first detected face object in Image 1
    face1 = faces1[0]
    try:
        # get_embedding extracts the 512-d ArcFace vector
        emb1 = get_embedding(face1)
        print("Successfully extracted 512-d embedding for Image 1.")
    except Exception as e:
        print(f"Error extracting embedding from Image 1: {e}")
        sys.exit(1)

    # 5. Detect faces and extract 512-d embedding for Image 2 (Different Person)
    # If the user passed the same image path and the image contains multiple faces,
    # we use the second face for the different-person test case.
    if img1_path == img2_path and len(faces1) > 1:
        print("\nNote: Same image path provided for both arguments. Using the second detected face in Image 1 for the different-person test case.")
        face2 = faces1[1]
        try:
            emb2 = get_embedding(face2)
            print("Successfully extracted 512-d embedding for face 2 in the same image.")
        except Exception as e:
            print(f"Error extracting embedding from face 2: {e}")
            sys.exit(1)
    else:
        print("\nDetecting faces in Image 2...")
        faces2 = detect_faces(img2)
        if not faces2:
            print("Error: No faces detected in Image 2. Please use an image containing a clear face.")
            sys.exit(1)
        
        # We take the first detected face object in Image 2
        face2 = faces2[0]
        try:
            emb2 = get_embedding(face2)
            print("Successfully extracted 512-d embedding for Image 2.")
        except Exception as e:
            print(f"Error extracting embedding from Image 2: {e}")
            sys.exit(1)

    # 6. Initialize the FAISS store wrapper
    print("\nInitializing FAISS Store...")
    store = FAISSStore()

    # 7. Enroll Image 1 (Reference) into the vector store as "Test Person"
    print("Enrolling Image 1 as 'Test Person'...")
    store.add("Test Person", emb1)
    print(f"FAISS index now contains {store.index.ntotal} registered item.")

    # 8. Save the index and names metadata to disk to verify serialization
    print(f"Saving FAISS index and metadata files to: {DB_PATH}")
    store.save_index(DB_PATH)

    # 9. Reload the index and names metadata from disk to verify deserialization
    print("Reloading FAISS index and metadata from disk...")
    new_store = FAISSStore()
    new_store.load_index(DB_PATH)
    print(f"Successfully loaded index containing {new_store.index.ntotal} items.")

    # 10. Test Case A: Same Person match check (Threshold should be > 0.7)
    # We search the reloaded index using the embedding of Image 1 itself.
    # Since Image 1 is the exact same face we enrolled, the cosine similarity should be 1.0 (or ~0.9999 due to float precision).
    # Since 1.0 > 0.7, this will pass.
    print("\n--- Running Test Case A (Same Person) ---")
    results_a = new_store.search(emb1, top_k=1)
    if results_a:
        name_a, score_a = results_a[0]
        print(f"Match result: Enrolled Person = '{name_a}', Similarity Score = {score_a:.4f}")
        if score_a > 0.7:
            print("SUCCESS: Test Case A passed! Similarity is > 0.7.")
        else:
            print(f"FAILURE: Test Case A failed. Similarity score {score_a:.4f} is not > 0.7.")
    else:
        print("FAILURE: Search returned no match for Test Case A.")

    # 11. Test Case B: Different Person match check (Threshold should be < 0.4)
    # We search the index using the embedding of Image 2 (different person).
    # Since only "Test Person" is in the database, FAISS will return "Test Person",
    # but the similarity score should be low because their faces are different.
    # We verify that this similarity score is < 0.4.
    print("\n--- Running Test Case B (Different Person) ---")
    results_b = new_store.search(emb2, top_k=1)
    if results_b:
        name_b, score_b = results_b[0]
        print(f"Match result: Closest Match = '{name_b}', Similarity Score = {score_b:.4f}")
        if score_b < 0.4:
            print("SUCCESS: Test Case B passed! Similarity is < 0.4.")
        else:
            print(f"FAILURE: Test Case B failed. Similarity score {score_b:.4f} is not < 0.4.")
            print("Note: If the two face photos look extremely similar or are bad quality, the score could be higher.")
    else:
        print("FAILURE: Search returned no match for Test Case B.")

if __name__ == "__main__":
    main()
