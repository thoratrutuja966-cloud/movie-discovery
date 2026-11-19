from django.db import migrations


def correct_oppenheimer_genres(apps, schema_editor):
    alias = schema_editor.connection.alias
    Movie = apps.get_model("discovery", "Movie")
    Genre = apps.get_model("discovery", "Genre")

    movies = Movie.objects.using(alias).filter(title__iexact="Oppenheimer")
    genre_ids = []
    for name in ("Biography", "Drama", "History"):
        genre, _ = Genre.objects.using(alias).get_or_create(
            name=name,
            defaults={"slug": name.lower()},
        )
        genre_ids.append(genre.pk)

    for movie in movies:
        movie.genres.set(genre_ids)


class Migration(migrations.Migration):
    dependencies = [
        ("discovery", "0004_language_alter_movie_language_movie_languages"),
    ]

    operations = [
        migrations.RunPython(correct_oppenheimer_genres, migrations.RunPython.noop),
    ]
