from django.contrib import admin

from .models import Techannel


@admin.register(Techannel)
class TechannelAdmin(admin.ModelAdmin):
    list_display = ['id',
                    'abbr',
                    'name',
                    ]

