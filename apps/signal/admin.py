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


class TechannelFilter(InputFilter):
    parameter_name = 'techannel_abbr'
    title = _('Techannel_Abbr')

    def queryset(self, request, queryset):
        if self.value() is not None:
            try:
                techannel_abbr = self.value()
            except ValueError:
                return queryset
            return queryset.filter(techannel__abbr=techannel_abbr)


@admin.register(Signal)
class SignalAdmin(admin.ModelAdmin):
    list_display = ['id',
                    'symbol',
                    'position',
                    'leverage',
                    'entry_points',
                    'take_profits',
                    'stop_loss',
                    'techannel',
                    'outer_signal_id',
                    'status',
                    'message_date',
                    'created',
                    ]
    select_related_fields = ['techannel', 'entry_points', 'take_profits', ]
    search_fields = ['id', 'outer_signal_id', 'symbol', 'techannel__abbr', ]
    list_filter = [
        '_status',
        OuterIDFilter,
        TechannelFilter,
    ]
    actions = [
        'form_buy_orders',
        'push_orders',
        'run_bought_worker',
        'run_sold_worker',
        'sell_by_market',
        'try_to_close',
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

    @staticmethod
    def take_profits(signal):
        return ' - '.join([str(i.value) for i in signal.take_profits.all()])

    @staticmethod
    def entry_points(signal):
        return ' - '.join([str(i.value) for i in signal.entry_points.all()])

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

    def sell_by_market(self, request, queryset):
        for signal in queryset:
            self._sell_by_market_one(request, signal)

    def try_to_close(self, request, queryset):
        for signal in queryset:
            self._try_to_close(request, signal)

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

    @notifications_handling('')
    def _sell_by_market_one(self, request, signal):
        signal.try_to_spoil(force=True)

    @notifications_handling('')
    def _try_to_close(self, request, signal):
        signal.try_to_close()


class PointOuterIDFilter(InputFilter):
    parameter_name = 'outer_id'
    title = _('Outer_ID')

    def queryset(self, request, queryset):
        if self.value() is not None:
            try:
                outer_id = self.value()
            except ValueError:
                return queryset
            return queryset.filter(signal__outer_signal_id=outer_id)


class PointTechannelFilter(InputFilter):
    parameter_name = 'techannel_abbr'
    title = _('Techannel_Abbr')

    def queryset(self, request, queryset):
        if self.value() is not None:
            try:
                techannel_abbr = self.value()
            except ValueError:
                return queryset
            return queryset.filter(signal__techannel__abbr=techannel_abbr)


class SignalIDFilter(InputFilter):
    parameter_name = 'signal_id'
    title = _('Signal_id')

    def queryset(self, request, queryset):
        if self.value() is not None:
            try:
                signal_id = self.value()
            except ValueError:
                return queryset
            return queryset.filter(signal__id=signal_id)


@admin.register(EntryPoint)
class EntryPointAdmin(admin.ModelAdmin):
    list_display = ['id',
                    'signal',
                    'signal_status',
                    'value',
                    ]
    select_related_fields = ['signal', 'signal__techannel', ]
    search_fields = ['id', 'signal__outer_signal_id', 'signal__symbol', 'signal__techannel__abbr', ]
    list_filter = [
        'signal___status',
        SignalIDFilter,
        PointOuterIDFilter,
        PointTechannelFilter,
    ]

    @staticmethod
    def signal_status(order):
        return order.signal.status


@admin.register(TakeProfit)
class TakeProfitAdmin(admin.ModelAdmin):
    list_display = ['id',
                    'signal',
                    'signal_status',
                    'value',
                    ]
    select_related_fields = ['signal', 'signal__techannel', ]
    search_fields = ['id', 'signal__outer_signal_id', 'signal__symbol', 'signal__techannel__abbr', ]
    list_filter = [
        'signal___status',
        SignalIDFilter,
        PointOuterIDFilter,
        PointTechannelFilter,
    ]

    @staticmethod
    def signal_status(order):
        return order.signal.status
