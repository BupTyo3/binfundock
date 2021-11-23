from django.contrib import admin

from .models import Telegram


@admin.register(Telegram)
class TelegramAdmin(admin.ModelAdmin):
    pass

