import uuid

import django.db.models.deletion
from django.db import migrations, models


def populate_booking_ids(apps, schema_editor):
    BookingHistory = apps.get_model("discovery", "BookingHistory")
    for booking in BookingHistory.objects.filter(booking_id__isnull=True).iterator():
        booking.booking_id = uuid.uuid4()
        booking.save(update_fields=["booking_id"])


class Migration(migrations.Migration):
    dependencies = [("discovery", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="showtime",
            name="screen",
            field=models.CharField(default="Screen 1", max_length=80),
        ),
        migrations.AddField(
            model_name="bookinghistory",
            name="showtime",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="bookings", to="discovery.showtime"),
        ),
        migrations.AddField(
            model_name="bookinghistory",
            name="payment_reference",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="bookinghistory",
            name="seats",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="bookinghistory",
            name="total_amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=9),
        ),
        migrations.AddField(
            model_name="bookinghistory",
            name="ticket_email_sent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="bookinghistory",
            name="email_error",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="bookinghistory",
            name="booking_id",
            field=models.UUIDField(null=True, editable=False),
        ),
        migrations.RunPython(populate_booking_ids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="bookinghistory",
            name="booking_id",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
