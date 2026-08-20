import random
import secrets

ANIMALS = [
    "dog", "cat", "fox", "owl", "bear", "wolf", "lion", "tiger", "panda", "eagle",
    "shark", "whale", "zebra", "koala", "otter", "moose", "raven", "hawk", "deer", "seal",
    "goat", "duck", "swan", "crab", "frog", "mouse", "horse", "camel", "rhino", "llama",
]

# A separate, deliberately short, fixed list for member check-in passwords —
# no digits, no other animals allowed. Collisions between two different
# members' current passwords are fine: Sign Up/Join/Unsign always require
# the matching username alongside it.
MEMBER_ANIMALS = [
    "dog", "cat", "fish", "horse", "mouse", "goat", "tiger", "rabbit", "lion", "donkey", "wolf",
    "bear",
]


def generate_password() -> str:
    """animal + integer 0-99, e.g. "panda42". Python never zero-pads an int
    in an f-string, so the "no leading zeros" requirement holds structurally."""
    return f"{random.choice(ANIMALS)}{random.randint(0, 99)}"


def generate_member_password() -> str:
    """animal only, no digits — drawn fresh on every member check-in."""
    return random.choice(MEMBER_ANIMALS)


def generate_admin_password() -> str:
    """A real administrative credential (staff's reset password) — not the
    kiosk's playful animal schemes, cryptographically random via `secrets`."""
    return secrets.token_urlsafe(9)


def generate_unique_passwords(n: int) -> list[str]:
    """n distinct plaintext passwords, for bulk test-account creation where
    showing two players the same password in one batch would be confusing."""
    seen = set()
    while len(seen) < n:
        seen.add(generate_password())
    return list(seen)
