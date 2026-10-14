from pathlib import Path

from PIL import Image


image_path = Path(r"C:\SCADA BONT V11\RUNMONITORNEW.jpg")
backup_path = image_path.with_name("RUNMONITORNEW.before-center-line-removal.jpg")

if not backup_path.exists():
    backup_path.write_bytes(image_path.read_bytes())

image = Image.open(image_path).convert("RGB")
pixels = image.load()

# Central dashed divider occupies x=642..645 and ends above the lower diagram.
# Blend a narrow strip from untouched pixels on both sides to retain the
# original gray background gradient without altering nearby diagram elements.
x_left, x_right = 638, 649
y_end = 458
for y in range(min(y_end, image.height)):
    left = pixels[x_left, y]
    right = pixels[x_right, y]
    for x in range(x_left + 1, x_right):
        ratio = (x - x_left) / (x_right - x_left)
        pixels[x, y] = tuple(
            round(left[channel] * (1.0 - ratio) + right[channel] * ratio)
            for channel in range(3)
        )

image.save(image_path, quality=96, subsampling=0)
