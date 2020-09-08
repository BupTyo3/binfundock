from django.contrib import admin

from .models import SignalModel


@admin.register(SignalModel)
class SignalAdmin(admin.ModelAdmin):
    pass


