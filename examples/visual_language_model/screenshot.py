import mss, numpy as np
from PIL import Image

with mss.mss() as sct:
    monitor = {"top": 100, "left": 200, "width": 250, "height": 80}  # adjust these
    sct_img = sct.grab(monitor)
    img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
    img.save("examples/visual_language_model/pictures/clock.png")
