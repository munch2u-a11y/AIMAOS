"""Basic image editing, shared by every AIMAOS agent — resize, rotate, flip,
simple enhancement, or convert to a single-page PDF. Purely mechanical (no
model involved), so unlike vision-based reading this is fully deterministic
and reliable. Uses Pillow.
"""
import os

from PIL import Image, ImageEnhance

# (width, height) in pixels at 200 DPI — matches PDF_RENDER_DPI used
# elsewhere in shared_tools for consistency between rendered and edited pages.
PAGE_SIZES_PX = {
    "letter": (1700, 2200),
    "legal": (1700, 2800),
    "a4": (1654, 2339),
}

TOOL_DEFINITION = {
    "name": "edit_image",
    "description": "Performs a basic edit on an image file: resize (to explicit pixels or a standard "
                   "paper size), rotate, flip, a simple brightness/contrast/sharpness/grayscale "
                   "enhancement, or convert it to a single-page PDF.",
    "parameters": {
        "type": "object",
        "properties": {
            "image_path": {
                "type": "string",
                "description": "Path to the source image (PNG/JPEG/etc)."
            },
            "action": {
                "type": "string",
                "enum": ["resize", "rotate", "flip", "enhance", "to_pdf"],
                "description": "Which edit to perform."
            },
            "output_path": {
                "type": "string",
                "description": "Where to save the result. Defaults to the input path with an "
                               "'_edited' suffix (or .pdf extension for to_pdf)."
            },
            "width": {"type": "integer", "description": "resize only: target width in pixels."},
            "height": {"type": "integer", "description": "resize only: target height in pixels."},
            "page_size": {
                "type": "string",
                "enum": ["letter", "legal", "a4"],
                "description": "resize only: resize to fit a standard paper size instead of explicit "
                               "width/height, preserving aspect ratio (letterboxed onto a white page)."
            },
            "degrees": {
                "type": "integer",
                "description": "rotate only: degrees clockwise (90, 180, or 270 typical)."
            },
            "direction": {
                "type": "string",
                "enum": ["horizontal", "vertical"],
                "description": "flip only: axis to flip across."
            },
            "enhancement": {
                "type": "string",
                "enum": ["brightness", "contrast", "sharpness", "grayscale"],
                "description": "enhance only: which adjustment to apply."
            },
            "factor": {
                "type": "number",
                "description": "enhance only: adjustment strength (1.0 = unchanged, >1 increases, "
                               "<1 decreases). Ignored for grayscale."
            }
        },
        "required": ["image_path", "action"]
    }
}


def _default_output(image_path, suffix, new_ext=None):
    base, ext = os.path.splitext(image_path)
    return f"{base}{suffix}{new_ext or ext}"


def _resize_to_page(img, page_size):
    target_w, target_h = PAGE_SIZES_PX.get(page_size.lower(), PAGE_SIZES_PX["letter"])
    scale = min(target_w / img.width, target_h / img.height)
    new_size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
    resized = img.resize(new_size, Image.LANCZOS)
    canvas = Image.new("RGB", (target_w, target_h), "white")
    offset = ((target_w - new_size[0]) // 2, (target_h - new_size[1]) // 2)
    canvas.paste(resized, offset)
    return canvas


def execute(image_path, action, output_path=None, width=None, height=None, page_size=None,
            degrees=None, direction=None, enhancement=None, factor=1.5):
    if not image_path or not os.path.isfile(image_path):
        return f"Error: image not found: {image_path}"

    try:
        img = Image.open(image_path)
        img.load()
    except Exception as e:
        return f"Error opening image: {e}"

    if action == "resize":
        if page_size:
            img = _resize_to_page(img.convert("RGB"), page_size)
        elif width and height:
            img = img.resize((int(width), int(height)), Image.LANCZOS)
        else:
            return "Error: resize needs either page_size, or both width and height."
        output_path = output_path or _default_output(image_path, "_resized")

    elif action == "rotate":
        if degrees is None:
            return "Error: rotate needs degrees."
        img = img.rotate(-int(degrees), expand=True)
        output_path = output_path or _default_output(image_path, "_rotated")

    elif action == "flip":
        if direction not in ("horizontal", "vertical"):
            return "Error: flip needs direction ('horizontal' or 'vertical')."
        img = img.transpose(Image.FLIP_LEFT_RIGHT if direction == "horizontal" else Image.FLIP_TOP_BOTTOM)
        output_path = output_path or _default_output(image_path, "_flipped")

    elif action == "enhance":
        if enhancement == "grayscale":
            img = img.convert("L")
        elif enhancement == "brightness":
            img = ImageEnhance.Brightness(img).enhance(factor)
        elif enhancement == "contrast":
            img = ImageEnhance.Contrast(img).enhance(factor)
        elif enhancement == "sharpness":
            img = ImageEnhance.Sharpness(img).enhance(factor)
        else:
            return "Error: enhancement must be one of brightness, contrast, sharpness, grayscale."
        output_path = output_path or _default_output(image_path, "_enhanced")

    elif action == "to_pdf":
        output_path = output_path or _default_output(image_path, "", ".pdf")
        try:
            img.convert("RGB").save(output_path, "PDF")
        except Exception as e:
            return f"Error saving PDF: {e}"
        return f"Converted to PDF: {output_path}"

    else:
        return f"Unknown action '{action}'. Use resize, rotate, flip, enhance, or to_pdf."

    try:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
        img.save(output_path)
    except Exception as e:
        return f"Error saving result: {e}"

    return f"{action} applied -> {output_path} ({img.width}x{img.height})"
