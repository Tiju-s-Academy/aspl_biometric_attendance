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

                                        # Simplified attendance creation
                                        if bio_data.direction == 'in':
                                            # Create new attendance record for check-in
                                            att_vals = {
                                                'employee_id': hr_employee.id,
                                                'check_in': bio_data.log_date,
                                                'comment': user_date + '(I)',
                                            }
                                            last_attendance = self.env['hr.attendance'].sudo().create(att_vals)
                                            prev_bio_data = bio_data

                                        elif bio_data.direction == 'out' and prev_bio_data and prev_bio_data.direction == 'in':
                                            # Update check-out time for the last attendance
                                            if last_attendance and not last_attendance.check_out:
                                                last_attendance.write({
                                                    'check_out': bio_data.log_date,
                                                    'comment': (last_attendance.comment or '') + ', ' + user_date + '(O)'
                                                })

                                        # Remove other conditions as we only care about first and last entries

                conn.close()
            except ValueError as e:
                raise ValidationError(_('Connection error: ' + e))
