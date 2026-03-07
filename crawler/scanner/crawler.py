import asyncio
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

class WebCrawler:
    def __init__(self, start_url, max_depth, max_concurrency=20):
        self.start_url = start_url
        self.max_depth = max_depth
        self.max_concurrency = max_concurrency
        self.visited_urls = set()
        self.results = []

    def is_valid_url(self, url):
        """Перевіряє, чи посилання веде на той самий домен"""
        parsed_start = urlparse(self.start_url)
        parsed_url = urlparse(url)
        return parsed_start.netloc == parsed_url.netloc

    async def fetch_and_parse(self, session, url, depth, source_url, queue):
        """Асинхронно завантажує сторінку та шукає нові лінки"""
        if depth > self.max_depth or url in self.visited_urls:
            return

        self.visited_urls.add(url)

        try:
            async with session.get(url, timeout=10) as response:
                status_code = response.status

                self.results.append({
                    'source': source_url if source_url else 'Start',
                    'url': url,
                    'status': status_code,
                    'is_broken': status_code >= 400
                })

                if depth < self.max_depth and status_code == 200:
                    content_type = response.headers.get('Content-Type', '')
                    if 'text/html' in content_type:
                        html_content = await response.text()
                        self._extract_links(html_content, url, depth, queue)
        except Exception as e:
            self.results.append({
                'source': source_url if source_url else 'Start',
                'url': url,
                'status': 'Error',
                'is_broken': True
            })

    def _extract_links(self, html_content, current_url, depth, queue):
        """Синхронний парсинг HTML за допомогою BeautifulSoup"""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            
            if href.startswith(('#', 'mailto:', 'tel:', 'javascript:')):
                continue
                
            full_url = urljoin(current_url, href)
            
            if self.is_valid_url(full_url) and full_url not in self.visited_urls:
                queue.put_nowait((full_url, depth + 1, current_url))

    async def worker(self, session, queue):
        """Воркер, який безперервно бере задачі з черги і виконує їх"""
        while True:
            url, depth, source_url = await queue.get()
            try:
                await self.fetch_and_parse(session, url, depth, source_url, queue)
            finally:
                queue.task_done()

    async def crawl(self):
        """Головна точка входу для запуску асинхронного сканування"""
        queue = asyncio.Queue()
        queue.put_nowait((self.start_url, 0, None))

        async with aiohttp.ClientSession() as session:
            workers = [
                asyncio.create_task(self.worker(session, queue))
                for _ in range(self.max_concurrency)
            ]

            await queue.join()

            for w in workers:
                w.cancel()
        
        return self.results