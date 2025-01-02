# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
import datetime

import pyodbc
import pytz
from dateutil.relativedelta import relativedelta
from odoo import fields, models, _
from odoo.exceptions import ValidationError


class AttendanceLog(models.Model):
    _name = "attendance.log"
    _description = "Attendance of Biometric Machine aspl"
    _order = "log_date desc"

    device_log_id = fields.Integer(string="DeviceLogId")
    user_id = fields.Many2one('res.users', string='User')
    employee = fields.Many2one('hr.employee', string='Employee')
    log_date = fields.Datetime(string="LogDate")
    direction = fields.Char(string="Direction")

    def generate_attendance(self):
        connector_ids = self.env['connector.sqlserver'].search([('auto_gen_attendance', '=', True)])
        for connector in connector_ids:
            try:
                conn_str = (
                    f'DRIVER={{ODBC Driver 17 for SQL Server}};'
                    f'SERVER={connector.db_ip};'
                    f'PORT={connector.db_port};'
                    f'DATABASE={connector.db_name};'
                    f'UID={connector.db_user};'
                    f'PWD={connector.password};'
                    f'TrustServerCertificate=yes;'
                )
                conn = pyodbc.connect(conn_str, timeout=10)

                start_date = (datetime.datetime.today() - relativedelta(months=1)).strftime("%Y-%m-%d")
                end_date = datetime.datetime.today().strftime("%Y-%m-%d")
                t1 = f"DeviceLogs_{(datetime.datetime.today() - relativedelta(days=15)).month}_{(datetime.datetime.today() - relativedelta(months=1)).year}"
                t2 = f"DeviceLogs_{datetime.datetime.today().month}_{datetime.datetime.today().year}"

                sql = "select DeviceLogId,UserId,LogDate,Direction from " + str(
                    t1) + " where cast(LogDate as DATE) >= '" + str(
                    start_date) + "' and cast(LogDate as DATE) <= '" + str(
                    end_date) + "' UNION select DeviceLogId,UserId,LogDate,Direction from " + str(
                    t2) + " where cast(LogDate as DATE) >= '" + str(
                    start_date) + "' and cast(LogDate as DATE) <= '" + str(
                    end_date) + "' order by UserId,LogDate;"

                if conn:
                    cursor = conn.cursor()
                    cursor.execute(sql)
                    row = cursor.fetchone()

                    prev_bio_data = False
                    last_attendance = False
                    user_time = pytz.timezone(self.env.user.partner_id.tz)
                    while row is not None:
                        row = cursor.fetchone()
                        if row is None:
                            continue
                        else:
                            row = list(row)
                            hr_employee = self.env['hr.employee'].search([('biometric_no', '=', row[1])])
                            if hr_employee:
                                if len(hr_employee) > 1:
                                    continue

                                if row[2] is not None:
                                    local = pytz.timezone(self.env.user.partner_id.tz)
                                    local_dt = local.localize(row[2], is_dst=None)
                                    row[2] = local_dt.astimezone(pytz.utc).strftime("%Y-%m-%d %H:%M:%S")

                                if row is not None:
                                    model_data = {
                                        'device_log_id': row[0],
                                        'user_id': hr_employee.user_id.id,
                                        'employee': hr_employee.id,
                                        'log_date': row[2],
                                        'direction': row[3],
                                    }
                                    existing_record = self.env['attendance.log'].search(
                                        [('device_log_id', '=', row[0]), ('log_date', '=', row[2])])
                                    if not existing_record:
                                        bio_data = self.env['attendance.log'].create(model_data)

                                        # create hr.attendance
                                        user_date = bio_data.log_date.astimezone(user_time).strftime("%H:%M")

                                        # make prev_bio_data empty when employee change, or date change
                                        if prev_bio_data and (
                                                prev_bio_data.employee != bio_data.employee or prev_bio_data.log_date.date() != bio_data.log_date.date()):
                                            # set check-out in last attendance if check-out not find.
                                            if prev_bio_data.employee == bio_data.employee and prev_bio_data.log_date.date() != bio_data.log_date.date() and not last_attendance.check_out:
                                                last_attendance.write({'check_out': last_attendance.check_in,
                                                                       'comment': 'Check Out not found.',
                                                                       'has_error': True})
                                            prev_bio_data = False
                                            last_attendance = False

                                        if bio_data.direction == 'out' and not prev_bio_data:
                                            # check last entry of in direction without check-out then set check-out in last entry for same day and continue
                                            no_check_out_attendances = self.env['hr.attendance'].search([
                                                ('employee_id', '=', hr_employee.id),
                                                ('check_out', '=', False),
                                            ], order='check_in desc', limit=1)
                                            if no_check_out_attendances and no_check_out_attendances.check_in.date() == bio_data.log_date.date():
                                                no_check_out_attendances.write(
                                                    {'check_out': bio_data.log_date,
                                                     'comment': no_check_out_attendances.comment + ', ' + user_date + '(O)'})
                                                last_attendance = no_check_out_attendances
                                                prev_bio_data = bio_data
                                                continue
                                            else:
                                                if no_check_out_attendances and no_check_out_attendances.check_in.date() != bio_data.log_date.date():
                                                    no_check_out_attendances.write(
                                                        {'check_out': no_check_out_attendances.check_in,
                                                         'comment': 'Check Out not found.',
                                                         'has_error': True})

                                                # continue if first entry get of out direction
                                                att_vals = {
                                                    'employee_id': hr_employee.id,
                                                    'check_in': bio_data.log_date,
                                                    'check_out': bio_data.log_date,
                                                    'comment': "Check In not found.",
                                                    'has_error': True
                                                }
                                                self.env['hr.attendance'].create(att_vals)
                                                continue

                                        if bio_data.direction == 'in':
                                            if prev_bio_data and prev_bio_data.direction == 'in':
                                                last_attendance.check_in = bio_data.log_date
                                                last_attendance.write(
                                                    {'check_in': bio_data.log_date,
                                                     'has_error': True,
                                                     'comment': last_attendance.comment + ', ' + user_date + '(I)'})
                                            else:
                                                existing_attendance = self.env['hr.attendance'].search([
                                                    ('employee_id', '=', hr_employee.id),
                                                    ('check_in', '=', bio_data.log_date),
                                                ], limit=1)
                                                if existing_attendance:
                                                    last_attendance = existing_attendance
                                                else:
                                                    # check last in attendance with current in attendance
                                                    last_in_attendances = self.env['hr.attendance'].search([
                                                        ('employee_id', '=', hr_employee.id),
                                                        ('check_out', '=', False),
                                                        ('check_in', '!=', False),
                                                    ], order='check_in desc', limit=1)
                                                    if last_in_attendances and last_in_attendances.check_in.date() == bio_data.log_date.date():
                                                        last_in_attendances.write(
                                                            {'check_in': bio_data.log_date,
                                                             'has_error': True,
                                                             'comment': last_in_attendances.comment + ', ' + user_date + '(I)'})
                                                        last_attendance = last_in_attendances
                                                        prev_bio_data = bio_data
                                                        continue
                                                    if last_in_attendances and last_in_attendances.check_in.date() != bio_data.log_date.date():
                                                        last_in_attendances.write(
                                                            {'check_out': last_in_attendances.check_in,
                                                             'comment': 'Check Out not found.',
                                                             'has_error': True})
                                                    # create new hr.attendance
                                                    att_vals = {
                                                        'employee_id': hr_employee.id,
                                                        'check_in': bio_data.log_date,
                                                        'comment': user_date + '(I)',
                                                    }
                                                    last_attendance = self.env['hr.attendance'].create(att_vals)

                                        elif prev_bio_data and prev_bio_data.direction == 'in' and bio_data.direction == 'out':
                                            if not last_attendance.check_out:
                                                last_attendance.write(
                                                    {'check_out': bio_data.log_date,
                                                     'comment': last_attendance.comment + ', ' + user_date + '(O)'})
                                        elif prev_bio_data and prev_bio_data.direction == 'out' and bio_data.direction == 'out':
                                            last_attendance.comment = last_attendance.comment + ', ' + user_date + '(O)'
                                            last_attendance.write({'has_error': True,
                                                                   'comment': last_attendance.comment + ', ' + user_date + '(O)'})
                                        prev_bio_data = bio_data

                conn.close()
            except ValueError as e:
                raise ValidationError(_('Connection error: ' + e))
