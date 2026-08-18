from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import admin_services, services
from .admin_serializers import (
    AdminAddLoginSerializer,
    AdminBulkTestPlayersSerializer,
    AdminCourtCreateSerializer,
    AdminCourtSerializer,
    AdminPlayerCreateSerializer,
    AdminPlayerEditSerializer,
    AdminPlayerSerializer,
    AdminRemovePlayerSerializer,
)
from .models import Court, Player
from .permissions import IsAdmin


def _get_player_or_404(pk):
    try:
        return Player.objects.get(pk=pk)
    except Player.DoesNotExist:
        return None


def _get_court_or_404(pk):
    try:
        return Court.objects.get(pk=pk)
    except Court.DoesNotExist:
        return None


class AdminPlayerListCreateView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        players = Player.objects.select_related("user").order_by("display_name")
        return Response(AdminPlayerSerializer(players, many=True).data)

    def post(self, request):
        serializer = AdminPlayerCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            player, plaintext = admin_services.create_player(
                display_name=data["display_name"],
                username=data.get("username") or None,
                enable_login=data.get("enable_login", False),
            )
        except services.ServiceError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        payload = AdminPlayerSerializer(player).data
        if plaintext:
            payload["password"] = plaintext
        return Response(payload, status=status.HTTP_201_CREATED)


class AdminPlayerDetailView(APIView):
    permission_classes = [IsAdmin]

    def patch(self, request, pk):
        player = _get_player_or_404(pk)
        if player is None:
            return Response({"detail": "Player not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = AdminPlayerEditSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            player = admin_services.edit_player(player, **serializer.validated_data)
        except services.ServiceError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(AdminPlayerSerializer(player).data)


class AdminPlayerLoginView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        player = _get_player_or_404(pk)
        if player is None:
            return Response({"detail": "Player not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = AdminAddLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            plaintext = admin_services.add_login(player, serializer.validated_data["username"])
        except services.ServiceError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        payload = AdminPlayerSerializer(player).data
        payload["password"] = plaintext
        return Response(payload)


class AdminPlayerDisableLoginView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        player = _get_player_or_404(pk)
        if player is None:
            return Response({"detail": "Player not found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            admin_services.disable_login(player)
        except services.ServiceError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(AdminPlayerSerializer(player).data)


class AdminPlayerResetPasswordView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        player = _get_player_or_404(pk)
        if player is None:
            return Response({"detail": "Player not found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            plaintext = admin_services.reset_password(player)
        except services.ServiceError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        payload = AdminPlayerSerializer(player).data
        payload["password"] = plaintext
        return Response(payload)


class AdminPlayerDeactivateView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        player = _get_player_or_404(pk)
        if player is None:
            return Response({"detail": "Player not found."}, status=status.HTTP_404_NOT_FOUND)
        admin_services.deactivate_player(player)
        return Response(AdminPlayerSerializer(player).data)


class AdminBulkTestPlayersView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request):
        serializer = AdminBulkTestPlayersSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        results = admin_services.create_test_players(serializer.validated_data["count"])
        return Response(results, status=status.HTTP_201_CREATED)


class AdminCourtCreateView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request):
        serializer = AdminCourtCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            court = admin_services.create_court(**serializer.validated_data)
        except services.ServiceError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(AdminCourtSerializer(court).data, status=status.HTTP_201_CREATED)


class AdminCourtRemovePlayerView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        court = _get_court_or_404(pk)
        if court is None:
            return Response({"detail": "Court not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = AdminRemovePlayerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            admin_services.remove_player_from_court(
                court, serializer.validated_data["username"]
            )
        except services.ServiceError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminCourtDropView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        court = _get_court_or_404(pk)
        if court is None:
            return Response({"detail": "Court not found."}, status=status.HTTP_404_NOT_FOUND)
        admin_services.drop_court(court)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminCourtDeactivateView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        court = _get_court_or_404(pk)
        if court is None:
            return Response({"detail": "Court not found."}, status=status.HTTP_404_NOT_FOUND)
        admin_services.deactivate_court(court)
        return Response(AdminCourtSerializer(court).data)
