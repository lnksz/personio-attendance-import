import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import requests
from loguru import logger

import personio

TMP_DIR = Path(__file__).resolve().parents[1] / "tmp"
DEPRECATED_TOKEN = "00000000-0000-0000-0000-000000000000.deprecated"


def response(status=200, body=None, content_type="application/json"):
    result = requests.Response()
    result.status_code = status
    result.headers["Content-Type"] = content_type
    result._content = json.dumps(body if body is not None else {"success": True}).encode()
    result.request = requests.Request(
        "PUT",
        "https://example.app.personio.com/svc/attendance-api/v1/days",
        headers={"Cookie": "ATHENA_SESSION=private-session"},
    ).prepare()
    return result


def make_day():
    day = personio.PersonioDay("2026-10-16")
    day.add_period(
        {
            "id": "legacy-period-uuid",
            "start": "2026-10-16T08:28:59",
            "end": "2026-10-16T12:35:59",
            "period_type": "work",
            "legacy_break_min": 0,
            "comment": "[Example project]",
            "project_id": "1234",
        }
    )
    return day


class AttendancePayloadTests(unittest.TestCase):
    def test_uses_current_batch_payload(self):
        day = make_day()
        self.assertEqual(
            day.to_personio_attendance(42),
            {
                "employee_id": 42,
                "dates": ["2026-10-16"],
                "periods": [
                    {
                        "start": "08:28",
                        "end": "12:35",
                        "start_day_delta": 0,
                        "end_day_delta": 0,
                        "type": "work",
                        "comment": "[Example project]",
                        "project_id": "1234",
                    }
                ],
            },
        )
        self.assertEqual(day.periods[0]["start"], "2026-10-16T08:28:59")

    def test_preserves_overnight_dates(self):
        day = make_day()
        day.periods[0].update(start="2026-10-16T23:30:00", end="2026-10-17T01:15:00")
        period = day.to_personio_attendance(42)["periods"][0]
        self.assertEqual((period["start"], period["end"]), ("23:30", "01:15"))
        self.assertEqual((period["start_day_delta"], period["end_day_delta"]), (0, 1))

    def test_offsets_are_relative_to_attendance_date(self):
        day = make_day()
        day.periods[0].update(start="2026-10-17T00:10:00", end="2026-10-17T01:15:00")
        period = day.to_personio_attendance(42)["periods"][0]
        self.assertEqual((period["start_day_delta"], period["end_day_delta"]), (1, 1))

    def test_open_period_and_nullable_metadata(self):
        day = make_day()
        day.periods[0].update(end=None, comment=None, project_id=None)
        period = day.to_personio_attendance(42)["periods"][0]
        self.assertIsNone(period["end"])
        self.assertIsNone(period["end_day_delta"])
        self.assertIsNone(period["project_id"])
        self.assertIsNone(period["comment"])


class SessionCookieTests(unittest.TestCase):
    def setUp(self):
        TMP_DIR.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=TMP_DIR)
        self.addCleanup(self.temp.cleanup)
        self.session_file = Path(self.temp.name) / "session.json"

    def save(self, cookies):
        personio.save_session_cookies(
            [{"name": name, "value": value} for name, value in cookies.items()],
            str(self.session_file),
        )

    def test_deprecated_xsrf_cookie_does_not_prove_login(self):
        self.save({"ATHENA-XSRF-TOKEN": DEPRECATED_TOKEN, "personio_session": "legacy"})
        self.assertEqual(personio.load_session_cookies(str(self.session_file)), {})

    def test_athena_session_does_not_require_xsrf_cookie(self):
        self.save({"ATHENA_SESSION": "authenticated-session"})
        self.assertEqual(
            personio.load_session_cookies(str(self.session_file)),
            {
                "ATHENA_SESSION": "authenticated-session",
            },
        )

    def test_empty_auth_cookie_does_not_prove_login(self):
        self.save({"ATHENA_SESSION": "", "ATHENA-XSRF-TOKEN": DEPRECATED_TOKEN})
        self.assertEqual(personio.load_session_cookies(str(self.session_file)), {})


