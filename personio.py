import requests
from loguru import logger
from config import HOST


def login(url: str, email: str, password: str) -> tuple[requests.Session, str, str, str]:
    logger.info("Login")
    session = requests.Session()
    login = session.post(
        url,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:134.0) Gecko/20100101 Firefox/134.0",
            "Origin": HOST,
        },
        data={"email": email, "password": password},
    )

    logger.trace(f"Headers: {str(login.headers)}")
    logger.trace(f"Cookies: {login.cookies}")
    logger.trace(f"Response: {login.text[:256]}\n")

    if login.status_code != 200:
        logger.error(f"Login failed: {login.status_code} {login.text}")
        raise requests.exceptions.HTTPError("Login failed")

    token1 = login.cookies.get("XSRF-TOKEN")
    if not token1:
        logger.error("Login failed: 'XSRF-TOKEN' cookie not found")
        raise requests.exceptions.RequestException("Login failed: 'XSRF-TOKEN' cookie not found")

    token2 = login.cookies.get("personio_session")
    if not token2:
        logger.error("Login failed: 'personio_session' cookie not found")
        raise requests.exceptions.RequestException("Login failed: 'personio_session' cookie not found")

    token3 = login.cookies.get("ATHENA-XSRF-TOKEN")
    if not token3:
        logger.error("Login failed: 'ATHENA-XSRF-TOKEN' cookie not found")
        raise requests.exceptions.RequestException("Login failed: 'ATHENA-XSRF-TOKEN' cookie not found")

    logger.info("Login successful!")

    return session, token1, token2, token3


def get_projects(session: requests.Session, projects_url: str) -> requests.Response:
    response = session.get(projects_url, headers={"Accept": "application/json"})
    logger.debug("Projects:")
    logger.trace(f"Headers: {str(response.headers)}\nResponse:{response.text[:256]}\n")
    return response
