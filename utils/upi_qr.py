"""
utils/upi_qr.py
Generates a dynamic UPI payment QR code as a base64 PNG data-URI.

UPI deep-link format:
  upi://pay?pa=<VPA>&pn=<NAME>&am=<AMOUNT>&cu=INR&tn=<NOTE>

When scanned in any UPI app (PhonePe, Google Pay, Paytm, BHIM, etc.)
the app pre-fills the payee and the exact invoice amount.
"""
import io
import base64

import qrcode
from qrcode.image.pure import PyPNGImage


def make_upi_qr(upi_id: str, payee_name: str, amount: float,
                note: str = "", size: int = 90) -> str:
    """
    Build a UPI payment QR and return a base64 data-URI string.

    Args:
        upi_id      – e.g. '44941352398@sbi'
        payee_name  – e.g. 'M/S Sri Devi Industries'
        amount      – invoice grand total (float), e.g. 9300.0
        note        – invoice number / reference
        size        – pixel size of the image (square)

    Returns:
        data-URI string suitable for <img src="...">.
    """
    # Build the UPI URL
    import urllib.parse
    params = {
        "pa": upi_id,
        "pn": payee_name,
        "am": f"{amount:.2f}",
        "cu": "INR",
    }
    if note:
        params["tn"] = note

    upi_url = "upi://pay?" + urllib.parse.urlencode(params)

    # Generate the QR code image in memory
    qr = qrcode.QRCode(
        version=None,          # auto-select smallest version
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(upi_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    # Resize to target pixel size
    img = img.get_image().resize((size, size))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    return f"data:image/png;base64,{b64}"
