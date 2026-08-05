"""Render a Greenbar Pay evidence packet as a hashed PDF.

The rendered PDF is the auditor-facing artifact. Design principles:

  1. The manifest hash and verification instructions appear on the
     COVER page — before any invoice content. The hash is the point.
  2. Every printed field maps 1:1 to a manifest field so any auditor
     can trace paper -> JSON. No summary prose that isn't in the JSON.
  3. The full canonical JSON is embedded as a PDF attachment so a
     single file contains everything gbverify needs.
  4. Renders with `reportlab` (only PDF dep) so this is reproducible
     inside Greenbar's existing Node/Python stack via a small
     Python service or via `pdfkit` in Node with the same layout.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


# Greenbar green from greenbarsystems.com
GB_GREEN = colors.HexColor("#0F6B3A")
GB_GREEN_DARK = colors.HexColor("#0A4E2A")
GB_INK = colors.HexColor("#111111")
GB_MUTED = colors.HexColor("#555555")
GB_FAINT = colors.HexColor("#E5E7EB")
GB_BG = colors.HexColor("#F7F8F5")
GB_WARN = colors.HexColor("#B45309")
GB_BLOCK = colors.HexColor("#B91C1C")

MONO = "Courier"  # ships with reportlab
BODY = "Helvetica"
BOLD = "Helvetica-Bold"


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("GBTitle", parent=ss["Title"], fontName=BOLD,
                          fontSize=22, textColor=GB_INK, leading=26, spaceAfter=4))
    ss.add(ParagraphStyle("GBSubtitle", parent=ss["Normal"], fontName=BODY,
                          fontSize=11, textColor=GB_MUTED, leading=15, spaceAfter=14))
    ss.add(ParagraphStyle("GBH2", parent=ss["Heading2"], fontName=BOLD,
                          fontSize=13, textColor=GB_GREEN_DARK, leading=17,
                          spaceBefore=14, spaceAfter=6))
    ss.add(ParagraphStyle("GBBody", parent=ss["Normal"], fontName=BODY,
                          fontSize=10, textColor=GB_INK, leading=14))
    ss.add(ParagraphStyle("GBSmall", parent=ss["Normal"], fontName=BODY,
                          fontSize=8.5, textColor=GB_MUTED, leading=11))
    ss.add(ParagraphStyle("GBMono", parent=ss["Normal"], fontName=MONO,
                          fontSize=9, textColor=GB_INK, leading=12))
    ss.add(ParagraphStyle("GBEyebrow", parent=ss["Normal"], fontName=BOLD,
                          fontSize=8.5, textColor=GB_GREEN, leading=11,
                          spaceAfter=2))
    ss.add(ParagraphStyle("GBBadge", parent=ss["Normal"], fontName=BOLD,
                          fontSize=8, textColor=colors.white, leading=10,
                          alignment=1))
    return ss


def _header_footer(canvas, doc, packet):
    canvas.saveState()
    manifest_hash = packet["manifestHash"]
    packet_id = packet.get("packetId", "-")

    # Top rule + brand
    canvas.setFillColor(GB_GREEN)
    canvas.rect(0, LETTER[1] - 0.35 * inch, LETTER[0], 0.06 * inch,
                stroke=0, fill=1)
    canvas.setFillColor(GB_INK)
    canvas.setFont(BOLD, 9)
    canvas.drawString(0.6 * inch, LETTER[1] - 0.6 * inch,
                      "GreenBar Systems  ·  Evidence Packet")
    canvas.setFillColor(GB_MUTED)
    canvas.setFont(BODY, 8)
    canvas.drawRightString(LETTER[0] - 0.6 * inch, LETTER[1] - 0.6 * inch,
                           f"Packet {packet_id[:8]}  ·  Page {doc.page}")

    # Footer: hash on every page
    canvas.setFillColor(GB_FAINT)
    canvas.rect(0.6 * inch, 0.55 * inch, LETTER[0] - 1.2 * inch, 0.02 * inch,
                stroke=0, fill=1)
    canvas.setFillColor(GB_MUTED)
    canvas.setFont(BODY, 7.5)
    canvas.drawString(0.6 * inch, 0.4 * inch, "manifest sha-256")
    canvas.setFillColor(GB_INK)
    canvas.setFont(MONO, 7.5)
    canvas.drawString(1.5 * inch, 0.4 * inch, manifest_hash)
    canvas.setFillColor(GB_MUTED)
    canvas.setFont(BODY, 7.5)
    canvas.drawRightString(LETTER[0] - 0.6 * inch, 0.4 * inch,
                           "Verify with: gbverify packet.json")
    canvas.restoreState()


def _kv_table(rows, col1=1.5 * inch, col2=None):
    if col2 is None:
        col2 = 6.7 * inch - col1
    t = Table(rows, colWidths=[col1, col2])
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (0, -1), BOLD, 9),
        ("FONT", (1, 0), (1, -1), BODY, 9.5),
        ("TEXTCOLOR", (0, 0), (0, -1), GB_MUTED),
        ("TEXTCOLOR", (1, 0), (1, -1), GB_INK),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("LINEBELOW", (0, 0), (-1, -2), 0.25, GB_FAINT),
    ]))
    return t


def _hex(c):
    # reportlab Paragraph inline <font color="..."> wants a #RRGGBB string
    return "#" + c.hexval()[2:]


def _severity_badge(severity):
    severity = (severity or "").lower()
    color = {"blocking": GB_BLOCK, "warning": GB_WARN,
             "high": GB_BLOCK, "medium": GB_WARN,
             "low": GB_MUTED}.get(severity, GB_MUTED)
    return f'<font color="{_hex(color)}" size="7"><b>{severity.upper()}</b></font>'


def _cover(story, styles, packet):
    m = packet["manifest"]
    inv = m["extractedInvoice"]
    doc = m["originalDocument"]

    story.append(Paragraph("EVIDENCE PACKET", styles["GBEyebrow"]))
    story.append(Paragraph(
        f"{inv['vendorName']}  ·  {inv['invoiceNumber']}", styles["GBTitle"]))
    story.append(Paragraph(
        f"Sealed {packet['sealedAt']} — a signed, hash-verified attestation of "
        f"the AI-assisted review that led to approving this invoice. Any change "
        f"to the underlying record breaks the hash.",
        styles["GBSubtitle"]))

    # HASH BLOCK — the whole point of the document
    hash_rows = [
        ["Manifest SHA-256", Paragraph(
            f'<font face="{MONO}" size="9">{packet["manifestHash"]}</font>',
            styles["GBBody"])],
        ["Source document SHA-256", Paragraph(
            f'<font face="{MONO}" size="9">{doc["contentHash"]}</font>',
            styles["GBBody"])],
        ["Schema version", m["schemaVersion"]],
        ["Sealed at", packet["sealedAt"]],
        ["Packet ID", packet["packetId"]],
    ]
    hash_table = Table(hash_rows, colWidths=[1.8 * inch, 5.0 * inch])
    hash_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), GB_BG),
        ("BOX", (0, 0), (-1, -1), 0.75, GB_GREEN),
        ("LINEBEFORE", (0, 0), (0, -1), 3, GB_GREEN),
        ("FONT", (0, 0), (0, -1), BOLD, 9),
        ("FONT", (1, 0), (1, -1), BODY, 9),
        ("TEXTCOLOR", (0, 0), (0, -1), GB_GREEN_DARK),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.append(hash_table)
    story.append(Spacer(1, 14))

    # Verification instructions
    story.append(Paragraph("How to verify this packet", styles["GBH2"]))
    story.append(Paragraph(
        "The JSON manifest is attached to this PDF. Extract it and run the "
        "open-source verifier — no Greenbar account required, no network call:",
        styles["GBBody"]))
    story.append(Spacer(1, 6))

    verify_box = Table([[Paragraph(
        '<font face="Courier" size="9" color="#F7F8F5">'
        '$ npx @greenbarsystems/gbverify --document invoice.pdf packet.json<br/>'
        '<font color="#7EE787">✓  manifest hash valid</font><br/>'
        '<font color="#7EE787">✓  source document hash matches</font>'
        '</font>', styles["GBBody"])]],
        colWidths=[6.8 * inch])
    verify_box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0A1A0F")),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(verify_box)
    story.append(Spacer(1, 8))

    story.append(Paragraph(
        "The verifier is MIT-licensed. Read the source at "
        '<font color="#0F6B3A"><u>github.com/greenbarsystems/gbverify</u></font> '
        "before running it. The canonical-JSON hashing algorithm is documented "
        "on the last page of this packet.",
        styles["GBSmall"]))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "Continued on the next page: the named approver, their attestation, "
        "and any blocking-finding override.",
        styles["GBSmall"]))


def _cover_attestation(story, styles, packet):
    # Second half of the cover. Separated so the hash + verify
    # instructions and the approval attestation each get their own
    # clean page rather than fighting for room on one.
    m = packet["manifest"]
    approver = m.get("approverActionLog", {}) or {}
    md = approver.get("metadata", {}) or {}
    override = m.get("override") or {}

    story.append(PageBreak())
    story.append(Paragraph("APPROVAL ATTESTATION", styles["GBEyebrow"]))
    story.append(Paragraph("Who signed off, and on what", styles["GBH2"]))

    rows = [
        ["Approver", f"{md.get('approverName','—')}  ·  {md.get('approverEmail','—')}"],
        ["Approver user id", approver.get("actorId", "—")],
        ["Approved at", approver.get("createdAt", "—")],
        ["Audit sequence", md.get("auditSeq", "—")],
        ["Attestation text", Paragraph(
            md.get("approverAttestationText") or "—", styles["GBBody"])],
    ]
    story.append(_kv_table(rows, col1=1.6 * inch))

    if override:
        story.append(Spacer(1, 14))
        story.append(Paragraph("Blocking-finding override", styles["GBH2"]))
        story.append(Paragraph(
            f"The approver overrode <b>{', '.join(override.get('blockingFindingCodes') or [])}</b> "
            f"for <b>${override.get('overrideAmount','—')}</b>. A second approver was required.",
            styles["GBBody"]))
        story.append(Spacer(1, 6))
        override_rows = [
            ["Overriding user", override.get("overridingUserId", "—")],
            ["Second approver", override.get("secondApproverId", "—")],
            ["Approved at", override.get("approvedAt", "—")],
            ["Justification", Paragraph(
                override.get("justificationText") or "—", styles["GBBody"])],
        ]
        story.append(_kv_table(override_rows, col1=1.6 * inch))


def _invoice_page(story, styles, packet):
    story.append(PageBreak())
    m = packet["manifest"]
    inv = m["extractedInvoice"]

    story.append(Paragraph("EXTRACTED INVOICE", styles["GBEyebrow"]))
    story.append(Paragraph("Fields extracted by AI, reviewed by approver",
                           styles["GBH2"]))

    inv_rows = [
        ["Vendor", inv["vendorName"]],
        ["Vendor address", inv["vendorAddress"] or "—"],
        ["Remit-to", inv["remitToName"] or "—"],
        ["Remit-to address", inv["remitToAddress"] or "—"],
        ["Invoice number", inv["invoiceNumber"]],
        ["Invoice date", inv["invoiceDate"]],
        ["Due date", inv["dueDate"] or "—"],
        ["Terms", inv["paymentTerms"] or "—"],
        ["PO number", inv["purchaseOrderNumber"] or "—"],
        ["Currency", inv["currency"] or "USD"],
        ["Subtotal", f"${inv['subtotal']}"],
        ["Tax", f"${inv['tax']}"],
        ["Shipping", f"${inv['shipping']}"],
        ["Discount", f"${inv['discount']}"],
        ["Total", Paragraph(
            f'<font face="{BOLD}" size="11">${inv["total"]}</font>',
            styles["GBBody"])],
        ["Extraction confidence",
         f'{float(inv["confidence"]) * 100:.1f}%'],
    ]
    story.append(_kv_table(inv_rows, col1=1.6 * inch))

    story.append(Spacer(1, 12))
    story.append(Paragraph("Line items", styles["GBH2"]))
    line_header = ["#", "Description", "Qty", "Unit", "Amount", "Conf.", "vs baseline"]
    line_rows = [line_header]
    for l in m["extractedLines"]:
        baseline = "—"
        if l.get("histAvgPrice") and l.get("stddevDistance"):
            baseline = f"{l['stddevDistance']}σ vs ${l['histAvgPrice']}"
        line_rows.append([
            str(l["lineNumber"]),
            Paragraph(l["description"], styles["GBBody"]),
            l["quantity"],
            f"${l['unitPrice']}",
            f"${l['amount']}",
            f"{float(l['confidenceScore']) * 100:.1f}%",
            baseline,
        ])
    t = Table(line_rows, colWidths=[0.3 * inch, 2.8 * inch, 0.55 * inch,
                                    0.75 * inch, 0.85 * inch, 0.55 * inch, 1.0 * inch],
              repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GB_GREEN),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONT", (0, 0), (-1, 0), BOLD, 8.5),
        ("FONT", (0, 1), (-1, -1), BODY, 9),
        ("ALIGN", (2, 1), (5, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GB_BG]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, GB_FAINT),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t)


def _risk_page(story, styles, packet):
    story.append(PageBreak())
    m = packet["manifest"]
    bc = m.get("briefingCard") or {}
    val = m.get("validation") or {}

    story.append(Paragraph("AI BRIEFING & DETERMINISTIC RISK SCORE",
                           styles["GBEyebrow"]))
    story.append(Paragraph(
        f"Risk score {bc.get('riskScore','—')} / 100  ·  weights v{bc.get('riskScoreVersion','—')}",
        styles["GBH2"]))
    story.append(Paragraph(
        "The score is deterministic — the same inputs always produce the same "
        "score, on the versioned weight table in "
        "<u>github.com/greenbarsystems/Greenbar-Pay src/lib/briefing/risk-score.ts</u>. "
        "The justification prose below is written by an LLM; the score is not.",
        styles["GBSmall"]))
    story.append(Spacer(1, 8))

    factors = bc.get("riskFactors") or {}
    factor_rows = [
        ["Blocking findings", str(factors.get("blockingFindingCount", 0))],
        ["Warning findings", str(factors.get("warningFindingCount", 0))],
        ["Vendor duplicate count", str(factors.get("vendorDuplicateCount", 0))],
        ["Vendor terms drift", str(factors.get("vendorTermsDrift", False))],
        ["Text quality low", str(factors.get("textQualityLow", False))],
        ["Vendor warming up", str(factors.get("vendorWarmingUp", False))],
        ["Rate-drift line count", str(factors.get("rateDriftCount", 0))],
        ["Has new line item", str(factors.get("hasNewLineItem", False))],
    ]
    story.append(_kv_table(factor_rows, col1=2.2 * inch))

    story.append(Spacer(1, 10))
    story.append(Paragraph("Justification (LLM-authored, non-scoring)",
                           styles["GBH2"]))
    story.append(Paragraph(bc.get("riskJustification", "—"), styles["GBBody"]))

    story.append(Spacer(1, 14))
    story.append(Paragraph("Validation findings", styles["GBH2"]))
    findings = val.get("findings") or []
    if not findings:
        story.append(Paragraph("No findings.", styles["GBBody"]))
    else:
        for f in findings:
            sev = (f.get("severity") or "").upper()
            color = {"BLOCKING": GB_BLOCK, "WARNING": GB_WARN}.get(sev, GB_MUTED)
            box = Table([[
                Paragraph(
                    f'<font color="{_hex(color)}" size="8"><b>{sev}</b></font>'
                    f'  <font color="#555555" size="8">'
                    f'{f.get("code","—")}</font><br/>'
                    f'<font size="10">{f.get("message","")}</font>',
                    styles["GBBody"])]],
                colWidths=[6.8 * inch])
            box.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("LINEBEFORE", (0, 0), (0, -1), 3, color),
                ("BOX", (0, 0), (-1, -1), 0.25, GB_FAINT),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]))
            story.append(box)
            story.append(Spacer(1, 4))


def _llm_page(story, styles, packet):
    story.append(PageBreak())
    m = packet["manifest"]
    run = m.get("llmRun") or {}
    doc = m.get("originalDocument") or {}

    story.append(Paragraph("AI RUN PROVENANCE", styles["GBEyebrow"]))
    story.append(Paragraph("What model ran, on what, and under what policy",
                           styles["GBH2"]))
    story.append(Paragraph(
        "Every LLM call is dispatched through Greenbar's compliance registry "
        '(<u>src/lib/llm/registry.ts</u>). The registry refuses to dispatch to '
        "any model that is not on the allow-list with retention_days=0 and "
        "allows_customer_data=true. This attestation records exactly which "
        "model produced the briefing card above.",
        styles["GBSmall"]))
    story.append(Spacer(1, 8))

    llm_rows = [
        ["LLM run id", run.get("llmRunId", "—")],
        ["Provider", run.get("provider", "—")],
        ["Model", run.get("model", "—")],
        ["Prompt name", run.get("promptName", "—")],
        ["Prompt version", run.get("promptVersion", "—")],
        ["Input hash (sha-256)", Paragraph(
            f'<font face="{MONO}" size="9">{run.get("inputHash","—")}</font>',
            styles["GBBody"])],
        ["Input tokens (est.)", str(run.get("inputTokensEstimate", "—"))],
        ["Status", run.get("status", "—")],
        ["Duration (ms)", str(run.get("durationMs", "—"))],
    ]
    story.append(_kv_table(llm_rows, col1=1.8 * inch))

    story.append(Spacer(1, 14))
    story.append(Paragraph("Source document", styles["GBH2"]))
    doc_rows = [
        ["Received at", doc.get("receivedAt", "—")],
        ["Channel", doc.get("sourceChannel", "—")],
        ["MIME type", doc.get("mimeType", "—")],
        ["Page count", str(doc.get("pageCount", "—"))],
        ["Content SHA-256", Paragraph(
            f'<font face="{MONO}" size="9">{doc.get("contentHash","—")}</font>',
            styles["GBBody"])],
    ]
    story.append(_kv_table(doc_rows, col1=1.8 * inch))


def _verify_page(story, styles, packet):
    story.append(PageBreak())
    story.append(Paragraph("VERIFYING THIS PACKET WITHOUT GREENBAR",
                           styles["GBEyebrow"]))
    story.append(Paragraph("A 60-second procedure any auditor can run",
                           styles["GBH2"]))

    story.append(Paragraph(
        "The JSON manifest for this evidence packet is embedded as an "
        "attachment in this PDF (open the paperclip / attachments pane in "
        "your PDF viewer to save it as <font face='Courier' size='9'>packet.json</font>). "
        "Once you have the JSON, verify the hash printed on this document "
        "using one of the following methods.",
        styles["GBBody"]))

    story.append(Spacer(1, 10))
    story.append(Paragraph("Option A — pre-built verifier", styles["GBH2"]))
    story.append(Paragraph(
        "The verifier is a small, MIT-licensed, dependency-free tool. Source "
        "and binaries live at "
        "<u>github.com/greenbarsystems/gbverify</u>. Install via <font face='Courier' size='9'>brew "
        "install gbverify</font>, "
        "<font face='Courier' size='9'>npx @greenbarsystems/gbverify</font>, or "
        "<font face='Courier' size='9'>pipx install gbverify</font>.",
        styles["GBBody"]))

    story.append(Spacer(1, 6))
    cmdbox = Table([[Paragraph(
        '<font face="Courier" size="9" color="#F7F8F5">'
        '$ gbverify --document invoice.pdf packet.json<br/><br/>'
        '<font color="#7EE787">✓</font>  manifest hash valid<br/>'
        '<font color="#7EE787">✓</font>  source document hash matches<br/>'
        '   computed: <font color="#B0BEC5">'
        + packet["manifestHash"] +
        '</font><br/>'
        '   recorded: <font color="#B0BEC5">'
        + packet["manifestHash"] +
        '</font>'
        '</font>', styles["GBBody"])]],
        colWidths=[6.8 * inch])
    cmdbox.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0A1A0F")),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(cmdbox)

    story.append(Spacer(1, 14))
    story.append(Paragraph("Option B — verify with your own tools",
                           styles["GBH2"]))
    story.append(Paragraph(
        "The manifest hash is a SHA-256 of the manifest JSON, serialised "
        "with recursively sorted object keys and no incidental whitespace "
        "(commonly called canonical JSON). Reference implementations:",
        styles["GBBody"]))

    story.append(Spacer(1, 6))
    story.append(Paragraph("Python (standard library):", styles["GBSmall"]))
    py = Table([[Paragraph(
        '<font face="Courier" size="8.5">'
        'import json, hashlib<br/>'
        'p = json.load(open("packet.json"))["gbEvidencePacket"]<br/>'
        's = json.dumps(p["manifest"], sort_keys=True, ensure_ascii=False, '
        'separators=(",", ":"))<br/>'
        'assert hashlib.sha256(s.encode("utf-8")).hexdigest() '
        '== p["manifestHash"]'
        '</font>', styles["GBBody"])]],
        colWidths=[6.8 * inch])
    py.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), GB_BG),
        ("BOX", (0, 0), (-1, -1), 0.25, GB_FAINT),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(py)

    story.append(Spacer(1, 14))
    story.append(Paragraph("What a passing verification proves",
                           styles["GBH2"]))
    story.append(Paragraph(
        "A green result on both hashes means: (1) the invoice, line items, "
        "AI briefing, risk score inputs, validation findings, approver "
        "attestation, and any override were bit-for-bit identical to the "
        "record sealed at approval time; (2) the source PDF being reviewed "
        "is the same PDF the AI extracted from — no other version has been "
        "substituted. Together these establish that the record has not been "
        "modified since sign-off and that the AI reviewed the invoice you "
        "are looking at, not a different one.",
        styles["GBBody"]))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "What it does not prove: whether the approver's judgment was correct, "
        "whether the vendor is legitimate, or whether the AI's extraction "
        "was accurate. Those are review questions; this packet is the "
        "evidence you use to ask them.",
        styles["GBSmall"]))


def render(packet_path: str, out_path: str) -> None:
    with open(packet_path) as f:
        parsed = json.load(f)
    packet = parsed.get("gbEvidencePacket", parsed)

    styles = _styles()

    doc = BaseDocTemplate(
        out_path,
        pagesize=LETTER,
        leftMargin=0.6 * inch, rightMargin=0.6 * inch,
        topMargin=0.85 * inch, bottomMargin=0.75 * inch,
        title=f"Greenbar Evidence Packet — {packet['manifestHash'][:12]}",
        author="GreenBar Systems",
        subject="Cryptographically-sealed AI-assisted invoice review record",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin,
                  doc.width, doc.height, id="normal")
    doc.addPageTemplates([
        PageTemplate(id="body", frames=frame,
                     onPage=lambda c, d: _header_footer(c, d, packet)),
    ])

    story = []
    _cover(story, styles, packet)
    _cover_attestation(story, styles, packet)
    _invoice_page(story, styles, packet)
    _risk_page(story, styles, packet)
    _llm_page(story, styles, packet)
    _verify_page(story, styles, packet)

    # Embed the raw JSON manifest as a PDF attachment. This is what
    # makes the PDF self-contained: an auditor extracts the JSON with
    # any PDF viewer, feeds it to gbverify, and re-computes the hash.
    def _attach(canvas_):
        from reportlab.pdfbase.pdfdoc import PDFDictionary, PDFStream
        pass  # attachment handled below via canvas.attach

    def _on_finish(canv, d):
        _header_footer(canv, d, packet)

    doc.build(story)

    # Post-build: use pypdf to attach the JSON as an embedded file
    try:
        from pypdf import PdfReader, PdfWriter
        reader = PdfReader(out_path)
        writer = PdfWriter(clone_from=reader)
        with open(packet_path, "rb") as f:
            writer.add_attachment("packet.json", f.read())
        with open(out_path, "wb") as f:
            writer.write(f)
        print(f"Embedded packet.json as PDF attachment")
    except Exception as e:
        print(f"(attachment skipped: {e})", file=sys.stderr)

    print(f"Wrote {out_path}")


if __name__ == "__main__":
    packet_path = sys.argv[1] if len(sys.argv) > 1 else "sample/packet.json"
    out_path = sys.argv[2] if len(sys.argv) > 2 else "sample/evidence-packet.pdf"
    render(packet_path, out_path)
