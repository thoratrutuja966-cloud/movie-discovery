from datetime import date, timedelta
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from discovery.models import Genre, Movie, Showtime, Theater

class Command(BaseCommand):
    help = "Load a small local demo catalogue for the movie discovery page."
    def handle(self, *args, **kwargs):
        names = ["Action", "Adventure", "Comedy", "Drama", "Fantasy", "Sci-Fi", "Thriller", "Animation", "Romance"]
        genres = {name: Genre.objects.get_or_create(name=name, slug=name.lower().replace(" ", "-"))[0] for name in names}
        data = [
            ("The Last Signal", "A radio astronomer catches a message that changes everything.", "English", 2025, 8.7, 98, ["Sci-Fi", "Thriller"], "the-last-signal.svg"),
            ("Monsoon Letters", "Two strangers reconnect through notes carried across Mumbai.", "Hindi", 2026, 8.2, 91, ["Drama", "Romance"], "monsoon-letters.png"),
            ("Paper Planets", "A young inventor builds a world beyond the rooftops.", "English", 2025, 7.9, 84, ["Adventure", "Animation"], "paper-planets.svg"),
            ("One More Sunday", "A chaotic family reunion turns into a city-wide treasure hunt.", "Hindi", 2024, 7.6, 77, ["Comedy", "Adventure"], "one-more-sunday.svg"),
            ("Blue Hour", "A night-shift nurse uncovers a quiet conspiracy.", "Tamil", 2026, 8.4, 72, ["Drama", "Thriller"], "blue-hour.svg"),
            ("Orbit Kids", "A crew of school friends accidentally launches their science project.", "English", 2024, 7.8, 69, ["Sci-Fi", "Comedy"], "orbit-kids.svg"),
            ("The Glass Kingdom", "A cartographer journeys through a kingdom hidden in the clouds.", "Hindi", 2025, 8.1, 63, ["Fantasy", "Adventure"], "the-glass-kingdom.svg"),
            ("Midnight Masala", "A food truck owner races to save her family restaurant.", "Hindi", 2026, 7.5, 60, ["Comedy", "Drama"], "midnight-masala.svg"),
            ("Wild Current", "Kayakers get caught between a storm and a mountain rescue.", "English", 2023, 7.7, 55, ["Action", "Adventure"], "wild-current.svg"),
            ("Little Comets", "A spirited animation about finding your place in the universe.", "English", 2025, 8.6, 51, ["Animation", "Fantasy"], "little-comets.svg"),
            ("Red Line", "A detective has one train ride to stop a planned heist.", "Tamil", 2024, 7.9, 49, ["Action", "Thriller"], "red-line.svg"),
            ("A Map of Us", "Old friends take the scenic route home after a wedding.", "Marathi", 2025, 7.8, 44, ["Drama", "Comedy"], "a-map-of-us.svg"),
        ]
        for title, synopsis, language, year, rating, popularity, tags, poster in data:
            movie, _ = Movie.objects.update_or_create(title=title, defaults={"synopsis": synopsis, "language": language, "release_date": date(year, 6, 15), "rating": Decimal(str(rating)), "popularity": popularity, "poster_url": f"/static/discovery/posters/{poster}"})
            movie.genres.set([genres[t] for t in tags if t in genres])
        theaters = [Theater.objects.get_or_create(name=name, city=city)[0] for name, city in [("CineSquare", "Mumbai"), ("Northstar Screens", "Delhi"), ("Riverwalk Cinema", "Pune"), ("Metroplex", "Bengaluru")]]
        now = timezone.now().replace(minute=0, second=0, microsecond=0)
        for i, movie in enumerate(Movie.objects.all()):
            for j, theater in enumerate(theaters[:2 + i % 3]):
                Showtime.objects.get_or_create(movie=movie, theater=theater, starts_at=now + timedelta(days=(i + j) % 7, hours=2 + j * 3), defaults={"ticket_price": Decimal(220 + (i * 25) + j * 40)})
        self.stdout.write(self.style.SUCCESS(f"Loaded {Movie.objects.count()} movies and demo showtimes."))
