from ollama import Client
import mss
from PIL import Image
from datetime import datetime

# 1) Capture the clock region
def capture_clock_screenshot(path="examples/visual_language_model/pictures/clock.png"
                             , monitor_index=0):
    with mss.mss() as sct:
        # 0 = all monitors; 1 = first monitor; 2 = second monitor; etc.
        monitor = sct.monitors[monitor_index]
        sct_img = sct.grab(monitor)
        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
        img.save(path)
    return path

# 2) Ask the VLM to read it
def ask_clock_time(image_path):
    client = Client()  # no host/port args
    response = client.generate(
        model="llama3.2-vision",
        prompt="What time is displayed on the game clock in this image near the tnt symbol?",
        images=[ image_path ]          # <-- plural key
    )
    # the response text can come back as "response" or "text"
    return response.get("response") or response.get("text")

if __name__ == "__main__":
    img_path = capture_clock_screenshot(monitor_index=0)
    detected = ask_clock_time(img_path)
    print(f"{datetime.now().isoformat()}: Detected clock time → {detected}")
