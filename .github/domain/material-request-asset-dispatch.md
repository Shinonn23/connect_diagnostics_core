# Material Request, Demo/Loan Fulfillment, Return Inspection และ Dispatch

**Target:** Frappe/ERPNext v16 (`version-16`)

เอกสารนี้เป็น source of truth ของส่วนต่อขยาย Material Request สำหรับการยืม,
Customer Demo/Loan, หลักฐานขนส่ง และการตรวจรับคืน โดยคง Stock/Asset accounting
ไว้กับเอกสาร native ของ ERPNext

## 1. ขอบเขตและหลักการ

- หนึ่ง Material Request มีหนึ่งปลายทางและหนึ่ง native
  `material_request_type`; ต่างปลายทางหรือ purpose ต้องเปิดคนละใบ
- `request_usage` แยก `Employee Borrow`, `Customer Demo`,
  `Customer Loan` และ `Internal Permanent Use`
- Customer Demo ตัดสิน route จากมูลค่าทุนต่อ stock UOM หนึ่งหน่วยใน Company
  Currency โดยไม่รวม VAT:
  - มากกว่า 10,000.00 บาท: `Stock Capitalization`
  - เท่ากับหรือต่ำกว่า 10,000.00 บาท: `Stock Entry`
  - `Existing Asset` ใช้ Asset path ต่อโดยไม่ประเมินเกณฑ์ใหม่
- Customer Loan และ Employee Borrow ใช้ได้ทั้ง Stock และ Asset
- Stock Entry, Purchase Order, Asset Capitalization, Asset Movement,
  Quality Inspection และเอกสารขาย native เป็น source of truth
- `fulfillment_route` บอกวิธี ไม่ใช่สถานะ; ไม่มี reservation, item status,
  automatic completion, split หรือ transit warehouse
- Dispatch บันทึก logistics/POD และอ้าง movement ที่ submit แล้วเท่านั้น
- Clearance/Aging เป็น Phase 2 และไม่อยู่ใน implementation ชุดนี้

## 2. การอนุมัติ: Frappe Workflow เท่านั้น

แอป **ไม่สร้าง ไม่แก้ ไม่ export และไม่ hardcode** Workflow, Workflow State,
Workflow Action หรือ Transition และไม่เขียน `workflow_state` ลงเอกสาร
Workflow เป็น site-owned configuration ที่ผู้ดูแลระบบสร้างผ่าน Frappe Desk

ตัวแอปเปิด transition tasks ให้ผู้ดูแล site เลือกผูกกับ native Workflow:

| Transition task | ใช้กับ action |
|---|---|
| `Validate Material Request: Submit for Approval` | ตรวจข้อมูลปลายทางก่อนส่งอนุมัติ |
| `Validate Material Request: Close` | ตรวจ downstream, การคืน และ QA ก่อนปิด |
| `Capture Print Action: Authorized` | เก็บ authorized snapshot ตอนอนุมัติ |

Workflow ที่ธุรกิจต้องตั้งค่าบนแต่ละ site:

| Current | Action | Role | Next | Docstatus |
|---|---|---|---|---:|
| Draft | Submit for Approval | Purchase Requester | Pending Approval | 0 |
| Pending Approval | Approve | C-Level Approver | Approved | 1 |
| Pending Approval | Reject | C-Level Approver | Rejected | 0 |
| Pending Approval | Withdraw | Purchase Requester | Draft | 0 |
| Rejected | Revise | Purchase Requester | Draft | 0 |
| Approved | Close | Accounts User | Closed | 1 |
| Approved/Closed | Cancel | ผู้มีสิทธิ์ cancel | Cancelled | 2 |

C-Level self-approval ใช้ความสามารถของ native Workflow ได้ ส่วน Asset
Capitalization ใช้ Workflow site-owned แยก
`Draft → Pending Approval → Approved` พร้อม Rejected/Revise และ native Cancel
โดย action อนุมัติผูก `Capture Print Action: Authorized`

## 3. Material Request

Custom fields บน header เป็น optional ใน schema เพื่อเปิดเอกสารเก่าได้:

