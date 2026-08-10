# Changelog

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
