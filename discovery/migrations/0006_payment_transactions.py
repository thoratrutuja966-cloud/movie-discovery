import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("discovery", "0005_correct_oppenheimer_genres"),
    ]

    operations = [
        migrations.AlterField(
            model_name="bookinghistory",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Payment pending"),
                    ("confirmed", "Confirmed"),
                    ("failed", "Payment failed"),
                    ("cancelled", "Cancelled"),
                ],
                db_index=True,
                default="pending",
                max_length=12,
            ),
        ),
        migrations.CreateModel(
            name="PaymentTransaction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("provider", models.CharField(default="stripe", max_length=20)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("succeeded", "Succeeded"), ("failed", "Failed"), ("expired", "Expired")], db_index=True, default="pending", max_length=12)),
                ("amount_minor", models.PositiveIntegerField(help_text="Amount in the currency's smallest unit, such as paise.")),
                ("currency", models.CharField(default="inr", max_length=3)),
                ("checkout_session_id", models.CharField(blank=True, max_length=255, null=True, unique=True)),
                ("payment_intent_id", models.CharField(blank=True, max_length=255)),
                ("idempotency_key", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("checkout_url", models.URLField(blank=True, max_length=1000)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("error_message", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("booking", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="payment_attempts", to="discovery.bookinghistory")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="PaymentWebhookEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_id", models.CharField(max_length=255, unique=True)),
                ("event_type", models.CharField(max_length=120)),
                ("received_at", models.DateTimeField(auto_now_add=True)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={"ordering": ["-received_at"]},
        ),
    ]
