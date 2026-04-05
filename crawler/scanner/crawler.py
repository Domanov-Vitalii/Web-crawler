import asyncio
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

class WebCrawler:
    def __init__(self, start_url, max_depth, max_pages=100000, max_concurrency=20):
        self.start_url = start_url
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.max_concurrency = max_concurrency
        self.visited_urls = set()
        self.results = []
        self.robot_parser = None
        self.user_agent = '*'

    async def _setup_robot_parser(self, session):
        """Завантажує та налаштовує парсер для robots.txt."""
        parsed_uri = urlparse(self.start_url)
        robots_url = f"{parsed_uri.scheme}://{parsed_uri.netloc}/robots.txt"
        self.robot_parser = RobotFileParser(robots_url)
        try:
            async with session.get(robots_url, timeout=5) as response:
                if response.status == 200:
                    text = await response.text()
                    self.robot_parser.parse(text.splitlines())
                else:
                    # Якщо robots.txt не знайдено, дозволяємо все
                    self.robot_parser.allow_all = True
        except Exception:
            # У разі помилки, дозволяємо все
            self.robot_parser.allow_all = True

    def is_valid_url(self, url):
        """Перевіряє, чи посилання веде на той самий домен"""
        parsed_start = urlparse(self.start_url)
        parsed_url = urlparse(url)
        return parsed_start.netloc == parsed_url.netloc

    async def fetch_and_parse(self, session, url, depth, source_url, queue):
        """Асинхронно завантажує сторінку та шукає нові лінки"""
        if depth > self.max_depth or url in self.visited_urls or len(self.visited_urls) >= self.max_pages:
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

                if depth < self.max_depth and status_code == 200 and len(self.visited_urls) < self.max_pages:
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
            
            if self.robot_parser.can_fetch(self.user_agent, full_url) and self.is_valid_url(full_url) and full_url not in self.visited_urls:
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
        
        async with aiohttp.ClientSession() as session:
            await self._setup_robot_parser(session)

            if not self.robot_parser.can_fetch(self.user_agent, self.start_url):
                print(f"Crawling is disallowed by robots.txt for the start URL: {self.start_url}")
                return self.results

            queue.put_nowait((self.start_url, 0, None))

            workers = [
                asyncio.create_task(self.worker(session, queue))
                for _ in range(self.max_concurrency)
            ]

            await queue.join()

            for w in workers:
                w.cancel()
        
        return self.results