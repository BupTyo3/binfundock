from django.contrib import admin

from .models import Strategy


@admin.register(Strategy)
class StrategyAdmin(admin.ModelAdmin):
    pass

