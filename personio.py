import time
import requests
import uuid
from loguru import logger
from playwright.sync_api import sync_playwright, TimeoutError


class PersonioDay:
    def __init__(self, date: str):
        self.date = date
        self.periods = []
        self.uuid = str(uuid.uuid1())

    def __str__(self):
        return f"{self.date} - {len(self.periods)}"

    def __repr__(self):
        return self.__str__()

    def add_period(self, period: dict):
        self.periods.append(period)

    def to_personio_attendance(self, employee_id: int):
        return {
            "employee_id": employee_id,
            "periods": self.periods,
        }


def login(
    user: str,
    password: str,
    url: str = "https://login.personio.com/u/login/identifier",
    company_hash: str = "",
) -> dict[str, str]:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        def snapshot_on_timeout(label: str) -> None:
            path = f"error_{label}.png"
            logger.error(f"❌ Timeout reached. Taking screenshot: {path}")
            page.screenshot(path=path, full_page=True)

        logger.info("🌐 Navigating to login.personio.com...")
        try:
            page.goto(
                f"{url}?state={company_hash}",
                wait_until="networkidle",
            )
        except TimeoutError:
            snapshot_on_timeout("goto")
            browser.close()
            return {}

        try:
            logger.info("⌛ Waiting for email input...")
            page.wait_for_selector('input[name="username"]', timeout=10000)
        except TimeoutError:
            snapshot_on_timeout("email_field")
            browser.close()
            return {}

        logger.info("📧 Entering email...")
        page.fill('input[name="username"]', user)
        page.click('button[type="submit"]')

        try:
            logger.info("⌛ Waiting for password field...")
            page.wait_for_selector('input[name="password"]', timeout=10000)
        except TimeoutError:
            snapshot_on_timeout("password_field")
            browser.close()
            return {}

        logger.info("🔑 Entering password...")
        page.fill('input[name="password"]', password)
        page.click('button[type="submit"]')

        logger.info("⏳ Waiting for auth cookies...")
        required_cookies = {"ATHENA-XSRF-TOKEN"}
        cookies = {}
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            cookies = {
                name: value
                for cookie in context.cookies()
                if (name := cookie.get("name")) and (value := cookie.get("value"))
            }
            if required_cookies.issubset(cookies.keys()):
                break
            time.sleep(0.2)

        if not required_cookies.issubset(cookies.keys()):
            logger.error(f"❌ Required cookies not found. Present: {sorted(cookies.keys())}")
            snapshot_on_timeout("postlogin_tokens")
            browser.close()
            return {}

        logger.success("✅ Login successful. Cookies saved.")
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
