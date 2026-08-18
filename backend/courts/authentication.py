from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

from .models import PlayerSession


class PlayerSessionAuthentication(BaseAuthentication):
    """Replaces DRF's stock TokenAuthentication. Resolves the same
    `Authorization: Token <key>` header against PlayerSession instead of
    the one-per-user Token model, since a session is now scoped to a
    Location. `request.auth` becomes the PlayerSession instance."""

    keyword = b"token"

    def authenticate(self, request):
        auth = get_authorization_header(request).split()
        if not auth or auth[0].lower() != self.keyword:
            return None
        if len(auth) == 1:
            raise AuthenticationFailed("Invalid token header. No credentials provided.")
        if len(auth) > 2:
            raise AuthenticationFailed("Invalid token header. Token string should not contain spaces.")
        try:
            key = auth[1].decode()
        except UnicodeError:
            raise AuthenticationFailed("Invalid token header. Token string should not contain invalid characters.")

        try:
            session = PlayerSession.objects.select_related("user", "location").get(key=key)
        except PlayerSession.DoesNotExist:
            raise AuthenticationFailed("Invalid token.")

        if not session.user.is_active:
            raise AuthenticationFailed("User inactive or deleted.")

        return (session.user, session)

    def authenticate_header(self, request):
        return self.keyword.decode()
