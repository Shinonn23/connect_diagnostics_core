# Changelog

## [0.46.0](https://github.com/Shinonn23/connect_diagnostics_core/compare/v0.45.0...v0.46.0) (2026-08-20)


### Features

* freeze stock transactions for items under active Stock Count ([9b75503](https://github.com/Shinonn23/connect_diagnostics_core/commit/9b75503267c804face7d20ebc4789776310f467b))


### Code Refactoring

* retire Storage Location doctype, use native Warehouse tree for Stock Count ([710df59](https://github.com/Shinonn23/connect_diagnostics_core/commit/710df591dd048d379ecb98c5c6bb121008b9f754))
* retire Storage Location, use native Warehouse tree for Stock Count ([1ba8299](https://github.com/Shinonn23/connect_diagnostics_core/commit/1ba829990df695037d8366b3aaf113ba5c244302))

## [0.45.0](https://github.com/Shinonn23/connect_diagnostics_core/compare/v0.44.2...v0.45.0) (2026-08-19)


### Features

* enforce Quotation signatory, add Delivery Terms Template, and redesign the Signatory/Terms layout ([0492703](https://github.com/Shinonn23/connect_diagnostics_core/commit/04927039d6af4988fc4f985eb77b5f244f7fe3f0))

## [0.44.2](https://github.com/Shinonn23/connect_diagnostics_core/compare/v0.44.1...v0.44.2) (2026-08-19)


### Bug Fixes

* restore POS received/change rows lost by the live-DEV print format sync ([b79ffc4](https://github.com/Shinonn23/connect_diagnostics_core/commit/b79ffc46d27707ad63d01926b1a08ea07353c731))
* restore POS received/change rows lost by the live-DEV print format sync ([38345a2](https://github.com/Shinonn23/connect_diagnostics_core/commit/38345a2b45f4e6693220a8f4f145eaed49d8a2e7))

## [0.44.1](https://github.com/Shinonn23/connect_diagnostics_core/compare/v0.44.0...v0.44.1) (2026-08-19)


### Bug Fixes

* replace Goods Receipt/Sales Order's local date macro with the shared helper ([f9a0f16](https://github.com/Shinonn23/connect_diagnostics_core/commit/f9a0f162aafce6a0681799c8a430bf9bc8cc38e5))
* sync live-DEV print format content and stop pinning template content in tests ([1416c07](https://github.com/Shinonn23/connect_diagnostics_core/commit/1416c07a779571f6b0af16f6ec943d9705022ce0))
* sync live-DEV print format content and stop pinning template content in tests ([93be77f](https://github.com/Shinonn23/connect_diagnostics_core/commit/93be77ff2df52586395c58b2168412816ab4bfd0))
* sync live-DEV print format content that never deployed ([1372a4d](https://github.com/Shinonn23/connect_diagnostics_core/commit/1372a4dcaaba46af1eef77b61eccc7873c4f0bcc))

## [0.44.0](https://github.com/Shinonn23/connect_diagnostics_core/compare/v0.43.5...v0.44.0) (2026-08-19)


### Features

* update Desk-edited print formats; redesign Shipment Box Label sizes ([8c064b4](https://github.com/Shinonn23/connect_diagnostics_core/commit/8c064b46038a59110c1e95e23e00f5a1aec5893e))


### Bug Fixes

* pass print_settings into the Shipment Box Label test render context ([6bb77bf](https://github.com/Shinonn23/connect_diagnostics_core/commit/6bb77bf3de4110b9353489cf7bcb52d9ef0d024f))


### Tests

* remove print format rendering tests ([594735c](https://github.com/Shinonn23/connect_diagnostics_core/commit/594735c3d3506930145c327e7f76873a6858f9fd))


### Documentation

* remove the "never test print formats" rule this branch had added ([3b86a20](https://github.com/Shinonn23/connect_diagnostics_core/commit/3b86a20dca6b73432f94af19af0d5a10ddd7d48b))

## [0.43.5](https://github.com/Shinonn23/connect_diagnostics_core/compare/v0.43.4...v0.43.5) (2026-08-19)


### Bug Fixes

* register Credit Note in the print-format test suite ([8de1a94](https://github.com/Shinonn23/connect_diagnostics_core/commit/8de1a946578cc276c6cb828164d437aec4dfa44a))
* render POS received/change fields on the abbreviated tax invoice ([cec50bf](https://github.com/Shinonn23/connect_diagnostics_core/commit/cec50bf5ad1e4a0a5f1bccdb783f04ed1a704bb5))
* resolve braced autoname hyphen-token bug, POS print gap, and doc fixes ([8c331a0](https://github.com/Shinonn23/connect_diagnostics_core/commit/8c331a0178214cf333ac967b3e89be6a192bcbb3))
* resolve braced autoname tokens never matching hyphenated names ([5fdee97](https://github.com/Shinonn23/connect_diagnostics_core/commit/5fdee97845a8d6645c1e857305e425e4f0834e00))


### Documentation

* correct the bench path and dev site name ([2c978ca](https://github.com/Shinonn23/connect_diagnostics_core/commit/2c978ca1b79836efc74cb54472dd4c134e0f40d7))

## [0.43.4](https://github.com/Shinonn23/connect_diagnostics_core/compare/v0.43.3...v0.43.4) (2026-08-19)


### Code Refactoring

* delete app-owned Workflow records from the database ([a8a135c](https://github.com/Shinonn23/connect_diagnostics_core/commit/a8a135ceaec3db378118933d0660833bde675557))
* remove workflow-derived enforcement from document hooks ([9fc273d](https://github.com/Shinonn23/connect_diagnostics_core/commit/9fc273d920527301d072711eee1bf34ab6b0c59f))
* remove workflow-only roles, profiles, and approval permissions ([e81c0ff](https://github.com/Shinonn23/connect_diagnostics_core/commit/e81c0ffa9440cceb03fc2f4b28b1f9a9ef3fb185))
* remove workflow-state custom fields ([5acdb1f](https://github.com/Shinonn23/connect_diagnostics_core/commit/5acdb1f7171c1e8acc2aee6fbb2e0ea132508bd8))
* remove workflow-state fields from app-owned DocTypes ([df84f49](https://github.com/Shinonn23/connect_diagnostics_core/commit/df84f49e73d8a21b4a72d4be0694caa68130c08f))
* reset custom workflow architecture to a workflow-free baseline ([01e8796](https://github.com/Shinonn23/connect_diagnostics_core/commit/01e87962b97a263930534d1cf324837703216323))
* stop provisioning app-owned Workflows ([54f958a](https://github.com/Shinonn23/connect_diagnostics_core/commit/54f958aca19e5e6ade8cfc14718d5dd21154d132))


### Documentation

* describe the workflow-free baseline and guard against regressions ([c2f93e9](https://github.com/Shinonn23/connect_diagnostics_core/commit/c2f93e9adc3703d503c2dada982d5202daa37277))

## [0.43.3](https://github.com/Shinonn23/connect_diagnostics_core/compare/v0.43.2...v0.43.3) (2026-08-18)


### Bug Fixes

* retire the Print Configuration Template workspace link ([5168056](https://github.com/Shinonn23/connect_diagnostics_core/commit/5168056a85c20caa6c7a5942bafaba64bbbea5b7))
* retire the Print Configuration Template workspace link ([bfbf381](https://github.com/Shinonn23/connect_diagnostics_core/commit/bfbf3812cb0263348ae541b2bd2afbfe46124860))

## [0.43.2](https://github.com/Shinonn23/connect_diagnostics_core/compare/v0.43.1...v0.43.2) (2026-08-18)


### Bug Fixes

* keep Shipment Box Label static and correct print-format counts ([f257f4f](https://github.com/Shinonn23/connect_diagnostics_core/commit/f257f4fb915d89cad44ff22b8ee30128e9fde03b))


### Code Refactoring

* remove per-Customer print configuration ([8ab8d7d](https://github.com/Shinonn23/connect_diagnostics_core/commit/8ab8d7db8632e38ea05da5f16ce7a63bd7a51f35))

## [0.43.1](https://github.com/Shinonn23/connect_diagnostics_core/compare/v0.43.0...v0.43.1) (2026-08-17)


### Bug Fixes

* strip Thai prefixes from By-Tax-ID address lookup ([4762372](https://github.com/Shinonn23/connect_diagnostics_core/commit/476237245ab2fc816325a46c12c1899f9abc3634))

## [0.43.0](https://github.com/Shinonn23/connect_diagnostics_core/compare/v0.42.1...v0.43.0) (2026-08-17)


### Features

* add credit note reason select field to Sales Invoice ([86cbd65](https://github.com/Shinonn23/connect_diagnostics_core/commit/86cbd6503c0e3c7ca19c8749474f1e37e8c63edd))
* add credit note reason select field to Sales Invoice ([abbade2](https://github.com/Shinonn23/connect_diagnostics_core/commit/abbade2c6885030fa8f1df379a55a1e013b66bc1))

## [0.42.1](https://github.com/Shinonn23/connect_diagnostics_core/compare/v0.42.0...v0.42.1) (2026-08-17)


### Bug Fixes

* skip P2P exception gate when workflow is inactive ([e00fb2f](https://github.com/Shinonn23/connect_diagnostics_core/commit/e00fb2f08ad99b15aef7fc2d85545af2f60db114))
* stop over-strict submit gates from blocking P2P and tax-invoice operations ([30231bf](https://github.com/Shinonn23/connect_diagnostics_core/commit/30231bf5c2b3abc9abfa49310dc3b9b76548e137))
* warn instead of block on incomplete customer tax details ([b7f3d54](https://github.com/Shinonn23/connect_diagnostics_core/commit/b7f3d54ae2aadd1d517c8c479fd7b26e5b4580da))

## [0.42.0](https://github.com/Shinonn23/connect_diagnostics_core/compare/v0.41.2...v0.42.0) (2026-08-16)


### Features

* group Stock and Stock Counting under an Inventory Desk folder ([a02600e](https://github.com/Shinonn23/connect_diagnostics_core/commit/a02600ef05da0e786800ab0b2b572c06b42d3eb4))
* group Stock and Stock Counting under an Inventory Desk folder ([c70fcf5](https://github.com/Shinonn23/connect_diagnostics_core/commit/c70fcf50499a98c386920c7da0b54e4288b45dc3))

## [0.41.2](https://github.com/Shinonn23/connect_diagnostics_core/compare/v0.41.1...v0.41.2) (2026-08-16)


### Continuous Integration

* make DEV deployment release-driven and gate expensive checks ([92c6afd](https://github.com/Shinonn23/connect_diagnostics_core/commit/92c6afd273e933200b249a4eef376f7effc74b51))
* make DEV deployment release-driven and gate expensive checks ([9fcc1e5](https://github.com/Shinonn23/connect_diagnostics_core/commit/9fcc1e5285fa2d4c5cfa1581e74ea8fbf3003302))

## [0.41.1](https://github.com/Shinonn23/connect_diagnostics_core/compare/v0.41.0...v0.41.1) (2026-08-13)


### Bug Fixes

* don't force manual item entry on Stock Count before fetching ([8d8c654](https://github.com/Shinonn23/connect_diagnostics_core/commit/8d8c654f6ff26d0a0bac61f446beb5ebcc6279cc))
* sample Stock Count lines, not item codes, and save before fetching ([098adc0](https://github.com/Shinonn23/connect_diagnostics_core/commit/098adc0a55ebadca8c48f28802bdf8663b4bd2bf))
* Stock Count random selection and draft item entry ([178cd7d](https://github.com/Shinonn23/connect_diagnostics_core/commit/178cd7d7aec32ceca18166b7bd2be69566e705ad))

## [0.41.0](https://github.com/Shinonn23/connect_diagnostics_core/compare/v0.40.1...v0.41.0) (2026-08-12)


### Features

* add Stock Count cycle/yearly counting with location-aware adjustments ([d52b6da](https://github.com/Shinonn23/connect_diagnostics_core/commit/d52b6da6fbd5c13a4b8190008ab678bf1c66cfe3))


### Bug Fixes

* make every bootstrap insert idempotent, not just the top-level check ([8d20f43](https://github.com/Shinonn23/connect_diagnostics_core/commit/8d20f430145ba13452e8a63d9dba20fe9b8805dc))
* make Stock Count integration tests self-sufficient and skip broken dep walk ([33a3281](https://github.com/Shinonn23/connect_diagnostics_core/commit/33a32816b92d7ddeba0708f69fe13f4dc98202fe))
* make the ERPNext test-record bootstrap idempotent across test categories ([dbacf36](https://github.com/Shinonn23/connect_diagnostics_core/commit/dbacf360361a1bdf2c49d8c801144e523f06e577))
* resolve remaining CI failures after ERPNext bootstrap fix ([e2d893e](https://github.com/Shinonn23/connect_diagnostics_core/commit/e2d893ebae73b7f6adce530a653f86bdcfe05788))
* supply Customer Code during ERPNext's eager test-record bootstrap ([3caf95b](https://github.com/Shinonn23/connect_diagnostics_core/commit/3caf95bc16e96a2abf1f30ec19f76cc411cc5778))

## [0.40.1](https://github.com/Shinonn23/connect_diagnostics_core/compare/v0.40.0...v0.40.1) (2026-08-12)


### Bug Fixes

* **lint:** apply ruff formatting to workflow code ([908f544](https://github.com/Shinonn23/connect_diagnostics_core/commit/908f5445c8951ee28250d727ca68977a589e028e))


### Code Refactoring

* **workflow:** make approval workflow the single owner ([8f69c19](https://github.com/Shinonn23/connect_diagnostics_core/commit/8f69c191d1dbe20344b64a28ab19e3d687beba8e))

## [0.40.0](https://github.com/Shinonn23/connect_diagnostics_core/compare/v0.39.0...v0.40.0) (2026-08-12)


### Features

* **naming:** standardize operational document numbers ([647983f](https://github.com/Shinonn23/connect_diagnostics_core/commit/647983fe5efa88335d314255536d718a02823d79))
* **naming:** standardize operational document numbers ([91b1fec](https://github.com/Shinonn23/connect_diagnostics_core/commit/91b1fec3e7fcb0d138de9781e4b65c93b28eecef))


### Bug Fixes

* **ci:** normalize naming lint files ([0ccfaba](https://github.com/Shinonn23/connect_diagnostics_core/commit/0ccfaba9310e5f6d06ad4464d8c7d77632ecd102))
* **naming:** remove unavailable stock count doctype ([8bd7d3e](https://github.com/Shinonn23/connect_diagnostics_core/commit/8bd7d3eebbe7626bd08c3f258835b5e38161cf34))

## [0.39.0](https://github.com/Shinonn23/connect_diagnostics_core/compare/v0.38.0...v0.39.0) (2026-08-10)


### Features

* register Department and Territory accounting dimensions ([41cb149](https://github.com/Shinonn23/connect_diagnostics_core/commit/41cb1494da43381e6e73c6a740c65699bffd3bb3))
* register Department and Territory accounting dimensions ([8f1db4d](https://github.com/Shinonn23/connect_diagnostics_core/commit/8f1db4d38ce5c03c6f87e79e34d7204c1e807cfc))


### Tests

* update Employee insert_after chain for accounting_department ([72d3380](https://github.com/Shinonn23/connect_diagnostics_core/commit/72d3380d4a889b6a33e26689cf4659e450064b9a))

## [0.38.0](https://github.com/Shinonn23/connect_diagnostics_core/compare/v0.37.0...v0.38.0) (2026-08-10)


### Features

* **payroll:** require reviewed salary slips ([73b38b4](https://github.com/Shinonn23/connect_diagnostics_core/commit/73b38b45fc9ad50e4240801d6f5e59a2423c44d0))

## [0.37.0](https://github.com/Shinonn23/connect_diagnostics_core/compare/v0.36.10...v0.37.0) (2026-08-10)


### Features

* relocate national ID fields and format them with checksum validation ([d75650b](https://github.com/Shinonn23/connect_diagnostics_core/commit/d75650bd345b4d1c0b313854ccf028e041b48712))
* relocate national ID fields and format them with checksum validation ([dbc873c](https://github.com/Shinonn23/connect_diagnostics_core/commit/dbc873c570acd274e8667e32d988261d77f2174a))


### Styles

* wrap over-length assertion lines in backfill patch test ([73b68c3](https://github.com/Shinonn23/connect_diagnostics_core/commit/73b68c329ffa1c8ff9a75cd5b7116f29dc773da2))

## [0.36.10](https://github.com/Shinonn23/connect_diagnostics_core/compare/v0.36.9...v0.36.10) (2026-08-09)


### Bug Fixes

* drop retired legacy column instead of copying in strip-prefix patch ([8905170](https://github.com/Shinonn23/connect_diagnostics_core/commit/890517017f1bfb06a9ccd5934511c4482f5c01fc))

## [0.36.9](https://github.com/Shinonn23/connect_diagnostics_core/compare/v0.36.8...v0.36.9) (2026-08-09)


### Bug Fixes

* drop orphan DKSH-sales patch entries from patches.txt ([8fc058d](https://github.com/Shinonn23/connect_diagnostics_core/commit/8fc058d5ef3e16d6268c79cd1b2d4e292d13a925))
* drop orphan DKSH-sales patch entries from patches.txt ([eedec67](https://github.com/Shinonn23/connect_diagnostics_core/commit/eedec67baf085efcdc7b8d478e087c43835d85e5))

## [0.36.8](https://github.com/Shinonn23/connect_diagnostics_core/compare/v0.36.7...v0.36.8) (2026-08-09)


### Bug Fixes

* guard alternative-name migrations against retired target tables ([cbea092](https://github.com/Shinonn23/connect_diagnostics_core/commit/cbea092f20beb85a625bcc9b19656907807b22bf))
* guard alternative-name migrations against retired target tables ([568a557](https://github.com/Shinonn23/connect_diagnostics_core/commit/568a5578178ce274f477ff1e6afbd33cea615e01))

## [0.36.7](https://github.com/Shinonn23/connect_diagnostics_core/compare/v0.36.6...v0.36.7) (2026-08-09)


### Bug Fixes

* **dksh:** prepare item schema before migration ([ddd6526](https://github.com/Shinonn23/connect_diagnostics_core/commit/ddd652685687b6f94288ab15f773c495dff63838))
* **dksh:** prepare item schema before migration ([7796de7](https://github.com/Shinonn23/connect_diagnostics_core/commit/7796de74ca7d49bbacf0363d0467e003cc38a1e2))

## [0.36.6](https://github.com/Shinonn23/connect_diagnostics_core/compare/v0.36.5...v0.36.6) (2026-08-09)


### Bug Fixes

* **regulatory:** restore grouped workspace navigation ([53360c1](https://github.com/Shinonn23/connect_diagnostics_core/commit/53360c18a02bfe41d33e4141f0bef3c14303d3be))
* **regulatory:** restore grouped workspace navigation ([47165c6](https://github.com/Shinonn23/connect_diagnostics_core/commit/47165c692eafd052a0137dfe76e30e093f46e698))
* restore grouped regulatory workspace navigation ([e817a85](https://github.com/Shinonn23/connect_diagnostics_core/commit/e817a85ae2dc9e4717447bebe78aa18cd7ef2c06))

## [0.36.5](https://github.com/Shinonn23/connect_diagnostics_core/compare/v0.36.4...v0.36.5) (2026-08-09)


### Bug Fixes

* remove stray trailing blank line ([9b12feb](https://github.com/Shinonn23/connect_diagnostics_core/commit/9b12feb2e1a677676e8d0fc9b98ebdc0b85182a7))


### Code Refactoring

* remove accounting reports and department user permission ([382d0c6](https://github.com/Shinonn23/connect_diagnostics_core/commit/382d0c6c2195d30d43cb2956aa937b382e983467))
* remove alternative names from customer, item, and supplier ([622790b](https://github.com/Shinonn23/connect_diagnostics_core/commit/622790be107d54af95e7f67c06a44a1ab81c5151))
* remove alternative names, accounting reports, and department user permission ([fd56185](https://github.com/Shinonn23/connect_diagnostics_core/commit/fd56185e6a5ef36b3d4f17039a120b21a93bdbcb))

## [0.36.4](https://github.com/Shinonn23/connect_diagnostics_core/compare/v0.36.3...v0.36.4) (2026-08-09)


### Bug Fixes

* stop discarding build_response errors silently in exporter ([7fcb59f](https://github.com/Shinonn23/connect_diagnostics_core/commit/7fcb59fb6ddb7da44f4d0a16b6bfdc7d6a6ca101))


### Miscellaneous Chores

* add patch rollback parity and stop silent exporter failure ([ad50a7a](https://github.com/Shinonn23/connect_diagnostics_core/commit/ad50a7ac8eb9056f86e29bda66d6dbb44ea23b5b))
* add rollback patches for parity and remove dead patch ([afcbfed](https://github.com/Shinonn23/connect_diagnostics_core/commit/afcbfed6d971f0d947536126ffac37f9dff91175))

## [0.36.3](https://github.com/Shinonn23/connect_diagnostics_core/compare/v0.36.2...v0.36.3) (2026-08-09)


### Documentation

* slim CLAUDE.md/AGENTS.md and move domain knowledge to .github/domain ([3d1507e](https://github.com/Shinonn23/connect_diagnostics_core/commit/3d1507e5fa5382f36e70f52b230e44fdbb316002))
* slim CLAUDE.md/AGENTS.md and move domain knowledge to .github/domain ([ecfe6c3](https://github.com/Shinonn23/connect_diagnostics_core/commit/ecfe6c34c0a64dc5765a9b274ad96a5e7292abd7))

## [0.36.2](https://github.com/Shinonn23/connect_diagnostics_core/compare/v0.36.1...v0.36.2) (2026-08-09)


### Continuous Integration

* deploy production on push to production branch ([213a0ef](https://github.com/Shinonn23/connect_diagnostics_core/commit/213a0ef98da891cf86af1cac6de5820b23d6a05d))
* deploy production on push to production branch ([1fd8aa0](https://github.com/Shinonn23/connect_diagnostics_core/commit/1fd8aa09c21a02593a2a9135a04eea45a9f7f2bb))

## [0.36.1](https://github.com/Shinonn23/connect_diagnostics_core/compare/v0.36.0...v0.36.1) (2026-08-09)


### Bug Fixes

* skip payroll period seeding when an overlapping one exists ([7ce79d0](https://github.com/Shinonn23/connect_diagnostics_core/commit/7ce79d07dd997b4154de998c1d1f0f64facf72c5))

## [0.36.0](https://github.com/Shinonn23/connect_diagnostics_core/compare/v0.35.0...v0.36.0) (2026-08-09)


### Features

* **regulatory:** add medical device regulatory master ([fd684d8](https://github.com/Shinonn23/connect_diagnostics_core/commit/fd684d8df0e45cac9b4dc282acca40538f5b2e66))


### Tests

* **workspace:** cover regulatory navigation ([194a3ed](https://github.com/Shinonn23/connect_diagnostics_core/commit/194a3ed17b5f113b5ff6674394b514d5499e3779))

## [0.35.0](https://github.com/Shinonn23/connect_diagnostics_core/compare/v0.34.1...v0.35.0) (2026-08-09)


### Features

* add Thai payroll foundation and Employee payroll fields ([10fb67d](https://github.com/Shinonn23/connect_diagnostics_core/commit/10fb67db4b6d36cf09721996839ec2440a22b935))
* add Thai payroll foundation and Employee payroll fields ([7e649ed](https://github.com/Shinonn23/connect_diagnostics_core/commit/7e649ed43d13990451d6611b544c86f8fe44bda0))

## [0.34.1](https://github.com/Shinonn23/connect_diagnostics_core/compare/v0.34.0...v0.34.1) (2026-08-09)


### Documentation

* add workspace navigation skill ([b442879](https://github.com/Shinonn23/connect_diagnostics_core/commit/b442879eb0e9b3166fd33127996854f04010dbc3))
* add workspace navigation skill ([dfd8b77](https://github.com/Shinonn23/connect_diagnostics_core/commit/dfd8b77e66b693cf3a24b42f41fb347a148c3131))

## [0.34.0](https://github.com/Shinonn23/connect_diagnostics_core/compare/v0.33.0...v0.34.0) (2026-08-09)


### Features

* embed diagnostics navigation in ERPNext workspaces ([b51672e](https://github.com/Shinonn23/connect_diagnostics_core/commit/b51672e61b9d8184a470c96648962f2737d8fb11))
* embed diagnostics navigation in ERPNext workspaces ([c32f915](https://github.com/Shinonn23/connect_diagnostics_core/commit/c32f915926cc06baeb3504c5607e2f53af67f364))


### Documentation

* require workspace navigation for new modules ([b12d79d](https://github.com/Shinonn23/connect_diagnostics_core/commit/b12d79d7d689f231a6700c70a9bac2cf315e5b0d))
* require workspace navigation for new modules ([76a65f2](https://github.com/Shinonn23/connect_diagnostics_core/commit/76a65f2b35f392edef5335445cf1a9587a3fdc98))

## [0.33.0](https://github.com/Shinonn23/connect_diagnostics_core/compare/v0.32.1...v0.33.0) (2026-08-08)


### Features

* add Connect Diagnostics DKSH module and reference foundation ([c154cd6](https://github.com/Shinonn23/connect_diagnostics_core/commit/c154cd639a7ebc0c4e14b466a8097666a4056261))
* add DKSH Customer reference master with Convert to CD Customer ([6c89e6c](https://github.com/Shinonn23/connect_diagnostics_core/commit/6c89e6c123d4da8d633d72cb763f4c500952ceb5))
* allow several source Purchase Orders per tax invoice ([64a380a](https://github.com/Shinonn23/connect_diagnostics_core/commit/64a380a0a96cd2aa12b137b49bab8e4750a64c35))
* customer sales document requirements and onboarding cleanup ([a60a0bc](https://github.com/Shinonn23/connect_diagnostics_core/commit/a60a0bc82498987784a168bd4e99a087a82b4fcd))
* DKSH module and customer sales document requirements ([4c6db9d](https://github.com/Shinonn23/connect_diagnostics_core/commit/4c6db9d7b09d3eee6aa8d86196e2dce333ea9099))
* fold the Sales Order print date into the print registry ([bf09c94](https://github.com/Shinonn23/connect_diagnostics_core/commit/bf09c94dc5c4a3906feb499b5ed3de3f72d767ab))


### Code Refactoring

* move DKSH reference codes to a DKSH Item DocType ([61035a7](https://github.com/Shinonn23/connect_diagnostics_core/commit/61035a7e411c25089357c569a0cf200922d1fd06))


### Miscellaneous Chores

* register migrations and sync docs for the DKSH Item and print changes ([606c33e](https://github.com/Shinonn23/connect_diagnostics_core/commit/606c33e067de6ecd146fb81806b0a63f0befd3ac))


### Styles

* apply pinned ruff formatting to DKSH customer test ([edf5968](https://github.com/Shinonn23/connect_diagnostics_core/commit/edf59681cb51ad57d407474c53c78f58b9c965e4))
* apply pre-commit formatting ([b965d8c](https://github.com/Shinonn23/connect_diagnostics_core/commit/b965d8c713bb3ed73a7cf7856cb9fb7fecab3c87))


### Tests

* point print-registry unregistered tests at still-unregistered doctypes ([7243d0b](https://github.com/Shinonn23/connect_diagnostics_core/commit/7243d0bfa37cea8bb976d21e9ea7372b4009248c))

## [0.32.1](https://github.com/Shinonn23/connect_diagnostics_core/compare/v0.32.0...v0.32.1) (2026-08-08)


### Miscellaneous Chores

* add Notion Task Tracker skills for picking and updating tasks ([5352d7b](https://github.com/Shinonn23/connect_diagnostics_core/commit/5352d7bc23c2a1279f015530c83a1b317794fa3b))
* add Notion Task Tracker skills for picking and updating tasks ([bc85c78](https://github.com/Shinonn23/connect_diagnostics_core/commit/bc85c7848c099e4013905b69166e03923e04919b))

## [0.32.0](https://github.com/Shinonn23/connect_diagnostics_core/compare/v0.31.1...v0.32.0) (2026-08-08)


### Features

* move the Quotation signatory onto the Quotation ([c3a5501](https://github.com/Shinonn23/connect_diagnostics_core/commit/c3a5501c589620999b36481d06a273ac440deec7))
* rebuild print configuration on a document registry ([4204b04](https://github.com/Shinonn23/connect_diagnostics_core/commit/4204b043ad7605861725cf620a351c645a2ff32f))
* rebuild print configuration on a document registry ([a5feb43](https://github.com/Shinonn23/connect_diagnostics_core/commit/a5feb43e10020daed42aba87b630f28dd988ea12))


### Bug Fixes

* refresh the module map before the print registry patch reloads ([f672e57](https://github.com/Shinonn23/connect_diagnostics_core/commit/f672e571c19bed3bbdd029cb0732dfd23172dbbd))


### Code Refactoring

* group the Quotation signatory fields with their standard fields ([3f64c8c](https://github.com/Shinonn23/connect_diagnostics_core/commit/3f64c8c54440567d95d3a3c967c40a282a3916b0))


### Styles

* apply ruff-format to the Quotation signatory patch test ([c8ec7c6](https://github.com/Shinonn23/connect_diagnostics_core/commit/c8ec7c61865477a642cbed9be7fb2cd1322af409))


### Tests

* align the leave email and DKSH assertions with this branch ([a25e100](https://github.com/Shinonn23/connect_diagnostics_core/commit/a25e100bb59494c5063d71bd7a7cc117d6f13bca))

## [0.31.1](https://github.com/Shinonn23/connect_diagnostics_core/compare/v0.31.0...v0.31.1) (2026-08-07)


### Miscellaneous Chores

* disable all Frappe workflows ([eb6cec9](https://github.com/Shinonn23/connect_diagnostics_core/commit/eb6cec9e8dbfede436bb7ba6bce8317f59e5af5e))
* disable all Frappe workflows ([07df717](https://github.com/Shinonn23/connect_diagnostics_core/commit/07df7175bf8f87ab35f575d2edea6420dce0a7f0))

## [0.31.0](https://github.com/Shinonn23/connect_diagnostics_core/compare/v0.30.0...v0.31.0) (2026-08-06)


### Features

* configure quotation signatory defaults and print overrides ([82f516c](https://github.com/Shinonn23/connect_diagnostics_core/commit/82f516cc9dfbc69d735aa3b6c5492eba022461a9))
* configure quotation signatory defaults and print overrides ([4692163](https://github.com/Shinonn23/connect_diagnostics_core/commit/469216383584fb545f6b0082417ff50cb08febd5))

## [0.30.0](https://github.com/Shinonn23/connect_diagnostics_core/compare/v0.29.0...v0.30.0) (2026-08-04)


### Features

* configure document print formats ([6629196](https://github.com/Shinonn23/connect_diagnostics_core/commit/6629196fc549baee41d6320c038c14df6adfa777))
* configure document print formats ([093060d](https://github.com/Shinonn23/connect_diagnostics_core/commit/093060d9ca8505b4641447c8cd16c344ec20e08e))

## [0.29.0](https://github.com/Shinonn23/connect_diagnostics_core/compare/v0.28.0...v0.29.0) (2026-08-04)


### Features

* manage procure-to-pay workflows with fixtures ([839f9f0](https://github.com/Shinonn23/connect_diagnostics_core/commit/839f9f06cfd7155ff42547dc761596b3c106c74d))
* manage procure-to-pay workflows with fixtures ([b1055a1](https://github.com/Shinonn23/connect_diagnostics_core/commit/b1055a1caa9aa028e8f4de9ec8eff1c6304146b8))
* manage procure-to-pay workflows with fixtures ([dc07861](https://github.com/Shinonn23/connect_diagnostics_core/commit/dc07861a99322d3b702075f702ab163257762f28))
* **quotation:** add configurable customer print preferences ([135147e](https://github.com/Shinonn23/connect_diagnostics_core/commit/135147e7349f7221d42164f25bbbb1dde36b1bf0))


### Bug Fixes

* remove draft procure-to-pay documents during cutover ([7daa2ed](https://github.com/Shinonn23/connect_diagnostics_core/commit/7daa2ed7ee563114a648ba5cedda1741fc22a517))

## [0.28.0](https://github.com/Shinonn23/connect_diagnostics_core/compare/v0.27.2...v0.28.0) (2026-07-30)


### Features

* add shipment box label print format ([7477fab](https://github.com/Shinonn23/connect_diagnostics_core/commit/7477fabf5959e212c76613e31be337541bed22ea))
* add shipment box label print format ([b073757](https://github.com/Shinonn23/connect_diagnostics_core/commit/b073757cd57865dd6d3315291baa593975edf06c))

## [0.27.2](https://github.com/Shinonn23/connect_diagnostics_core/compare/v0.27.1...v0.27.2) (2026-07-29)


### Styles

* format release-please configuration ([af9d384](https://github.com/Shinonn23/connect_diagnostics_core/commit/af9d384dc330763a98c61dd0522eb394f4b63241))


### Continuous Integration

* adopt release-please versioning ([d94d520](https://github.com/Shinonn23/connect_diagnostics_core/commit/d94d520436f1ac5b9e0295de829e95f55f2661af))
* adopt release-please versioning ([620dd49](https://github.com/Shinonn23/connect_diagnostics_core/commit/620dd4951766a00bced0a8dd8a8ccd48a55c952b))
