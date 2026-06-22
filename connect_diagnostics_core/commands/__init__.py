# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from .refresh_address_display import refresh_address_display
from .uat_backup_restore import (
    restore_uat_backup,
    setup_uat_restore_cron,
    show_uat_restore_log,
    test_uat_backup_restore,
)

commands = [
    refresh_address_display,
    restore_uat_backup,
    test_uat_backup_restore,
    setup_uat_restore_cron,
    show_uat_restore_log,
]
