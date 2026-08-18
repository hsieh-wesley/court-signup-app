from django.core.management.base import BaseCommand

from courts import admin_services


class Command(BaseCommand):
    help = "Create (or reset) player1..playerN test accounts with fresh generated passwords."

    def add_arguments(self, parser):
        parser.add_argument("count", nargs="?", type=int, default=8)

    def handle(self, *args, **options):
        results = admin_services.create_test_players(options["count"])
        for r in results:
            self.stdout.write(f"{r['username']}: {r['password']}")
