# Workflow baseline: สิ่งที่ติดและข้อมูลที่ต้องยืนยัน

เอกสารนี้สรุปสิ่งที่ยังทำให้ implementation ของ workflow ทั้ง 8 แผนเดินต่อไม่ได้
และรวมคำถามที่เจ้าของระบบต้องตอบให้ครบในรอบเดียว ก่อนเปิดให้ worker แก้ code หรือ
เปิดใช้งาน fixture บน site ใด ๆ

แหล่งอ้างอิงหลัก:

- `README.md` — ขอบเขต, dependency graph และ fixed constraints
- `spec.md` — การแก้ความเข้าใจของ Plan 01–08 และเจ้าของ WF-01–18
- `decisions.md` — decision register ฉบับเต็ม
- `verification.md` — หลักฐาน audit และ gate status
- `workflow-route-manifest.json` — manifest ปัจจุบันยังเป็น blueprint/inert
- `permission-blueprint.json` — permission blueprint ปัจจุบันยังไม่ executable

## สถานะปัจจุบัน

ยังไม่ควรถือว่า workflow implementation เสร็จ แม้ใน worktree จะมี fixture, custom
field, patch และ test บางส่วนอยู่แล้ว เพราะ:

1. fixture ปัจจุบันยังเป็น artifact ที่ contested และ manifest ระบุ
   `records_are_inert: true` กับ `activation_status: prohibited-until-prerequisites-pass`;
2. target สำหรับ implementation/test ที่อนุญาตยังไม่ถูกอนุมัติ (`local` เป็น audit-only
   และ bench path ที่เคยคาดไว้ไม่มีอยู่ตาม checkpoint);
3. policy สำคัญของ approval, identity, scope, delegation, retry, correction และ
   domain side effect ยังไม่มี owner approval;
4. ยังไม่มี disposition ที่ได้รับอนุญาตสำหรับ dirty `hooks.py`, setup, patches,
   fixtures และ custom exports;
5. ยังไม่มีคำตัดสินสำหรับ legacy Workflow Actions ที่ค้างอยู่ จึงห้ามสร้างหรือ
   ลบประวัติแทนเจ้าของธุรกิจ;
6. G0 ยังไม่ผ่าน และ G1–G4 ยังไม่มีหลักฐานที่ยอมรับได้;
7. source plans ต้นฉบับทั้งแปดฉบับไม่ได้อยู่เป็น executable implementation contract
   ใน repository แล้ว เอกสาร superseding record นี้จึงเป็น baseline ที่ต้องใช้จนกว่าจะ
   ส่ง plan ฉบับ authoritative มาแทน.

`pre-commit run --all-files` ผ่านใน checkpoint ล่าสุด แต่ผลนี้พิสูจน์ได้เฉพาะรูปแบบ,
lint, type check, security scan และ dependency scan ไม่ได้พิสูจน์ business workflow,
native posting, migration หรือ site behavior

## สิ่งที่ต้องยืนยันก่อนเริ่ม implementation

### A. Target และสิทธิ์ในการเปลี่ยนแปลง — D-TARGET

กรุณาระบุ:

- bench root ที่ใช้จริง;
- site ที่เป็น DEV/test target และ site ที่ห้ามแตะ;
- อนุญาตเฉพาะ repository tests หรืออนุญาต install/update/migrate/fixture sync ด้วย;
- ใครเป็น technical owner ที่อนุมัติการเปลี่ยนแปลง;
- baseline commit, app/dependency versions และ effective site configuration ที่ต้อง freeze;
- วิธีสร้าง clean site และ populated upgrade rehearsal;
- rollback ที่อนุญาต หาก migration หรือ fixture validation ไม่ผ่าน.

### B. Shared approval contract — D-CORE

ต้องอนุมัติหรือแก้ proposal ต่อไปนี้:

- canonical source identity: `source_system`, `source_doctype`, `source_name`;
- source revision/version และ critical-field digest;
- provenance digest และ trusted source ของ provenance;
- operation identity รวม `action` และ `operation_id`;
- จุดที่ต้อง recheck current state ก่อน native effect แรก;
- transaction boundary และ row-lock pattern (`FOR UPDATE` หรือ native equivalent);
- กติกา retry กับ operation เดิม และการแยก legitimate same-amount operation;
- สิ่งที่ถือว่า stale และ error ที่ต้องส่งกลับ;
- ใครเป็นเจ้าของ operation claim/history: domain adapter หรือ app-owned model;
- ถ้าต้องมี durable claim/history ให้อนุมัติ schema, migration, unique key, rollback และ
  retention ก่อนสร้าง module กลาง.

