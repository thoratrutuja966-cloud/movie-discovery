from io import BytesIO
import textwrap

import qrcode
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from django.utils import timezone


def render_ticket_pdf(booking, verification_url):
    """Build a one-page PDF ticket in memory; no private file is left on disk."""
    output = BytesIO()
    page = canvas.Canvas(output, pagesize=A4)
    width, height = A4
    ink = colors.HexColor("#20201e")
    orange = colors.HexColor("#e8794f")

    page.setFillColor(ink)
    page.roundRect(42, height - 210, width - 84, 168, 14, fill=1, stroke=0)
    page.setFillColor(orange)
    page.setFont("Helvetica-Bold", 11)
    page.drawString(64, height - 82, "CINETRAIL  /  ADMISSION TICKET")
    page.setFillColor(colors.white)
    page.setFont("Helvetica-Bold", 25)
    page.drawString(64, height - 124, booking.movie.title[:34])
    page.setFont("Helvetica", 11)
    page.drawString(64, height - 151, f"Booking ID  {booking.booking_id}")

    showtime = booking.showtime
    details = [
        ("THEATER", showtime.theater.name if showtime else "Showtime unavailable"),
        ("CITY", showtime.theater.city if showtime else "—"),
        ("SCREEN", showtime.screen if showtime else "—"),
        ("SHOW TIME", timezone.localtime(showtime.starts_at).strftime("%A, %d %B %Y · %I:%M %p") if showtime else "—"),
        ("SEATS", ", ".join(booking.seats) or "—"),
        ("PAYMENT REFERENCE", booking.payment_reference or "—"),
        ("TOTAL", f"₹{booking.total_amount:.2f}"),
    ]
    y = height - 260
    for label, value in details:
        page.setFillColor(colors.HexColor("#77766f"))
        page.setFont("Helvetica-Bold", 8)
        page.drawString(64, y, label)
        page.setFillColor(ink)
        page.setFont("Helvetica", 11)
        for line_no, line in enumerate(textwrap.wrap(str(value), width=64)[:2]):
            page.drawString(190, y - (line_no * 14), line)
        y -= 37

    qr_image = qrcode.make(verification_url)
    qr_buffer = BytesIO()
    qr_image.save(qr_buffer, format="PNG")
    qr_buffer.seek(0)
    page.drawImage(ImageReader(qr_buffer), width - 155, 70, 92, 92, preserveAspectRatio=True, mask="auto")
    page.setFillColor(colors.HexColor("#77766f"))
    page.setFont("Helvetica", 8)
    page.drawString(64, 91, "Show this ticket at the theater. Scan the QR code to verify its status.")
    page.drawString(64, 76, "Payment references beginning DEMO- are sample records, not real charges.")
    page.setStrokeColor(colors.HexColor("#e9e7e0"))
    page.line(64, 116, width - 64, 116)
    page.save()
    output.seek(0)
    return output
