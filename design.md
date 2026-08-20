# Vyaprix Enterprise ERP: Full-Suite Google Stitch UI/UX Design System Specification
## The Blueprint for an Artisan Sandstone, Burnished Bronze & Forest Sage Visual System
### Global Corporate Mandate: POWERED BY Vyaprix software under PADASHETTY SOFTWARES

---

## 1. Global Visual Identity & Foundations (The Handcrafted Non-AI Aesthetic)

This design system rejects all modern, generic "AI-generated" website templates (such as glowing neon gradients, soft cool-blue cards, glassmorphic blur filters, and generic grey buttons). Instead, it implements a highly polished, **Artisan Sandstone, Burnished Bronze & Forest Sage** system. It delivers a premium, human-crafted feel inspired by state-of-the-art developer and designer interfaces (like Stripe, Figma, and Linear), using solid framing, warm sandstone textures, and organic accent colors.

### 1.1 Curated Color Palette & Tokens (Artisan Palette)
These tokens establish the rich visual palette across the platform:

```css
:root {
  /* Dynamic Bronze & Ochre Accents */
  --bronze: #a37d2e;                       /* Polished Antique Bronze (Primary Action buttons, active outlines) */
  --ochre: #b38b36;                        /* Warm Rich Ochre (Highlights, selected badges, price focus) */
  --bronze-dark: #7a5c1d;                  /* Deep Executive Bronze (Active click states, primary hover) */
  --bronze-light: #f7eed7;                 /* Soft Warm Sand (Hover states, input focus background) */
  
  /* Solid Natural Canvas */
  --ink: #1c1d1a;                          /* Obsidian Charcoal Black for crisp, high-contrast readability */
  --muted: #61635f;                        /* Graphite Grey for secondary details and subtexts */
  --surface: #ffffff;                      /* Crisp Alabaster White for active cards, tables, and pages */
  --sandstone: #f7f6f2;                    /* Warm Alabaster Sandstone for the main background canvas */
  --panel: #fcfbfa;                        /* Soft Warm Tint for alternative table rows */
  --stroke: #2e302c;                       /* Crisp graphite borders (Thin solid outline) */
  --stroke-subtle: #d4d2cc;                /* Soft stone border for secondary dividers */
  
  /* Organic Statutory Compliance Tags */
  --sage-green: #1e4620;                   /* Warm Forest Sage Green for positive transactions */
  --sage-light: #d1e2d3;                   /* Soft Sage backing */
  --rust-red: #7f1d1d;                     /* Deep Rust Red for cancellations and delete states */
  --rust-light: #fecaca;                   /* Soft Rust backing */
  --ochre-warn: #b45309;                   /* Ochre Amber for low stock and limit warnings */
  
  /* Physical Flat Offset Shadows (Zero AI Gradient Glows) */
  --shadow: 4px 4px 0px #2e302c;           /* Crisp physical offset shadow for human-designed card styling */
  --shadow-sm: 2px 2px 0px #2e302c;        /* Subtle offset shadow for buttons and badges */
}
```

### 1.2 Layout Geometry & Structure (Clean 8px Curvature)
- **Structured Geometry**: Curvatures are kept clean and geometric to avoid cheap pill-shaped round buttons:
  ```css
  .card, .panel, .input, .btn, .vyaprix-panel {
    border-radius: 8px !important;         /* Clean, structured 8px radius globally */
  }
  ```
- **Physical Sandstone Canvas**: The body uses a flat, warm Sandstone Alabaster canvas:
  ```css
  body {
    margin: 0;
    background-color: var(--sandstone);
    color: var(--ink);
    min-height: 100vh;
    font-family: "Outfit", "Segoe UI", sans-serif;
  }
  ```

### 1.3 Professional Typography Pairings
- **Header Titles, Invoices & Brand Labels**: Serif **`Domine`** (Google Fonts). Gives shop headers and billing layouts an authentic, human-publication quality.
- **Numbers, Ledgers & Table Columns**: Strictly monospaced **`JetBrains Mono`** or **`Courier Prime`**. Restricts digit width to keep decimal columns aligned.
- **Regular Control Panels & Inputs**: Clean sans-serif **`Outfit`** (Google Fonts). Modern geometric styling for dynamic cart views and settings grids.

---

## 2. Global Navigation Frame & Branding Credit

Every page generated inside Google Stitch must be enclosed in the appropriate global navigation frame and feature our branding attributions.

