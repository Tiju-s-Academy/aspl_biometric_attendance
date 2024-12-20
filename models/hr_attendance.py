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
    _inherit = ['hr.attendance']
    comment = fields.Text('Details')
    atten_status = fields.Boolean("Status")
    has_error = fields.Boolean("Mistake")