ค่า proposal ที่มีอยู่เป็นเพียงข้อเสนอ ยังไม่ใช่นโยบายที่อนุมัติแล้ว:

```text
(source_system, source_doctype, source_name, source_revision, action, operation_id)
```

### C. Business identity และ delegation — D-IDENTITY

ต้องกำหนด:

- immutable business identity ของ requester, maker, checker และ approver;
- ความสัมพันธ์ requester/actor/approver และ self-approval ที่ห้ามอย่างชัดเจน;
- scope dimensions เช่น company, domain, resource, amount และ currency พร้อม comparison semantics;
- กรณีไม่มี scope ต้อง deny หรือใช้ fallback อะไร;
- delegation: grantor, delegate, scope, action set, effective-from, expiry, timezone;
- revocation fact และ lookup/lock ที่ใช้ recheck ตอน execute;
- multi-role precedence เมื่อ user เดียวมีหลาย role;
- identity สำหรับ background/generated action และ trusted source ของ identity นั้น;
- อนุญาตหรือห้าม self-approval ใน correction/reversal;
- backup approver และการหมดอายุ/เพิกถอน.

### D. Domain decisions

ต้องมี owner, policy revision, effective date, enabled routes, deferred routes และ
ผลกระทบต่อเอกสารเดิมสำหรับแต่ละรายการ:

| Decision | ต้องตัดสินใจ | WF |
| --- | --- | --- |
| D-STOCK | count evidence, cutoff/reference time, blind count, exclusions, recount authority, adjustment rules | 03–05 |
| D-TRANSFER | direct/transit routes, scope, receipt ordering, retry และ reversal | 01–02 |
| D-ASSET | asset/equipment identity, custody/site, acknowledgement ordering | 06, 08 |
| D-ASSET-DISPOSAL | sale/scrap/write-off, authority, dates, accounts, evidence | 07 |
| D-SALES | exposure basis, thresholds, currencies, override authority, critical fields | 09 |
| D-CREDIT | physical return, price-only credit, retained credit, write-off, refund, period rules | 10 |
| D-PROCURE | RFQ/direct routes, supplier evidence, commitment, authority, currency | 11 |
| D-AP | invoice identity, matching tolerances, receipt owner, advance, direct expense, Is Paid | 12 |
| D-PAYMENT | voucher matrix, beneficiary/account/currency/amount authority, bank evidence, settlement | 10, 12–14 |
| D-PAYROLL | cutoff, grouping, off-cycle, correction/recovery, privacy, bank handoff | 14 |

ข้อจำกัดที่ตายตัวและห้ามออกแบบสวนทาง:

- stock/GL/AR/AP/asset/payment/payroll effects ต้องใช้ native ERPNext/HRMS;
- ห้ามสร้าง parallel posting engine;
- Salary Slip submit ผ่าน Payroll Entry เท่านั้น และห้ามสร้าง Salary Slip Workflow;
- Stock Count code เก่าห้าม revive; posting endpoint คือ native Stock Reconciliation;
- Workflow fixtures ทำได้เฉพาะ native configuration ที่ allowlist และผ่าน collision/recovery contract;
- ToDo เป็น notification/work assignment ไม่ใช่ delegated approval authority.

### E. Route scope สำหรับ WF-01–18

สำหรับแต่ละ WF ต้องตอบ `enabled` หรือ `deferred/disabled`, owner, เหตุผล, document type,
workflow name, entry points และหลักฐานที่ต้องส่ง:

- WF-01/02: Stock Entry transfer direct/transit;
- WF-03: emergency movement ระหว่าง freeze;
- WF-04/05: full/cycle count และ variance/recount;
- WF-06/08: Asset Movement และ equipment assignment/installation;
- WF-07: Asset disposal;
- WF-09: Sales Order/Credit approval;
- WF-10: Credit Note/AR write-off/refund boundary;
- WF-11: Material Request/Purchase Order procurement;
- WF-12: Purchase Invoice/payment handoff;
- WF-13: Payment Entry approval;
- WF-14: Payroll Entry review/processing/bank handoff;
- WF-15: role/scope assignment;
- WF-16: backup approver/delegation;
- WF-17: self-approval protection ทุก adapter;
- WF-18: freeze register/sign-off.

ทุก route ที่เปิดต้องระบุ UI, REST/RPC, import/bulk, generated document, queue/background,
post-submit update, cancel/amend/reopen, report/export/print/email, native effect แรก,
transaction boundary, lock, permission, privacy และ audit evidence