| Field | Type / Options |
|---|---|
| `request_usage` | Employee Borrow / Customer Demo / Customer Loan / Internal Permanent Use |
| `destination_type` | Employee / Customer / Company Site |
| `responsible_employee` | Link Employee |
| `destination_customer` | Link Customer |
| `destination_address` | Link Address |
| `asset_location` | Link Location |
| `expected_return_date` | Date |

ใช้ native `schedule_date` เป็น Planned Deployment Date และใช้
`destination_customer` แทน native `customer` ซึ่ง ERPNext v16 ล้างเมื่อ purpose
ไม่ใช่ Customer Provided. Field เดิม `purchase_reason` คงชื่อฐานข้อมูลไว้และแสดง
label เป็น Request Reason; `supporting_document_complete` ไม่เปลี่ยน

Transition task สำหรับ Submit for Approval ตรวจ:

- Employee Borrow ต้องมี Responsible Employee และ Expected Return Date
- Customer Demo/Loan ต้องมี Customer, Address, Responsible Employee และ
  Expected Return Date
- Address ต้องผูกกับ Customer และ Employee ต้อง Active/Company เดียวกับ MR
- Customer Demo ต้องมี `destination_type = Customer`
- Internal Permanent Use ต้องมี warehouse สำหรับ Stock หรือ leaf Asset Location
  สำหรับ Asset

### Material Request Item

| Field | Type | Access |
|---|---|---|
| `fulfillment_route` | Stock Entry / Existing Asset / Purchase / Stock Capitalization | Accounts, allow on submit |
| `allocated_asset` | Link Asset | Accounts, allow on submit |
| `unit_cost_ex_vat` | Currency | Server-computed snapshot |
| `cost_source` | Small Text | Server-computed source/date |

`Refresh Unit Cost` ทำงานบน server และอนุญาต Accounts/System Manager:

- Existing stock ใช้ valuation rate ล่าสุดของ source warehouse ณ วันที่ MR
- ของที่เพิ่งซื้อและยังไม่มี valuation ใช้ Purchase Receipt
  `base_net_amount / stock_qty`
- เปรียบเทียบหลังปัดด้วย native currency precision
- ต้นทุนเป็นต่อ stock UOM หนึ่งหน่วย ไม่ใช่ยอดรวมทั้งบรรทัด และไม่รวม VAT
- ถ้าหาต้นทุนไม่ได้ Customer Demo เลือก route ไม่ได้
- Version ของ Frappe เก็บประวัติ snapshot; ไม่มี cost audit engine เพิ่ม

Route matrix:

| Usage | Routes |
|---|---|
| Employee Borrow | Stock Entry / Existing Asset / Purchase / Stock Capitalization |
| Customer Demo | Stock Entry / Existing Asset / Stock Capitalization |
| Customer Loan | Stock Entry / Existing Asset / Purchase / Stock Capitalization |
| Internal Permanent Use | Stock Entry / Existing Asset / Purchase / Stock Capitalization |

Customer Demo ห้าม Purchase route. หากต้องซื้อใหม่ ให้เปิด Purchase MR แยก,
รับสินค้าแล้ว refresh ต้นทุน จากนั้นเลือก Stock หรือ Capitalization ตามเกณฑ์
Demo MR เดียวมี Stock และ Asset lines ผสมกันได้เมื่อทุกบรรทัดไปปลายทางเดียวกัน

`Existing Asset` ต้องมี `allocated_asset`; Stock Entry/Purchase ต้องไม่มี Asset.
Asset ต้อง submit แล้ว, Item/Company ตรง และไม่ Sold, Scrapped, Capitalized,
Cancelled, In Maintenance หรือ Out of Order. Allocation เป็น planning reference
ไม่ใช่ hard reservation

เมื่อมี downstream document ที่ยังไม่ Cancelled ห้ามเปลี่ยน route, Asset หรือ cost
snapshot จนกว่าจะ cancel/reverse downstream ตาม native lifecycle

## 4. Downstream และ Authorized snapshot

- PO Item และ Stock Entry Detail ใช้ native MR/MR Item links/counters
- Asset Movement, Asset Capitalization และ Quality Inspection มี
  `material_request` link สำหรับ Connections/validation
