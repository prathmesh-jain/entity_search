from playwright.sync_api import sync_playwright
import time
import random

def yahoo_search_playwright(query: str, page_num: int = 1, results_per_page: int = 10):
    """
    Search Yahoo with Playwright, return a list of {title, link} dicts.
    Uses XPath based on observed structure.
    page_num starts from 1.
    """
    # Calculate which result to start from
    # Yahoo uses `b=` parameter: start index, 1-based
    start = (page_num - 1) * results_per_page + 1
    
    search_url = f"https://search.yahoo.com/search?p={query}&b={start}"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # You can try using firefox or webkit if needed
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800}
        )
        page = context.new_page()
        page.goto(search_url, timeout=60000)

        # wait for something that signals results have loaded
        # Using a generic selector that matches result items, adjust if fails
        try:
            page.wait_for_selector('xpath=//*[@id="web"]/ol/li[1]/div/div[1]/a', timeout=10000)
        except:
            print("Timeout waiting for first result link. Page may not be loaded properly.")
            # maybe return empty or fallback
            context.close()
            browser.close()
            return []

        results = []
        # Loop over the first results_per_page results, using XPath pattern
        for i in range(1, results_per_page + 1):
            # Build the XPath for the i-th result
            xpath = f'//*[@id="web"]/ol/li[{i}]/div/div[1]/a'
            # Try to get the element
            try:
                element_handle = page.query_selector(f'xpath={xpath}')
                if element_handle:
                    link = element_handle.get_attribute('href')
                    title = element_handle.inner_text().strip()
                    results.append({"title": title, "link": link})
                else:
                    # optionally log that the particular result wasn't found
                    # (maybe because Yahoo changed layout or fewer results)
                    # print(f"Result {i} not found with XPath: {xpath}")
                    pass
            except Exception as e:
                # log or skip
                # print(f"Error for result {i}: {e}")
                pass

        # Sleep a little to mimic human browsing
        time.sleep(random.uniform(2, 5))
        
        context.close()
        browser.close()
        return results

if __name__ == "__main__":
    q = "openai"
    for page_n in [1, 2]:
        res = yahoo_search_playwright(q, page_num=page_n, results_per_page=10)
        print(f"Page {page_n}:")
        for item in res:
            print(" -", item)
