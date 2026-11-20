from datetime import date
from urllib.parse import quote_plus

from django.core.management.base import BaseCommand

from discovery.models import CastMember, Genre, Language, Movie


class Command(BaseCommand):
    help = "Complete the Task 3 demo movie catalogue with metadata and safe trailer links."

    def handle(self, *args, **options):
        # The titles originally supplied by the demo catalogue are fictional stories.
        # Their sample cast is explicitly labelled so it cannot be mistaken for real credits.
        catalogue = [
            {
                "title": "Wild India", "language": ["English"], "genres": ["Documentary", "Nature"],
                "cast": ["Joseph Bader"], "certification": "U", "duration": 44,
                "description": "A wildlife documentary exploring India's varied habitats, from mountain landscapes to forests and dry grasslands, and the animals adapted to survive in them.",
                "trailer": "search", "poster": "/static/discovery/posters/wild-india.jpg",
            },
            {
                "title": "Oppenheimer", "language": ["English", "Hindi"], "genres": ["Biography", "Drama", "History"],
                "cast": ["Cillian Murphy", "Emily Blunt", "Matt Damon", "Robert Downey Jr.", "Florence Pugh"],
                "certification": "A (India) / R (US)", "duration": 180,
                "description": "Christopher Nolan's historical drama follows physicist J. Robert Oppenheimer and the scientists of the Manhattan Project, then examines the political and personal consequences of building the atomic bomb.",
                "trailer": "https://www.youtube.com/watch?v=bK6ldnjE3Y0",
                "poster": "/static/discovery/posters/oppenheimer.jpg",
            },
            {
                "title": "The Glass Kingdom", "language": ["Hindi"], "genres": ["Fantasy", "Adventure"],
                "cast": ["Aarav Sen (sample cast)", "Mira Das (sample cast)", "Dev Malhotra (sample cast)"],
                "certification": "U/A 7+ (demo)", "duration": 118,
                "description": "A young cartographer follows a map into a kingdom hidden above the clouds. To bring its divided communities together, she must learn why the kingdom's glass bridges are beginning to disappear.",
                "trailer": "search", "poster": "https://cdn.penguin.co.uk/dam-assets/books/9781473589520/9781473589520-jacket-large.jpg",
            },
            {
                "title": "A Map of Us", "year": 2025, "catalog_rating": "7.8", "popularity": 44,
                "language": ["Marathi"], "genres": ["Drama", "Comedy"],
                "cast": ["Anaya Kulkarni (sample cast)", "Rohan Deshmukh (sample cast)", "Sana Patil (sample cast)"],
                "certification": "U/A 7+ (demo)", "duration": 106,
                "description": "After a friend's wedding, three old friends take a winding road home. A forgotten paper map sends them through familiar towns, old memories and one unexpectedly important detour.",
                "trailer": "search", "poster": "/static/discovery/posters/a-map-of-us.svg",
            },
            {
                "title": "Red Line", "year": 2024, "catalog_rating": "7.9", "popularity": 49,
                "language": ["Tamil"], "genres": ["Action", "Thriller"],
                "cast": ["Kavin Raj (sample cast)", "Meera Venkatesh (sample cast)", "Arjun Kumar (sample cast)"],
                "certification": "U/A 13+ (demo)", "duration": 112,
                "description": "A railway detective has one late-night train ride to identify a planned heist. With the suspect somewhere among the passengers, every stop brings a new clue and a tighter deadline.",
                "trailer": "search", "poster": "/static/discovery/posters/red-line.svg",
            },
            {
                "title": "Little Comets", "year": 2025, "catalog_rating": "8.6", "popularity": 51,
                "language": ["English"], "genres": ["Animation", "Fantasy"],
                "cast": ["Tara Bloom (sample cast)", "Leo Park (sample cast)", "Nico Wells (sample cast)"],
                "certification": "U (demo)", "duration": 92,
                "description": "When a small comet lands near a quiet observatory, a curious child and a shy new friend set out to help it find its way home. Their journey turns the night sky into a place of discovery and belonging.",
                "trailer": "search", "poster": "/static/discovery/posters/little-comets.svg",
            },
            {
                "title": "Orbit Kids", "language": ["English"], "genres": ["Sci-Fi", "Comedy"],
                "cast": ["Jamie Cole (sample cast)", "Asha Reed (sample cast)", "Benji Fox (sample cast)"],
                "certification": "U (demo)", "duration": 98,
                "description": "A group of school friends accidentally launches its science-fair project into orbit. With a homemade control room and a very short window to bring it back, the kids turn teamwork into their most important experiment.",
                "trailer": "search", "poster": "https://images.unsplash.com/photo-1704296435295-1290879e3c5f?auto=format&fit=crop&fm=jpg&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D&ixlib=rb-4.1.0&q=60&w=3000",
            },
            {
                "title": "Blue Hour", "language": ["Tamil"], "genres": ["Drama", "Thriller"],
                "cast": ["Leela Raman (sample cast)", "Vikram Iyer (sample cast)", "Nila Joseph (sample cast)"],
                "certification": "U/A 13+ (demo)", "duration": 110,
                "description": "During a quiet night shift, a nurse notices that several patients share an unexplained pattern. Her search for answers uncovers a conspiracy inside the hospital and puts her own safety at risk.",
                "trailer": "search", "poster": "https://images.unsplash.com/photo-1758022039037-8644d5206e45?auto=format&fit=crop&fm=jpg&ixid=NHwxMjA3fDA%3D&ixlib=rb-4.1.0&q=60&w=3000",
            },
            {
                "title": "One More Sunday", "language": ["Hindi"], "genres": ["Comedy", "Adventure"],
                "cast": ["Kavya Sharma (sample cast)", "Ishaan Verma (sample cast)", "Farah Ali (sample cast)"],
                "certification": "U/A 7+ (demo)", "duration": 104,
                "description": "A crowded family reunion takes an unexpected turn when a playful clue sends relatives across the city on a treasure hunt. The search gives one busy family a reason to spend one more Sunday together.",
                "trailer": "search", "poster": "https://images.unsplash.com/photo-1758275557262-e88aa1bd0bd1?auto=format&fit=crop&fm=jpg&ixid=NHwxMjA3fDA%3D&ixlib=rb-4.1.0&q=60&w=3000",
            },
            {
                "title": "Spider-Man: Brand New Day", "language": ["English"], "genres": ["Action", "Adventure", "Sci-Fi"],
                "cast": ["Tom Holland", "Zendaya", "Sadie Sink", "Jacob Batalon", "Jon Bernthal", "Mark Ruffalo"],
                "certification": "PG-13 (US)", "duration": 145,
                "description": "Peter Parker fights crime full-time in a city that has forgotten his identity. As his isolated life begins to change him, a new threat forces him to protect the people who no longer know him.",
                "trailer": "https://www.youtube.com/watch?v=62bIsvRcPv0",
                "poster": "/static/discovery/posters/spider-man-brand-new-day.jpg",
            },
        ]

        extra_genres = ["Documentary", "Nature", "Biography", "History"]
        for name in extra_genres:
            Genre.objects.get_or_create(name=name, defaults={"slug": name.lower().replace(" ", "-")})

        for item in catalogue:
            title = item["title"]
            movie = Movie.objects.filter(title__iexact=title).first()
            if not movie and title == "Spider-Man: Brand New Day":
                movie = Movie.objects.filter(title__iexact="Spider-Man: Brand New Day,").first()
            if not movie:
                year = item.get("year", 2025)
                movie = Movie.objects.create(
                    title=title,
                    synopsis=item["description"],
                    release_date=date(year, 6, 15),
                    catalog_rating=item.get("catalog_rating", "0"),
                    popularity=item.get("popularity", 0),
                )

            movie.title = title
            movie.description = item["description"]
            movie.trailer_url = (
                "https://www.youtube.com/results?search_query=" + quote_plus(f"{title} official trailer")
                if item["trailer"] == "search" else item["trailer"]
            )
            movie.certification = item["certification"]
            movie.duration_minutes = item["duration"]
            movie.poster_url = item["poster"]
            if title == "Oppenheimer":
                movie.release_date = date(2023, 7, 21)
            elif title == "Spider-Man: Brand New Day":
                movie.release_date = date(2026, 7, 31)
            elif title == "Blue Hour":
                movie.release_date = date(2026, 6, 15)
            movie.save()
            movie.languages.set([Language.objects.get_or_create(name=name)[0] for name in item["language"]])
            movie.genres.set([Genre.objects.get(name=name) for name in item["genres"]])
            movie.cast_members.set([
                CastMember.objects.get_or_create(name=name)[0] for name in item["cast"]
            ])

        self.stdout.write(self.style.SUCCESS(f"Completed Task 3 details for {len(catalogue)} movies."))
