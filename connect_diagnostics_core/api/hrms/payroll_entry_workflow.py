# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Payroll Entry mixin preserving HRMS accounting generation as a draft."""

from __future__ import annotations

from typing import Any


class PayrollEntryWorkflowMixin:
    """Keep HRMS source links while preventing accrual JE direct submission."""

    def make_journal_entry(self: Any, *args: Any, **kwargs: Any) -> Any:
        # HRMS uses this flag only for its direct submit.  The native document
        # construction and Salary Slip linking remain in the superclass.
        if len(args) >= 7:
            args = (*args[:6], False, *args[7:])
        else:
            kwargs["submit_journal_entry"] = False
        return super().make_journal_entry(*args, **kwargs)
