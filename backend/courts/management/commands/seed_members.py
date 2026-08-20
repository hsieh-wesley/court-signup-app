from django.core.management.base import BaseCommand

from courts import admin_services, services

SEED_MEMBERS = [
    ("alice", "5550100001"),
    ("bob", "5550100002"),
    ("mike", "5550100003"),
    ("sara", "5550100004"),
    ("john", "5550100005"),
    ("emma", "5550100006"),
    ("jake", "5550100007"),
    ("lucy", "5550100008"),
    ("ryan", "5550100009"),
    ("kate", "5550100010"),
]


class Command(BaseCommand):
    help = "Idempotently seed 10 demo members (alice..kate) with placeholder phone numbers."

    def handle(self, *args, **options):
        for username, phone_number in SEED_MEMBERS:
            try:
                player, membership, plaintext = admin_services.start_membership(
                    username=username, phone_number=phone_number
                )
            except services.ServiceError as exc:
                self.stdout.write(f"{username}: skipped ({exc})")
                continue
            note = f"password {plaintext}" if plaintext else "existing account"
            self.stdout.write(f"{username}: membership started, phone {phone_number}, {note}")
