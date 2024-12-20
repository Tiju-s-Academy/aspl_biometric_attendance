# -*- coding: utf-8 -*-
###############################################################################
#
# Aspire Softserv Pvt. Ltd.
# Copyright (C) Aspire Softserv Pvt. Ltd.(<https://aspiresoftserv.com>).
#
###############################################################################
{
    "name": "ESSL Biometric Attendance",
    "category": "Attendance",
    "summary": "Live attendance updates from ESSL attendance device.",
    "version": "17.0.0.1.0",
    "price": 19.99,
    "license": "AGPL-3",
    'description': """
        ESSL biometric devices are quite popular for attendance management. This modules provides integration between ESSL device and Odoo attendance module. It provides you almost live view of presence.
    """,
    "author": "Aspire Softserv Pvt. Ltd",
    "website": "https://aspiresoftserv.com",
    "depends": ['base', 'hr', 'hr_attendance'],
    "external_dependencies": {
        'python': ['pymssql', 'pytz']
    },
    "data": [
        'security/user_group.xml',
        'security/ir.model.access.csv',
        'data/attendance_log_cron.xml',
        'views/hr_attendance_views.xml',
        'views/attendance_log_view.xml',
        'views/connector_setup.xml',
        'views/inherit_hr_employee_view.xml',
    ],
    "application": True,
    "installable": True,
    "maintainer": "Aspire Softserv Pvt. Ltd",
    "support": "odoo@aspiresoftserv.com",
    "images": ['static/description/banner.gif'],
}
