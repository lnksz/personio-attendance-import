import os
import json
import random
import time
import requests
import uuid
import re
from loguru import logger
from playwright.sync_api import sync_playwright, TimeoutError, Page


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


SESSION_FILE = os.environ.get("PERSONIO_SESSION_FILE", ".personio-session.json")
REQUIRED_COOKIE_NAMES = {"ATHENA-XSRF-TOKEN"}


def _cookies_to_map(cookies: list[dict]) -> dict[str, str]:
    return {
        name: value
        for cookie in cookies
        if (name := cookie.get("name")) and (value := cookie.get("value"))
    }


def load_session_cookies(path: str = SESSION_FILE) -> dict[str, str]:
    if not os.path.exists(path):
        return {}

    if os.stat(path).st_mtime < time.time() - 3600:
        logger.info(f"Session file {path} is older than 1 hour")
        return {}

    with open(path) as session_file:
        state = json.load(session_file)

    cookies = _cookies_to_map(state.get("cookies", []))
    if not REQUIRED_COOKIE_NAMES.issubset(cookies.keys()):
        logger.warning(f"Session file {path} is missing required cookies")
        return {}

    logger.info(f"Using saved Personio session from {path}")
    return cookies


def save_session_cookies(cookies: list[dict], path: str = SESSION_FILE) -> None:
    with open(path, "w") as session_file:
        json.dump({"cookies": cookies}, session_file, indent=2)
    os.chmod(path, 0o600)
    logger.info(f"Saved Personio session to {path}")


def bootstrap_manual_login(
    url: str = "https://login.personio.com/u/login/identifier",
    company_hash: str = "",
    session_file: str = SESSION_FILE,
) -> dict[str, str]:
    executable_path = os.environ.get("PERSONIO_CHROMIUM_PATH", "/snap/bin/chromium")

    if os.path.exists(session_file):
        os.remove(session_file)
        logger.info(f"Removed existing Personio session file {session_file}")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=executable_path,
            headless=False,
            args=["--disable-dev-shm-usage", "--no-sandbox", "--disable-setuid-sandbox"],
        )
        context = browser.new_context()
        page = context.new_page()

        logger.info("Open browser for manual Personio login")
        page.goto(f"{url}?state={company_hash}", wait_until="domcontentloaded")

        logger.info("Complete the login in the opened browser window")
        logger.info("Waiting up to 5 minutes for Personio session cookies...")

        cookies = {}
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            cookie_list = context.cookies()
            cookies = _cookies_to_map(cookie_list)
            if REQUIRED_COOKIE_NAMES.issubset(cookies.keys()):
                save_session_cookies(cookie_list, session_file)
                browser.close()
                return cookies
            time.sleep(1)

        page.screenshot(path="error_manual_login_timeout.png", full_page=True)
        browser.close()
        logger.error("Manual login did not produce required cookies")
        return {}


def login(
    user: str,
    password: str,
    url: str = "https://login.personio.com/u/login/identifier",
    company_hash: str = "",
) -> dict[str, str]:
    saved_cookies = load_session_cookies()
    if saved_cookies:
        return saved_cookies

    if os.environ.get("PERSONIO_MANUAL_LOGIN", "").lower() == "true":
        return bootstrap_manual_login(url=url, company_hash=company_hash)

    if not user.strip():
        logger.error("Personio email is empty; configure EMAIL before automated login")
        return {}

    if not password.strip():
        logger.error("Personio password is empty; set PERSO_PASS or configure PASSWORD before automated login")
        return {}

    debug_mode = os.environ.get("DEBUG_PERSONIO_LOGIN", "").lower() == "true"

    with sync_playwright() as p:
        # Launch browser with anti-detection measures using system chromium
        browser = p.chromium.launch(
            headless=not debug_mode,  # Set to False for debugging
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-default-browser-check",
                "--no-first-run",
                "--disable-gpu",
                "--no-sandbox",  # Needed for container environments
                "--disable-setuid-sandbox",
            ],
        )

        # Create context with realistic settings
        context = browser.new_context(
            user_agent="Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:151.0) Gecko/20100101 Firefox/151.0",
            locale="en-US",
            timezone_id="UTC",
            viewport={"width": 1280, "height": 720},
        )

        # Override navigator.webdriver and other bot detection signals
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => false,
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
        # Add realistic delays to simulate human typing
        page.fill('input[name="username"]', user)
        time.sleep(random.uniform(0.5, 1.5))
        page.click('button[type="submit"]')
        time.sleep(random.uniform(1, 2))

        try:
            logger.info("⌛ Waiting for password field...")
            page.wait_for_selector('input[name="password"]', timeout=10000)
        except TimeoutError:
            snapshot_on_timeout("password_field")
            browser.close()
            return {}

        logger.info("🔑 Entering password...")
        # Add realistic delays
        page.fill('input[name="password"]', password)
        time.sleep(random.uniform(0.5, 1.5))
        page.click('button[type="submit"]')
        time.sleep(random.uniform(2, 4))

        # Wait for Vercel security challenge to complete
        # The page shows "we are verifying your browser" during challenge
        logger.info("⏳ Waiting for security challenge verification...")
        challenge_detected = False
        try:
            # Check if challenge message appears
            page.wait_for_function(
                """() => document.body.innerText.includes('We are verifying')""", timeout=5000
            )
            challenge_detected = True
            logger.info("🔐 Security challenge detected, waiting for completion...")

            # Now wait for it to disappear (challenge completing)
            page.wait_for_function(
                """() => !document.body.innerText.includes('We are verifying')""",
                timeout=30000,  # Give challenge up to 30 seconds
            )
            logger.info("✓ Security challenge completed")
        except TimeoutError:
            if challenge_detected:
                logger.warning("⚠ Challenge verification timed out after 30s, continuing anyway...")
            else:
                logger.info("ℹ No challenge message detected (may have been skipped)")

        # Wait for page navigation to complete after challenge
        time.sleep(random.uniform(1, 2))
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except TimeoutError:
            logger.warning("⚠ Network idle timeout, checking for cookies anyway...")

        logger.info("⏳ Waiting for auth cookies...")
        required_cookies = REQUIRED_COOKIE_NAMES
        cookies = {}
        deadline = time.monotonic() + 15  # Increased to 15s for challenge completion time
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
            logger.error(f"❌ Required cookies not found after {15}s")
            logger.error(f"   Expected: {required_cookies}")
            logger.error(f"   Got: {sorted(cookies.keys())}")
            if cookies:
                logger.debug(f"   All cookies: {sorted(cookies.keys())}")
            snapshot_on_timeout("postlogin_tokens")
            browser.close()
            return {}

        save_session_cookies(context.cookies())
        logger.success("✅ Login successful. Cookies saved.")
        browser.close()
        return cookies


