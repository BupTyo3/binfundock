from django.contrib import admin

from .models import CronTask


@admin.register(CronTask)
class CronTaskAdmin(admin.ModelAdmin):
    list_display = ['id',
                    'form_buy_orders_enabled',
                    'push_job_enabled',
                    'pull_job_enabled',
                    'bought_worker_enabled',
                    'sold_worker_enabled',
                    ]

