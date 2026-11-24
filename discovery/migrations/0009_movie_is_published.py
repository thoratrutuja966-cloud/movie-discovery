from django.db import migrations, models


UNPUBLISHED_TITLES = ("Little Comets", "Red Line", "A Map of Us")


def unpublish_placeholder_movies(apps, schema_editor):
    Movie = apps.get_model("discovery", "Movie")
    Movie.objects.using(schema_editor.connection.alias).filter(title__in=UNPUBLISHED_TITLES).update(is_published=False)


def republish_placeholder_movies(apps, schema_editor):
    Movie = apps.get_model("discovery", "Movie")
    Movie.objects.using(schema_editor.connection.alias).filter(title__in=UNPUBLISHED_TITLES).update(is_published=True)


class Migration(migrations.Migration):
    dependencies = [("discovery", "0008_analytics_indexes")]

    operations = [
        migrations.AddField(
            model_name="movie",
            name="is_published",
            field=models.BooleanField(default=True, help_text="Show this movie in the public catalogue and allow new bookings."),
        ),
        migrations.RunPython(unpublish_placeholder_movies, republish_placeholder_movies),
    ]
