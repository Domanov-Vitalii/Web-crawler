import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

class WebCrawler:
    def __init__(self, start_url, max_depth):
        self.start_url = start_url
        self.max_depth = max_depth
        self.visited_urls = set()
        self.results = []

    def is_valid_url(self, url):
        """
        Перевіряє, чи посилання належить до того ж домену, що й стартовий URL.
        Це потрібно, щоб краулер не пішов гуляти по всьому інтернету.
        """
        parsed_start = urlparse(self.start_url)
        parsed_url = urlparse(url)
        return parsed_start.netloc == parsed_url.netloc

    def crawl(self):
        """
        Основний метод обходу в ширину (Breadth-First Search).
        Використовує чергу для поступового заглиблення.
        """
        queue = [(self.start_url, 0, None)]

        while queue:
            current_url, depth, source_url = queue.pop(0)
            if depth > self.max_depth or current_url in self.visited_urls:
                continue

            self.visited_urls.add(current_url)
            print(f"[{depth}] Перевірка: {current_url}")

            try:
                response = requests.get(current_url, timeout=5)
                status_code = response.status_code
                
                self.results.append({
                    'source': source_url if source_url else 'Start',
                    'url': current_url,
                    'status': status_code,
                    'is_broken': status_code >= 400
                })

                if depth < self.max_depth and status_code == 200 and 'text/html' in response.headers.get('Content-Type', ''):
                    self._extract_links(response.text, current_url, depth, queue)

            except requests.RequestException as e:
                self.results.append({
                    'source': source_url,
                    'url': current_url,
                    'status': 'Error (Timeout/DNS)',
                    'is_broken': True
                })

        return self.results

    def _extract_links(self, html_content, current_url, depth, queue):
        """
        Парсить HTML, знаходить всі <a> теги, формує правильні абсолютні посилання
        і додає їх у чергу для подальшої перевірки.
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']

            if href.startswith('#') or href.startswith('mailto:') or href.startswith('tel:'):
                continue

            full_url = urljoin(current_url, href)

            if self.is_valid_url(full_url) and full_url not in self.visited_urls:
                 queue.append((full_url, depth + 1, current_url))