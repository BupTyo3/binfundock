from django.contrib import admin
from .models import CronTask

@admin.register(CronTask)
class CronTaskAdmin(admin.ModelAdmin):
    list_display = ['id',
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



