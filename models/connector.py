# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
import pyodbc
from pyodbc import OperationalError
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)

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
            _logger.info('Attempting to connect to the database at %s with user %s on port %s', server, rec.db_user, rec.db_port)
            try:
                conn_str = (
                    f'DRIVER={{ODBC Driver 17 for SQL Server}};'
                    f'SERVER={server},{rec.db_port};'
                    f'DATABASE={rec.db_name};'
                    f'UID={rec.db_user};'
                    f'PWD={rec.password}'
                )
                conn = pyodbc.connect(conn_str)
                rec.write({'state': 'active'})
                _logger.info('Successfully connected to the database at %s', server)
            except OperationalError as e:
                _logger.error('OperationalError: %s', e)
                raise ValidationError(_('Connection error: Unable to connect to the database. Please check your connection details and try again. Error: %s') % e)
            except ValueError as e:
                _logger.error('ValueError: %s', e)
                raise ValidationError(_('Connection error: ' + str(e)))
            finally:
                if 'conn' in locals():
                    conn.close()
                    _logger.info('Database connection closed.')

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
