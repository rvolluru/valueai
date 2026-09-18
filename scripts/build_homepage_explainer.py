from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[1]
MEDIA_DIR = ROOT / "apps" / "web" / "public" / "media" / "how-it-works"
OUTPUT_PATH = MEDIA_DIR / "jouft-how-it-works.mp4"
POSTER_PATH = MEDIA_DIR / "jouft-how-it-works-poster.jpg"
LOGO_PATH = ROOT / "apps" / "web" / "src" / "assets" / "jouft-logo.png"

WIDTH, HEIGHT = 1280, 720
FPS = 30
BURGUNDY = (88, 22, 31)
IVORY = (247, 244, 238)
CHARCOAL = (29, 25, 25)
MUTED = (106, 96, 91)
GOLD = (176, 145, 92)

DISPLAY_FONT = "/System/Library/Fonts/Supplemental/Didot.ttc"
BODY_FONT = "/System/Library/Fonts/Avenir Next.ttc"

SCENES = [
    {
        "image": "01-upload.png",
        "eyebrow": "01  CREATE YOUR LISTING",
        "title": "Capture every angle.",
        "body": "Upload clear photos and a few item details.\nJOUFT guides you toward the shots that matter.",
        "align": "left",
    },
    {
        "image": "02-analysis.png",
        "eyebrow": "02  AI-ASSISTED ANALYSIS",
        "title": "Know what you have.",
        "body": "JOUFT identifies the item, reviews condition,\nand estimates a patient trade-market value.",
        "align": "right",
    },
    {
        "image": "03-match.png",
        "eyebrow": "03  VALUE-ALIGNED DISCOVERY",
        "title": "Find a worthy exchange.",
        "body": "Explore desirable pieces matched by value,\nthen offer one or more items as trade choices.",
        "align": "center",
    },
    {
        "image": "04-trade-ship.png",
        "eyebrow": "04  ACCEPT, SHIP, TRACK",
        "title": "Trade with clarity.",
        "body": "Review shipping costs before accepting.\nBoth members receive labels and tracking updates.",
        "align": "left",
    },
]


def font(path: str, size: int, index: int = 0) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size=size, index=index)


DISPLAY_LARGE = font(DISPLAY_FONT, 62)
DISPLAY_MEDIUM = font(DISPLAY_FONT, 52)
BODY = font(BODY_FONT, 24)
BODY_SMALL = font(BODY_FONT, 18)
EYEBROW = font(BODY_FONT, 16)


