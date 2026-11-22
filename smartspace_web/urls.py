from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import include, path


handler404 = "homepage.views.page_not_found"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("homepage.urls")),
    path("rooms/", include("rooms_web.urls")),
    path("sensors/", include("sensors_web.urls")),
    path("reports/", include("reports_web.urls")),
    path("inspections/", include("reports_web.plan_urls")),
    path("accounts/login/", LoginView.as_view(), name="login"),
    path("accounts/logout/", LogoutView.as_view(), name="logout"),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if settings.DEBUG_TOOLBAR:
    from debug_toolbar.toolbar import debug_toolbar_urls

    urlpatterns += debug_toolbar_urls()