### 2.1 Front-End Navigation Shell (`templates/base.html`)
- **Sticky Top Bar** (`.site-header`): Thin graphite bottom border (`1px solid var(--stroke)`). Integrates the serif brand logo **Vyaprix** on the left.
- **Dynamic Navigation Link Tabs**: Rectangular navigation buttons. Hovering highlights the button in soft warm sand (`background: var(--bronze-light); border: 1px solid var(--stroke)`).
- **Flash Notification Stack**: Clean warning banners with matching border outlines (`1px solid var(--stroke)`) and offset shadows (`var(--shadow-sm)`).

### 2.2 Corporate Sidebar Layout (`templates/admin/base_admin.html`)
- **Visual Sidebar Column** (`.admin-sidebar`): A clean, left-aligned column with a solid white background (`--surface`) and a `1px solid var(--stroke-subtle)` right border.
- **Vertical Navigation Items**: Simple rectangular blocks. Active links highlight in deep bronze (`background: var(--bronze); color: #1a1a1a; border: 1.5px solid var(--stroke)`).
- **Main Viewport Column**: Flat, structured display with a top bar showing active user profiles.

### 2.3 Unremovable Global Branding Credit (Attribution Constraint)
The platform branding credit must remain visible at the bottom of every page layout, settings form, checkout panel, and tax invoice:
```html
<footer class="vyaprix-immutable-footer">
    POWERED BY Vyaprix software under PADASHETTY SOFTWARES
</footer>
```
- **Aesthetics**: Font-family: monospaced, font-size: `11px`, letter-spacing: `2px`, color: `var(--muted)`, uppercase, centered alignment.

---

## 3. High-Fidelity Screen-by-Screen Visual Prompt Matrix

---

### Page 1: Secure Login Gateway (`templates/login.html`)
A premium center-split card layout that matches the active tenant's branding.

```
+---------------------------------------------------------------+
|                       [ Tenant Logo ]                         |
|                   M/S SRI DEVI INDUSTRIES                     |
|                                                               |
|   =========================================================   |
|   ADMIN LOGIN                                                 |
|   =========================================================   |
|                                                               |
|   Username   [_______________________________________]        |
|   Password   [_______________________________________]        |
|                                                               |
|   [                      SIGN IN                         ]    |
|                                                               |
|     POWERED BY Vyaprix software under PADASHETTY SOFTWARES    |
+---------------------------------------------------------------+
```
- **Visual Elements**:
  - **Login Card Box**: Solid white canvas (`background: var(--surface)`), sharp `1.5px solid var(--stroke)` border, and a bold offset shadow (`var(--shadow)`).
  - **Form Input Fields**: Clean rectangular inputs. Focus highlights the input in soft sand (`background: var(--bronze-light)`) and adds a bold bronze focus outline (`border-color: var(--bronze)`).
  - **Primary Sign In Button**: Solid bronze action block (`background: var(--bronze); color: #1c1d1a; border: 1.5px solid var(--stroke); box-shadow: var(--shadow-sm)`).
  - **Attribution Credit**: Centered monospaced attribution footer printed underneath the login container.

---

### Page 2: POS Billing Terminal (`templates/index.html`)
A responsive 60/40 checkout terminal designed to optimize item management and minimize checkout times.