def smoothstep(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def contain_logo(max_width: int) -> Image.Image:
    logo = Image.open(LOGO_PATH).convert("RGBA")
    ratio = max_width / logo.width
    return logo.resize((max_width, int(logo.height * ratio)), Image.Resampling.LANCZOS)


def draw_tracking(draw: ImageDraw.ImageDraw, current: float, total: float) -> None:
    y = HEIGHT - 8
    draw.rectangle((0, y, WIDTH, HEIGHT), fill=(255, 255, 255, 80))
    draw.rectangle((0, y, int(WIDTH * current / total), HEIGHT), fill=GOLD + (255,))


def draw_intro(progress: float) -> Image.Image:
    canvas = Image.new("RGBA", (WIDTH, HEIGHT), IVORY + (255,))
    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.rectangle((0, 0, WIDTH, 10), fill=BURGUNDY + (255,))
    logo = contain_logo(470)
    canvas.alpha_composite(logo, ((WIDTH - logo.width) // 2, 194))
    opacity = int(255 * smoothstep(min(1.0, progress * 2.0)))
    caption = "TRADE  ·  ELEVATE  ·  BELONG."
    box = draw.textbbox((0, 0), caption, font=EYEBROW)
    draw.text(((WIDTH - (box[2] - box[0])) / 2, 145), caption, font=EYEBROW, fill=BURGUNDY + (opacity,))
    title = "Luxury deserves a second story."
    title_box = draw.textbbox((0, 0), title, font=DISPLAY_MEDIUM)
    draw.text(((WIDTH - (title_box[2] - title_box[0])) / 2, 394), title, font=DISPLAY_MEDIUM, fill=CHARCOAL + (opacity,))
    body = "See how JOUFT turns pieces you own into pieces you love."
    body_box = draw.textbbox((0, 0), body, font=BODY)
    draw.text(((WIDTH - (body_box[2] - body_box[0])) / 2, 478), body, font=BODY, fill=MUTED + (opacity,))
    return canvas


def scene_background(image: Image.Image, progress: float) -> Image.Image:
    zoom = 1.0 + (0.035 * smoothstep(progress))
    crop_w = int(image.width / zoom)
    crop_h = int(image.height / zoom)
    drift = int((image.width - crop_w) * (progress - 0.5) * 0.5)
    left = max(0, min(image.width - crop_w, (image.width - crop_w) // 2 + drift))
    top = max(0, (image.height - crop_h) // 2)
    crop = image.crop((left, top, left + crop_w, top + crop_h))
    return ImageOps.fit(crop, (WIDTH, HEIGHT), method=Image.Resampling.LANCZOS).convert("RGBA")


def make_readability_gradient(align: str) -> Image.Image:
    x = np.arange(WIDTH, dtype=np.float32)
    y = np.arange(HEIGHT, dtype=np.float32)
    if align == "left":
        horizontal = 195.0 * np.maximum(0.0, 1.0 - x / 720.0)
    elif align == "right":
        horizontal = 190.0 * np.maximum(0.0, (x - 540.0) / 740.0)
    else:
        horizontal = 105.0 * np.maximum(0.0, 1.0 - np.abs(x - WIDTH / 2) / (WIDTH / 2))
    vertical = 0.80 + 0.20 * (y / HEIGHT)
    alpha = np.outer(vertical, horizontal).clip(0, 255).astype(np.uint8)
    overlay = np.empty((HEIGHT, WIDTH, 4), dtype=np.uint8)
    overlay[:, :, :3] = (18, 12, 12)
    overlay[:, :, 3] = alpha
    return Image.fromarray(overlay, "RGBA")


READABILITY_GRADIENTS = {align: make_readability_gradient(align) for align in ("left", "right", "center")}


def add_readability_gradient(canvas: Image.Image, align: str) -> None:
    canvas.alpha_composite(READABILITY_GRADIENTS[align])


def draw_scene(scene: dict[str, str], source: Image.Image, progress: float) -> Image.Image:
    canvas = scene_background(source, progress)
    add_readability_gradient(canvas, scene["align"])
    draw = ImageDraw.Draw(canvas, "RGBA")
    fade = smoothstep(min(1.0, progress * 3.0))
    text_alpha = int(255 * fade)
    if scene["align"] == "right":
        x, anchor = 1190, "ra"
    elif scene["align"] == "center":
        x, anchor = WIDTH // 2, "ma"
    else:
        x, anchor = 82, "la"
    y = 214
    draw.text((x, y), scene["eyebrow"], font=EYEBROW, anchor=anchor, fill=(245, 224, 191, text_alpha))
    draw.text((x, y + 48), scene["title"], font=DISPLAY_LARGE, anchor=anchor, fill=(255, 252, 247, text_alpha))
    for index, line in enumerate(scene["body"].splitlines()):
        draw.text((x, y + 142 + index * 35), line, font=BODY, anchor=anchor, fill=(245, 241, 234, text_alpha))
    return canvas


def draw_outro(progress: float) -> Image.Image:
    canvas = Image.new("RGBA", (WIDTH, HEIGHT), BURGUNDY + (255,))
    draw = ImageDraw.Draw(canvas, "RGBA")
    logo = contain_logo(430)
    # The logo is burgundy, so place it on an ivory lockup for contrast.
    lockup = Image.new("RGBA", (logo.width + 100, logo.height + 70), IVORY + (255,))
    lockup.alpha_composite(logo, (50, 35))
    canvas.alpha_composite(lockup, ((WIDTH - lockup.width) // 2, 145))
    fade = int(255 * smoothstep(min(1.0, progress * 2.0)))
    title = "Your closet is full of possibilities."
    box = draw.textbbox((0, 0), title, font=DISPLAY_MEDIUM)
    draw.text(((WIDTH - (box[2] - box[0])) / 2, 392), title, font=DISPLAY_MEDIUM, fill=(255, 250, 244, fade))
    body = "List. Match. Trade."
    body_box = draw.textbbox((0, 0), body, font=BODY)
    draw.text(((WIDTH - (body_box[2] - body_box[0])) / 2, 486), body, font=BODY, fill=(238, 218, 188, fade))
    draw.rounded_rectangle((520, 548, 760, 608), radius=2, fill=IVORY + (255,))
    cta = "DISCOVER JOUFT"
    cta_box = draw.textbbox((0, 0), cta, font=BODY_SMALL)
    draw.text(((WIDTH - (cta_box[2] - cta_box[0])) / 2, 567), cta, font=BODY_SMALL, fill=BURGUNDY + (255,))
    return canvas


def crossfade(previous: Image.Image, current: Image.Image, local_progress: float) -> Image.Image:
    edge = 0.07
    if local_progress < edge:
        amount = smoothstep(local_progress / edge)
        return Image.blend(previous, current, amount)
    return current


def write_frame(writer: cv2.VideoWriter, frame: Image.Image) -> None:
    rgb = np.asarray(frame.convert("RGB"))
    writer.write(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))


def main() -> None:
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    sources = [Image.open(MEDIA_DIR / scene["image"]).convert("RGB") for scene in SCENES]
    intro_seconds = 5
    scene_seconds = 8
    outro_seconds = 6
    total_seconds = intro_seconds + scene_seconds * len(SCENES) + outro_seconds
    total_frames = total_seconds * FPS

    writer = cv2.VideoWriter(
        str(OUTPUT_PATH),
        cv2.VideoWriter_fourcc(*"avc1"),
        FPS,
        (WIDTH, HEIGHT),
    )
    if not writer.isOpened():
        raise RuntimeError("Could not initialize MP4 video writer")

    previous = draw_intro(1.0)
    for frame_index in range(total_frames):
        seconds = frame_index / FPS
        if seconds < intro_seconds:
            progress = seconds / intro_seconds
            frame = draw_intro(progress)
        elif seconds < intro_seconds + scene_seconds * len(SCENES):
            scene_elapsed = seconds - intro_seconds
            scene_index = min(len(SCENES) - 1, int(scene_elapsed // scene_seconds))
            local_progress = (scene_elapsed % scene_seconds) / scene_seconds
            current = draw_scene(SCENES[scene_index], sources[scene_index], local_progress)
            if local_progress < 0.07:
                frame = crossfade(previous, current, local_progress)
            else:
                frame = current
            if local_progress >= 0.93:
                previous = current
        else:
            local_progress = (seconds - intro_seconds - scene_seconds * len(SCENES)) / outro_seconds
            current = draw_outro(local_progress)
            frame = crossfade(previous, current, local_progress)

        draw_tracking(ImageDraw.Draw(frame, "RGBA"), seconds, total_seconds)
        write_frame(writer, frame)

    writer.release()
    poster = draw_scene(SCENES[2], sources[2], 0.45).convert("RGB")
    poster.save(POSTER_PATH, quality=90, optimize=True)
    print(f"Wrote {OUTPUT_PATH}")
    print(f"Wrote {POSTER_PATH}")


if __name__ == "__main__":
    main()
