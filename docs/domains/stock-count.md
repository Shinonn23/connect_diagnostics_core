# Stock Count

The app-owned Stock Count system was retired as part of the clean stock reset.

Stock counting now uses standard ERPNext Stock Reconciliation and the native
ERPNext stock workflow. The app no longer owns Stock Count DocTypes, variance
reports, freeze hooks, holding-warehouse fields, or related workspace entries.

No data-cleanup or rollback patch is provided because the reset is for the
unused DEV environment.
