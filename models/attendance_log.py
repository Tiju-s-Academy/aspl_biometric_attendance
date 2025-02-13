# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
import datetime

import pymssql
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
                conn = pymssql.connect(server=connector.db_ip, user=connector.db_user,
                                       password=connector.password, database=connector.db_name,
                                       port=connector.db_port)

                start_date = (datetime.datetime.today() - relativedelta(months=1)).strftime("%Y-%m-%d")
                end_date = datetime.datetime.today().strftime("%Y-%m-%d")
                t1 = f"DeviceLogs_{(datetime.datetime.today() - relativedelta(days=15)).month}_{(datetime.datetime.today() - relativedelta(months=1)).year}"
                t2 = f"DeviceLogs_{datetime.datetime.today().month}_{datetime.datetime.today().year}"

                sql = """
                    WITH OrderedLogs AS (
                        SELECT DeviceLogId, UserId, LogDate,
                        ROW_NUMBER() OVER(PARTITION BY UserId, CAST(LogDate AS DATE) 
                                        ORDER BY LogDate) as first_entry,
                        ROW_NUMBER() OVER(PARTITION BY UserId, CAST(LogDate AS DATE) 
                                        ORDER BY LogDate DESC) as last_entry,
                        COUNT(*) OVER(PARTITION BY UserId, CAST(LogDate AS DATE)) as entry_count
                        FROM (
                            SELECT DeviceLogId, UserId, LogDate FROM """ + str(t1) + """
                            WHERE cast(LogDate as DATE) >= '""" + str(start_date) + """' 
                            AND cast(LogDate as DATE) <= '""" + str(end_date) + """'
                            UNION ALL
                            SELECT DeviceLogId, UserId, LogDate FROM """ + str(t2) + """
                            WHERE cast(LogDate as DATE) >= '""" + str(start_date) + """' 
                            AND cast(LogDate as DATE) <= '""" + str(end_date) + """'
                        ) combined_logs
                    )
                    SELECT DeviceLogId, UserId, LogDate,
                        CASE 
                            WHEN first_entry = 1 THEN 'in'
                            WHEN last_entry = 1 THEN 'out'
                            WHEN entry_count = 1 THEN 'in'
                            ELSE 'mid'
                        END as Direction
                    FROM OrderedLogs
                    ORDER BY UserId, LogDate;
                """

                if conn:
                    cursor = conn.cursor()
                    cursor.execute(sql)
                    row = cursor.fetchone()

                    prev_bio_data = False
                    last_attendance = False
                    # Use UTC if user timezone is not set
                    user_tz = self.env.user.partner_id.tz or 'UTC'
                    user_time = pytz.timezone(user_tz)
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
                                    # Use same timezone fallback for local conversion
                                    local_tz = self.env.user.partner_id.tz or 'UTC'
                                    local = pytz.timezone(local_tz)
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

                                        # Add safety check for last_attendance
                                        if prev_bio_data and (prev_bio_data.employee != bio_data.employee or 
                                                            prev_bio_data.log_date.date() != bio_data.log_date.date()):
                                            if (prev_bio_data.employee == bio_data.employee and 
                                                prev_bio_data.log_date.date() != bio_data.log_date.date() and 
                                                last_attendance and not last_attendance.check_out):
                                                last_attendance.write({
                                                    'check_out': last_attendance.check_in,
                                                    'comment': 'Check Out not found.',
                                                    'has_error': True
                                                })
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
                                            try:
                                                # First check for any unclosed attendance
                                                open_attendance = self.env['hr.attendance'].search([
                                                    ('employee_id', '=', hr_employee.id),
                                                    ('check_out', '=', False)
                                                ], order='check_in desc', limit=1)
                                                
                                                if open_attendance:
                                                    # If open attendance is from a previous date or same date
                                                    if open_attendance.check_in.date() <= bio_data.log_date.date():
                                                        # Close the previous attendance with its check_in time
                                                        open_attendance.write({
                                                            'check_out': open_attendance.check_in,
                                                            'comment': (open_attendance.comment or '') + ', Auto-closed: multiple check-ins',
                                                            'has_error': True
                                                        })
                                                
                                                # Create new attendance record
                                                att_vals = {
                                                    'employee_id': hr_employee.id,
                                                    'check_in': bio_data.log_date,
                                                    'comment': user_date + '(I)',
                                                }
                                                last_attendance = self.env['hr.attendance'].sudo().create(att_vals)
                                                prev_bio_data = bio_data
                                                
                                            except Exception as e:
                                                _logger.warning(f"Attendance creation failed for employee {hr_employee.name}: {str(e)}")
                                                continue

                                        elif bio_data.direction == 'out':
                                            # Find the most recent unclosed attendance
                                            open_attendance = self.env['hr.attendance'].search([
                                                ('employee_id', '=', hr_employee.id),
                                                ('check_out', '=', False)
                                            ], order='check_in desc', limit=1)
                                            
                                            if open_attendance:
                                                open_attendance.write({
                                                    'check_out': bio_data.log_date,
                                                    'comment': (open_attendance.comment or '') + ', ' + user_date + '(O)'
                                                })
                                                last_attendance = open_attendance
                                            else:
                                                # If no open attendance found, create a new complete record
                                                att_vals = {
                                                    'employee_id': hr_employee.id,
                                                    'check_in': bio_data.log_date,
                                                    'check_out': bio_data.log_date,
                                                    'comment': "Auto-generated: single out punch",
                                                    'has_error': True
                                                }
                                                last_attendance = self.env['hr.attendance'].sudo().create(att_vals)
                                            
                                            prev_bio_data = bio_data

                conn.close()
            except ValueError as e:
                raise ValidationError(_('Connection error: ' + e))
