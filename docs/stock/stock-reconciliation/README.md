# Stock Reconciliation

Physical stock counting and quantity correction use ERPNext's standard Stock Reconciliation document and native stock posting behavior.

Connect Diagnostics Core does not define a separate app-owned stock-count posting document. Any app validation around counting must terminate at the native Stock Reconciliation boundary rather than posting inventory through a parallel mechanism.
