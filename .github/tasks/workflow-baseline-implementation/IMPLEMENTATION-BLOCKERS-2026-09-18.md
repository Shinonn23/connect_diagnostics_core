# Workflow implementation: blockers, decisions, and one-round confirmation

สถานะเอกสาร: execution brief ณ 2026-09-18  
เป้าหมาย: แยกคำสั่งที่อนุญาตแล้วออกจากงานที่ทีมต้องลงมือทำ และเหลือเฉพาะคำถามธุรกิจที่ไม่มีคำตอบจริง

เอกสารนี้แยก **คำสั่ง/ข้อกำหนดที่ผู้ใช้ยืนยันแล้ว** ออกจาก **งาน implementation ที่ทีมต้องทำ** และ **คำถามธุรกิจที่ยังขาดจริง** ไม่ถือว่า fixture หรือ test ที่ผ่านเป็นหลักฐานว่า business workflow เสร็จแล้ว

## 1. ข้อกำหนดที่ยืนยันแล้ว ไม่ต้องถามซ้ำ

- ทำ implementation จริงบน DEV ได้ รวมถึง code, fixture, Custom Field, permission, hook, setup, patch, configuration, install/update/migrate และ target-backed tests
- target ปัจจุบันคือ DEV site `local` บน bench `/home/shinon/frappe/connect_diagnostics`; ห้ามอ้างผลกับ site อื่นโดยยังไม่ได้ตรวจ target
- ใช้ Notion `ERPNext — 2026-08-13 13:00 — Go-Live Readiness` และคำตัดสินล่าสุดเป็น business source
- workflow อิง Role/Permission ไม่ผูกกับชื่อคน, email หรือ User ID
- ใช้ native Frappe/ERPNext/HRMS Workflow และ permission ก่อน; ห้ามสร้าง posting/approval engine ซ้ำ
- Salary Slip submit ต้องผ่าน Payroll Entry และห้ามสร้าง Salary Slip Workflow
- Stock Count เดิมห้าม revive; adjustment ต้องผ่าน native Stock Reconciliation
- Payment Entry เป็น approval boundary แทน Payment Request approval
- ห้าม self-approval ในขั้นตรวจ/อนุมัติ; ทีมต้องแยก Send for Review/Resubmit ออกจาก Final Approve และตรวจ Frappe 16.31.0 จริง ไม่ตั้ง `allow_self_approval=0` แบบ blanket จน maker ส่งงานหรือ resubmit ไม่ได้
- ของเดิมแก้/แทนที่ได้เมื่อจำเป็น แต่ต้อง backup, migration/recovery และห้ามสร้าง approval history ที่ไม่เคยเกิดขึ้นจริง
- ต้องทดสอบหลาย user/หลาย role ทั้ง UI และ API/RPC รวม success, return/reject, unauthorized, self-approval, revoke/change permission และ repeated action
- ผู้ใช้ยืนยันเพิ่ม: **ตัด Equipment ออกจาก scope** เหลือเฉพาะ Stock และ Assets
- Item เดิมที่จะถูกตัดมูลค่าเป็นศูนย์ให้ใช้ **Stock Item ที่แปลงเป็น Asset** และให้ลงค่าใช้จ่ายทันทีในกระบวนการ native ที่เหมาะสม ไม่สร้าง Equipment workflow หรือ Equipment posting engine
- การอนุญาต DEV รวมถึงการจัดการ dirty files, operation identity, lock, retry, migration, recovery และการปรับ/แทน Workflow เดิมภายใน scope ไม่ต้องขออนุมัติซ้ำ
- WF-08/Equipment เป็น `disabled / out of scope` แล้ว ให้ปิด route ใหม่และรักษาประวัติเดิมตามหลักฐาน ไม่ต้องยืนยัน scope นี้ซ้ำ

## 2. สิ่งที่ตรวจพบแล้วบน DEV

สภาพแวดล้อมที่ตรวจพบ:

