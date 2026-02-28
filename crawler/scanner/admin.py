from django.contrib import admin
from .models import ScanTask, ScanResult

admin.site.register(ScanTask)
admin.site.register(ScanResult)