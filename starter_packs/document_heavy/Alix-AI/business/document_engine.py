import os
import re
import subprocess
import json
import logging
from docxtpl import DocxTemplate
from docx import Document
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

logger = logging.getLogger(__name__)

# A literal {{ ... }} surviving in rendered output is a real, well-known
# docxtpl failure signature -- Jinja tags Word has split across separate XML
# runs (e.g. from autocorrect/formatting) go unrecognized by docxtpl and pass
# through untouched, so the field silently never gets filled even though
# render() reported no error. Anything matching this after render means the
# document is broken, not just "rendered" -- flag it rather than reporting
# a plain success.
_UNRENDERED_TAG_RE = re.compile(r"\{\{.*?\}\}")

class DocumentEngine:
    """
    Advanced Document Engine for Alix-AI.
    Renders Jinja2 templates inside Word .docx files, handles context validation,
    adds dynamic Table of Contents (TOC), and optionally converts output to PDF.
    """
    def __init__(self, template_path):
        self.template_path = os.path.abspath(template_path)
        if not os.path.exists(self.template_path):
            raise FileNotFoundError(f"Template document not found: {self.template_path}")

    def _add_toc(self, paragraph):
        """Injects Word TOC field XML elements into a paragraph."""
        run = paragraph.add_run()
        fldChar = OxmlElement('w:fldChar')
        fldChar.set(qn('w:fldCharType'), 'begin')
        instrText = OxmlElement('w:instrText')
        instrText.set(qn('xml:space'), 'preserve')
        instrText.text = 'TOC \\o "1-3" \\h \\z \\u'
        fldChar2 = OxmlElement('w:fldChar')
        fldChar2.set(qn('w:fldCharType'), 'separate')
        fldChar3 = OxmlElement('w:fldChar')
        fldChar3.set(qn('w:fldCharType'), 'end')
        run._r.append(fldChar)
        run._r.append(instrText)
        run._r.append(fldChar2)
        run._r.append(fldChar3)

    def _force_update_toc(self, doc):
        """Forces Word to update fields (including TOC) upon next document open."""
        element = doc.settings.element.find(qn('w:updateFields'))
        if element is None:
            element = OxmlElement('w:updateFields')
            element.set(qn('w:val'), 'true')
            doc.settings.element.insert(0, element)

    def validate_context(self, context, required_fields=None):
        """
        Validates context data dictionary against required fields.
        Fills missing fields with formatted placeholders.
        Returns (validated_context, missing_fields) -- the caller needs to
        know WHICH fields were left as placeholders, not just get a document
        that quietly contains them.
        """
        validated = dict(context or {})
        missing = []
        if required_fields:
            for field in required_fields:
                if field not in validated or validated[field] is None or validated[field] == "":
                    missing.append(field)
                    # Human-friendly missing placeholder
                    display_name = field.replace('_', ' ').title()
                    validated[field] = f"[{display_name} Required]"
        return validated, missing

    def _check_rendered_output(self, output_path):
        """Deterministic post-render sanity check -- catches a document that
        rendered without error but is still actually broken, rather than
        trusting that "no exception" means "correct." Returns a dict with
        `structural_error` (None if the file reopens cleanly) and
        `unrendered_tags` (any literal {{ }} text still present -- a real
        docxtpl failure signature, not a false positive)."""
        issues = {"structural_error": None, "unrendered_tags": []}
        try:
            doc = Document(output_path)
        except Exception as e:
            issues["structural_error"] = str(e)
            return issues

        texts = [p.text for p in doc.paragraphs]
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    texts.extend(p.text for p in cell.paragraphs)
        for section in doc.sections:
            for part in (section.header, section.footer):
                texts.extend(p.text for p in part.paragraphs)

        for text in texts:
            for match in _UNRENDERED_TAG_RE.findall(text):
                issues["unrendered_tags"].append(match)
        return issues

    def generate(self, context, output_path, include_toc=False, convert_to_pdf=False, required_fields=None):
        """
        Renders template with context, saves to output_path (.docx),
        optionally inserts TOC, and optionally renders PDF.
        Returns a dict with paths to generated files.
        """
        output_path = os.path.abspath(output_path)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # 1. Context validation
        validated_context, missing_fields = self.validate_context(context, required_fields=required_fields)

        # 2. Render Jinja2 Docx template
        doc_tpl = DocxTemplate(self.template_path)
        doc_tpl.render(validated_context)
        doc_tpl.save(output_path)

        # 3. Handle TOC insertion if requested
        if include_toc:
            doc = Document(output_path)
            if len(doc.paragraphs) > 0:
                new_para = doc.paragraphs[0].insert_paragraph_before('Table of Contents')
                new_para.style = 'Heading 1'
                toc_para = doc.paragraphs[1].insert_paragraph_before('')
                self._add_toc(toc_para)
                doc.paragraphs[2].insert_paragraph_before('').add_run().add_break()
                self._force_update_toc(doc)
                doc.save(output_path)

        # 4. Post-render validation -- on the FINAL saved file (after TOC),
        # not the pre-TOC intermediate, so it reflects what actually ships.
        issues = self._check_rendered_output(output_path)
        issues["missing_fields"] = missing_fields

        has_issues = bool(issues["structural_error"] or issues["unrendered_tags"] or issues["missing_fields"])
        results = {
            "docx_path": output_path,
            "pdf_path": None,
            "status": "issues_found" if has_issues else "success",
            "issues": issues,
        }

        # 5. Optional PDF Conversion via LibreOffice
        if convert_to_pdf:
            pdf_path = self.convert_to_pdf(output_path)
            results["pdf_path"] = pdf_path

        return results

    def convert_to_pdf(self, docx_path):
        """Converts a .docx file to .pdf using LibreOffice soffice CLI."""
        docx_path = os.path.abspath(docx_path)
        output_dir = os.path.dirname(docx_path)
        base_name = os.path.splitext(os.path.basename(docx_path))[0]
        expected_pdf = os.path.join(output_dir, f"{base_name}.pdf")

        try:
            cmd = ["soffice", "--headless", "--convert-to", "pdf", docx_path, "--outdir", output_dir]
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if os.path.exists(expected_pdf):
                return expected_pdf
        except Exception as e:
            logger.warning(f"LibreOffice PDF conversion failed: {e}")

        return None
