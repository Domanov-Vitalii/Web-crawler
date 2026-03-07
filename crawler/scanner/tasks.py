import asyncio
from celery import shared_task
from .models import ScanTask, ScanResult
from .crawler import WebCrawler

@shared_task
def run_crawler_task(task_id):
    """Ця функція виконується у фоні воркером Celery"""
    try:
        task = ScanTask.objects.get(id=task_id)
        task.status = 'RUNNING'
        task.save()

        crawler = WebCrawler(start_url=task.target_url, max_depth=task.depth)

        results = asyncio.run(crawler.crawl())

        total_links = len(results)
        broken_links = sum(1 for r in results if r['is_broken'])

        ScanResult.objects.create(
            task=task,
            total_unique_links=total_links,
            broken_links_count=broken_links,
            raw_data=results
        )

        task.status = 'COMPLETED'
        task.total_links = total_links
        task.broken_links = broken_links
        task.save()

    except Exception as e:
        task = ScanTask.objects.get(id=task_id)
        task.status = 'FAILED'
        task.save()