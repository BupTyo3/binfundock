from django.contrib import admin, messages
from django.utils.translation import ugettext_lazy as _

from apps.market.utils import get_or_create_market
from utils.admin import InputFilter

from .models import Signal, EntryPoint, TakeProfit


class OuterIDFilter(InputFilter):
    parameter_name = 'outer_id'
    title = _('Outer_ID')

    def queryset(self, request, queryset):
        if self.value() is not None:
            try:
                outer_id = self.value()
            except ValueError:
                return queryset
            return queryset.filter(outer_signal_id=outer_id)


@admin.register(Signal)
class SignalAdmin(admin.ModelAdmin):
    list_display = ['id', 'main_coin', 'symbol',
                    'stop_loss',
                    'outer_signal_id',
                    'status',
                    ]
    search_fields = ['id', 'outer_signal_id', 'symbol', ]
    list_filter = [
        '_status',
        OuterIDFilter,
    ]
    actions = [
        'form_buy_orders',
        'push_orders',
        'run_bought_worker',
        'run_sold_worker',
        'update_info_by_api',
    ]

    def notifications_handling(value):
        def decorate(f):
            def applicator(self, request, signal):
                try:
                    f(self, request, signal)
                except ValueError as ex:
                    messages.error(request, f"{ex} T_ID={signal.id}: {signal.outer_signal_id}")
                else:
                    msg = f"Successful action for T_ID={signal.id}: {signal.outer_signal_id}"
                    messages.success(request, msg)
            return applicator
        return decorate

    def form_buy_orders(self, request, queryset):
        for signal in queryset:
            self._form_one(request, signal)

    def push_orders(self, request, queryset):
        for signal in queryset:
            self._push_order_one(request, signal)

    def update_info_by_api(self, request, queryset):
        for signal in queryset:
            self._update_by_api_one(request, signal)

    def run_bought_worker(self, request, queryset):
        for signal in queryset:
            self._run_bought_worker_one(request, signal)

    def run_sold_worker(self, request, queryset):
        for signal in queryset:
            self._run_sold_worker_one(request, signal)
            pass

    @notifications_handling('')
    def _form_one(self, request, signal):
        signal.formation_buy_orders(get_or_create_market())

    @notifications_handling('')
    def _push_order_one(self, request, signal):
        signal.push_orders()

    @notifications_handling('')
    def _update_by_api_one(self, request, signal):
        signal.update_info_by_api()

    @notifications_handling('')
    def _run_bought_worker_one(self, request, signal):
        signal.worker_for_bought_orders()

    @notifications_handling('')
    def _run_sold_worker_one(self, request, signal):
        signal.worker_for_sold_orders()


@admin.register(EntryPoint)
class EntryPointAdmin(admin.ModelAdmin):
    pass


@admin.register(TakeProfit)
class TakeProfitAdmin(admin.ModelAdmin):
    pass