```
+-----------------------------------------------------------------------------------+
| POS SEARCH: [ Search by name, SKU, or barcode... (F2) ]     [+ ADD CUSTOM ITEM]   |
+-----------------------------------------------------------------------------------+
|  [Item Grid Cards]                               | Cart Workspace:                |
|  +--------------------+  +--------------------+  | [Cart Table Body]              |
|  | Premium Smartwatch |  | Cotton Polo Shirt  |  | #  Item      Rate  Qty   Total  |
|  | SKU: WCH-102       |  | SKU: AP-802        |  | 1  Smartwatch 4500  2.00  9000.00|
|  | Stock: 14 pcs      |  | Stock: 3 pcs       |  |                                |
|  | Rate: [ 4500.00  ] |  | Qty: [___]         |  | Discount: [__________________] |
|  | [1 kg] [30 Pkt]    |  | [+ ADD TO CART]    |  | Pay Mode: [💵 Cash] [📱 UPI]   |
|  +--------------------+  +--------------------+  | GST Toggle: [🧾 Apply 5% GST]  |
|                                                  | Grand Total: INR 14400.00      |
|                                                  | [       SAVE & PRINT (F4)       ]  |
+-----------------------------------------------------------------------------------+
|                       POWERED BY Vyaprix software under PADASHETTY SOFTWARES     |
+-----------------------------------------------------------------------------------+
```
- **Visual Elements**:
  - **Search Header**: Rectangular search input featuring thin borders and quick custom item buttons on the right.
  - **Category Tabs**: Grid of rectangular buttons. The active category highlights in deep bronze (`background: var(--bronze); color: #1a1a1a; border: 1px solid var(--stroke)`).
  - **Catalogue Grid**:
    - **Editable Rate Row** (`.rate-override-row`): A sharp-edged input box (`border: 1px solid var(--stroke)`) on the product card that lets staff adjust rates dynamically before checkout.
    - **Quick Add Actions**:
      - `.bag-1` (Warm Sand): Adds 1 standard unit dynamically.
      - `.bag-30` (Forest Sage): Adds 30 units at once (highlighted in soft packaging teal).
      - `.bag-loose` (Antique Bronze): Opens a sharp-edged popover for fractional units.
  - **Cart Column**:
    - **Cart Table**: Crisp data rows with sharp borders and action buttons. Includes number-steppers (`.qty-stepper` with flat buttons) and editable rates (`.rate-input`).
    - **Payment Pills**: Flat rectangular selectors. Active selection highlights in ledger yellow (`background: var(--paper-yellow)`).
    - **Grand Total Container**: Large bold monospaced total displayed at the bottom of the sidebar.
    - **Attribution Credit**: Center-aligned attribution footer printed at the bottom of the sidebar.

---

### Page 3: Statutory Tax Invoice (`templates/bill_print.html`)
An authentic, printable A5 landscape layout modeled directly after physical bookkeeping vouchers.

```
+-----------------------------------------------------------------------------------+
|                              M/S SRI DEVI INDUSTRIES                              |
|                          FSSAI: 12345  |  ISO: 9001:2015                          |
|                                                                                   |
|  [ ORIGINAL COPY ]                                                                |
|  Invoice No: INV-40302                        Date: 21-May-2026                   |
|  +-----------------------------------------------------------------------------+  |
|  | Sr.  Product Name        HSN/SAC    Qty          Unit Price   Taxable value |  |
|  | 1    Smartwatch          8517       2.000 PCS    4,500.00     9,000.00      |  |
|  +-----------------------------------------------------------------------------+  |
|  | Bank Details: SBI A/c 44941352398          CGST (2.5%):        225.00       |  |
|  | IFSC: SBIN0003304 | UPI: 4494@sbi          SGST (2.5%):        225.00       |  |
|  | [ UPI QR Code Image ]                      Grand Total:      9,450.00       |  |
|  +-----------------------------------------------------------------------------+  |
|  | Customer Signature                         Authorised Signatory             |  |
|  +-----------------------------------------------------------------------------+  |
|  |            POWERED BY Vyaprix software under PADASHETTY SOFTWARES           |  |
|  +-----------------------------------------------------------------------------+  |
|  - - - - - - - - - - - - - - - - - - - ✂ cut here - - - - - - - - - - - - - - - -  |
|  [ DUPLICATE COPY ]                                                               |
|  ... (repeats exact invoice layout above for duplicate records) ...               |
+-----------------------------------------------------------------------------------+
```
- **Visual Elements**:
  - **Sheet Canvas** (`.a5-sheet`): Set to A5 landscape during print, hiding all browser margins and web elements.
  - **Original & Duplicate Copies**: Separated by a printable scissor line indicator (`✂ cut here`).
  - **Layout Geometry**: Thin, solid black boundaries (`1px solid #000000`). No curves.
  - **Information Grids**: Detailed tables mapping invoice metadata, buyer/supplier states, place of supply, and payment modes.
  - **Bank Details & QR Code**: A dedicated box listing the bank name, branch, account number, and IFSC code, next to an active, printable UPI QR code.
  - **Attribution Credit**: Printed centered at the bottom of both copy layouts: `POWERED BY Vyaprix software under PADASHETTY SOFTWARES`.

---

### Page 4: Admin Analytics Cockpit (`templates/admin/dashboard.html`)
The central administrative monitoring terminal.

