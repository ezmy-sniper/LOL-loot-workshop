"""Generate an original multi-resolution Windows icon with only the standard library."""
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from loot_workshop.theme import icon_pixels

images = []
for size in (16, 32, 48, 64, 128):
    pixels = icon_pixels(size)
    bitmap = b''.join(bytes((b, g, r, a)) for row in reversed(pixels) for r, g, b, a in row)
    mask_width = (size + 31) // 32 * 4
    mask = bytes(mask_width * size)
    header = struct.pack('<IiiHHIIiiII', 40, size, size * 2, 1, 32, 0, len(bitmap), 0, 0, 0, 0)
    images.append((size, header + bitmap + mask))
offset = 6 + 16 * len(images)
entries = []
for size, data in images:
    entries.append(struct.pack('<BBBBHHII', size, size, 0, 0, 1, 32, len(data), offset))
    offset += len(data)
dest = Path(__file__).resolve().parents[1] / 'assets' / 'workshop.ico'
dest.parent.mkdir(exist_ok=True)
dest.write_bytes(struct.pack('<HHH', 0, 1, len(images)) + b''.join(entries) + b''.join(data for _, data in images))
print('Generated assets/workshop.ico')
