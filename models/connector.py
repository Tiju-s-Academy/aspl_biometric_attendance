# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
import pymssql
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class Connector(models.Model):
    _name = 'connector.sqlserver'
    _description = 'SQL Server connector class for fetch attendance from the device'
    _rec_name = 'name'

    @api.onchange('db_name', 'db_ip', 'db_user', 'password', 'db_port')
    def on_info(self):
        self.state = 'new'

    name = fields.Char(string='Name', required=True)
    db_name = fields.Char(string='Database', required=True)
    db_ip = fields.Char(string='Server', required=True)
    db_user = fields.Char(string='User', required=True)
    password = fields.Char(string='Password', required=True)
    db_port = fields.Char(string='Database port', required=True)
    state = fields.Selection([('new', 'New'), ('active', 'Active'), ('deactive', 'De Active')], default='new')
    auto_gen_attendance = fields.Boolean("Automatic Attendance Generation")

    def connect(self):
        for rec in self:
            server = rec.db_ip
            try:
                conn = pymssql.connect(
                    host=server, user=rec.db_user, password=rec.password, database=rec.db_name, port=rec.db_port)
                rec.write({'state': 'active'})
            except ValueError as e:
                raise ValidationError(_('Connection error: ' + e))
            conn.close()

    def active(self):
        self.write({'state': 'active'})

    def deactive(self):
        self.write({'state': 'deactive'})

    def disconnect(self, conn):
        conn.close()

    def getNewCursor(self, conn):
        return conn.cursor()

    def selectView(self, cursor, view_name):
        cursor.execute('SELECT * FROM ' + view_name)
        return cursor
