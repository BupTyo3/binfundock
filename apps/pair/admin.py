from django.contrib import admin

from .models import Pair


@admin.register(Pair)
class PairAdmin(admin.ModelAdmin):
    list_display = ['id', 'symbol', 'min_price', 'step_price', 'step_quantity', 'min_quantity', 'min_amount', ]
    search_fields = ['symbol', ]

