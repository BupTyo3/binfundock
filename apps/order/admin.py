from django.contrib import admin

from .models import BuyOrder, SellOrder


@admin.register(BuyOrder)
class BuyOrderAdmin(admin.ModelAdmin):
    pass


@admin.register(SellOrder)
class SellOrderAdmin(admin.ModelAdmin):
    pass
