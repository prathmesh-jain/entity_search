from playwright.sync_api import sync_playwright
from playwright.async_api import async_playwright
import asyncio
import random

headers = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "accept-encoding": "gzip, deflate, br, zstd",
    "accept-language": "en-US,en;q=0.9",
    "cache-control": "max-age=0",
    "sec-ch-ua": '"Google Chrome";v="120", "Chromium";v="120", "Not=A?Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1"
}

def bing_search_browser(query, page=1, num_results=10):
    first = (page - 1) * num_results + 1
    url = f"https://www.bing.com/search?q={query}&first={first}"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),extra_http_headers=headers,ignore_https_errors=True)
        page_obj = context.new_page()
        page_obj.goto(url,wait_until="domcontentloaded", timeout=60000)
        page_obj.wait_for_selector("li.b_algo h2 a", timeout=5000)

        elements = page_obj.query_selector_all("li.b_algo h2 a")
        results = [{"title": e.inner_text(), "link": e.get_attribute("href")} for e in elements]

        browser.close()
        return results

async def _search_with_playwright(query: str, max_results: int = 10):
        """Search using Playwright method with anti-detection measures."""
        results = []
        seen = set()
        
        page = 1
        results_per_page = 10
        
        while len(results) < max_results:
            # Create fresh browser instance for each page to avoid detection
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        '--no-sandbox',
                        '--disable-blink-features=AutomationControlled',
                        '--disable-web-security',
                        '--disable-features=VizDisplayCompositor'
                    ]
                )
                
                # Create new context with randomized properties
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                    viewport={"width": 1366 + random.randint(-100, 100), "height": 768 + random.randint(-50, 50)},
                    ignore_https_errors=True,
                    extra_http_headers={
                        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                        "accept-language": "en-US,en;q=0.9",
                        "cache-control": "no-cache",
                        "sec-ch-ua": '"Google Chrome";v="122", "Chromium";v="122", "Not=A?Brand";v="24"',
                        "sec-ch-ua-mobile": "?0",
                        "sec-ch-ua-platform": '"Windows"',
                        "sec-fetch-dest": "document",
                        "sec-fetch-mode": "navigate",
                        "sec-fetch-site": "none",
                        "sec-fetch-user": "?1",
                        "upgrade-insecure-requests": "1"
                    }
                )
                
                try:
                    page_obj = await context.new_page()
                    
                    # Remove automation indicators
                    await page_obj.add_init_script("""
                        Object.defineProperty(navigator, 'webdriver', {
                            get: () => undefined,
                        });
                        
                        window.chrome = {
                            runtime: {},
                        };
                        
                        Object.defineProperty(navigator, 'plugins', {
                            get: () => [1, 2, 3, 4, 5],
                        });
                        
                        Object.defineProperty(navigator, 'languages', {
                            get: () => ['en-US', 'en'],
                        });
                    """)
                    
                    remaining = max_results - len(results)
                    first = (page - 1) * results_per_page + 1
                    url = f"https://www.bing.com/search?q={query}&first={first}"
                    
                    print(f"Making Bing request: page={page}, first={first}, remaining={remaining}")
                    
                    # Navigate with random delay
                    await asyncio.sleep(random.uniform(2, 4))
                    await page_obj.goto(url, wait_until="domcontentloaded", timeout=60000)
                    
                    # Random mouse movement to simulate human behavior
                    await page_obj.mouse.move(random.randint(100, 500), random.randint(100, 400))
                    await asyncio.sleep(random.uniform(1, 2))
                    
                    try:
                        await page_obj.wait_for_selector("li.b_algo h2 a", timeout=10000)
                    except:
                        print(f"Timeout waiting for results on page {page}")
                        break
                    
                    elements = await page_obj.query_selector_all("li.b_algo h2 a")
                    
                    if not elements:
                        print(f"No more results found on page {page}")
                        break
                    
                    page_results = []
                    for element in elements:
                        try:
                            link = await element.get_attribute("href")
                            if link and isinstance(link, str):
                                clean = link
                                if clean not in seen:
                                    seen.add(clean)
                                    page_results.append({"url": clean, "source": "bing"})
                                    
                                    if len(results) + len(page_results) >= max_results:
                                        break
                        except Exception as e:
                            print(f"Error extracting link from element: {e}")
                            continue
                    
                    results.extend(page_results)
                    print(f"Found {len(page_results)} results on page {page}")
                    
                    # If we got fewer results than expected, we've reached the end
                    if len(page_results) < results_per_page:
                        print(f"Received fewer results ({len(page_results)}) than expected, stopping pagination")
                        break
                    
                    page += 1
                    
                finally:
                    await browser.close()
                
                # Longer delay between pages to avoid detection
                if len(results) < max_results:
                    await asyncio.sleep(random.uniform(8, 15))
        
        print(f"Found {len(results)} results from Bing (Playwright) for: {query}")
        return results


if __name__ == "__main__":
    # for r in bing_search_browser("Ashley Smith Daughter of Mark Smith(Commisioner of County Commision of Sarasota, Florida)", page=1):
    #     print(r)
    # for r in bing_search_browser("Ashley Smith Daughter of Mark Smith(Commisioner of County Commision of Sarasota, Florida)", page=2):
    #     print(r)
    for r in asyncio.run(_search_with_playwright("Ashley Smith Daughter of Mark Smith(Commisioner of County Commision of Sarasota, Florida)", max_results=30)):
        print(r)
