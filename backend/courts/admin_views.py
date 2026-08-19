from django.db.models import Q
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import admin_services, services
from .admin_serializers import (
    AdminAddLoginSerializer,
    AdminBulkTestPlayersSerializer,
    AdminCourtCountSerializer,
    AdminCourtCreateSerializer,
    AdminCourtSerializer,
    AdminLocationCreateSerializer,
    AdminLocationEditSerializer,
    AdminLocationSerializer,
    AdminPlayerCreateSerializer,
    AdminPlayerEditSerializer,
    AdminPlayerSerializer,
    AdminRemovePlayerSerializer,
    CourtActivityLogSerializer,
    LoginLogSerializer,
)
from .models import Court, CourtActivityLog, Location, LoginLog, Player
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


def _get_location_or_404(pk):
    try:
        return Location.objects.get(pk=pk)
    except Location.DoesNotExist:
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
            return Response({"detail": str(exc)}, status=exc.status)
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
            return Response({"detail": str(exc)}, status=exc.status)
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
            return Response({"detail": str(exc)}, status=exc.status)
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
            return Response({"detail": str(exc)}, status=exc.status)
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
            return Response({"detail": str(exc)}, status=exc.status)
        payload = AdminPlayerSerializer(player).data
        payload["password"] = plaintext
        return Response(payload)


class AdminPlayerDeactivateView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        player = _get_player_or_404(pk)
        if player is None:
            return Response({"detail": "Player not found."}, status=status.HTTP_404_NOT_FOUND)
        admin_services.deactivate_player(player, actor=request.user)
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
        data = serializer.validated_data
        try:
            court = admin_services.create_court(
                location=data["location_id"],
                number=data.get("number"),
                capacity=data.get("capacity"),
            )
        except services.ServiceError as exc:
            return Response({"detail": str(exc)}, status=exc.status)
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
                court, serializer.validated_data["username"], actor=request.user
            )
        except services.ServiceError as exc:
            return Response({"detail": str(exc)}, status=exc.status)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminCourtDropView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        court = _get_court_or_404(pk)
        if court is None:
            return Response({"detail": "Court not found."}, status=status.HTTP_404_NOT_FOUND)
        admin_services.drop_court(court, actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminCourtDeactivateView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        court = _get_court_or_404(pk)
        if court is None:
            return Response({"detail": "Court not found."}, status=status.HTTP_404_NOT_FOUND)
        admin_services.deactivate_court(court, actor=request.user)
        return Response(AdminCourtSerializer(court).data)


class AdminLocationListCreateView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        locations = Location.objects.all().order_by("name")
        return Response(AdminLocationSerializer(locations, many=True).data)

    def post(self, request):
        serializer = AdminLocationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            location = admin_services.create_location(**serializer.validated_data)
        except services.ServiceError as exc:
            return Response({"detail": str(exc)}, status=exc.status)
        return Response(AdminLocationSerializer(location).data, status=status.HTTP_201_CREATED)


class AdminLocationDetailView(APIView):
    permission_classes = [IsAdmin]

    def patch(self, request, pk):
        location = _get_location_or_404(pk)
        if location is None:
            return Response({"detail": "Location not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = AdminLocationEditSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            location = admin_services.edit_location(location, **serializer.validated_data)
        except services.ServiceError as exc:
            return Response({"detail": str(exc)}, status=exc.status)
        return Response(AdminLocationSerializer(location).data)


class AdminLocationCourtCountView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        location = _get_location_or_404(pk)
        if location is None:
            return Response({"detail": "Location not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = AdminCourtCountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            admin_services.set_court_count(
                location, serializer.validated_data["count"], actor=request.user
            )
        except services.ServiceError as exc:
            return Response({"detail": str(exc)}, status=exc.status)
        return Response(AdminLocationSerializer(location).data)


class AdminLoginHistoryView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        qs = LoginLog.objects.select_related("user", "location").all()
        location_id = request.query_params.get("location_id")
        if location_id:
            qs = qs.filter(location_id=location_id)
        username = request.query_params.get("username")
        if username:
            qs = qs.filter(username=username)
        context = request.query_params.get("context")
        if context:
            qs = qs.filter(context=context)
        date = request.query_params.get("date")
        if date:
            qs = qs.filter(created_at__date=date)
        limit = int(request.query_params.get("limit", 200))
        return Response(LoginLogSerializer(qs[:limit], many=True).data)


class AdminCourtActivityHistoryView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        qs = CourtActivityLog.objects.all()
        location_id = request.query_params.get("location_id")
        if location_id:
            qs = qs.filter(location_id=location_id)
        court_id = request.query_params.get("court_id")
        if court_id:
            qs = qs.filter(court_id=court_id)
        event_type = request.query_params.get("event_type")
        if event_type:
            qs = qs.filter(event_type=event_type)
        username = request.query_params.get("username")
        if username:
            qs = qs.filter(Q(player_1_username=username) | Q(player_2_username=username))
        date = request.query_params.get("date")
        if date:
            qs = qs.filter(created_at__date=date)
        limit = int(request.query_params.get("limit", 200))
        return Response(CourtActivityLogSerializer(qs[:limit], many=True).data)
