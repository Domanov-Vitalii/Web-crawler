from django.db import models
from django.contrib.auth.models import User

class ScanTask(models.Model):
    """Модель для зберігання завдання на сканування (1-to-M з User)"""
    STATUS_CHOICES = [
        ('PENDING', 'Очікує'),
        ('RUNNING', 'Виконується'),
        ('COMPLETED', 'Завершено'),
        ('FAILED', 'Помилка'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='scan_tasks')

    target_url = models.URLField(max_length=1000, verbose_name="Стартовий URL")
    depth = models.PositiveIntegerField(default=1, verbose_name="Глибина сканування")
    
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Час створення")

    def __str__(self):
        return f"Task {self.id} | {self.target_url} ({self.status})"


class ScanResult(models.Model):
    """Модель для зберігання результатів обходу (1-to-1 з ScanTask)"""
    task = models.OneToOneField(ScanTask, on_delete=models.CASCADE, related_name='result')

    total_unique_links = models.PositiveIntegerField(default=0, verbose_name="Всього унікальних посилань")
    broken_links_count = models.PositiveIntegerField(default=0, verbose_name="Кількість битих")
    
    raw_data = models.JSONField(null=True, blank=True, verbose_name="Детальні результати")

    finished_at = models.DateTimeField(auto_now_add=True, verbose_name="Час завершення")

    def __str__(self):
        return f"Result for Task {self.task.id}"