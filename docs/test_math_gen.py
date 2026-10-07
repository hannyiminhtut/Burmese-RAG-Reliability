import docx
from docx.oxml import parse_xml

doc = docx.Document()
p = doc.add_paragraph("Testing equation:")
xml_str = (
    '<m:oMathPara xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">'
    '<m:oMath>'
    '<m:r><m:t>Hit@k = </m:t></m:r>'
    '<m:f>'
    '<m:num><m:r><m:t>1</m:t></m:r></m:num>'
    '<m:den><m:r><m:t>N</m:t></m:r></m:den>'
    '</m:f>'
    '</m:oMath>'
    '</m:oMathPara>'
)
p._p.append(parse_xml(xml_str))
doc.save("docs/test_math.docx")
print("Saved test_math.docx successfully!")
