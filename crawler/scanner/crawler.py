import asyncio
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
from playwright.async_api import async_playwright

class WebCrawler:
    def __init__(self, start_url, max_depth, max_pages=100000, max_concurrency=10):
        self.start_url = start_url
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.max_concurrency = max_concurrency 
        self.visited_urls = set()
        self.results = []
        self.robot_parser = None
        self.user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

    async def _setup_robot_parser(self, session):
        parsed_uri = urlparse(self.start_url)
        robots_url = f"{parsed_uri.scheme}://{parsed_uri.netloc}/robots.txt"
        self.robot_parser = RobotFileParser(robots_url)
        try:
            async with session.get(robots_url, timeout=5) as response:
                if response.status == 200:
                    text = await response.text()
                    self.robot_parser.parse(text.splitlines())
                else:
                    self.robot_parser.allow_all = True
        except Exception:
            self.robot_parser.allow_all = True

    def is_valid_url(self, url):
        parsed_start = urlparse(self.start_url)
        parsed_url = urlparse(url)
        return parsed_start.netloc == parsed_url.netloc

    async def _abort_unneeded_requests(self, route):
        # Дозволимо скриптам та XHR/Фетчам працювати, заблокуємо лише зайве
        if route.request.resource_type in ["image", "media", "font"]:
            await route.abort()
        else:
            await route.continue_()

    async def _fetch_with_aiohttp(self, session, url, source_url):
        try:
            headers = {'User-Agent': self.user_agent}
            async with session.get(url, headers=headers, timeout=10) as response:
                status_code = response.status
                content_type = response.headers.get('content-type', '')
                
                html_content = ""
                if status_code == 200 and 'text/html' in content_type:
                    html_content = await response.text()
                    
                return status_code, content_type, html_content
        except Exception:
            return None, None, None

    async def fetch_and_parse(self, session, browser_context, url, depth, source_url, queue):
        if depth > self.max_depth or url in self.visited_urls or len(self.visited_urls) >= self.max_pages:
            return

        self.visited_urls.add(url)
        
        # Спочатку намагаємось швидко отримати сторінку через aiohttp
        status_code, content_type, html_content = await self._fetch_with_aiohttp(session, url, source_url)
        
        # Якщо aiohttp не впорався (наприклад, 403 або 429 через anti-bot Cloudflare) або знайшов дуже мало контенту, чи взагалі помилка,
        # АБО сторінка виглядає як SPA базис (наприклад, мало тегів <a>, багато скриптів) - переходимо до Playwright
        needs_playwright = False
        
        if status_code is None or status_code in [403, 429, 503]:
            needs_playwright = True
        elif status_code == 200 and 'text/html' in content_type:
            soup = BeautifulSoup(html_content, 'html.parser')
            # Емпіричне правило: якщо посилань дуже мало, ймовірно це SPA (React/Vue/JS)
            if len(soup.find_all('a', href=True)) < 5:
                needs_playwright = True
                
        # Якщо можна обійтись aiohttp
        if not needs_playwright:
            if status_code is not None:
                self.results.append({
                    'source': source_url if source_url else 'Start',
                    'url': url,
                    'status': status_code,
                    'is_broken': status_code >= 400
                })
                if depth < self.max_depth and status_code == 200 and html_content:
                    self._extract_links(html_content, url, depth, queue)
            else:
                self.results.append({
                    'source': source_url if source_url else 'Start',
                    'url': url,
                    'status': 'Error',
                    'is_broken': True
                })
            return

        # ---- PLAYWRIGHT FALLBACK (ТІЛЬКИ ДЛЯ РЕАЛЬНОЇ ПОТРЕБИ) ----
        page = None
        try:
            page = await browser_context.new_page()
            await page.route("**/*", self._abort_unneeded_requests)
            
            # Зменшуємо таймаут, щоб не блокувати чергу назавжди
            response = await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            
            if getattr(self.robot_parser, 'allow_all', False) == False and not self.robot_parser.can_fetch(self.user_agent, url):
                # Навіть якщо роботс не пускає, Playwright все одно може зчитувати
                pass

            if not response:
                raise Exception("No response")

            status_code = response.status
            self.results.append({
                'source': source_url if source_url else 'Start',
                'url': url,
                'status': status_code,
                'is_broken': status_code >= 400
            })

            if depth < self.max_depth and status_code == 200 and len(self.visited_urls) < self.max_pages:
                content_type = response.headers.get('content-type', '')
                if 'text/html' in content_type:
                    html_content = await page.content()
                    self._extract_links(html_content, url, depth, queue)

        except Exception as e:
            self.results.append({
                'source': source_url if source_url else 'Start',
                'url': url,
                'status': 'Error',
                'is_broken': True
            })
        finally:
            if page:
                await page.close()

    def _extract_links(self, html_content, current_url, depth, queue):
        soup = BeautifulSoup(html_content, 'html.parser')

        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']

            if href.startswith(('#', 'mailto:', 'tel:', 'javascript:')):
                continue

            full_url = urljoin(current_url, href)

            if getattr(self.robot_parser, 'allow_all', False) or self.robot_parser.can_fetch(self.user_agent, full_url):
                if self.is_valid_url(full_url) and full_url not in self.visited_urls:
                    queue.put_nowait((full_url, depth + 1, current_url))

    async def worker(self, session, browser_context, queue):
        while True:
            url, depth, source_url = await queue.get()
            try:
                await self.fetch_and_parse(session, browser_context, url, depth, source_url, queue)
            finally:
                queue.task_done()

    async def crawl(self):
        queue = asyncio.Queue()

        async with aiohttp.ClientSession() as session:
            await self._setup_robot_parser(session)

            if getattr(self.robot_parser, 'allow_all', False) == False and not self.robot_parser.can_fetch(self.user_agent, self.start_url):
                pass

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(user_agent=self.user_agent)

                queue.put_nowait((self.start_url, 0, None))

                workers = [
                    asyncio.create_task(self.worker(session, context, queue))
                    for _ in range(self.max_concurrency)
                ]

                await queue.join()

                for w in workers:
                    w.cancel()
                    
                await context.close()
                await browser.close()

        return self.results
