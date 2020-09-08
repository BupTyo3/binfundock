from django.contrib import admin

from .models import SignalAdmin


@admin.register(SignalAdmin)
class SignalAdmin(admin.ModelAdmin):
    pass


