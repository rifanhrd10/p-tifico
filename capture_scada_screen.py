from pathlib import Path

import ctypes
from ctypes import wintypes

from PIL import Image


output = Path(r"C:\SCADA BONT V11\scada-current-screen.png")

user32 = ctypes.windll.user32
hwnd_target = None


@ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
def enum_window(hwnd, _):
    global hwnd_target
    if not user32.IsWindowVisible(hwnd):
        return True
    length = user32.GetWindowTextLengthW(hwnd)
    title = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, title, length + 1)
    if title.value.strip().upper() == "SCADA BONT":
        hwnd_target = hwnd
        return False
    return True


user32.EnumWindows(enum_window, 0)
if not hwnd_target:
    raise RuntimeError("SCADA BONT window was not found")

rect = wintypes.RECT()
user32.GetWindowRect(hwnd_target, ctypes.byref(rect))
width = rect.right - rect.left
height = rect.bottom - rect.top

gdi32 = ctypes.windll.gdi32
window_dc = user32.GetWindowDC(hwnd_target)
memory_dc = gdi32.CreateCompatibleDC(window_dc)
bitmap = gdi32.CreateCompatibleBitmap(window_dc, width, height)
old_bitmap = gdi32.SelectObject(memory_dc, bitmap)
user32.PrintWindow(hwnd_target, memory_dc, 2)

class BitmapInfoHeader(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]

header = BitmapInfoHeader()
header.biSize = ctypes.sizeof(BitmapInfoHeader)
header.biWidth = width
header.biHeight = -height
header.biPlanes = 1
header.biBitCount = 32
header.biCompression = 0
buffer = ctypes.create_string_buffer(width * height * 4)
gdi32.GetDIBits(memory_dc, bitmap, 0, height, buffer, ctypes.byref(header), 0)
Image.frombuffer("RGBA", (width, height), buffer, "raw", "BGRA", 0, 1).convert("RGB").save(output)

gdi32.SelectObject(memory_dc, old_bitmap)
gdi32.DeleteObject(bitmap)
gdi32.DeleteDC(memory_dc)
user32.ReleaseDC(hwnd_target, window_dc)
print(output)
