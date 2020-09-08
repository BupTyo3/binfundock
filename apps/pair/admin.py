from django.contrib import admin

from .models import Pair


@admin.register(Pair)
class PairAdmin(admin.ModelAdmin):
    pass