- Frappe 16.31.0, ERPNext 16.32.1, HRMS 16.16.0, app `connect_diagnostics_core` 0.51.2
- มี backup ก่อน migration และ `bench --site local migrate` ผ่านแล้ว
- test เฉพาะ workflow reset 11 tests และ fixture blueprint 4 tests ผ่าน
- `pre-commit run --all-files` ผ่าน; ผลนี้ยังไม่ใช่หลักฐาน business behavior
- ยังมี Workflow Action ค้าง 7 รายการ: Material Request 2, Purchase Order 3, Stock Count 2
- runtime มี legacy/competing workflow state/action อยู่ จึงต้องตรวจ collision และ pending document ต่อรายการ
- source worktree มี dirty และ untracked files จำนวนมาก ทั้ง hooks, patches, setup-managed Custom Fields, workflow fixtures และ task records; ห้ามตีความว่าเป็น approved change ทั้งหมด

งานที่ต้องแก้จาก decision เรื่อง Equipment:

- route/fixture `WF-08 Equipment Assignment/Installation` ต้องเปลี่ยนเป็น `deferred/disabled` และไม่นับเป็น enabled route
- Workflow/State/Action Master ของ Equipment ที่ไม่ถูกใช้งานต้องถูกจัดการด้วย migration ที่ตรวจสอบย้อนกลับได้ ไม่ลบประวัติที่มีอยู่เอง
- ต้องกำหนด native Asset route ใหม่ให้ครอบคลุม Stock Item → Asset → immediate expense โดยยืนยันว่าไม่เกิด duplicate GL/stock effect
- ต้องตรวจ custom fields, hooks, workspace links, permissions, tests และ manifest ที่กล่าวถึง Equipment ทั้งหมด
- ไม่ลบประวัติ Equipment ที่มีอยู่โดยอัตโนมัติ; แยก new runtime scope ออกจาก historical data

## 3. งาน implementation ที่ทีมต้องทำเอง

รายการต่อไปนี้ไม่ใช่ owner blocker:

- บันทึก DEV `local` และสิทธิ์ที่ได้รับเป็น approved execution record แล้วตรวจ baseline/configuration จริง
- integration owner และ independent reviewer ตรวจ dirty/untracked diff แล้วจัด keep/revise/remove/defer ตาม scope โดยไม่ล้าง worktree ที่ไม่เกี่ยวข้อง
- ออกแบบและทดสอบ source identity, revision binding, provenance, idempotency, lock และ transaction boundary
- ตรวจ Payment Entry Workflow เดิม; ปรับหรือแทนที่เมื่อขัด desired state โดยรักษา approval control ระหว่าง migration
- ปิด WF-08 runtime/manifest/tests และตรวจทุก reference ที่เกี่ยวกับ Equipment
- inventory Workflow Actions ค้างทั้ง 7 รายการแบบ exact-record พร้อมสถานะ source, ผลกระทบ, safety และ proposed disposition; เก็บไว้ก่อนเมื่อยังไม่มีสิทธิ์ตัดสินแทนธุรกิจ
- สร้าง native positive/negative/bypass/retry/concurrency/correction และ end-to-end evidence ของ route ที่เปิด
- แยก G0 เป็น baseline ที่บันทึกจากคำอนุญาตแล้ว และใช้ G4 เป็น final verification/sign-off หลัง implementation ไม่ใช่เงื่อนไขห้ามเริ่มงาน

หยุดเฉพาะเมื่อพบการเปลี่ยนนอก scope, ความเสี่ยงข้อมูลเสียหายแบบกู้คืนไม่ได้, public contract ที่ยังไม่มี authority, business rule ขัดกันจริง หรือจำเป็นต้องสร้าง engine ใหม่ที่ขัดข้อกำหนด

## 4. คำถามธุรกิจที่ยังต้องมีคำตอบจริง

