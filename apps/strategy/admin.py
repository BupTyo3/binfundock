from django.contrib import admin

from .models import FirstStrategy


@admin.register(FirstStrategy)
class FirstStrategyAdmin(admin.ModelAdmin):
    pass

