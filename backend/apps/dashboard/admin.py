from django.contrib import admin

from .models import DashboardOTPDevice


@admin.register(DashboardOTPDevice)
class DashboardOTPDeviceAdmin(admin.ModelAdmin):
    list_display = ("user", "confirmed", "created_at", "updated_at")
    list_filter = ("confirmed",)
    search_fields = ("user__username", "user__email")
    readonly_fields = (
        "user", "confirmed", "created_at", "updated_at", "last_used_counter",
    )

    # TOTP 비밀키와 복구 코드 해시는 Django admin에서도 노출하지 않는다.
    fields = readonly_fields

# Register your models here.
