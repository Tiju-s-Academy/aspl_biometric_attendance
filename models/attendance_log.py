# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
import datetime
import logging

import pymssql
import pytz
from dateutil.relativedelta import relativedelta
from odoo import fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

class AttendanceLog(models.Model):
    _name = "attendance.log"
    _description = "Attendance of Biometric Machine aspl"
    _order = "log_date desc"

    device_log_id = fields.Integer(string="DeviceLogId")
    user_id = fields.Many2one('res.users', string='User')
    employee = fields.Many2one('hr.employee', string='Employee')
    log_date = fields.Datetime(string="LogDate")
    direction = fields.Char(string="Direction")

    def _force_create_attendance(self, vals):
        """Create attendance record directly using SQL to bypass validation"""
        query = """
            INSERT INTO hr_attendance 
            (employee_id, check_in, check_out, comment, has_error, create_uid, create_date, write_uid, write_date) 
            VALUES (%s, %s, %s, %s, %s, %s, NOW(), %s, NOW()) RETURNING id
        """
        self.env.cr.execute(query, (
            vals['employee_id'],
            vals['check_in'],
            vals.get('check_out', None),
            vals.get('comment', ''),
            vals.get('has_error', False),
            self.env.uid,
            self.env.uid
        ))
        return self.env.cr.fetchone()[0]

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
                    WITH DailyLogs AS (
                        SELECT DeviceLogId, UserId, LogDate,
                            FIRST_VALUE(LogDate) OVER(PARTITION BY UserId, CAST(LogDate AS DATE) 
                                ORDER BY LogDate) as first_log,
                            LAST_VALUE(LogDate) OVER(PARTITION BY UserId, CAST(LogDate AS DATE) 
                                ORDER BY LogDate ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) as last_log
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
                    SELECT DISTINCT DeviceLogId, UserId, LogDate,
                        CASE 
                            WHEN LogDate = first_log THEN 'in'
                            WHEN LogDate = last_log AND LogDate != first_log THEN 'out'
                            ELSE NULL
                        END as Direction
                    FROM DailyLogs
                    WHERE LogDate = first_log OR LogDate = last_log
                    ORDER BY UserId, LogDate;
                """

                if conn:
                    cursor = conn.cursor()
                    cursor.execute(sql)
                    row = cursor.fetchone()

                    prev_bio_data = False
                    last_attendance = False
                    # Use UTC if user timezone is not set
                    user_tz = self.env.user.partner_id.tz or 'Asia/Kolkata'  # Default to IST if no timezone
                    user_time = pytz.timezone(user_tz)
                    utc = pytz.UTC

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
                                    # Convert the database time to user's timezone
                                    naive_dt = row[2]
                                    if isinstance(naive_dt, str):
                                        naive_dt = datetime.datetime.strptime(naive_dt, "%Y-%m-%d %H:%M:%S")
                                    
                                    # First localize to user timezone
                                    local_dt = user_time.localize(naive_dt, is_dst=None)
                                    # Then convert to UTC for storage
                                    utc_dt = local_dt.astimezone(utc)
                                    
                                    _logger.info(f"Time conversion for {row[1]}: Original: {row[2]}, Local: {local_dt}, UTC: {utc_dt}")
                                    
                                    row[2] = utc_dt.strftime("%Y-%m-%d %H:%M:%S")

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
                                        local_time = pytz.utc.localize(datetime.datetime.strptime(row[2], "%Y-%m-%d %H:%M:%S"))
                                        user_date = local_time.astimezone(user_time).strftime("%H:%M")

                                        # Check for any unclosed attendance
                                        open_attendance = self.env['hr.attendance'].search([
                                            ('employee_id', '=', hr_employee.id),
                                            ('check_out', '=', False)
                                        ], order='check_in desc', limit=1)

                                        # If this is a new day compared to open attendance, close previous and create new
                                        if open_attendance and open_attendance.check_in.date() != bio_data.log_date.date():
                                            # Close previous day's attendance with its check-in time
                                            open_attendance.sudo().write({
                                                'check_out': open_attendance.check_in,
                                                'comment': (open_attendance.comment or '') + ', Auto-closed: new day',
                                                'has_error': True
                                            })
                                            # Create new attendance for the new day
                                            att_vals = {
                                                'employee_id': hr_employee.id,
                                                'check_in': bio_data.log_date,
                                                'comment': user_date + '(I)',
                                            }
                                            last_attendance = self.env['hr.attendance'].sudo().create(att_vals)
                                            prev_bio_data = bio_data
                                            continue

                                        # Handle same day entries
                                        if bio_data.direction == 'in':
                                            try:
                                                if not open_attendance:
                                                    att_vals = {
                                                        'employee_id': hr_employee.id,
                                                        'check_in': row[2],  # Using UTC time directly
                                                        'comment': user_date + '(I)',
                                                    }
                                                    last_attendance = self.env['hr.attendance'].sudo().create(att_vals)
                                                    prev_bio_data = bio_data
                                            except Exception as e:
                                                _logger.info(f"Using force create for {hr_employee.name}: {str(e)}")
                                                # If normal create fails, use force create
                                                att_id = self._force_create_attendance(att_vals)
                                                last_attendance = self.env['hr.attendance'].sudo().browse(att_id)
                                                prev_bio_data = bio_data

                                        elif bio_data.direction == 'out':
                                            if open_attendance and open_attendance.check_in.date() == bio_data.log_date.date():
                                                open_attendance.sudo().write({
                                                    'check_out': row[2],  # Using UTC time directly
                                                    'comment': (open_attendance.comment or '') + ', ' + user_date + '(O)'
                                                })
                                                last_attendance = open_attendance
                                                prev_bio_data = bio_data

                conn.close()
            except ValueError as e:
                raise ValidationError(_('Connection error: ' + e))
