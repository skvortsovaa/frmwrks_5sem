"""Реальное обновление старой схемы с сохранением исторических измерений."""

import subprocess
import sys

import pytest


@pytest.mark.parametrize("conflict", [False, True])
def test_normalization_migration_preserves_data_or_rolls_back(
        tmp_path, conflict):
    code = '''
import os, sys
os.environ['DJANGO_SETTINGS_MODULE'] = 'smartspace_web.settings'
from django.conf import settings
settings.DATABASES['default']['NAME'] = sys.argv[1]
import django
django.setup()
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone
call_command('migrate', 'rooms_web', '0002', verbosity=0)
call_command('migrate', 'sensors_web', '0002', verbosity=0)
call_command('migrate', 'reports_web', '0003', verbosity=0)
executor = MigrationExecutor(connection)
apps = executor.loader.project_state([
    ('rooms_web', '0002_pr10_admin_fields'),
    ('sensors_web', '0002_pr10_admin_fields'),
    ('reports_web', '0003_pr10_relation_labels'),
]).apps
Room = apps.get_model('rooms_web', 'Room')
Sensor = apps.get_model('sensors_web', 'Sensor')
Metric = apps.get_model('reports_web', 'Metric')
Report = apps.get_model('reports_web', 'Report')
Reading = apps.get_model('reports_web', 'Reading')
room = Room.objects.create(name='History', floor=1, area=25, slug='history')
sensor = Sensor.objects.create(id='S', room=room, active=True, battery=85)
for key, low, high in [('temperature', 18, 24), ('humidity', 40, 60),
                       ('leak', 0, 0)]:
    Metric.objects.create(id=key, name=key, unit='unit',
                          minimum=low, maximum=high)
report = Report.objects.create(
    id='R', room=room, room_name='Historical name',
    checked_at=timezone.now(), sensor_active=True, battery=85,
    temperature_value=30, temperature_minimum=18, temperature_maximum=24,
    temperature_normal=False, humidity_value=50, humidity_minimum=40,
    humidity_maximum=60, humidity_normal=True, leak_detected=False,
    status='ПРЕДУПРЕЖДЕНИЕ',
)
Reading.objects.create(
    id='original-reading', sensor=sensor, report=report,
    metric_id='temperature', measured_at=report.checked_at,
    value=32 if sys.argv[2] == 'True' else 30,
    minimum=18, maximum=24, status='ПРЕДУПРЕЖДЕНИЕ',
)
Report.objects.create(
    id='empty', room=room, room_name='Historical name',
    checked_at=timezone.now(), sensor_active=False, battery=0,
    status='НЕТ ДАННЫХ',
)
if sys.argv[2] == 'True':
    try:
        call_command('migrate', verbosity=0)
    except ValueError as error:
        assert 'расходятся' in str(error)
    else:
        raise AssertionError('Conflicting copies must stop the migration')
    assert Report.objects.get(pk='R').temperature_value == 30
    assert Reading.objects.count() == 1
    assert not connection.cursor().execute(
        "SELECT 1 FROM django_migrations WHERE app='reports_web' "
        "AND name='0004_normalize_report_readings'"
    ).fetchone()
    sys.exit(0)
call_command('migrate', verbosity=0)
from reports_web.models import Report as NewReport, Reading as NewReading
r = NewReport.objects.get(pk='R')
assert r.room_name == 'Historical name' and r.battery == 85
assert r.temperature['value'] == 30 and r.humidity['value'] == 50
assert r.leak_detected is False
r.validate_readings()
assert NewReading.objects.count() == 3
assert NewReading.objects.filter(pk='original-reading').exists()
assert NewReport.objects.get(pk='empty').temperature is None
columns = [col.name for col in connection.introspection.get_table_description(
    connection.cursor(), 'reports_web_report')]
assert 'temperature_value' not in columns and 'leak_detected' not in columns
call_command('migrate', 'reports_web', '0003', verbosity=0)
old = Report.objects.get(pk='R')
assert old.temperature_value == 30 and old.humidity_value == 50
assert old.leak_detected is False
call_command('migrate', verbosity=0)
assert NewReading.objects.count() == 3
assert connection.cursor().execute(
    'PRAGMA integrity_check').fetchone()[0] == 'ok'
assert not connection.cursor().execute('PRAGMA foreign_key_check').fetchall()
'''
    result = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path / "upgrade.sqlite3"),
         str(conflict)], capture_output=True, text=True, encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, result.stdout + result.stderr