```
+-----------------------------------------------------------------------------------+
|  [Today's Revenue: Rs 14,400]    [Today's Bills: 24]    [Average Bill: Rs 600]    |
+-----------------------------------------------------------------------------------+
|  Weekly Revenue Chart:                                                            |
|  100% |                                                                           |
|   50% |   [Bar]        [Bar]        [Bar]        [Bar]        [Bar]               |
|    0% +------------------------------------------------------------------         |
|           Mon          Tue          Wed          Thu          Fri                 |
|                                                                                   |
|  Top Products (Month):                           Payment Mix:                     |
|  1. Smartwatch - 14 sold                         - Cash: Rs 8,000 (55%)           |
|  2. Polo Shirt - 8 sold                          - UPI: Rs 4,400 (30%)            |
+-----------------------------------------------------------------------------------+
|                       POWERED BY Vyaprix software under PADASHETTY SOFTWARES     |
+-----------------------------------------------------------------------------------+
```
- **Visual Elements**:
  - **Dashboard Metric Cards Row**: 4 solid white metric cards with paper-thin borders (`1px solid var(--stroke)`). Highlights key figures in deep ink-black bold (`font-size: 1.6rem`).
  - **Weekly Revenue Bar-Chart**: A clean, CSS-based layout showing vertical bars whose heights reflect revenue totals. Hovering over a bar reveals exact sales values.
  - **Top Products & Payment Mix**: Split-card layout showing top-performing inventory items and active checkout configurations.
  - **Attribution Credit**: Center-aligned uppercase attribution footer printed at the bottom of the grid.

---

### Page 5: Stock Catalog Manager (`templates/admin/products.html`)
A master-detail catalog view that supports image uploads, HSN tags, and active SKU filters.

```
+-----------------------------------------------------------------------------------+
|  Filter: [ Search...            ]   Category: [ All ]               [ Filter ]    |
+-----------------------------------------------------------------------------------+
|  Add / Edit Product Card:            | Catalog Directory Table:                  |
|  Name:      [___________________]    | SKU        Name       Stock    Actions    |
|  SKU:       [___________________]    | WCH-102    Smartwatch 14 pcs   [Edit]     |
|  Category:  [ Select...         ]    | AP-802     Polo Shirt 3 pcs    [Toggle]   |
|  Price/Unit:[___________________]    | [Product Thumbnail Image Preview]         |
|  HSN Code:  [___________________]    |                                           |
|  [Select Image...]   [ Active [x] ]  |                                           |
|  [         Save Changes           ]  |                                           |
+-----------------------------------------------------------------------------------+
|                       POWERED BY Vyaprix software under PADASHETTY SOFTWARES     |
+-----------------------------------------------------------------------------------+
```
- **Visual Elements**:
  - **Add/Edit Sidebar Card**: A standard, solid-white card panel (`.vyaprix-panel`) featuring fields for SKU, tax rates, weight parameters, barcode values, and an image upload zone.
  - **Catalogue Directory Table**: Tabular view displaying item metadata, stock limits, and quick-action toggles (Edit, Toggle, Delete).
  - **Soft-Delete Action**: Archives items securely while keeping records restorable in the backend database.
  - **Attribution Credit**: Center-aligned attribution footer printed at the bottom of the page.

---

### Page 6: Unified Invoice Ledger (`templates/admin/bills.html`)
The comprehensive transaction ledger. Supports date filters, cancel requests, and CSV exports.

```
+-----------------------------------------------------------------------------------+
|  Filters: Start: [ Date ]  End: [ Date ]  Mode: [ All ]      [Apply]  [Export CSV]|
+-----------------------------------------------------------------------------------+
|  Invoice Log Table:                                                               |
|  Bill No      Date        Customer      Grand Total   Payment    Actions          |
|  INV-40302    21-May-26   Ramesh Kumar  Rs. 9,450.00  UPI        [View] [Cancel]  |
|  INV-40301    20-May-26   Walk-in       Rs. 1,200.00  CASH       [View] [Cancel]  |
+-----------------------------------------------------------------------------------+
|                       POWERED BY Vyaprix software under PADASHETTY SOFTWARES     |
+-----------------------------------------------------------------------------------+
```
- **Visual Elements**:
  - **Filter Bar**: Flexbox-based header bar containing inputs for start/end dates, status dropdowns, payment configurations, and SKU filters.
  - **Invoice Log Table**: Tabular view listing invoice dates, totals, and payment modes.
  - **Cancel Flow**: Confirming a cancellation request prompts the operator to enter a cancellation reason before writing the change to the transaction log.
  - **Attribution Credit**: Center-aligned attribution footer printed at the bottom of the page.