- MR Connections แสดง Purchase Order, Stock Entry, Asset Movement,
  Asset Capitalization, Quality Inspection, Dispatch, Borrowed Asset Return Inspection และ Borrowed Item Resolution
- ห้าม override native mapper หรือเขียน `status`, `per_*`,
  `ordered_qty` โดยตรง
- MR และ Asset Capitalization เก็บเฉพาะ `authorized_by`, `authorized_at`,
  `authorized_signature`
- Snapshot คัดลอก Employee `quotation_signature` ตอน native Workflow action;
  ไม่ clone File และไม่ hash
- Submit/Checked snapshots ของ MR ถูก retire; action อื่นดูจาก Workflow Action,
  Timeline และ Version

Transition task สำหรับ Close บังคับให้ทุก Item มี route และมี downstream อย่างน้อย
หนึ่งเอกสาร Returnable usages ต้องมี Delivered Outbound และ outstanding เป็นศูนย์
Customer Demo ต้องผ่าน return movement และ QA ตามชนิด line ก่อน Close

## 5. Dispatch

`Dispatch` เป็น submittable DocType prefix `DSP`; `Dispatch Transfer` เป็น
child table. Parent เก็บ Company/MR, Outbound/Return/Retry, original trip,
ที่อยู่, driver/vehicle/carrier/tracking, เวลา, status และ POD

แต่ละ transfer เก็บ MR Item, Item, Asset, Qty/UOM, reference doctype/name และ
`against_dispatch_transfer` สำหรับ Return/Retry

กฎสำคัญ:

- Returnable Stock route ใช้ native Outward `Source → Borrow In Transit` และ End Transit
  `Transit → Borrow Warehouse`; หนึ่ง MR มีหนึ่ง Outward cycle และ Outward ต้องครบ 100%
- Asset route อ้าง submitted Asset Movement ของ MR และต้องมี Asset; ไม่มี custom Asset Transit
- Customer Demo Stock/Asset ต้องตรงกับ route จาก cost snapshot
- Return แต่ละเที่ยวใช้ native Return Outward `Borrow Warehouse → Transit` และ End Transit
  `Transit → QA Hold`; Batch/Serial identity ของเที่ยวคืนอาจต่างจากเที่ยวออก
- Return ยืนยันแล้วคงเป็น pending QA จน native Quality Inspection หรือ Borrowed Asset
  Return Inspection ได้รับการ Submit เป็น Accepted; จึงค่อย release ไป planned destination
- Asset เดียวกันอยู่ใน active outstanding Outbound ได้เพียงชุดเดียว
- Retry ใช้ Outward เดิม, อ้าง Failed Outbound และไม่เพิ่ม outstanding
- Failed Outbound ใช้ `Return to Origin` เพื่อสร้าง native End Transit กลับ source เดิมและตั้ง MR เป็น Stopped
- ไม่มี partial line status; คืนบางส่วนด้วย Return Dispatch แยก

Submit Outbound/Return/Retry เปลี่ยน logistics status เป็น Dispatched. หลัง submit
แก้ state/POD ผ่าน POST APIs เท่านั้น:

- `confirm_dispatch_delivery(...)`
- `override_dispatch_delivery(...)`
- `return_dispatch_to_origin(...)`
- `report_dispatch_failure(...)`

API re-fetch พร้อม row lock, ตรวจ permission/company/current state และคืน
`{"data": ..., "message": ...}`. Confirm/Override เป็น transaction เดียวกับ native End
Transit และ Asset Movement; ไม่มี background auto-submit และไม่มี `ignore_permissions`

## 6. Return QA

Stock Demo:

1. Return Dispatch ต้อง Delivered และ Return End Transit ต้องเข้า QA Hold เสมอ
2. Stock ใช้ native Quality Inspection อ้าง Return Dispatch Transfer และ exact Stock Entry Detail
3. Asset ใช้ Borrowed Asset Return Inspection อ้าง Return Dispatch line
4. Accepted สร้าง draft native release ให้คลัง Submit; Repairable ไป Repair และบังคับ reinspection
5. Damaged Beyond Repair รอ Borrowed Item Resolution ก่อน write-off

