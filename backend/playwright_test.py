from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from undetected_playwright import Malenia
from playwright_stealth import Stealth
import asyncio

url="https://siestasand.us/smith-throws-hat-in-the-ring-for-county-commission-race/"

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


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            timezone_id="America/New_York",
            ignore_https_errors=True,
            extra_http_headers=headers
        )
        # await Malenia.apply_stealth(context)
        page = await context.new_page()
        
        # Set a timeout for the page load
        response = await page.goto(url,wait_until='domcontentloaded')
        # await page.wait_for_load_state("networkidle")

            
        # Wait for the page to be fully loaded
        await page.wait_for_selector('body', timeout=30000)
            
        # Get page title and HTML content
        title = await page.title()
        content=await page.content()
        with open("content.html", "w", encoding="utf-8") as f:
            f.write(content)
        soup = BeautifulSoup(content, "html.parser")

        # Remove unwanted tags
        for tag in soup(["script", "style", "noscript", "img", "svg"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)

        with open("content.txt", "w", encoding="utf-8") as f:
            f.write(text)
        await browser.close()

asyncio.run(main())