def get_projects(session: requests.Session, projects_url: str) -> requests.Response:
    response = session.get(projects_url, headers={"Accept": "application/json"})
    logger.debug("Projects:")
    logger.trace(f"Headers: {str(response.headers)}\nResponse:{response.text[:256]}\n")
    return response


def _normalize_blacklist(blacklist: tuple[str, ...] | list[str] | str | None) -> list[str]:
    if not blacklist:
        return []

    if isinstance(blacklist, str):
        blacklist = (blacklist,)

    return [entry.strip().lower() for entry in blacklist if entry.strip()]


def _playwright_cookies(host: str, cookies: dict[str, str] | list[dict]) -> list[dict]:
    if isinstance(cookies, dict):
        cookie_url = host.rstrip("/") + "/"
        return [
            {"name": name, "value": value, "url": cookie_url}
            for name, value in cookies.items()
            if value
        ]

    return cookies


def _wait_for_approval_card_removed(page: Page, task_id: str, timeout: int = 5000) -> bool:
    if not task_id:
        return False

    try:
        page.wait_for_function(
            """
            taskId => !Array.from(
                document.querySelectorAll('[data-task-type="attendance-day-approval"]')
            ).some(element => element.getAttribute('data-test-id') === taskId)
            """,
            task_id,
            timeout=timeout,
        )
        return True
    except TimeoutError:
        return False


def approve_zeiterfassung_requests(
    page: Page,
    blacklist: tuple[str, ...] | list[str] | str | None = None,
) -> None:
    try:
        normalized_blacklist = _normalize_blacklist(blacklist)
        handled_task_ids = set()
        task_list = page.locator('ul[data-test-id="task-list"]')
        task_list.wait_for(state="visible", timeout=5000)

        cards = task_list.locator('[data-task-type="attendance-day-approval"]')
        if cards.count() == 0:
            return

        while True:
            current_count = cards.count()
            if current_count == 0:
                return

            approved_card = False
            for index in range(current_count):
                card = cards.nth(index)
                name = (card.locator("img").first.get_attribute("alt") or "").strip()
                task_id = (card.get_attribute("data-test-id") or "").strip()
                task_key = task_id or f"{index}:{name}"
                if task_key in handled_task_ids:
                    continue

                normalized_name = name.lower()

                if any(blocked_name in normalized_name for blocked_name in normalized_blacklist):
                    logger.info(f"Skipping zeiterfassung approval for blacklisted name: {name}")
                    handled_task_ids.add(task_key)
                    continue

                approve_button = card.locator('button[aria-label="Genehmigen"]').first
                handled_task_ids.add(task_key)
                try:
                    card.hover(timeout=5000)
                    approve_button.click(timeout=5000)
                except TimeoutError:
                    logger.warning(
                        f"Pointer click failed for {name or 'unknown employee'}; trying DOM click"
                    )
                    try:
                        approve_button.evaluate("button => button.click()", timeout=5000)
                    except TimeoutError as exc:
                        if _wait_for_approval_card_removed(page, task_id):
                            logger.info(
                                f"Approved zeiterfassung request for {name or 'unknown employee'}"
                            )
                            approved_card = True
                            break

                        logger.warning(
                            f"Failed to approve zeiterfassung request for "
                            f"{name or 'unknown employee'}: {exc}"
                        )
                        continue
                except Exception as exc:
                    logger.warning(
                        f"Failed to approve zeiterfassung request for "
                        f"{name or 'unknown employee'}: {exc}"
                    )
                    continue

                logger.info(f"Approved zeiterfassung request for {name or 'unknown employee'}")
                if task_id and not _wait_for_approval_card_removed(page, task_id):
                    logger.warning(
                        f"Approved zeiterfassung request for {name or 'unknown employee'}, "
                        "but the task card did not disappear within 5s; not retrying"
                    )
                approved_card = True
                break

            if not approved_card:
                return

    except Exception as exc:
        logger.warning(f"Failed to auto-approve zeiterfassung requests: {exc}")


