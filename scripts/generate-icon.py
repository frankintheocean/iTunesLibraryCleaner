"""Generate the flat OLED-black app icon used by Windows and Electron builds."""
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "resources" / "app.ico"
SIZE = 512
image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((16, 16, 496, 496), radius=104, fill="#000000")
# Flat, saturated equalizer bars; no gloss, gradients, or reflective highlights.
for box, color in [
    ((108, 212, 150, 357), "#00D8C9"),
    ((166, 155, 208, 357), "#00BDEB"),
    ((224, 112, 266, 357), "#087CF0"),
    ((282, 167, 324, 357), "#1266E8"),
    ((340, 220, 382, 357), "#20D6D0"),
]:
    draw.rounded_rectangle(box, radius=21, fill=color)
# Matte vinyl disc with clean, silver-grey grooves.
draw.ellipse((178, 246, 356, 424), fill="#050505", outline="#AAB4C4", width=5)
draw.ellipse((197, 265, 337, 405), outline="#E1E5EA", width=5)
draw.ellipse((213, 281, 321, 389), fill="#C9D0DA")
draw.ellipse((255, 323, 279, 347), fill="#000000")
# A simple silver eighth-note mark over the lower-right of the disc.
draw.line((329, 248, 329, 348), fill="#F3F5F7", width=16)
draw.line((329, 248, 383, 235), fill="#F3F5F7", width=16)
draw.line((383, 235, 383, 324), fill="#F3F5F7", width=16)
draw.ellipse((292, 333, 342, 383), fill="#F3F5F7")
draw.ellipse((346, 309, 396, 359), fill="#F3F5F7")
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
image.save(OUTPUT, format="ICO", sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)])
expected_sizes = {(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)}
with Image.open(OUTPUT) as check:
    available_sizes = set(check.ico.sizes()) if check.format == "ICO" else set()
    if check.format != "ICO" or not expected_sizes.issubset(available_sizes):
        raise SystemExit(f"Generated app icon failed size validation: {sorted(available_sizes)}")
    for dimensions in expected_sizes:
        variant = check.ico.getimage(dimensions)
        variant.load()
        if variant.size != dimensions or variant.mode not in {"RGBA", "RGB"}:
            raise SystemExit(f"Generated app icon variant failed validation: {dimensions}")
if OUTPUT.stat().st_size < 1024:
    raise SystemExit("Generated app icon is unexpectedly small.")
print(f"Generated and validated {OUTPUT} with sizes {sorted(expected_sizes)} ({OUTPUT.stat().st_size} bytes)")
