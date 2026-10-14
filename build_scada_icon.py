from PIL import Image, ImageOps

source = Image.open("SCADA_BONT_LOGO.jpg").convert("RGB")
crop = source.crop((280, 160, 1130, 610))
icon = Image.new("RGBA", (512, 512), (245, 249, 247, 255))
fit = ImageOps.contain(crop, (470, 330), Image.Resampling.LANCZOS).convert("RGBA")
icon.alpha_composite(fit, ((512 - fit.width) // 2, (512 - fit.height) // 2))
icon.save(
    "SCADA_BONT.ico",
    sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
)
