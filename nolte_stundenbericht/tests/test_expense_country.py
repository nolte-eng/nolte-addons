from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from odoo import Command
from odoo.tests import TransactionCase, tagged
from ..controllers import api_v1


@tagged("post_install", "-at_install")
class TestExpenseCountry(TransactionCase):
    """Synthetic rates test integration, not statutory rate amounts."""
    def setUp(self):
        super().setUp()
        self.day = date(2035, 5, 7)
        self.employee = self.env["hr.employee"].create({"name": "BMF country test employee",
            "stundenbericht_source": "app", "company_id": self.env.company.id})
        self.rates = self.env["nolte.bmf.rate"].create([
            {"year": 2035, "rate_key": "DE", "country_name": "Deutschland", "full_day": 10, "partial_day": 5, "overnight": 0},
            {"year": 2035, "rate_key": "TEST_FOREIGN", "country_name": "Testland", "full_day": 31, "partial_day": 17, "overnight": 40},
            {"year": 2035, "rate_key": "DANEMARK", "country_name": "Dänemark", "full_day": 33, "partial_day": 18, "overnight": 41},
            {"year": 2035, "rate_key": "TEST_FOREIGN:CITY", "country_name": "Testland", "location_name": "Teststadt", "full_day": 35, "partial_day": 19, "overnight": 42},
        ])

    def report(self, key="TEST_FOREIGN", employees=None):
        employees = employees if employees is not None else self.employee
        return self.env["nolte.service.report"].create({"name": "TEST-BMF-COUNTRY", "service_date": self.day,
            "country_rate_key": key, "state": "customer_confirmed",
            "member_ids": [Command.create({"employee_id": employee.id, "service_date": self.day,
                "segment_ids": [Command.create({"segment_type": "work", "start_time": "08:00", "end_time": "18:00"})]}) for employee in employees]})

    def test_backend_bmf_selection_tracks_country_key_and_service_year(self):
        from odoo.exceptions import UserError
        report = self.report()
        self.assertEqual(report.bmf_rate_id, self.rates.filtered(lambda rate: rate.rate_key == 'TEST_FOREIGN'))
        self.assertEqual(report.bmf_rate_year, 2035)
        city = self.rates.filtered(lambda rate: rate.rate_key == 'TEST_FOREIGN:CITY')
        report.bmf_rate_id = city
        self.assertEqual(report.country_rate_key, city.rate_key)
        next_year = city.copy({'year': 2036})
        with self.assertRaises(UserError), self.cr.savepoint():
            report.bmf_rate_id = next_year
        report.service_date = date(2036, 5, 7)
        self.assertEqual(report.bmf_rate_id, next_year)
        self.assertEqual(report.bmf_rate_year, 2036)
        report.country_rate_key = 'UNKNOWN_LEGACY_KEY'
        self.assertFalse(report.bmf_rate_id)
        self.assertEqual(report.country_rate_key, 'UNKNOWN_LEGACY_KEY')
        report.write({'service_date': self.day, 'country_rate_key': 'DK'})
        self.assertEqual(report.bmf_rate_id.rate_key, 'DANEMARK')
        self.assertEqual(report.country_rate_key, 'DK', 'Reading the selector must not rewrite legacy data')

    def test_hours_user_can_select_bmf_rates_without_expense_edit_access(self):
        from odoo.exceptions import AccessError
        tech = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'BMF dropdown technician', 'login': 'test_bmf_dropdown_technician',
            'group_ids': [Command.set([self.env.ref('nolte_stundenbericht.group_stundenbericht_user').id])],
            'company_id': self.env.company.id, 'company_ids': [Command.set(self.env.company.ids)]})
        report = self.report()
        report.owner_user_id = tech
        own = report.with_user(tech)
        self.assertIn('Testland', own.bmf_rate_id.display_name)
        own.bmf_rate_id = self.rates.filtered(lambda rate: rate.rate_key == 'TEST_FOREIGN:CITY')
        self.assertEqual(own.country_rate_key, 'TEST_FOREIGN:CITY')
        with self.assertRaises(AccessError):
            own.bmf_rate_id.write({'full_day': 999})
        with self.assertRaises(AccessError):
            self.env['nolte.expense.report'].with_user(tech).check_access('write')

    def monthly(self):
        monthly = self.env["nolte.expense.report"].create({"employee_id": self.employee.id, "month": self.day.replace(day=1)})
        if not monthly.line_ids.filtered(lambda item: item.date == self.day):
            self.env["nolte.expense.report.line"].create({"report_id": monthly.id, "date": self.day})
        return monthly

    def test_country_rate_reaches_each_employee_and_repeat_is_idempotent(self):
        other = self.employee.copy({"name": "Second BMF employee"})
        report = self.report(employees=self.employee | other)
        report.action_sync_spesenbericht()
        self.assertEqual(report.spesen_sync_state, "synchronized")
        lines = report.member_ids.mapped("expense_report_line_id")
        self.assertEqual(len(lines), 2)
        for line in lines:
            self.assertEqual(line.country, "TEST_FOREIGN")
            self.assertEqual(line.travel_type, "single")
            self.assertEqual(line.allowance, 17)
            self.assertFalse(line.rate_missing)
        source_lines = report.member_ids.mapped("work_report_line_id")
        report.action_sync_spesenbericht()
        self.assertEqual(report.member_ids.mapped("expense_report_line_id"), lines)
        self.assertEqual(report.member_ids.mapped("work_report_line_id"), source_lines)

    def test_legacy_country_code_uses_central_general_rate(self):
        report = self.report("DK")
        report.action_sync_spesenbericht()
        self.assertEqual(report.spesen_sync_state, "synchronized")
        self.assertEqual(report.member_ids.expense_report_line_id.country, "DANEMARK")
        self.assertEqual(report.member_ids.expense_report_line_id.allowance, 18)
        city = self.report("TEST_FOREIGN:CITY", employees=self.employee.copy({"name": "City rate employee"}))
        city.action_sync_spesenbericht()
        self.assertEqual(city.member_ids.expense_report_line_id.allowance, 19)

    def test_missing_year_rate_and_different_same_day_countries_are_conflicts(self):
        report = self.report("MISSING_TEST_RATE")
        report.action_sync_spesenbericht()
        self.assertEqual(report.spesen_sync_state, "conflict")
        self.assertFalse(report.member_ids.work_report_line_id)
        self.assertIn("MISSING_TEST_RATE", report.conflict_ids.description)
        report.unlink()
        first = self.report("DE")
        self.report("TEST_FOREIGN")
        first.action_sync_spesenbericht()
        self.assertEqual(first.spesen_sync_state, "conflict")
        self.assertFalse(first.member_ids.work_report_line_id)

    def test_manual_country_and_locked_month_are_not_overwritten(self):
        monthly = self.monthly()
        line = monthly.line_ids.filtered(lambda item: item.date == self.day)
        line.write({"country": "DE", "travel_type": "full", "breakfast": True})
        report = self.report()
        report.action_sync_spesenbericht()
        self.assertEqual(report.spesen_sync_state, "conflict")
        self.assertEqual(line.country, "DE")
        self.assertTrue(line.breakfast)
        self.assertFalse(line.work_report_line_id)
        line.country = False
        monthly.state = "submitted"
        report.action_sync_spesenbericht()
        self.assertEqual(report.spesen_sync_state, "conflict")
        self.assertFalse(line.country)

    def test_automatic_country_updates_but_manual_meals_and_hotel_are_preserved(self):
        monthly = self.monthly()
        line = monthly.line_ids.filtered(lambda item: item.date == self.day)
        line.write({"country": "DE", "travel_type": "single", "travel_type_automatic": True,
            "breakfast": True, "hotel_mode": "receipt", "hotel_input": 123})
        report = self.report()
        report.action_sync_spesenbericht()
        self.assertEqual(report.spesen_sync_state, "synchronized")
        self.assertEqual(line.country, "TEST_FOREIGN")
        self.assertAlmostEqual(line.allowance, 17 - 31 * .2)
        self.assertTrue(line.breakfast)
        self.assertEqual(line.hotel_mode, "receipt")
        self.assertEqual(line.hotel_amount, 123)

    def test_mobile_selection_reads_the_same_central_bmf_keys(self):
        tech = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "BMF selection test", "login": "test_bmf_selection",
            "group_ids": [Command.set([self.env.ref("base.group_user").id,
                self.env.ref("nolte_stundenbericht.group_stundenbericht_user").id])],
            "company_id": self.env.company.id, "company_ids": [Command.set(self.env.company.ids)]})
        self.employee.user_id = tech
        with patch.object(api_v1, "request", SimpleNamespace(env=self.env["nolte.service.report"].with_user(tech).env)):
            options = api_v1.NolteStundenberichtApiV1().bootstrap()["countries"]
        self.assertIn({"code": "TEST_FOREIGN:CITY", "name": "Testland (Teststadt)"}, options)

    def test_expense_sync_subtracts_explicit_pause_and_is_idempotent(self):
        report = self.report()
        member = report.member_ids
        member.segment_ids.end_time = "17:00"
        member.write({"segment_ids": [Command.create({"segment_type": "break", "start_time": "12:00", "end_time": "12:30"})]})
        report.action_sync_spesenbericht()
        self.assertEqual(report.spesen_sync_state, "synchronized")
        source, expense = member.work_report_line_id, member.expense_report_line_id
        self.assertEqual(source.break_minutes, 30)
        self.assertEqual(expense.break_minutes, 30)
        self.assertEqual(expense.work_hours, 8.5)
        report.action_sync_spesenbericht()
        self.assertEqual(member.work_report_line_id, source)
        self.assertEqual(member.expense_report_line_id, expense)
        self.assertEqual(expense.break_minutes, 30)
        self.assertEqual(expense.work_hours, 8.5)

    def test_daily_pause_union_clips_gaps_duplicates_and_other_reports(self):
        first = self.report()
        second = self.report()
        first.member_ids.segment_ids.unlink()
        second.member_ids.segment_ids.unlink()
        def add(member, kind, start, end):
            member.write({"segment_ids": [Command.create({"segment_type": kind, "start_time": start, "end_time": end})]})
        add(first.member_ids, "outbound_travel", "08:00", "09:00")
        add(first.member_ids, "work", "09:00", "12:00")
        add(second.member_ids, "work", "13:00", "17:00")
        add(second.member_ids, "return_travel", "17:00", "18:00")
        # This pause already lies in the gap between assignments.
        add(first.member_ids, "break", "12:00", "13:00")
        # Duplicate/overlapping pauses count only once, clipped to active time.
        add(first.member_ids, "break", "11:30", "12:30")
        add(second.member_ids, "break", "11:45", "12:30")
        add(second.member_ids, "break", "06:00", "07:00")
        summary = first._members_day_summary(first.member_ids | second.member_ids)
        self.assertEqual(summary, {"start_time": "08:00", "end_time": "18:00", "break_minutes": 90})
        first.action_sync_spesenbericht()
        self.assertEqual(first.spesen_sync_state, "synchronized")
        expense = first.member_ids.expense_report_line_id
        self.assertEqual(expense.break_minutes, 90)
        self.assertEqual(expense.work_hours, 8.5)
        self.assertEqual(second.member_ids.expense_report_line_id, expense)

    def test_pause_after_midnight_in_overnight_work(self):
        report = self.report()
        member = report.member_ids
        member.segment_ids.write({"start_time": "22:00", "end_time": "06:00"})
        member.write({"segment_ids": [Command.create({"segment_type": "break", "start_time": "01:00", "end_time": "01:30"}),
            Command.create({"segment_type": "break", "start_time": "23:45", "end_time": "00:15"})]})
        summary = report._members_day_summary(member)
        self.assertEqual(summary, {"start_time": "22:00", "end_time": "06:00", "break_minutes": 60})
        report.action_sync_spesenbericht()
        self.assertEqual(report.spesen_sync_state, "synchronized")
        self.assertEqual(member.expense_report_line_id.work_hours, 7.0)
