import os
import json
from pathlib import Path
import numpy as np
import faiss

class FAISSStore:
    def __init__(self, dimension: int = 512):
        """
        Initializes the FAISS vector database store.
        
        Args:
            dimension (int): The dimensions of the vector embeddings. ArcFace model uses 512 dimensions.
            
        === EXPLANATION: IndexFlatIP vs IndexFlatL2 ===
        - IndexFlatL2 uses Euclidean distance (L2 distance), which measures the straight line distance
          between two points in the 512-dimensional space. The distance is unbounded (>= 0) and lower is better.
        - IndexFlatIP uses Inner Product (IP) or dot product. When we scale (normalize) the input vectors
          to have an L2 norm of 1.0, the Inner Product matches Cosine Similarity exactly.
        - We prefer IndexFlatIP because:
          1. Face matching thresholds are conventionally set using Cosine Similarity (a score between -1.0 and 1.0).
          2. It is highly intuitive: a score closer to 1.0 means high similarity, while lower means different.
          3. L2 distance can scale infinitely depending on the vector norms, making thresholding harder.
        """
        self.dimension = dimension
        
        # We use Flat index because it is a brute-force exact search. At smaller scales (<100k vectors),
        # it is extremely fast and guarantees 100% search accuracy (no approximations).
        self.index = faiss.IndexFlatIP(self.dimension)
        
        # FAISS indexes only store vectors and assign sequential integer IDs (0, 1, 2, ...).
        # We maintain a separate list to map FAISS IDs back to human-readable names.
        # self.names[i] maps directly to the vector stored at index location i.
        self.names = []

    def add(self, name: str, embedding: np.ndarray):
        """
        Adds a person's name and their face embedding vector to the FAISS index watchlist.
        
        Args:
            name (str): The name/identity of the person.
            embedding (np.ndarray): The 512-d ArcFace embedding vector.
        """
        # Ensure the embedding is a 2D numpy array of type float32 with shape (1, 512)
        emb = np.asarray(embedding, dtype=np.float32).reshape(1, -1)
        
        # === EXPLANATION: Why we normalize embeddings before adding them ===
        # Cosine Similarity is defined as: (A . B) / (||A|| * ||B||).
        # If we normalize the vectors first so that their lengths (norms ||A|| and ||B||) are exactly 1.0:
        # Cosine Similarity simplifies to just (A . B) — which is the Inner Product!
        # Normalizing during insertion allows FAISS to skip computing vector lengths and divisions
        # during query time, reducing similarity search to pure dot-product matrix multiplication.
        # This yields a massive performance speedup.
        faiss.normalize_L2(emb)
        
        # Add the normalized embedding to the flat index
        self.index.add(emb)
        
        # Maintain the parallel index-to-name mapping
        self.names.append(name)

    def search(self, embedding: np.ndarray, top_k: int = 1) -> list:
        """
        Searches the FAISS index for the closest matching face embeddings.
        
        Args:
            embedding (np.ndarray): The query face embedding (512-d).
            top_k (int): Number of top matches to retrieve.
            
        Returns:
            list: A list of tuples containing [(name, confidence_score), ...] sorted descending by score.
            
        === EXPLANATION: Cosine Similarity & Higher Score Meaning ===
        - Cosine similarity measures the cosine of the angle between two vectors in a high-dimensional space.
        - If two vectors are pointing in the exact same direction, the angle is 0, and cos(0) = 1.0 (perfect match).
        - If the vectors are perpendicular, the angle is 90 degrees, and cos(90) = 0.0 (unrelated).
        - If they point in opposite directions, the angle is 180 degrees, and cos(180) = -1.0.
        - Therefore, a higher score (closer to 1.0) indicates that the vectors are highly aligned, meaning
          the faces have extremely similar characteristics (representing the same individual).
          
        === EXPLANATION: What top_k means and when to use top_k > 1 ===
        - top_k specifies the number of nearest-neighbor results we want the search to return.
        - We use top_k > 1 in scenarios such as:
          1. **Multiple Reference Images**: If a watchlist has multiple photos for the same person
             (e.g., front view, side profile, different lighting), returning top_k > 1 lets us retrieve
             multiple instances to verify the match robustness.
          2. **Candidate Review List**: For human-in-the-loop systems, we can present the top 5 matches
             to a security officer to let them make the final identification decision.
          3. **Voter-based Classification**: If 4 out of 5 of the top matches point to the same person,
             we can be much more confident in our final recognition classification.
        """
        # If the index has no registered vectors, return empty results
        if self.index.ntotal == 0:
            return []

        # We cannot request more items than the total currently enrolled in the index
        actual_k = min(top_k, self.index.ntotal)
        
        # Format the query embedding to shape (1, 512) and type float32
        emb = np.asarray(embedding, dtype=np.float32).reshape(1, -1)
        
        # Normalize the query embedding so the inner product equals cosine similarity
        faiss.normalize_L2(emb)
        
        # Perform the vector search.
        # - D: array of shape (1, actual_k) containing similarity scores (inner products / cosine similarities)
        # - I: array of shape (1, actual_k) containing the corresponding FAISS indices
        D, I = self.index.search(emb, actual_k)
        
        # Map FAISS search output indices to names and confidence scores
        results = [(self.names[idx], float(score)) for score, idx in zip(D[0], I[0]) if idx != -1]
        
        return results

    def save_index(self, path: str):
        """
        Saves the FAISS index binary and the names metadata mapping to disk.
        
        Args:
            path (str): File path for the FAISS binary file (e.g., 'data/db/faiss_index.bin').
        """
        p = Path(path)
        # Ensure the directories leading to the path exist
        p.parent.mkdir(parents=True, exist_ok=True)
        
        # Write the FAISS binary index
        faiss.write_index(self.index, str(p))
        
        # Write the list of names matching the FAISS indices as a JSON file at the same location
        names_path = p.with_suffix(".json")
        with open(names_path, "w", encoding="utf-8") as f:
            json.dump(self.names, f, indent=4)

    def load_index(self, path: str):
        """
        Loads the FAISS index binary and the names metadata mapping from disk.
        
        Args:
            path (str): File path for the FAISS binary file.
        """
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"FAISS index file not found at: {path}")
            
        # Read the FAISS binary index
        self.index = faiss.read_index(str(p))
        
        # Read the list of names matching the FAISS indices
        names_path = p.with_suffix(".json")
        if not names_path.exists():
            raise FileNotFoundError(f"Name mapping metadata file not found at: {names_path}")
            
        with open(names_path, "r", encoding="utf-8") as f:
            self.names = json.load(f)
