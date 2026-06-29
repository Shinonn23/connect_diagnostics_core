# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

# Alias to avoid shadowing the `refresh_address_display` submodule with the command of the
# same name. The shadow makes `@patch("...commands.refresh_address_display.<x>")` resolve to
# the command object instead of the module, so test mocks would silently not apply.
from .data_export import cd_data_export
from .refresh_address_display import refresh_address_display as refresh_address_display_command
from .sync_address_party_tax import sync_address_party_tax as sync_address_party_tax_command
from .uat_backup_restore import (
    restore_uat_backup,
    setup_uat_restore_cron,
    show_uat_restore_log,
    test_uat_backup_restore,
)

commands = [
    refresh_address_display_command,
    sync_address_party_tax_command,
    restore_uat_backup,
    test_uat_backup_restore,
    setup_uat_restore_cron,
    show_uat_restore_log,
    cd_data_export,
]
