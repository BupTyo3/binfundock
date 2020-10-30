
from django.db import transaction, migrations, models
import django.utils.timezone

from apps.market.models import get_or_create_market


def copy_to_signal_orig(apps, schema_editor):
    Signal = apps.get_model('signal', 'Signal')
    SignalOrig = apps.get_model('signal', 'SignalOrig')
    EntryPointOrig = apps.get_model('signal', 'EntryPointOrig')
    TakeProfitOrig = apps.get_model('signal', 'TakeProfitOrig')

    signals = Signal.objects.all()
    for signal in signals:
        so = SignalOrig.objects.create(
            techannel=signal.techannel,
            symbol=signal.symbol,
            stop_loss=signal.stop_loss,
            outer_signal_id=signal.outer_signal_id,
            position=signal.position,
            leverage=signal.leverage,
            message_date=signal.message_date)
        for ep in signal.entry_points.all():
            EntryPointOrig.objects.create(signal=so, value=ep.value)
        for tp in signal.take_profits.all():
            TakeProfitOrig.objects.create(signal=so, value=tp.value)
        signal.signal_orig = so
        signal.save()


def fill_signal_by_market_default(apps, schema_editor):
    Signal = apps.get_model('signal', 'Signal')

    signals = Signal.objects.all()
    signals.update(market=get_or_create_market())


class Migration(migrations.Migration):

    dependencies = [
        ('signal', '0007_auto_20201021_1128'),
    ]

    operations = [

        migrations.RunPython(
            code=fill_signal_by_market_default,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.RunPython(
            code=copy_to_signal_orig,
            reverse_code=migrations.RunPython.noop,
        ),

    ]