Asset Demo:

- ใช้ submittable `Borrowed Asset Return Inspection` prefix `BARI` และ `Borrowed Item Resolution` prefix `BIR`
- หนึ่งใบต่อหนึ่ง Asset ต่อการตรวจ โดยอ้าง MR และ Return Dispatch line
- เก็บ inspector/time, result, damage note, รูปเครื่อง/อุปกรณ์/Asset ID และ checklist
- Accepted ต้องไม่มี failed check
- Rejected ต้องมี failed check และ Damage Note
- ตรวจซ้ำได้ แต่มี Accepted active ได้เพียงหนึ่งใบต่อ Return line
- Quality Manager เป็นผู้ตรวจและ submit

## 7. รายงานของที่ยังไม่คืน

Query Report `Outstanding Borrowed Items` แสดงใน Stock ด้วย label ไทย
“ของที่ยังไม่คืน”:

```text
outstanding = outbound - QA-accepted returns - returned-to-origin - settled - written-off
```

Failed Outbound ยังนับค้างหนึ่งครั้ง; Return ระหว่างทางแสดงเป็น `pending_qa_qty` และยังไม่หัก;
Retry ไม่เพิ่มยอด; Cancelled Dispatch ไม่ถูกนับ. แสดง `returned_qty`, `pending_qa_qty`,
`settled_qty`, `written_off_qty` และแยก Asset ครอบคลุม Employee Borrow, Customer Demo
และ Customer Loan พร้อม due date/overdue days

Filters: Company, As-of Date, Usage, Responsible Employee, Customer, Material
Request และ Overdue Only

## 8. UI, Print และ Navigation

- MR แสดง Demo/Loan แยกกัน พร้อมเกณฑ์ 10,000 บาทและปุ่ม Refresh Unit Cost
- Demo route options จำกัดตาม cost snapshot; Existing Asset ยังเลือกได้
- Stock Workspace/Sidebar แสดง Dispatch, Borrowed Asset Return Inspection, Borrowed Item Resolution และรายงานค้างคืน
  โดย setup เป็น idempotent และใช้ `_save_without_export`
- Print Formats: Material Request, Dispatch, Borrowed Asset Return Inspection และ Demo
  Asset Label ใช้ native Chrome renderer และลง Print Audit Log เดิม
- Label ใช้ Asset ID สำหรับ Asset และ native Serial No สำหรับ serialized Stock

## 9. Migration และ deployment

Forward patches:

1. หยุด migrate หากพบ prototype usage `Customer Demo / Loan`; ผู้ใช้ต้องแยกค่าเอง
2. เพิ่ม fields แบบ null-safe โดยไม่ backfill destination/route/cost
3. Rename `Demo Return Inspection` และ child เป็น Borrowed Asset Return Inspection พร้อม rollback
4. เพิ่ม transit/return controls และลบ MR Submit/Checked snapshot fields หลัง backup

Rollback patches คืน schema ของ fields ได้ แต่ค่าที่ลบต้องกู้จาก backup. ไม่มี patch
สร้าง Workflow, map `workflow_state` หรือ retire Workflow อัตโนมัติ

ขั้นตอน human deployment:

1. Backup site
2. Migrate code/schema
3. ผู้ดูแล site สร้าง/ปรับ native Frappe Workflows และผูก transition tasks ตามข้อ 2
4. เมื่อยืนยันว่าไม่มีเอกสารใช้งาน Workflow เก่า ให้ผู้ดูแล retire
   `Material Request Flow` ผ่าน Desk
5. ปรับ controlled SOP: เกณฑ์ `> 10,000.00` ต่อเครื่องไม่รวม VAT,
   Stock return ใช้ Stock Entry + Quality Inspection, Asset return ใช้ Asset Movement
   + Borrowed Asset Return Inspection และ Borrowed Item Resolution

## 10. Phase 2: Clearance

- Demo ที่ยังเป็น Stock: Material Transfer ไป Clearance Warehouse และ native sales flow
- Demo ที่เป็น Asset: native `Sell Asset → Sales Invoice` โดยตรง
- ไม่มี Asset-to-Stock conversion
