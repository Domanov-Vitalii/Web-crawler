import csv
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.decorators import login_required
from .crawler import WebCrawler
from .models import ScanTask, ScanResult

def register_view(request):
    """Обробка сторінки реєстрації"""
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('home')
    else:
        form = UserCreationForm()
    return render(request, 'scanner/register.html', {'form': form})

@login_required
def home_view(request):
    if request.method == 'POST':
        start_url = request.POST.get('url')
        max_depth = int(request.POST.get('depth', 1))

        task = ScanTask.objects.create(user=request.user, target_url=start_url, depth=max_depth, status='RUNNING')
        
        crawler = WebCrawler(start_url=start_url, max_depth=max_depth)
        results = crawler.crawl()

        total_links = len(results)
        broken_links = sum(1 for r in results if r['is_broken'])

        task.status = 'COMPLETED'
        task.save()

        ScanResult.objects.create(task=task, total_unique_links=total_links, broken_links_count=broken_links, raw_data=results)

        return redirect('history')

    return render(request, 'scanner/index.html')

@login_required
def download_report_view(request, task_id):
    """Генерує CSV файл на основі збережених даних у базі"""
    task = get_object_or_404(ScanTask, id=task_id, user=request.user)
    
    if not hasattr(task, 'result') or not task.result.raw_data:
        return redirect('history')

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