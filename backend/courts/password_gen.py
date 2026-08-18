import random

ANIMALS = [
    "dog", "cat", "fox", "owl", "bear", "wolf", "lion", "tiger", "panda", "eagle",
    "shark", "whale", "zebra", "koala", "otter", "moose", "raven", "hawk", "deer", "seal",
    "goat", "duck", "swan", "crab", "frog", "mouse", "horse", "camel", "rhino", "llama",
]


def generate_password() -> str:
    """animal + integer 0-99, e.g. "panda42". Python never zero-pads an int
    in an f-string, so the "no leading zeros" requirement holds structurally."""
    return f"{random.choice(ANIMALS)}{random.randint(0, 99)}"


def generate_unique_passwords(n: int) -> list[str]:
    """n distinct plaintext passwords, for bulk test-account creation where
    showing two players the same password in one batch would be confusing."""
    seen = set()
    while len(seen) < n:
        seen.add(generate_password())
    return list(seen)
