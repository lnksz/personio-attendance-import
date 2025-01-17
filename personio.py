import requests
from loguru import logger


def login(url: str, email: str, password: str) -> tuple[requests.Session, str]:
    logger.info("Login")
    session = requests.Session()
    first_response = session.post(
        url,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:134.0) Gecko/20100101 Firefox/134.0",
            "Origin": "https://efr-gmbh.personio.de",
        },
        data={"email": email, "password": password},
    )

    logger.trace(f"Headers: {str(first_response.headers)}\nResponse:{first_response.text[:256]}\n")
    if first_response.status_code != 200:
        logger.error(f"Login failed: {first_response.status_code} {first_response.text}")
        raise requests.exceptions.HTTPError("Login failed")

    set_cookie = first_response.headers.get("set-cookie")
    if not set_cookie:
        logger.error("Login failed: 'set-cookie' header not found")
        raise requests.exceptions.RequestException("Login failed: 'set-cookie' header not found")
    token = set_cookie.split()[0].split("=")[1].rstrip(";")
    logger.trace(f"CSRF: {set_cookie}")
    logger.trace(f"CSRF: {token}")

    return session, token


def get_projects(session: requests.Session, projects_url: str) -> requests.Response:
    response = session.get(projects_url, headers={"Accept": "application/json"})
    logger.debug("Projects:")
    logger.trace(f"Headers: {str(response.headers)}\nResponse:{response.text[:256]}\n")
    return response
