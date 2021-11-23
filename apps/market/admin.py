from django.contrib import admin

from .models import Market


@admin.register(Market)
class BiMarketAdmin(admin.ModelAdmin):
    pass

