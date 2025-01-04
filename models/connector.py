# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
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

    def get_connection(self):
        """Shared connection method that can be used across the module"""
        self.ensure_one()
        try:
            _logger.info(f'Creating connection to {self.db_ip}:{self.db_port} with database {self.db_name}')
            
            # Try different connection configurations
            configs = [
                # Basic configuration
                {
                    'server': self.db_ip,
                    'user': self.db_user,
                    'password': self.password,
                    'database': self.db_name,
                    'port': int(self.db_port)
                },
                # Try with different server format
                {
                    'server': f'{self.db_ip}:{self.db_port}',
                    'user': self.db_user,
                    'password': self.password,
                    'database': self.db_name
                },
                # Try with minimal config
                {
                    'host': self.db_ip,
                    'user': self.db_user,
                    'password': self.password,
                    'database': self.db_name
                }
            ]

            last_error = None
            for i, config in enumerate(configs, 1):
                try:
                    _logger.info('Attempt %d: Trying connection with config: %s', 
                        i, {k:v for k,v in config.items() if k != 'password'})

                    # Test network connectivity first
                    if not self._test_network(self.db_ip, self.db_port):
                        _logger.warning('Network connectivity test failed')
                        continue

                    # Test connection and version
                    conn = pymssql.connect(**config)
                    cursor = conn.cursor()
                    cursor.execute('SELECT @@VERSION')
                    version = cursor.fetchone()
                    _logger.info('Successfully connected with config %d. SQL Server version: %s', i, version)
                    
                    return conn
                except Exception as e:
                    last_error = e
                    _logger.warning('Connection attempt %d failed: %s', i, str(e))
                    if 'conn' in locals():
                        try:
                            conn.close()
                        except:
                            pass
                    continue

            if last_error:
                raise last_error
            
        except Exception as e:
            _logger.error('Connection failed: %s', str(e), exc_info=True)
            raise ValidationError(_(f'Connection error: {str(e)}'))

    def test_connection(self):
        for rec in self:
            server = rec.db_ip
            _logger.info('Starting connection test sequence...')
            
            # Test network connectivity first
            if not self._test_network(server, rec.db_port):
                _logger.error('Network connectivity test failed')
                return False

            try:
                conn = self.get_connection()
                conn.close()
                return True
            except Exception as e:
                _logger.error(f'Connection failed: {str(e)}')
                return False

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
