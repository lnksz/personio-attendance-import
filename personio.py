import requests
import logging


def login(url: str, email: str, password: str) -> tuple[requests.Session, str]:
    session = requests.Session()

    first_response = session.post(
        url,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={"email": email, "password": password},
    )
    logging.info("Login")
    logging.debug(f"{str(first_response.headers)}\n{first_response.text}\n")
    set_cookie = first_response.headers["set-cookie"]
    token = set_cookie.split()[0].split("=")[1].rstrip(";")
    logging.debug(f"CSRF: {set_cookie}")
    logging.debug(f"CSRF: {token}")

    return session, token


def get_projects(session: requests.Session, projects_url: str) -> requests.Response:
    response = session.get(projects_url, headers={"Accept": "application/json"})
    logging.debug("Projects:")
    logging.debug(response.headers, "\n", response.text)
    return response