---

### Page 7: Invoice Details Viewer (`templates/admin/bill_detail.html`)
A high-contrast transaction view showing line items and active GST tax summaries.

```
+-----------------------------------------------------------------------------------+
|  Bill Detail: INV-40302                                     [Print]  [Download PDF]|
+-----------------------------------------------------------------------------------+
|  Invoice Date: 21-May-2026 14:32          Customer: Ramesh Kumar                  |
|  Operator: Raman (staff)                  Phone: 9845012345                       |
|                                                                                   |
|  Items Table:                                                                     |
|  #   Product Name    HSN/SAC    Qty    Unit   Rate        GST%     Amount         |
|  1   Smartwatch      8517       2.000  PCS    4,500.00    5.0%     9,000.00       |
|                                                                                   |
|  Summary Card:                                                                    |
|  Subtotal:   Rs 9,000.00     Discount: Rs 0.00        Taxable: Rs 9,000.00        |
|  GST (5%):   Rs 450.00       Grand Total: Rs 9,450.00 Payment: UPI                |
+-----------------------------------------------------------------------------------+
|                       POWERED BY Vyaprix software under PADASHETTY SOFTWARES     |
+-----------------------------------------------------------------------------------+
```
- **Visual Elements**:
  - **Master Information Header**: Split grid showing invoice metadata (date, operator, payment status) on the left, customer contact details on the right.
  - **Items Table**: High-contrast, clean grid showing HSN codes, quantity values, unit metrics, unit rates, tax percentages, and final taxable totals.
  - **Line Item Detail Box**: Highlights final totals, taxable income splits, and discount values in high-contrast monospaced bold text.
  - **Attribution Credit**: Center-aligned attribution footer printed at the bottom of the page.

---

### Page 8: Statuary GSTR Accounting Panel (`templates/admin/gst_report.html`)
A compilation panel used by accountants to verify tax compliance and prepare GSTR-1 and GSTR-3B filings.

```
+-----------------------------------------------------------------------------------+
|  GST Report Period: [ 21-Apr-2026 — 21-May-2026 ]                     [Export CSV]|
+-----------------------------------------------------------------------------------+
|  Summary Metrics:                                                                 |
|  [Bills: 24]  [Gross: Rs 2,50,000]  [Discount: Rs 5,000]  [Taxable: Rs 2,45,000]  |
|  [CGST: Rs 6,125]        [SGST: Rs 6,125]        [Total Tax Liability: Rs 12,250] |
+-----------------------------------------------------------------------------------+
|  Invoice-wise GST Table:                                                          |
|  #   Invoice No.  Date       Customer GSTIN      Taxable  CGST   SGST   Grand     |
|  1   INV-40302    21-May-26  27AAAAA1111A1Z1     9,000    225    225    9,450     |
+-----------------------------------------------------------------------------------+
|                       POWERED BY Vyaprix software under PADASHETTY SOFTWARES     |
+-----------------------------------------------------------------------------------+
```
- **Visual Elements**:
  - **Summary Cards Row**: 8 colored-tab metric cards (`.gst-card`) showing gross sales, discounts, central tax collections, and total liabilities.
  - **Invoice GST Compliance Table**: Tabular view displaying recipient GSTIN details, payment modes, and tax calculations.
  - **Action Bars**: Quick links that let users export GSTR-1 compliance CSV folders and GSTR-3B summary reports.
  - **Attribution Credit**: Center-aligned attribution footer printed at the bottom of the page.

---

### Page 9: Warehouse Inventory & Stock Ledger (`templates/admin/warehouse.html`)
The transaction-based stock manager. Log stock adjustments, restock levels, and physical counts.

```
+-----------------------------------------------------------------------------------+
|  Warehouse Stock Ledger                                                           |
+-----------------------------------------------------------------------------------+
|  SKU        Product Name   Unit   Current Stock   Adjust / Restock Actions        |
|  WCH-102    Smartwatch     PCS    14.000          [Restock  ] [Qty] [Note] [Save] |
|  AP-802     Polo Shirt     PCS    3.000           [Damage   ] [Qty] [Note] [Save] |
+-----------------------------------------------------------------------------------+
|                       POWERED BY Vyaprix software under PADASHETTY SOFTWARES     |
+-----------------------------------------------------------------------------------+
```
- **Visual Elements**:
  - **Stock Directory Table**: High-contrast, clean grid listing active SKU values, units (pcs, kg, liters, meters, hours), and stock counts.
  - **Stock Adjustment Row**: Dynamic inline form fields. Lets operators select adjustment actions (Restock, Damage, Transfer, Adjustment), input adjustment quantities, specify change notes, and post updates to the inventory ledger.
  - **Security Override Restriction**: Highlights superadmin-only database correction fields in red.
  - **Attribution Credit**: Center-aligned attribution footer printed at the bottom of the page.

