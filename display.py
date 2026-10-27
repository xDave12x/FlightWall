"""Output: the real LED panels, or a PNG/GIF preview that looks like them."""
from PIL import Image, ImageDraw


class MatrixDisplay:
    def __init__(self, cfg):
        from rgbmatrix import RGBMatrix, RGBMatrixOptions  # only exists on the Pi

        o = RGBMatrixOptions()
        panels = cfg.get("panels", 2)
        o.rows, o.cols, o.chain_length = 64, 64, panels
        o.hardware_mapping = cfg.get("hardware_mapping", "regular")
        o.gpio_slowdown = cfg.get("gpio_slowdown", 4)
        o.brightness = cfg.get("brightness", 60)
        o.drop_privileges = False
        for k in ("panel_type", "row_address_type", "multiplexing", "pwm_bits",
                  "pwm_lsb_nanoseconds", "limit_refresh_rate_hz"):
            if k in cfg:  # optional fine-tuning for panels with unusual driver chips
                setattr(o, k, cfg[k])
        mappers = []
        if panels == 2 and cfg.get("layout", "stacked") == "stacked":
            mappers.append("U-mapper")  # folds the 128x64 chain into 64x128 (one above the other)
        if mappers:
            o.pixel_mapper_config = ";".join(mappers)
        self.rotate = int(cfg.get("rotate", 0) or 0)  # done in Python; the library's Rotate mapper can crash
        self.matrix = RGBMatrix(options=o)
        self.canvas = self.matrix.CreateFrameCanvas()

    def show(self, img):
        if self.rotate:
            img = img.rotate(self.rotate, expand=True)
        self.canvas.SetImage(img.convert("RGB"))
        self.canvas = self.matrix.SwapOnVSync(self.canvas)


def led_preview(img, dot=7, gap_rows=(64,)):
    """Upscales a frame so each pixel looks like a round LED, with a seam between panels."""
    seam = dot
    w, h = img.width * dot, img.height * dot + seam * len([g for g in gap_rows if g < img.height])
    out = Image.new("RGB", (w + 2 * dot, h + 2 * dot), (14, 14, 16))
    d = ImageDraw.Draw(out)
    px = img.load()
    for y in range(img.height):
        yo = dot + y * dot + seam * sum(1 for g in gap_rows if y >= g)
        for x in range(img.width):
            c = px[x, y]
            lit = sum(c) > 30
            col = c if lit else (30, 30, 34)
            xo = dot + x * dot
            r = dot * 0.42 if lit else dot * 0.3
            cx, cy = xo + dot / 2, yo + dot / 2
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
    return out
