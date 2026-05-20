"""
utils/pdf.py — WeasyPrint helper for generating PDF invoices.

Usage:
    from utils.pdf import html_to_pdf
    pdf_bytes = html_to_pdf(rendered_html)
"""

import io

try:
    from weasyprint import HTML, CSS
    WEASYPRINT_AVAILABLE = True
except ImportError:
    WEASYPRINT_AVAILABLE = False


def html_to_pdf(html_string: str, base_url: str = None) -> bytes:
    """
    Convert an HTML string to PDF bytes using WeasyPrint.

    Args:
        html_string: Complete HTML document as string.
        base_url:    Base URL for resolving relative paths (CSS, images).
                     If None, uses current working directory.

    Returns:
        PDF content as bytes.

    Raises:
        RuntimeError: If WeasyPrint is not installed.
    """
    if not WEASYPRINT_AVAILABLE:
        raise RuntimeError(
            "WeasyPrint is not installed. Run: pip install WeasyPrint"
        )

    buf = io.BytesIO()
    HTML(string=html_string, base_url=base_url).write_pdf(buf)
    return buf.getvalue()