| ID | ระดับ | สิ่งที่ยังติด | สิ่งที่ต้องยืนยันหนึ่งครั้ง |
|---|---|---|---|
| D-TARGET | execution | ได้รับอนุญาตแล้ว | ทีมบันทึก approved execution record และตรวจ target จริง ไม่ถามซ้ำ |
| D-CORE | execution | เป็น technical design/test task | ทีมเลือกและทดสอบ identity, lock, retry และ recovery ตาม repository architecture |
| D-IDENTITY | P1 | business rule บางค่าที่ Notion/decision ล่าสุดยังไม่ระบุ | ถ้าพบค่าขาดจริงให้ถามเฉพาะ scope, delegation หรือ service identity ของ route ที่กำลังเปิด ไม่ถามทั้ง domain |
| D-STOCK | P1 | count/variance business rules ยังไม่ครบ | cutoff, blind count, exclusion, recount authority และ monthly/annual adjustment policy |
| D-TRANSFER | P1 | direct/transit transfer และ receipt ordering ยังไม่ปิด | route ที่เปิดจริง, scope, receipt order และ reversal policy |
| D-ASSET | P1 | หลังตัด Equipment ต้องเหลือ Asset custody/transfer/assignment ที่ชัด | Asset identity, custody/site และ acknowledgement order ที่ยังไม่มีใน business source |
| D-ASSET-DISPOSAL | P1 | disposal route ยังต้องผูกกับ native Asset/GL | sale/scrap/write-off, authority, effective date, account และ evidence |
| D-ITEM-ASSET | P1/Finance | ต้องพิสูจน์ผลทางบัญชีให้ตรงกับคำว่า expense ทันที | ทีมตรวจ configuration และทำ native proof เสนอ trigger, account, date, Stock/GL/NBV และ reversal; Finance ยืนยันเฉพาะ treatment หากบัญชีจริงยังไม่มีคำตอบ |
| D-SALES | P1 | SO/credit approval adapter ยังไม่ครบ | exposure basis, threshold, currency, override authority และ critical fields |
| D-CREDIT | P1 | credit note, AR write-off และ refund boundary ยังไม่ครบ | physical return vs price-only, retained credit, write-off, refund และ period authority |
| D-PROCURE | P1 | RFQ/direct procurement และ supplier evidence ยังไม่ปิด | route ที่เปิด, commitment/authority/currency และ pending document treatment |
| D-AP | P1 | PI matching/payment handoff ยังไม่ครบ | matching tolerance, receipt owner, advance/direct expense และ Is Paid rules |
| D-PAYMENT | P1 | ต้องตรวจ desired state กับ site-owned workflow และ pending PE โดยไม่ทำให้ control หาย | ทีมปรับ/แทนที่ตาม source requirement; ถ้าขาดจริงให้ถามเฉพาะ voucher authority หรือ bank treatment |
| D-PAYROLL | P1 | Payroll review/bank handoff ยังขาด end-to-end evidence | cutoff, grouping, off-cycle, correction/recovery, privacy และ bank authority |
| CONFIG-PENDING | route-specific | 7 legacy Workflow Actions ต้องตรวจผลกระทบ | ทีมส่ง exact-record inventory และ proposed disposition; หยุดเฉพาะ route/DocType ที่ migration กระทบจริง ไม่หยุดทั้ง 8 แผน |
| CONFIG-DIRTY | execution | dirty/untracked files ต้อง review | integration owner + reviewer จัด disposition ตาม scope ไม่ถามให้เจ้าของไล่ตอบทุกไฟล์ |
| G0/G4 | execution | ต้องสร้าง evidence และ sign-off | G0 บันทึก baseline ที่มีแล้ว; G4 ตรวจหลัง implementation/test |

## 5. รายละเอียดทางเทคนิคที่ทีมออกแบบและทดสอบเองได้

ทีมจะเลือกวิธีที่เหมาะสมและบันทึก rationale สำหรับ:

