import requests
from loguru import logger
from playwright.sync_api import sync_playwright


def login(
    user: str,
    password: str,
    url: str = "https://login.personio.com/u/login/identifier",
    company_hash: str = ""
) -> dict[str, str]:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        logger.info("🌐 Navigating to login.personio.com...")
        page.goto(
            f"{url}?state={company_hash}",
            wait_until="networkidle",
        )

        try:
            logger.info("⌛ Waiting for email input...")
            page.wait_for_selector('input[name="username"]', timeout=10000)
        except TimeoutError:
            logger.error("❌ Email field not found. Taking screenshot.")
            page.screenshot(path="error_screenshot.png")
            browser.close()
            return {}

        logger.info("📧 Entering email...")
        page.fill('input[name="username"]', user)
        page.click('button[type="submit"]')

        try:
            logger.info("⌛ Waiting for password field...")
            page.wait_for_selector('input[name="password"]', timeout=10000)
        except TimeoutError:
            logger.error("❌ Password field not found. Taking screenshot.")
            page.screenshot(path="error_password.png")
            browser.close()
            return {}

        logger.info("🔑 Entering password...")
        page.fill('input[name="password"]', password)
        page.click('button[type="submit"]')

        logger.info("⏳ Waiting for post-login page to load...")
        try:
            page.wait_for_load_state("networkidle")
        except TimeoutError:
            logger.error("❌ Post-login page did not load in time. Taking screenshot.")
            page.screenshot(path="error_postlogin.png")
            browser.close()
            return {}
        logger.success("✅ Login successful. Cookies saved.")

        cookies = {cookie["name"]: cookie["value"] for cookie in context.cookies()}
        browser.close()
        return cookies


def get_projects(session: requests.Session, projects_url: str) -> requests.Response:
    response = session.get(projects_url, headers={"Accept": "application/json"})
    logger.debug("Projects:")
    logger.trace(f"Headers: {str(response.headers)}\nResponse:{response.text[:256]}\n")
    return response


if __name__ == "__main__":
    from config import EMAIL, PASSWORD, COMPANY_HASH, LOGIN_URL
    login(user=EMAIL, password=PASSWORD, url=LOGIN_URL, company_hash=COMPANY_HASH)
