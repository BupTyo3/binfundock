from django.contrib import admin
from django.utils.translation import ugettext_lazy as _

from utils.admin import InputFilter
from .models import (
    BuyOrder,
    SellOrder,
    HistoryApiBuyOrder,
    HistoryApiSellOrder,
)


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


class OuterIDFilter(InputFilter):
    parameter_name = 'outer_id'
    title = _('Outer_ID')

    def queryset(self, request, queryset):
        if self.value() is not None:
            try:
                outer_id = self.value()
            except ValueError:
                return queryset
            return queryset.filter(signal__outer_signal_id=outer_id)


class TechannelFilter(InputFilter):
    parameter_name = 'techannel_abbr'
    title = _('Techannel_Abbr')

    def queryset(self, request, queryset):
        if self.value() is not None:
            try:
                techannel_abbr = self.value()
            except ValueError:
                return queryset
            return queryset.filter(signal__techannel__abbr=techannel_abbr)


class OrderIDFilter(InputFilter):
    parameter_name = 'order_id'
    title = _('Order_ID')

    def queryset(self, request, queryset):
        if self.value() is not None:
            try:
                order_id = self.value()
            except ValueError:
                return queryset
            return queryset.filter(main_order=order_id)


class CustomOrderIDFilter(InputFilter):
    parameter_name = 'custom_id'
    title = _('CustomOrder_ID')

    def queryset(self, request, queryset):
        if self.value() is not None:
            try:
                custom_id = self.value()
            except ValueError:
                return queryset
            return queryset.filter(main_order__custom_order_id=custom_id)


@admin.register(BuyOrder)
class BuyOrderAdmin(admin.ModelAdmin):
    list_display = ['id',
                    'symbol',
                    'signal_status',
                    'price',
                    'quantity',
                    'bought_quantity',
                    # 'stop_loss',
                    'custom_order_id',
                    'index',
                    'push_count',
                    'status',
                    'handled_worked',
                    'local_canceled',
                    'local_canceled_time',
                    'last_updated_by_api',
                    ]
    select_related_fields = ['signal', ]
    search_fields = ['id', 'custom_order_id', 'signal__outer_signal_id', 'symbol', ]
    list_filter = [
        '_status',
        'signal___status',
        SignalIDFilter,
        OuterIDFilter,
        TechannelFilter,
    ]

    @staticmethod
    def signal_status(order):
        return order.signal.status


@admin.register(SellOrder)
class SellOrderAdmin(admin.ModelAdmin):
    list_display = ['id',
                    'symbol',
                    'signal_status',
                    'price',
                    'quantity',
                    'sold_quantity',
                    'stop_loss',
                    'custom_order_id',
                    'index',
                    'push_count',
                    'status',
                    'handled_worked',
                    'local_canceled',
                    'local_canceled_time',
                    'last_updated_by_api',
                    ]
    select_related_fields = ['signal', ]
    search_fields = ['id', 'custom_order_id', 'signal__outer_signal_id', 'symbol', ]
    list_filter = [
        '_status',
        'signal___status',
        SignalIDFilter,
        OuterIDFilter,
        TechannelFilter,
    ]

    @staticmethod
    def signal_status(order):
        return order.signal.status


@admin.register(HistoryApiBuyOrder)
class HistoryApiBuyOrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'main_order', 'status', 'bought_quantity',
                    'created',
                    ]
    select_related_fields = ['main_order', ]
    search_fields = ['id', 'main_order__custom_order_id', 'main_order__symbol', ]
    list_filter = [
        'status',
        OrderIDFilter,
        CustomOrderIDFilter,
        ]


@admin.register(HistoryApiSellOrder)
class HistoryApiSellOrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'main_order', 'status', 'sold_quantity',
                    'created',
                    ]
    select_related_fields = ['main_order', ]
    search_fields = ['id', 'main_order__custom_order_id', 'main_order__symbol', ]
    list_filter = [
        'status',
        OrderIDFilter,
        CustomOrderIDFilter,
    ]