### F. Payment configuration — CONFIG-PAYMENT

ต้องระบุชื่อและสิทธิ์ของ site configuration owner กับ finance owner และตอบ:

- จะ retain, retire หรือ replace site-owned Payment Entry Workflow;
- desired state และ route revision;
- pending Payment Entry/Workflow Action เดิมจะจัดการอย่างไร;
- ห้ามปิด control เดิมจน replacement active และ verified — ใครเป็นผู้ sign-off;
- migration, repeat migrate, collision, rollback และ recovery;
- หลักฐานที่อนุญาตให้ตรวจ pending documents โดยไม่ fabricate history.

### G. Dirty worktree ownership — CONFIG-DIRTY

ต้องกำหนด owner และ disposition ทีละไฟล์/กลุ่มสำหรับ:

- `.codex/agents/*`, `.codex/config.toml`;
- `.github/tasks/*`;
- `connect_diagnostics_core/AGENTS.md`;
- `hooks.py` และ `patches.txt`;
- `setup/procure_to_pay.py` และ setup tests;
- `custom/*.json`;
- `fixtures/workflow*.json`;
- workflow patches, rollback patches และ tests.

แต่ละรายการต้องระบุ `keep / revise / remove / defer`, เหตุผล, owner, dependency และ
ผลต่อ migration order. ห้ามตีความว่าไฟล์ที่มีอยู่หรือ test ที่ผ่านแปลว่าอนุมัติแล้ว

### H. Legacy pending Workflow Actions — CONFIG-PENDING

ต้องมีเจ้าของธุรกิจของ Material Request, Purchase Order และ Stock และอนุมัติวิธี:

- inventory รายการค้างและ source document ที่เกี่ยวข้อง;
- ตรวจว่า action ใดเป็น valid pending state จริง;
- transition ต่อ, cancel/reject, quarantine หรือ manual resolution;
- หลักฐานที่เก็บรักษา;
- สิ่งที่ห้ามลบ/สร้าง/เปลี่ยนเพราะไม่มีประวัติที่เชื่อถือได้;
- owner และ sign-off ต่อรายการ.

## สิ่งที่ต้องออกแบบ/ส่งกลับในรูปแบบเดียวกัน

ส่งกลับ decision block ต่อรายการตาม template นี้:

```text
Decision ID:
Owner / backup owner:
Approved policy / desired state:
Revision:
Effective date/timezone:
Enabled routes:
Deferred/disabled routes and reason:
Affected existing documents/configuration:
Allowed target and mutation scope:
Required permissions/roles/scopes:
Required tests and evidence:
Migration/re-run behavior:
Collision behavior:
Rollback/recovery behavior:
Business sign-off:
Technical sign-off:
Security/Finance sign-off (ถ้าเกี่ยวข้อง):
```

## หลักฐานที่ต้องมีเพื่อปิดแต่ละ gate

| Gate | หลักฐานขั้นต่ำ |
| --- | --- |
| G0 | fixed constraints, WF-01–18 scope, decisions, owners, exact files, target baseline |
| G1 | native positive/negative/bypass/retry/concurrency/correction ต่อ module |
| G2 | revision, lock, provenance, ledger/history, privacy และ cross-module evidence |
| G3 | clean install, populated upgrade, repeated migrate, pending-document handling, recovery |
| G4 | technical + business owner sign-off ต่อ version/scope/evidence |

## สิ่งที่ worker จะทำหลังได้รับคำตอบ

1. freeze baseline และตรวจ dirty-file disposition;
2. ให้ independent reviewer ตรวจ plan, ownership, acceptance criteria, migration และ rollback;
3. แบ่ง worker ตาม exclusive files โดยมี integration owner คนเดียวสำหรับ hooks, patches,
   setup, config export และ ordering;
4. implement native adapters ตาม route ที่เปิดจริง โดยไม่สร้าง posting engine ซ้ำ;
5. เพิ่ม contract/integration tests ตาม entry points และ invariants;
6. ตรวจ fixture collision, deterministic rerun, pending actions และ rollback บน target ที่อนุมัติ;
7. run pre-commit, relevant app tests, target-backed tests และจัดทำ G0–G4 evidence;
8. independent final review ก่อนเปิด PR.

จนกว่าจะตอบ decision blocks ด้านบนครบ ห้ามถือว่า fixture หรือ patch ที่มีอยู่เป็น
production-ready และห้าม sync ไปยัง shared DEV/UAT