class AttendanceUploadTests(unittest.TestCase):
    def setUp(self):
        self.config = SimpleNamespace(
            PROFILE_ID=42,
            HOST="https://example.app.personio.com",
            ATTENDANCE_URL="https://example.app.personio.com/svc/attendance-api/v1/days/",
        )
        self.day = make_day()
        self.cookies = {
            "ATHENA_SESSION": "private-session",
            "ATHENA-XSRF-TOKEN": DEPRECATED_TOKEN,
        }
        self.session = Mock(spec=requests.Session)
        self.session.put.return_value = response()

    def upload(self):
        return personio.log_toggl_day_in_personio(
            self.session,
            self.config,
            self.day,
            self.day.date,
            self.cookies,
        )

    def test_puts_to_collection_without_uuid_or_deprecated_token(self):
        self.assertTrue(self.upload())
        args, kwargs = self.session.put.call_args
        self.assertEqual(args, (self.config.ATTENDANCE_URL.rstrip("/"),))
        self.assertEqual(kwargs["json"]["dates"], [self.day.date])
        self.assertNotIn("X-ATHENA-XSRF-TOKEN", kwargs["headers"])
        self.assertEqual(kwargs["headers"]["Referer"], self.config.HOST + "/")
        self.assertEqual(kwargs["timeout"], 30)
        self.assertFalse(kwargs["allow_redirects"])

    def test_keeps_real_xsrf_token_for_existing_sessions(self):
        self.cookies["ATHENA-XSRF-TOKEN"] = "real-xsrf-token"
        self.assertTrue(self.upload())
        self.assertEqual(
            self.session.put.call_args.kwargs["headers"]["X-ATHENA-XSRF-TOKEN"],
            "real-xsrf-token",
        )

    def test_accepts_json_without_legacy_success_flag(self):
        self.session.put.return_value = response(body={"data": []})
        self.assertTrue(self.upload())

    def test_accepts_no_content_success(self):
        self.session.put.return_value = response(status=204, content_type="")
        self.session.put.return_value._content = b""
        self.assertTrue(self.upload())

    def test_rejects_unsuccessful_responses(self):
        for result in [
            response(status=401),
            response(status=501, content_type=""),
            response(body={"success": False}),
            response(body={"errors": [{"title": "Rejected"}]}),
            response(content_type="text/html"),
        ]:
            with self.subTest(status=result.status_code, body=result.text):
                self.session.put.return_value = result
                self.assertFalse(self.upload())

    def test_rejects_malformed_json(self):
        self.session.put.return_value = response()
        self.session.put.return_value._content = b"not-json"
        self.assertFalse(self.upload())

    def test_retries_untrackable_projects_with_current_payload(self):
        self.session.put.side_effect = [
            response(
                status=400,
                body={
                    "errors": [
                        {
                            "type": "ATTENDANCE_PERIOD_PROJECT_NOT_TRACKABLE",
                            "title": "Projects with ids [1234] for employee 42 are not trackable",
                        }
                    ]
                },
            ),
            response(),
        ]
        self.assertTrue(self.upload())
        self.assertEqual(self.session.put.call_count, 2)
        sent = self.session.put.call_args.kwargs["json"]
        self.assertIsNone(sent["periods"][0]["project_id"])
        self.assertEqual(sent["periods"][0]["comment"], "[Example project]")
        self.assertEqual(sent["dates"], [self.day.date])
        self.assertEqual(self.day.periods[0]["project_id"], "1234")

    def test_stops_if_project_retry_cannot_remove_more_ids(self):
        self.session.put.return_value = response(
            status=400,
            body={
                "errors": [
                    {
                        "type": "ATTENDANCE_PERIOD_PROJECT_NOT_TRACKABLE",
                        "title": "Projects with ids [1234] for employee 42 are not trackable",
                    }
                ]
            },
        )
        self.assertFalse(self.upload())
        self.assertEqual(self.session.put.call_count, 2)

    def test_failure_logs_do_not_expose_session_cookies(self):
        output = io.StringIO()
        sink = logger.add(output, format="{message}", level="DEBUG")
        try:
            self.session.put.return_value = response(status=501, content_type="")
            self.assertFalse(self.upload())
        finally:
            logger.remove(sink)
        self.assertNotIn("private-session", output.getvalue())
        self.assertNotIn("Cookie", output.getvalue())


if __name__ == "__main__":
    unittest.main()