---

### Page 10: Tenant Profile & Settings Suite (`templates/admin/settings.html`)
The white-label control panel. Let's tenant admins manage profiles, update banking details, and upload brand assets.

```
+-----------------------------------------------------------------------------------+
|  Business Settings & custom White-Labeling Profile Panel                          |
+-----------------------------------------------------------------------------------+
|  🏢 Business Details:                                                            |
|  Shop Name: [ SuperMart Corp        ] Address 1: [______________________________] |
|  Tagline:   [ Manufacturing Rava   ] Website:   [ www.supermart.com             ] |
|                                                                                   |
|  📋 Tax & Compliance:                                                             |
|  GSTIN:     [ 27AAAAA1111A1Z1      ] FSSAI No:  [ 12345678901234                ] |
|  ISO No:    [ ISO 22000:2018       ] [x] Enable GST on Bills                      |
|                                                                                   |
|  🏦 Bank Accounts:                                                                |
|  Bank Name: [ State Bank of India  ] Account No: [ 44941352398                  ] |
|                                                                                   |
|  🎨 Brand Logos:                                                                  |
|  [Select Brand Logo]         [Select FSSAI Logo]          [Select ISO Certificate]|
|  [Current Logo Preview]      [Current FSSAI Image]        [Current ISO Image]     |
|                                                                                   |
|  [                          💾 Save Configuration Updates ]                        |
+-----------------------------------------------------------------------------------+
|                       POWERED BY Vyaprix software under PADASHETTY SOFTWARES     |
+-----------------------------------------------------------------------------------+
```
- **Visual Elements**:
  - **Fieldsets**: Styled using grouped containers (`.settings-group`) with clear legend headers (🏢 Business Details, 📋 Tax & Compliance, 🏦 Bank Accounts, 🎨 Brand Logos).
  - **Logos Grid**: Multi-column file upload area with dynamic preview boxes (`.logo-preview`) showing the current logo.
  - **Terms & Declaration Blocks**: Text boxes for entering invoice terms and statutory tax declarations.
  - **Attribution Credit**: Center-aligned attribution footer printed at the bottom of the page.

---

### Page 11: Customer Credit & Udhaar Ledger (`templates/admin/customers.html` & `customer_detail.html`)
Tools for tracking customer accounts, outstanding balances, credit limits, and credit risks.

```
+-----------------------------------------------------------------------------------+
|  Customer Directory & credit Risk Monitoring                                       |
+-----------------------------------------------------------------------------------+
|  Name            Phone         Credit Limit    Current Dues     Risk Index        |
|  Ramesh Kumar    9845012345    50,000.00       12,450.00        [Normal  ] [View] |
+-----------------------------------------------------------------------------------+
|                       POWERED BY Vyaprix software under PADASHETTY SOFTWARES     |
+-----------------------------------------------------------------------------------+
```
- **Visual Elements**:
  - **Credit Meter Progress Bars**: A visual progress bar showing outstanding dues relative to credit limits. If outstanding dues exceed 80% of the limit, highlights the bar in red.
  - **Udhaar Credit History Log**: Tabular view listing credit and debit note values.
  - **Risk Assessment Tags**: Simple tags that classify customer risk profiles (Safe: Green, Warning: Yellow, Critical: Red).
  - **Attribution Credit**: Center-aligned attribution footer printed at the bottom of the page.

---

### Page 12: Staff Management & Permissions Panel (`templates/admin/staff.html`)
Operator list, role assignments, password reset controls, and actor logs.

```
+-----------------------------------------------------------------------------------+
|  Staff Directory                                                                  |
+-----------------------------------------------------------------------------------+
|  Username        Role          SaaS Status     Last Login       Actions           |
|  Raman           Staff         Active          21-May-26 14:02  [Toggle] [Reset]  |
+-----------------------------------------------------------------------------------+
|                       POWERED BY Vyaprix software under PADASHETTY SOFTWARES     |
+-----------------------------------------------------------------------------------+
```
- **Visual Elements**:
  - **Add User Card**: Form with inputs for username, password, and role (superadmin, admin, staff).
  - **Active Staff Grid**: Table listing active users, roles, statuses, and login timestamps.
  - **Security Override Controls**: Outlined action buttons for toggling user access and resetting passwords.
  - **Attribution Credit**: Center-aligned attribution footer printed at the bottom of the page.

