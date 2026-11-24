import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("discovery", "0006_payment_transactions"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="paymenttransaction",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("succeeded", "Succeeded"),
                    ("failed", "Failed"),
                    ("expired", "Expired"),
                    ("refund_pending", "Refund pending"),
                    ("refunded", "Refunded"),
                ],
                db_index=True,
                default="pending",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="paymenttransaction",
            name="refund_id",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="paymenttransaction",
            name="refund_error",
            field=models.TextField(blank=True),
        ),
        migrations.CreateModel(
            name="SeatReservation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("seat_code", models.CharField(max_length=4)),
                ("status", models.CharField(choices=[("held", "Temporarily held"), ("booked", "Booked"), ("released", "Released")], db_index=True, default="held", max_length=10)),
                ("expires_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("booking", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="seat_reservations", to="discovery.bookinghistory")),
                ("payment_attempt", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="seat_reservations", to="discovery.paymenttransaction")),
                ("showtime", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="seat_reservations", to="discovery.showtime")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="seat_reservations", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["showtime_id", "seat_code"]},
        ),
        migrations.AddConstraint(
            model_name="seatreservation",
            constraint=models.UniqueConstraint(fields=("showtime", "seat_code"), name="unique_seat_row_per_showtime"),
        ),
        migrations.AddIndex(
            model_name="seatreservation",
            index=models.Index(fields=["showtime", "status", "expires_at"], name="discovery_s_showti_3ac947_idx"),
        ),
    ]
