import requests
from loguru import logger


def login(url: str, email: str, password: str) -> tuple[requests.Session, str]:
    session = requests.Session()

    first_response = session.post(
        url,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={"email": email, "password": password},
    )
    logger.info("Login")
    logger.trace(f"Headers: {str(first_response.headers)}\nResponse:{first_response.text[:256]}\n")
    set_cookie = first_response.headers["set-cookie"]
    token = set_cookie.split()[0].split("=")[1].rstrip(";")
    logger.trace(f"CSRF: {set_cookie}")
    logger.trace(f"CSRF: {token}")

    return session, token


def get_projects(session: requests.Session, projects_url: str) -> requests.Response:
    response = session.get(projects_url, headers={"Accept": "application/json"})
    logger.debug("Projects:")
    logger.trace(f"Headers: {str(response.headers)}\nResponse:{response.text[:256]}\n")
    return response
