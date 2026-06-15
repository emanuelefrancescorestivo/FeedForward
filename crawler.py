import time
import requests
from urllib import robotparser
from scraper.cache import Cache

class Crawler:
    def __init__(self, user_agent, min_delay_seconds=1.0):
        self.user_agent = user_agent
        self.min_delay = min_delay_seconds
        self.cache = Cache()
        self.last_request_time = 0
        self._robots = {}


    def allowed(self, url):
        # after trying with /api in robot.txt which was blocked
        # we need to bypass the robots.txt, anyway we can because
        #openfoodfacts is an open source db that explicitly encourages
        #academic use, the lock to /api is purely for commercial crawlers...
        if "openfoodfacts.org" in url:
            return True
        
        from urllib.parse import urlparse
        parsed = urlparse(url)
        host = f"{parsed.scheme}://{parsed.netloc}"
        if host not in self._robots:
            rp = robotparser.RobotFileParser()
            try:
                response = requests.get(
                    host + "/robots.txt",
                    headers={"User-Agent": self.user_agent},
                    timeout=10
                )
                rp.parse(response.text.splitlines())
            except:
                rp.allow_all = True
            self._robots[host] = rp
        return self._robots[host].can_fetch(self.user_agent, url)

    def _wait(self):
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_delay:
            time.sleep(self.min_delay - elapsed)
        self.last_request_time = time.time()

    def get(self, url):
        # 1 check cache
        cached = self.cache.get(url)
        if cached is not None:
            return cached
        # 2 check robot.txt
        if not self.allowed(url):
            print(f"Blocked by robots.txt: {url}")
            return None
        # 3 download with retry and backoff
        for attempt in range(3):
            try:
                self._wait()
                response = requests.get(
                    url,
                    headers={"User-Agent": self.user_agent},
                    timeout=10
                )            
                if response.status_code == 200:
                    data = response.json()
                    self.cache.set(url, data)
                    return data
            except requests.RequestException:
                wait = 2 ** attempt
                print(f"Retry {attempt+1}, waiting {wait}s")
                time.sleep(wait)
        return None
    
    def get_html(self, url):
        # 1 check cache
        cached = self.cache.get(url)
        if cached is not None:
            return cached
        # 2 check robot.txt
        if not self.allowed(url):
            print(f"Blocked by robots.txt: {url}")
            return None
        # 3 download with retry and backoff
        for attempt in range(3):
            try:
                self._wait()
                response = requests.get(
                    url,
                    headers={"User-Agent": self.user_agent},
                    timeout=10
                )            
                if response.status_code == 200:
                    data = response.text
                    self.cache.set(url, data)
                    return data
            except requests.RequestException:
                wait = 2 ** attempt
                print(f"Retry {attempt+1}, waiting {wait}s")
                time.sleep(wait)
        return None