---

### Page 13: Core Audit Log Panel (`templates/admin/audit.html`)
The operational audit log tracking database actions, billing updates, and stock movements.

```
+-----------------------------------------------------------------------------------+
|  Central Activity Log & Stock Movement Records                                    |
+-----------------------------------------------------------------------------------+
|  Audit Log Table:                                                                 |
|  Timestamp         Operator    Action     Entity     Entity ID    IP Address      |
|  21-May-26 14:32   Raman       CREATE     bill       10403        192.168.1.42    |
|                                                                                   |
|  Stock Movement Table:                                                            |
|  Date        Product         Change     Before     After      Reason   Note       |
|  21-May-26   Smartwatch      -2.000     16.000     14.000     sale     INV-40302  |
+-----------------------------------------------------------------------------------+
|                       POWERED BY Vyaprix software under PADASHETTY SOFTWARES     |
+-----------------------------------------------------------------------------------+
```
- **Visual Elements**:
  - **Unified Log Grid Layout**: High-contrast log list. Displays timestamps, operator names, database actions, entity classes, reference IDs, and IP addresses.
  - **Stock Movement Log Table**: Grid detailing stock changes, showing pre- and post-adjustment quantities, adjustment reasons, and operator notes.
  - **Attribution Credit**: Center-aligned attribution footer printed at the bottom of the page.

---

## 4. Google Stitch Front-End Visual Component Reference

Front-end elements designed inside Google Stitch should utilize the following structured styling parameters and layout mappings (Artisan Sandstone & Burnished Bronze):

```css
/* Artisan Sandstone Panel Card (Solid Borders, Flat Offset Shadows) */
.vyaprix-artisan-panel {
  background: var(--surface);
  border: 1.5px solid var(--stroke);
  box-shadow: var(--shadow);
  border-radius: 8px;
  padding: 20px;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.vyaprix-artisan-panel:hover {
  transform: translate(-2px, -2px);
  box-shadow: 6px 6px 0px var(--stroke);
}

/* Polished Bronze Action Button */
.vyaprix-btn-bronze {
  background: var(--bronze);
  color: var(--ink);
  border: 1.5px solid var(--stroke);
  box-shadow: var(--shadow-sm);
  border-radius: 8px;
  font-family: 'Outfit', sans-serif;
  font-weight: 600;
  padding: 10px 16px;
  cursor: pointer;
  transition: transform 0.1s ease, box-shadow 0.1s ease, background 0.15s ease;
}
.vyaprix-btn-bronze:hover {
  background: var(--ochre);
  transform: translate(-1px, -1px);
  box-shadow: 3px 3px 0px var(--stroke);
}
.vyaprix-btn-bronze:active {
  transform: translate(1px, 1px);
  box-shadow: 1px 1px 0px var(--stroke);
}

/* Stepper Stepper Controls */
.qty-stepper {
  display: flex;
  align-items: center;
  gap: 4px;
}
.qty-btn {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  border: 1.5px solid var(--stroke);
  background: var(--panel);
  cursor: pointer;
  font-size: 16px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s ease;
  font-family: inherit;
  color: var(--ink);
}
.qty-btn:hover {
  background: var(--bronze-light);
}

/* Editable Cart Rate Input */
.rate-input {
  width: 72px;
  padding: 4px 6px;
  border: 1.5px solid var(--stroke);
  border-radius: 6px;
  text-align: right;
  font-family: 'JetBrains Mono', monospace;
  font-weight: 600;
  background: var(--panel);
  color: var(--ink);
  transition: border-color 0.15s ease;
}
.rate-input:focus {
  outline: none;
  border-color: var(--bronze);
  background: var(--bronze-light);
}

/* Non-Removable Footer Credit */
.vyaprix-immutable-footer {
  text-align: center;
  padding: 24px 0;
  margin-top: auto;
  border-top: 1.5px solid var(--stroke);
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  letter-spacing: 2px;
  text-transform: uppercase;
  color: var(--muted);
  background: var(--surface);
}
```