def approve_zeiterfassung_dashboard(
    host: str,
    cookies: dict[str, str] | list[dict],
    blacklist: tuple[str, ...] | list[str] | str | None = None,
) -> None:
    try:
        cookies_for_browser = _playwright_cookies(host, cookies)
        if not cookies_for_browser:
            logger.warning("No Personio auth cookies available for approval")
            return

        debug_mode = os.environ.get("DEBUG_PERSONIO_LOGIN", "").lower() == "true"
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=not debug_mode,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--no-default-browser-check",
                    "--no-first-run",
                    "--disable-gpu",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                ],
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:151.0) Gecko/20100101 Firefox/151.0",
                locale="en-US",
                timezone_id="UTC",
                viewport={"width": 1280, "height": 720},
            )
            try:
                context.add_cookies(cookies_for_browser)
                page = context.new_page()
                page.goto(host, wait_until="domcontentloaded")
                approve_zeiterfassung_requests(page, blacklist)
            finally:
                browser.close()
    except Exception as exc:
        logger.warning(f"Failed to open Personio dashboard for approval: {exc}")


def get_untrackable_project_ids(resp: requests.Response) -> list[str]:
    if resp.status_code != 400:
        return []

    try:
        resp_dict = resp.json()
    except requests.exceptions.JSONDecodeError:
        return []

    untrackable_projects_title_re = re.compile(
        r"Projects with ids \[([^\]]+)\] for employee \d+ are not trackable"
    )
    for error in resp_dict.get("errors", []):
        if error.get("type") != "ATTENDANCE_PERIOD_PROJECT_NOT_TRACKABLE":
            continue

        title = error.get("title", "")
        match = untrackable_projects_title_re.search(title)
        if not match:
            return []

        return [
            project_id.strip() for project_id in match.group(1).split(",") if project_id.strip()
        ]

    return []


def remove_untrackable_project_ids(attendance: dict, project_ids: list[str]) -> int:
    untrackable_ids = set(project_ids)
    removed = 0
    for period in attendance["periods"]:
        if period.get("project_id") in untrackable_ids:
            period["project_id"] = None
            removed += 1
    return removed


def log_toggl_day_in_personio(
    session: requests.Session,
    config,
    day: PersonioDay,
    date: str,
    cookies: dict[str, str],
) -> bool:
    attendance = day.to_personio_attendance(config.PROFILE_ID)
    logger.info(f"Registering entries ({len(attendance['periods'])}) from {date}")
    token = cookies.get("ATHENA-XSRF-TOKEN", "")

    while True:
        resp = session.put(
            f"{config.ATTENDANCE_URL}/{uuid.uuid1()}",
            json=attendance,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json, text/plain, */*",
                "Accept-Encoding": "gzip, deflate, br, zstd",
                "Referer": "https://efr-gmbh.app.personio.com/",
                "X-ATHENA-XSRF-TOKEN": token,
            },
        )
        content_type = resp.headers.get("content-type", "")
        logger.info(f"response: {resp.status_code} {content_type}")
        logger.trace(f"reponse content:\n {resp.text}")

        untrackable_project_ids = get_untrackable_project_ids(resp)
        if untrackable_project_ids:
            removed = remove_untrackable_project_ids(attendance, untrackable_project_ids)
            if removed:
                logger.warning(
                    f"Personio project ids {untrackable_project_ids} are not trackable for {date}; retrying without project mapping"
                )
                continue

        if resp.status_code != 200 or "application/json" not in content_type:
            logger.error(
                f"Attendance Req:\n"
                f"Heads: {resp.request.headers}\n"
                f"Request: {resp.request.body}\n"
                f"Response: {resp}\n{resp.text}\n"
            )
            logger.error(f"FAILED to register attendance for {date}")
            return False

        resp_dict = json.loads(resp.text)
        if resp.status_code != 200 or not resp_dict["success"]:
            logger.error(f"Attendance Req:\n{resp.request.headers}\n{resp.request.body}")
            logger.info(f"Attendance Resp:\n{resp.text}")
            logger.error(f"FAILED to register attendance for {date}")
            return False
        return True


if __name__ == "__main__":
    from config import CONFIG

    cookies = login(
        user=CONFIG.EMAIL,
        password=CONFIG.PASSWORD,
        url=CONFIG.LOGIN_URL,
        company_hash=CONFIG.COMPANY_HASH,
    )
    if not cookies:
        logger.error("Login failed, approval skipped")
        raise SystemExit(1)

    approve_zeiterfassung_dashboard(CONFIG.HOST, cookies, CONFIG.NON_APPROVABLE)
