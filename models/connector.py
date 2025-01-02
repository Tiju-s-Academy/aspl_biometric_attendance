# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
import pyodbc
from pyodbc import OperationalError
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError

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

    def test_connection(self):
        for rec in self:
            server = rec.db_ip
            _logger.debug('Testing connection to the database at %s with user %s on port %s', server, rec.db_user, rec.db_port)
            try:
                conn_str = f'mssql+pymssql://{rec.db_user}:{rec.password}@{server}:{rec.db_port}/{rec.db_name}'
                engine = create_engine(conn_str)
                connection = engine.connect()
                connection.close()
                _logger.info('Successfully tested connection to the database at %s', server)
                return True
            except OperationalError as e:
                _logger.error('OperationalError: %s', e)
                return False
            except ValueError as e:
                _logger.error('ValueError: %s', e)
                return False

    def connect(self):
        for rec in self:
            _logger.debug('Attempting to connect with the following details: IP=%s, User=%s, Port=%s, Database=%s', rec.db_ip, rec.db_user, rec.db_port, rec.db_name)
            if rec.test_connection():
                rec.write({'state': 'active'})
                _logger.info('Successfully connected to the database at %s', rec.db_ip)
            else:
                _logger.debug('Failed to connect to the database with the provided details.')
                raise ValidationError(_('Connection error: Unable to connect to the database. Please check your connection details and try again.'))

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
