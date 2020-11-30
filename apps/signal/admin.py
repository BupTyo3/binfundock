from decimal import Decimal, Inexact, Context

from django.contrib import admin, messages
from django.utils.translation import ugettext_lazy as _
from django.db.models import (
    F, Case, When, ExpressionWrapper,
    CharField, Count, Sum, Q, Subquery, OuterRef,
    FloatField, Func, Value, Aggregate,
)
from django.db.models.functions import Abs, Concat, Upper, Cast
from django.contrib.postgres.aggregates.general import StringAgg

from apps.market.models import get_or_create_market, get_or_create_futures_market
from utils.admin import InputFilter

from .models import (
    Signal,
    EntryPoint,
    TakeProfit,
    HistorySignal,
    SignalOrig,
    EntryPointOrig,
    TakeProfitOrig,
)


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


def float_to_decimal(f):
    "Convert a floating point number to a Decimal with no loss of information"
    n, d = f.as_integer_ratio()
    numerator, denominator = Decimal(n), Decimal(d)
    ctx = Context(prec=60)
    result = ctx.divide(numerator, denominator)
    while ctx.flags[Inexact]:
        ctx.flags[Inexact] = False
        ctx.prec *= 2
        result = ctx.divide(numerator, denominator)
    return result


@admin.register(Signal)
class SignalAdmin(admin.ModelAdmin):
    list_display = ['id',
                    'symbol',
                    'market',
                    'position',
                    'leverage',
                    # 'e_points',
                    # 't_profits',
                    'entry_points',
                    'take_profits',
                    'stop_loss',
                    'techannel',
                    'outer_signal_id',
                    'status',
                    'amount',
                    'income',
                    'perc_inc',
                    'message_date',
                    'created',
                    'all_targets',
                    'signal_orig',
                    ]
    select_related_fields = ['techannel', 'entry_points', 'take_profits', 'market', ]
    search_fields = ['id', 'outer_signal_id', 'symbol', 'techannel__abbr', 'market__name', ]
    list_filter = [
        '_status',
        OuterIDFilter,
        TechannelFilter,
    ]
    actions = [
        'first_forming',
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

    def get_queryset(self, request):
        qs = super(SignalAdmin, self).get_queryset(request)

        # UNCOMMENT for only PostgreSQL
        # decrease in the number of requests
        # these and other correspondence e_points, t_profits places

        # qs = qs.annotate(t_profits=StringAgg(
        #     Cast('take_profits__value', output_field=CharField()),
        #     output_field=CharField(), delimiter='-', distinct=True))
        # qs = qs.annotate(e_points=StringAgg(
        #     Cast('entry_points__value', output_field=CharField()),
        #     output_field=CharField(), delimiter='-', distinct=True))

        res = qs.annotate(perc_inc=Case(
            When(amount=0, then=0),
            default=F('income') / F('amount') * 100))
        return res

    # def t_profits(self, obj):
    #     return obj.t_profits
    #
    # def e_points(self, obj):
    #     return obj.e_points

    def perc_inc(self, obj):
          return round(obj.perc_inc, 2)

    @staticmethod
    def take_profits(signal):
        return ' - '.join([str(i.value) for i in signal.take_profits.all()])

    @staticmethod
    def entry_points(signal):
        return ' - '.join([str(i.value) for i in signal.entry_points.all()])

    def first_forming(self, request, queryset):
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
        is_success = signal.first_formation_orders()
        if not is_success:
            raise ValueError("Couldn't form Signal")

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


class MainSignalIDFilter(InputFilter):
    parameter_name = 'signal_id'
    title = _('Signal_id')

    def queryset(self, request, queryset):
        if self.value() is not None:
            try:
                signal_id = self.value()
            except ValueError:
                return queryset
            return queryset.filter(main_signal_id=signal_id)


@admin.register(EntryPoint)
class EntryPointAdmin(admin.ModelAdmin):
    list_display = ['id',
                    'signal',
                    'signal_status',
                    'value',
                    'created',
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
                    'created',
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


@admin.register(HistorySignal)
class HistorySignalAdmin(admin.ModelAdmin):
    list_display = ['id', 'main_signal', 'status', 'current_price', 'created', ]
    select_related_fields = ['main_signal', ]
    search_fields = ['id', 'main_signal__outer_signal_id', 'main_signal__symbol', 'main_signal__techannel__abbr', ]
    list_filter = [
        'status',
        MainSignalIDFilter,
    ]


@admin.register(EntryPointOrig)
class EntryPointOrigAdmin(admin.ModelAdmin):
    list_display = ['id',
                    'signal',
                    'value',
                    'created',
                    ]
    select_related_fields = ['signal', 'signal__techannel', ]
    search_fields = ['id', 'signal__outer_signal_id', 'signal__symbol', 'signal__techannel__abbr', ]
    list_filter = [
        SignalIDFilter,
        PointOuterIDFilter,
        PointTechannelFilter,
    ]


@admin.register(TakeProfitOrig)
class TakeProfitOrigAdmin(admin.ModelAdmin):
    list_display = ['id',
                    'signal',
                    'value',
                    'created',
                    ]
    select_related_fields = ['signal', 'signal__techannel', ]
    search_fields = ['id', 'signal__outer_signal_id', 'signal__symbol', 'signal__techannel__abbr', ]
    list_filter = [
        SignalIDFilter,
        PointOuterIDFilter,
        PointTechannelFilter,
    ]






@admin.register(SignalOrig)
class SignalOrigAdmin(admin.ModelAdmin):
    list_display = ['id',
                    'symbol',
                    'position',
                    'leverage',
                    'entry_points',
                    'take_profits',
                    # 'e_points',
                    # 't_profits',
                    'stop_loss',
                    'techannel',
                    'outer_signal_id',
                    'sig_count',
                    'max_profit',
                    'max_loss',
                    'message_date',
                    'created',
                    ]
    select_related_fields = ['techannel', 'entry_points', 'take_profits', ]
    search_fields = ['id', 'outer_signal_id', 'symbol', 'techannel__abbr', ]
    list_filter = [
        OuterIDFilter,
        TechannelFilter,
    ]
    actions = [
        'bim_spot_create',
        'bim_futures_create',
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

    def get_queryset(self, request):
        qs = super(SignalOrigAdmin, self).get_queryset(request)
        qs = qs.annotate(sig_count=Count('market_signals'))

        # UNCOMMENT for only PostgreSQL
        # decrease in the number of requests
        # these and other correspondence e_points, t_profits places

        # qs = qs.annotate(t_profits=StringAgg(
        #     Cast('take_profits__value', output_field=CharField()),
        #     output_field=CharField(), delimiter='-', distinct=True))
        # qs = qs.annotate(e_points=StringAgg(
        #     Cast('entry_points__value', output_field=CharField()),
        #     output_field=CharField(), delimiter='-', distinct=True))

        # Annotate by max_loss and max_profit
        # max_loss (LONG) all buy orders have been worked and sell all by stop_loss
        # max_profit (LONG) all buy orders have been worked and sell all by all take_profits
        # for SHORT - reverse
        entry_points__count_sq = qs.filter(id=OuterRef('pk'))\
            .annotate(entry_points__cnt=Count('entry_points')).values('entry_points__cnt')

        qs_ep = qs.filter(id=OuterRef('pk'))\
            .annotate(ep_amoun=Sum(1 / (Subquery(entry_points__count_sq) * F('entry_points__value')),
                                   output_field=FloatField())).values('ep_amoun')

        take_profits__count_sq = qs.filter(id=OuterRef('pk')) \
            .annotate(take_profits__cnt=Count('take_profits')).values('take_profits__cnt')

        qs_tp = qs.filter(id=OuterRef('pk'))\
            .annotate(tp_amoun=Sum(F('take_profits__value') / Subquery(take_profits__count_sq),
                                   output_field=FloatField())).values('tp_amoun')

        qs = qs.annotate(max_loss=Abs((Subquery(qs_ep) * F('stop_loss') - 1) * 100))

        qs = qs.annotate(max_profit=Abs((Subquery(qs_ep) * Subquery(qs_tp) - 1) * 100))
        return qs

    def sig_count(self, obj):
        return obj.sig_count

    def max_profit(self, obj):
        return round(obj.max_profit, 2)

    def max_loss(self, obj):
        return round(obj.max_loss, 2)

    # def t_profits(self, obj):
    #     return obj.t_profits
    #
    # def e_points(self, obj):
    #     return obj.e_points

    @staticmethod
    def take_profits(signal):
        return ' - '.join([str(i.value) for i in signal.take_profits.all()])

    @staticmethod
    def entry_points(signal):
        return ' - '.join([str(i.value) for i in signal.entry_points.all()])

    def bim_spot_create(self, request, queryset):
        for signal in queryset:
            self._bim_spot_create_one(request, signal)

    def bim_futures_create(self, request, queryset):
        for signal in queryset:
            self._bim_futures_create_one(request, signal)

    @notifications_handling('')
    def _bim_spot_create_one(self, request, signal):
        market = get_or_create_market()
        signal.create_market_signal(market=market)

    @notifications_handling('')
    def _bim_futures_create_one(self, request, signal):
        market = get_or_create_futures_market()
        signal.create_market_signal(market=market)
