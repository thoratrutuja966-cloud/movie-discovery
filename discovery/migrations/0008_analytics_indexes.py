from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("discovery", "0007_seat_reservations"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="bookinghistory",
            index=models.Index(fields=["status", "booked_at"], name="booking_status_time_idx"),
        ),
        migrations.AddIndex(
            model_name="paymenttransaction",
            index=models.Index(fields=["status", "created_at"], name="payment_status_time_idx"),
        ),
    ]
