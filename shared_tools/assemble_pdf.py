"""Assembles multiple source files (PDFs and/or images) into one final PDF,
in order, with every page normalized to a uniform page size — shared by
every AIMAOS agent. This is the tool for "package the rendered petition
together with the scanned birth certificate into one filing-ready PDF, all
pages letter-size" style directives. Uses PyMuPDF (fitz), already installed.

Each source page is placed scaled-to-fit (aspect ratio preserved, centered,
not stretched) within the target page box — PDF pages are drawn via
show_pdf_page (keeps real vector/text content, doesn't rasterize), images
via insert_image.
"""
import os

import fitz

# (width, height) in points (72pt = 1 inch) — standard PDF page sizes.
PAGE_SIZES_PT = {
    "letter": (612, 792),
    "legal": (612, 1008),
    "a4": (595, 842),
}
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")

TOOL_DEFINITION = {
    "name": "assemble_pdf",
    "description": "Combines multiple PDFs and/or images into one final PDF, in the given order, "
                   "with every page resized to a uniform standard page size (letter by default). Use "
                   "to package a rendered document together with scanned attachments into one file.",
    "parameters": {
        "type": "object",
        "properties": {
            "source_files": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Ordered absolute paths to PDFs and/or images to combine."
            },
            "output_path": {
                "type": "string",
                "description": "Where to save the assembled PDF."
            },
            "page_size": {
                "type": "string",
                "enum": ["letter", "legal", "a4"],
                "description": "Uniform page size for every page in the output (default 'letter')."
            }
        },
        "required": ["source_files", "output_path"]
    }
}


def _fit_rect(target_w, target_h, src_w, src_h):
    """Largest centered rect of src's aspect ratio that fits within target."""
    scale = min(target_w / src_w, target_h / src_h)
    w, h = src_w * scale, src_h * scale
    x0, y0 = (target_w - w) / 2, (target_h - h) / 2
    return fitz.Rect(x0, y0, x0 + w, y0 + h)


def execute(source_files, output_path, page_size="letter"):
    if not source_files:
        return "Error: source_files must not be empty."
    target_w, target_h = PAGE_SIZES_PT.get((page_size or "letter").lower(), PAGE_SIZES_PT["letter"])

    missing = [f for f in source_files if not os.path.isfile(f)]
    if missing:
        return f"Error: file(s) not found: {', '.join(missing)}"

    out_doc = fitz.open()
    page_counts = []
    try:
        for path in source_files:
            ext = os.path.splitext(path)[1].lower()
            if ext == ".pdf":
                src = fitz.open(path)
                n = src.page_count
                for i in range(n):
                    src_page = src[i]
                    rect = _fit_rect(target_w, target_h, src_page.rect.width, src_page.rect.height)
                    new_page = out_doc.new_page(width=target_w, height=target_h)
                    new_page.show_pdf_page(rect, src, i)
                src.close()
                page_counts.append((path, n))
            elif ext in IMAGE_EXTENSIONS:
                with fitz.open(path) as img_doc:
                    pix = img_doc[0].get_pixmap()
                    src_w, src_h = pix.width, pix.height
                rect = _fit_rect(target_w, target_h, src_w, src_h)
                new_page = out_doc.new_page(width=target_w, height=target_h)
                new_page.insert_image(rect, filename=path)
                page_counts.append((path, 1))
            else:
                out_doc.close()
                return f"Error: unsupported file type '{ext}' for {path}. Use a PDF or an image."

        os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
        out_doc.save(output_path)
    except Exception as e:
        out_doc.close()
        return f"Error assembling PDF: {e}"

    total_pages = out_doc.page_count
    out_doc.close()
    summary = "\n".join(f"  - {os.path.basename(p)}: {n} page(s)" for p, n in page_counts)
    return (f"Assembled {total_pages} page(s) into {output_path} (uniform {page_size} size):\n{summary}")