- transaction boundary, row lock/`FOR UPDATE`, retry, idempotency claim และ recovery
- migration ordering, repeat migrate, collision detection และ rollback/reconciliation
- native API/UI/REST/RPC/import/background path coverage
- validation ที่ server boundary และ recheck permission/state ก่อน native effect แรก
- การใช้ native Workflow, Version, Workflow comment และ ToDo ตามขอบเขตของมัน
- การจัดทำ test users/roles บน DEV โดยไม่ผูก fixture กับ named users
- การทำ backup/snapshot และการตรวจ pending documents โดยไม่ fabricate history

สิ่งเหล่านี้จะหยุดเฉพาะเมื่อพบการเปลี่ยนนอก scope, ความเสี่ยงข้อมูลเสียหายแบบกู้คืนไม่ได้, public contract ที่ยังไม่มี authority, business rule ขัดกันจริง หรือจำเป็นต้องสร้าง engine ใหม่ที่ขัดข้อกำหนด การเพิ่ม Custom Field หรือ schema extension ที่อยู่ใน scope ไม่ใช่เหตุให้หยุดโดยอัตโนมัติ

## 6. หลักฐานที่ต้องส่งก่อนประกาศเสร็จ

1. DEV version/site/configuration และ backup reference
2. final route manifest ที่แสดง WF-08 เป็น deferred/disabled และระบุ Asset replacement route
3. effective Workflow/Workflow State/Action Master และ Custom DocPerm หลัง migrate
4. pending Workflow Action disposition ต่อรายการ พร้อมหลักฐานว่าไม่สร้างประวัติเทียม
5. repeat migrate แบบ idempotent และ recovery/collision evidence
6. multi-user tests: maker→reviewer/approver→executor, reject/return, unauthorized, self-approval, permission revoke/change, API และ repeated action
7. native document effects: stock ledger, Asset, GL/expense, payment, procurement และ payroll ตาม route ที่เปิด
8. independent review ของ diff, permissions, migration, tests และ evidence
9. technical + business sign-off สำหรับ version/scope/evidence

## 7. สิ่งที่อาจต้องขอจากเจ้าของระบบ/Finance แบบเจาะจง

ไม่ต้องตอบ decision blocks ทั้งตารางซ้ำ เจ้าของระบบหรือ Finance จะถูกถามเฉพาะเมื่อทีมตรวจ source/configuration แล้วพบค่าธุรกิจที่ไม่มีคำตอบจริง เช่น treatment บัญชีของ Stock Item → Asset → immediate expense, threshold/authority ที่ไม่มีใน source หรือ route ที่ขัดกัน โดยต้องส่ง proposal พร้อมหลักฐานก่อนถาม

```text
Missing business value:
Evidence/configuration checked:
Implementation proposal:
Affected route/documents:
Exact decision required:
Impact if deferred:
Required business/finance sign-off:
```

### วิธีเดินงานต่อ

1. ลงมือทำ route ที่ข้อกำหนดครบก่อน เช่น Stock Transfer ปกติ
2. สร้าง maker → reviewer/approver → executor evidence ด้วยหลาย user/role
3. ตรวจ native stock/GL/Asset effect, retry, API bypass และ self-approval
4. inventory pending Workflow Actions และแยกผลกระทบเฉพาะ DocType ที่ได้รับผล
5. ทำ native proof สำหรับ Stock Item → Asset → immediate expense แล้วค่อยส่ง proposal ที่มีตัวเลขจริงให้ Finance หากยังขาด treatment

งานที่ dependency ครบให้เดินต่อได้ทันที ไม่รอคำตอบของ module ที่ไม่เกี่ยวข้อง และไม่ประกาศทั้งชุดเสร็จจากตัวอย่างเดียว

## 8. เกณฑ์ปิดเอกสารนี้

เอกสารนี้ปิดเมื่อ execution record, route manifest และ tests สอดคล้องกัน, DEV migration/re-run ผ่าน, native effects ผ่านการตรวจ และ independent review ไม่มี P0/P1 ค้างอยู่
