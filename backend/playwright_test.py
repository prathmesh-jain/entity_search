from playwright.sync_api import sync_playwright

url="https://www.ministeriopublico.gov.py/nota/caso-mocipar-fiscales-acusan-y-solicitan-juicio-oral-y-publico-para-los-supuestos-13671"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context=browser.new_context(ignore_https_errors=True)
    page = context.new_page()
    page.goto(url,wait_until="domcontentloaded")
    page.wait_for_selector("body",timeout=30000)
    content = page.content()
    print(page.title())
    browser.close()
