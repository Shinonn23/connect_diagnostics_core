# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import frappe
from frappe.email.doctype.email_template.email_template import EmailTemplate
from frappe.tests.utils import FrappeTestCase


class TestLeaveNotificationTemplates(FrappeTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        fixture_path = Path(
            frappe.get_app_path(
                "connect_diagnostics_core",
                "fixtures",
                "email_template.json",
            )
        )
        fixtures = json.loads(fixture_path.read_text(encoding="utf-8"))
        cls.templates: dict[str, dict[str, Any]] = {fixture["name"]: fixture for fixture in fixtures}

    def _context(self, **overrides: Any) -> dict[str, Any]:
        context: dict[str, Any] = {
            "name": "LAP.83-BE.07-14.0001",
            "employee": "EMP-0001",
            "employee_name": "สมชาย ใจดี",
            "company": "Connect Diagnostics",
            "department": "Operations",
            "leave_type": "Annual Leave",
            "from_date": "2026-07-20",
            "to_date": "2026-07-22",
            "half_day": 0,
            "half_day_date": None,
            "total_leave_days": 3.0,
            "description": "พักผ่อนกับครอบครัว",
            "leave_balance": 8.0,
            "leave_approver": "approver@example.com",
            "leave_approver_name": "ผู้อนุมัติ ทดสอบ",
            "posting_date": "2026-07-14",
            "status": "Open",
        }
        context.update(overrides)
        return context

    def _render(self, template_name: str, **overrides: Any) -> tuple[str, str]:
        template = cast(EmailTemplate, frappe.get_doc(self.templates[template_name]))
        context = self._context(**overrides)
        subject = template.get_formatted_subject(context).strip()
        response = template.get_formatted_response(context)
        return subject, response

    def test_fixture_contains_both_leave_notification_templates(self) -> None:
        self.assertEqual(
            set(self.templates),
            {"Leave Approval Notification", "Leave Status Notification"},
        )

    def test_templates_use_response_html_only(self) -> None:
        for fixture in self.templates.values():
            template = cast(EmailTemplate, frappe.get_doc(fixture))

            self.assertEqual(template.use_html, 1)
            self.assertIsNone(template.response)
            self.assertTrue(template.response_html)
            self.assertEqual(template.response_, template.response_html)
            self.assertLessEqual(len(template.subject), 140)

    def test_approval_template_renders_full_details_and_escapes_user_content(self) -> None:
        subject, response = self._render(
            "Leave Approval Notification",
            employee_name="สมชาย <script>alert(1)</script>",
            description="เหตุผล <b>สำคัญ</b>\nบรรทัดถัดไป",
            half_day=1,
            half_day_date="2026-07-20",
            total_leave_days=0.5,
        )

        self.assertIn("มีคำขอลาใหม่รอพิจารณา", subject)
        self.assertIn("ข้อมูลพนักงาน", response)
        self.assertIn("รายละเอียดการลา", response)
        self.assertIn("ครึ่งวัน", response)
        self.assertIn("20-07-2026", response)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", response)
        self.assertIn("เหตุผล &lt;b&gt;สำคัญ&lt;/b&gt;<br>บรรทัดถัดไป", response)
        self.assertIn("/desk/leave-application/LAP.83-BE.07-14.0001", response)
        self.assertNotIn("<script>", response)

    def test_rejected_status_template_omits_approver_reason(self) -> None:
        subject, response = self._render(
            "Leave Status Notification",
            status="Rejected",
        )

        self.assertIn("ผลการพิจารณาใบลา", subject)
        self.assertIn("ใบลาของคุณไม่ได้รับการอนุมัติ", response)
        self.assertIn("เหตุผลการลา", response)
        self.assertNotIn("เหตุผลที่ไม่อนุมัติ", response)
        self.assertNotIn("เหตุผลการพิจารณา", response)

    def test_approved_status_template_reports_approval(self) -> None:
        subject, response = self._render(
            "Leave Status Notification",
            status="Approved",
        )

        self.assertIn("ผลการพิจารณาใบลา", subject)
        self.assertIn("ใบลาของคุณได้รับการอนุมัติแล้ว", response)

    def test_cancelled_status_template_reports_cancellation(self) -> None:
        subject, response = self._render(
            "Leave Status Notification",
            status="Cancelled",
        )

        self.assertIn("ผลการพิจารณาใบลา", subject)
        self.assertIn("ใบลาของคุณถูกยกเลิกแล้ว", response)
        self.assertNotIn("ใบลาของคุณไม่ได้รับการอนุมัติ", response)

    def test_templates_handle_empty_optional_fields_and_preserve_zero(self) -> None:
        _, response = self._render(
            "Leave Approval Notification",
            department=None,
            description=None,
            leave_balance=0,
            total_leave_days=0,
        )

        self.assertGreaterEqual(response.count("0 วัน"), 2)
        self.assertNotIn("None", response)
        self.assertNotIn("DebugUndefined", response)
        self.assertNotIn("{{", response)
