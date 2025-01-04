# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
import pyodbc
from pyodbc import OperationalError
import pymssql
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging
import socket
import time

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

    def _test_network(self, host, port):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((host, int(port)))
            sock.close()
            if result == 0:
                _logger.info(f"Port {port} is open on host {host}")
                return True
            _logger.error(f"Port {port} is closed on host {host}")
            return False
        except Exception as e:
            _logger.error(f"Network test failed: {str(e)}")
            return False

    def test_connection(self):
        for rec in self:
            server = rec.db_ip
            _logger.info('Starting connection test sequence...')
            
            # Test network connectivity first
            if not self._test_network(server, rec.db_port):
                _logger.error('Network connectivity test failed')
                return False

            # Try different connection methods
            methods = [
                self._try_pymssql_connection,
                self._try_pyodbc_connection,
                self._try_direct_connection
            ]

            for method in methods:
                try:
                    if method(rec):
                        return True
                except Exception as e:
                    _logger.error(f'Connection method {method.__name__} failed: {str(e)}')
                    continue
            
            return False

    def _try_pymssql_connection(self, rec):
        _logger.info('Attempting PyMSSQL connection...')
        try:
            conn = pymssql.connect(
                server=rec.db_ip,
                user=rec.db_user,
                password=rec.password,
                database=rec.db_name,
                port=int(rec.db_port),
                timeout=10
            )
            _logger.info('PyMSSQL connection successful')
            conn.close()
            return True
        except Exception as e:
            _logger.error(f'PyMSSQL connection failed: {str(e)}')
            raise

    def _try_pyodbc_connection(self, rec):
        _logger.info('Attempting PyODBC connection...')
        try:
            conn_str = (
                f'DRIVER={{ODBC Driver 17 for SQL Server}};'
                f'SERVER={rec.db_ip};'
                f'PORT={rec.db_port};'
                f'DATABASE={rec.db_name};'
                f'UID={rec.db_user};'
                f'PWD={rec.password};'
                f'TrustServerCertificate=yes;'
                f'Timeout=10;'
            )
            _logger.debug(f'Connection string: {conn_str}')
            conn = pyodbc.connect(conn_str)
            _logger.info('PyODBC connection successful')
            conn.close()
            return True
        except Exception as e:
            _logger.error(f'PyODBC connection failed: {str(e)}')
            raise

    def _try_direct_connection(self, rec):
        _logger.info('Attempting direct TCP connection...')
        try:
            conn_str = f"tcp:host={rec.db_ip},port={rec.db_port};uid={rec.db_user};pwd={rec.password}"
            sock = socket.create_connection((rec.db_ip, int(rec.db_port)), timeout=10)
            _logger.info('TCP connection successful')
            sock.close()
            return True
        except Exception as e:
            _logger.error(f'Direct TCP connection failed: {str(e)}')
            raise

    def connect(self):
        for rec in self:
            _logger.info(f'Attempting to connect to {rec.db_ip}:{rec.db_port}')
            start_time = time.time()
            
            if rec.test_connection():
                elapsed_time = time.time() - start_time
                _logger.info(f'Connection successful after {elapsed_time:.2f} seconds')
                rec.write({'state': 'active'})
            else:
                _logger.error('All connection attempts failed')
                raise ValidationError(_('Connection error: Unable to connect to the database. Please check the logs for detailed error information.'))

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
