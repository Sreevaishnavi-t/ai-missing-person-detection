import os
import sys

import cv2

# Add the project root to Python's import path so backend/ can be imported.
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.embedder import detect_faces


def main():
    # cv2.VideoCapture(0) opens the default camera, usually the built-in webcam.
    cap = cv2.VideoCapture(0)

    # Stop early if OpenCV cannot connect to the webcam.
    if not cap.isOpened():
        print("Error: Could not open webcam.")
        sys.exit(1)

    print("Starting webcam stream... Press 'Q' to exit.")

    try:
        # Keep reading frames until the camera fails or the user presses Q.
        while True:
            # cap.read() returns a success flag and the current frame in BGR format.
            ret, frame = cap.read()
            if not ret:
                print("Failed to grab frame.")
                break

            # detect_faces() returns one InsightFace Face object for each detected face.
            faces = detect_faces(frame)

            # Handle every detected face in the current frame.
            for face in faces:
                print("Face detected!")

                # face.bbox stores [x_min, y_min, x_max, y_max] as numbers.
                x1, y1, x2, y2 = face.bbox.astype(int)

                # Draw a green rectangle around the face on the frame we will display.
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

            # Show the live webcam frame with any face boxes drawn on it.
            cv2.imshow("Webcam", frame)

            # waitKey(1) refreshes the window and captures a key press if one happened.
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), ord("Q")):
                print("Exiting...")
                break
    finally:
        # Always release the webcam, even if detection or display raises an error.
        cap.release()

        # Close any OpenCV windows opened by this script.
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
