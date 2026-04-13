import csv
from collections import Counter
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.decorators import login_required
from .crawler import WebCrawler
from .models import ScanTask, ScanResult
from .tasks import run_crawler_task


def register_view(request):
    """Обробка сторінки реєстрації"""
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('scanner:index')
    else:
        form = UserCreationForm()
    return render(request, 'scanner/register.html', {'form': form})

@login_required
def home_view(request):
    """Головна сторінка зі сканером"""
    if request.method == 'POST':
        start_url = request.POST.get('url')
        max_depth = int(request.POST.get('depth', 1))

        task = ScanTask.objects.create(
            user=request.user,
            target_url=start_url,
            depth=max_depth,
            status='PENDING'
        )
        run_crawler_task.delay(task.id)
        return redirect('scanner:history')

    return render(request, 'scanner/index.html')

@login_required
def download_report_view(request, task_id):
    """Генерує CSV файл на основі збережених даних у базі"""
    task = get_object_or_404(ScanTask, id=task_id, user=request.user)
    
    if not hasattr(task, 'result') or not task.result.raw_data:
        return redirect('scanner:history')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="broken_links_{task.id}.csv"'
    
    writer = csv.DictWriter(response, fieldnames=['source', 'url', 'status', 'is_broken'])
    writer.writeheader()
    for row in task.result.raw_data:
        writer.writerow(row)

    return response

@login_required
def history_view(request):
    """Сторінка з історією сканувань поточного користувача"""
    tasks = ScanTask.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'scanner/history.html', {'tasks': tasks})

@login_required
def report_details_view(request, task_id):
    """Сторінка з графіками та деталями конкретного сканування"""
    task = get_object_or_404(ScanTask, id=task_id, user=request.user)
    
    if not hasattr(task, 'result') or not task.result.raw_data:
        return redirect('scanner:history')

    raw_data = task.result.raw_data
    
    broken_links = [row for row in raw_data if row.get('is_broken')]
    
    status_counts = Counter(str(row.get('status', 'Error')) for row in raw_data)
    
    context = {
        'task': task,
        'broken_links': broken_links,
        'working_count': task.result.total_unique_links - task.result.broken_links_count,
        'broken_count': task.result.broken_links_count,
        'status_labels': list(status_counts.keys()),
        'status_values': list(status_counts.values()),
    }
    
    return render(request, 'scanner/report_details.html', context)


@login_required
def pending_tasks_api(request):
    """API endpoint to get the status of pending or currently running tasks for dynamic UI updates"""
    task_ids = request.GET.get('task_ids')
    
    if task_ids:
        # Check specific tasks
        ids = [int(x) for x in task_ids.split(',') if x.isdigit()]
        tasks = ScanTask.objects.filter(user=request.user, id__in=ids)
    else:
        # Check all pending/running tasks by default
        tasks = ScanTask.objects.filter(user=request.user, status__in=['PENDING', 'RUNNING'])
        
    data = []
    for t in tasks:
        item = {
            'id': t.id,
            'status': t.status,
            'target_url': t.target_url,
        }
        if t.status == 'COMPLETED' and hasattr(t, 'result'):
            item['total'] = t.result.total_unique_links
            item['broken'] = t.result.broken_links_count
        elif t.status == 'FAILED' and hasattr(t, 'result'):
            item['total'] = 0
            item['broken'] = 0

        data.append(item)
        
    return JsonResponse({'tasks': data})