# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    biometric_no = fields.Char("Biometric Code", size=10)
