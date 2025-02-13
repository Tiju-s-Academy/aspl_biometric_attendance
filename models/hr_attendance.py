# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import models, fields, api


class IrRule(models.Model):
    _inherit = 'ir.rule'

    @api.model
    def archive_attendance_rule(self):
        if self.env.ref('hr_attendance.hr_attendance_rule_attendance_manager', raise_if_not_found=False):
            self.env.ref('hr_attendance.hr_attendance_rule_attendance_manager').update({'active': False})


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    comment = fields.Text('Details')
    atten_status = fields.Boolean("Status")
    has_error = fields.Boolean("Mistake")
    department_id = fields.Many2one('hr.department', related='employee_id.department_id', 
                                  string='Department', store=True)
    
    def name_get(self):
        result = []
        for attendance in self:
            if not attendance.check_out:
                result.append((attendance.id, f"{attendance.employee_id.name} (Check In)"))
            else:
                worked_hours = '{:.2f}'.format(attendance.worked_hours)
                result.append((
                    attendance.id, 
                    f"{attendance.employee_id.name}: {worked_hours} hours"
                ))
        return result

    @api.model
    def get_unusual_days(self, date_from, date_to=None):
        """Return unusual days in calendar view. Empty method to avoid error."""
        return {}
