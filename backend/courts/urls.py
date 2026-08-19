from django.urls import include, path

from . import views

urlpatterns = [
    path("admin/", include("courts.admin_urls")),
    path("auth/login/", views.LoginView.as_view(), name="login"),
    path("auth/logout/", views.LogoutView.as_view(), name="logout"),
    path("locations/", views.LocationListView.as_view(), name="location-list"),
    path("players/register/", views.RegisterPlayerView.as_view(), name="player-register"),
    path(
        "players/check-username/",
        views.CheckUsernameView.as_view(),
        name="player-check-username",
    ),
    path("courts/", views.CourtListView.as_view(), name="court-list"),
    path("me/status/", views.PlayerStatusView.as_view(), name="my-status"),
    path("queue-entries/", views.QueueEntryCreateView.as_view(), name="queue-entry-create"),
    path(
        "queue-entries/<int:pk>/join/",
        views.JoinOpenSlotView.as_view(),
        name="queue-entry-join",
    ),
    path(
        "queue-entries/<int:pk>/unsign/",
        views.UnsignView.as_view(),
        name="queue-entry-unsign",
    ),
    path("pairs/unsign/", views.QuickUnsignView.as_view(), name="quick-unsign"),
]
