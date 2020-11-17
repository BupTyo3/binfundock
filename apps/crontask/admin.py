from django.contrib import admin
from .models import CronTask


@admin.register(CronTask)
class CronTaskAdmin(admin.ModelAdmin):
    list_display = ['id',
                    'balance_to_signal_perc',
                    'slip_delta_sl_perc',
                    'first_forming_enabled',
                    'push_job_enabled',
                    'pull_job_enabled',
                    'bought_worker_enabled',
                    'sold_worker_enabled',
                    'spoil_worker_enabled',
                    'close_worker_enabled',

                    'ai_algorithm',
                    'crypto_passive',
                    'assist_leverage',
                    'assist_altcoin',
                    'assist_origin',
                    'white_bull',
                    ]

    actions = [
        'balance_coef_plus_5',
        'balance_coef_plus_10',
        'balance_coef_minus_5',
        'balance_coef_minus_10',
    ]

    def balance_coef_plus_10(self, request, queryset):
        value = 10
        for cron_task in queryset:
            self._change_balance_coefficient_one(request, cron_task, value)

    def balance_coef_minus_10(self, request, queryset):
        value = -10
        for cron_task in queryset:
            self._change_balance_coefficient_one(request, cron_task, value)

    def balance_coef_plus_5(self, request, queryset):
        value = 5
        for cron_task in queryset:
            self._change_balance_coefficient_one(request, cron_task, value)

    def balance_coef_minus_5(self, request, queryset):
        value = -5
        for cron_task in queryset:
            self._change_balance_coefficient_one(request, cron_task, value)

    def _change_balance_coefficient_one(self, request, cron_task, value):
        cron_task.change_balance_coefficient(value)

    def has_delete_permission(self, request, obj=None):
        #Disable delete
        return False
