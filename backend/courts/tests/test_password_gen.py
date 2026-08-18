import re

from courts.password_gen import ANIMALS, generate_password, generate_unique_passwords

PASSWORD_RE = re.compile(r"^([a-z]+)(0|[1-9][0-9]?)$")


def test_generate_password_matches_format_and_never_leading_zero():
    for _ in range(1000):
        password = generate_password()
        match = PASSWORD_RE.match(password)
        assert match, f"{password!r} does not match animal+0-99 format"
        animal, number = match.groups()
        assert animal in ANIMALS
        assert 0 <= int(number) <= 99
        # No leading zero: "0" is fine, but "01".."09" must never appear.
        assert not (len(number) == 2 and number[0] == "0")


def test_generate_unique_passwords_has_no_duplicates():
    passwords = generate_unique_passwords(20)
    assert len(passwords) == 20
    assert len(set(passwords)) == 20
