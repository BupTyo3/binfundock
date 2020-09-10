from django.contrib import admin

from .models import Signal, EntryPoint, TakeProfit


@admin.register(Signal)
class SignalAdmin(admin.ModelAdmin):
    pass


@admin.register(EntryPoint)
class EntryPointAdmin(admin.ModelAdmin):
    pass


@admin.register(TakeProfit)
class TakeProfitAdmin(admin.ModelAdmin):
    pass

