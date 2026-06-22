"""
Generate two test face images by capturing frames from the webcam.
- Press 'C' to capture the current frame.
- After two captures, both images are saved and the script exits.
- Press 'Q' to quit early.

If no webcam is available, falls back to upscaling the existing Tom_Hanks.png
and using t1.jpg directly (cropped to one face region).
"""

import os
import sys
import cv2
import numpy as np

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "watchlist")
PERSON_A = os.path.join(OUTPUT_DIR, "person_a.jpg")
PERSON_B = os.path.join(OUTPUT_DIR, "person_b.jpg")


def try_webcam_capture():
    """Attempt to capture two frames from webcam."""
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        return False

    print("Webcam opened. Press 'C' to capture a face, 'Q' to quit.")
    print("Capture two different face photos (e.g., your face, then a friend's or a photo on your phone).")
    captured = []

    while len(captured) < 2:
        ret, frame = cap.read()
        if not ret:
            break

        display = frame.copy()
        cv2.putText(display, f"Captured: {len(captured)}/2  |  Press C=capture, Q=quit",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.imshow("Capture Test Faces", display)

        key = cv2.waitKey(1) & 0xFF
        if key in (ord("c"), ord("C")):
            captured.append(frame.copy())
            print(f"  Captured frame {len(captured)}")
        elif key in (ord("q"), ord("Q")):
            break

    cap.release()
    cv2.destroyAllWindows()

    if len(captured) == 2:
        cv2.imwrite(PERSON_A, captured[0])
        cv2.imwrite(PERSON_B, captured[1])
        print(f"Saved: {PERSON_A}")
        print(f"Saved: {PERSON_B}")
        return True

    return False


def fallback_from_existing():
    """
    Use existing images in watchlist, upscaling Tom_Hanks.png to a usable
    resolution and cropping a single face from t1.jpg (Friends cast).
    """
    tom_path = os.path.join(OUTPUT_DIR, "Tom_Hanks.png")
    friends_path = os.path.join(OUTPUT_DIR, "t1.jpg")

    # --- Person A: Upscale Tom_Hanks.png from 112x112 to 512x512 ---
    if os.path.exists(tom_path):
        img = cv2.imread(tom_path)
        if img is not None:
            # Upscale with INTER_CUBIC for better quality
            upscaled = cv2.resize(img, (512, 512), interpolation=cv2.INTER_CUBIC)
            cv2.imwrite(PERSON_A, upscaled)
            print(f"Created person_a.jpg by upscaling Tom_Hanks.png to 512x512")
        else:
            print("Error: Could not read Tom_Hanks.png")
            return False
    else:
        print("Error: Tom_Hanks.png not found in watchlist.")
        return False

    # --- Person B: Crop a face region from the Friends group photo ---
    if os.path.exists(friends_path):
        img2 = cv2.imread(friends_path)
        if img2 is not None:
            h, w = img2.shape[:2]
            # Crop the center-left face area (approximate region of one person)
            # The Friends image is 1280x886, cropping the center person's face area
            cx, cy = int(w * 0.39), int(h * 0.28)
            crop_size = int(min(h, w) * 0.3)
            x1 = max(0, cx - crop_size // 2)
            y1 = max(0, cy - crop_size // 2)
            x2 = min(w, x1 + crop_size)
            y2 = min(h, y1 + crop_size)
            cropped = img2[y1:y2, x1:x2]
            # Resize to a reasonable detection size
            resized = cv2.resize(cropped, (512, 512), interpolation=cv2.INTER_CUBIC)
            cv2.imwrite(PERSON_B, resized)
            print(f"Created person_b.jpg by cropping a face from t1.jpg and resizing to 512x512")
        else:
            print("Error: Could not read t1.jpg")
            return False
    else:
        print("Error: t1.jpg not found in watchlist.")
        return False

    return True


if __name__ == "__main__":
    print("Attempting webcam capture for test images...")
    if not try_webcam_capture():
        print("Webcam not available or capture incomplete. Falling back to existing images.")
        if fallback_from_existing():
            print(f"\nTest images ready!")
            print(f"  Person A: {PERSON_A}")
            print(f"  Person B: {PERSON_B}")
            print(f"\nNow run:")
            print(f'  python test_phase2.py "{PERSON_A}" "{PERSON_B}"')
        else:
            print("Failed to create test images.")
            sys.exit(1)
    else:
        print(f"\nTest images ready!")
        print(f"  Person A: {PERSON_A}")
        print(f"  Person B: {PERSON_B}")
        print(f"\nNow run:")
        print(f'  python test_phase2.py "{PERSON_A}" "{PERSON_B}"')
