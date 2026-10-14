import zipfile
import xml.etree.ElementTree as ET
import os

with zipfile.ZipFile('revive1.docx') as z:
    rels_xml = z.read('word/_rels/document.xml.rels')
    root = ET.fromstring(rels_xml)
    rel_map = {elem.attrib.get('Id'): elem.attrib.get('Target') for elem in root}

    doc_xml = z.read('word/document.xml')
    doc_tree = ET.fromstring(doc_xml)
    for p in doc_tree.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p'):
        text = ''.join(p.itertext()).strip()
        blips = p.findall('.//{http://schemas.openxmlformats.org/drawingml/2006/main}blip')
        if blips:
            for b in blips:
                r_id = b.attrib.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed')
                print(f'Text: "{text[:50]}" -> Image: {rel_map.get(r_id)}')

print("\n--- Media in review 2.docx ---")
with zipfile.ZipFile('review 2.docx') as z:
    rels_xml = z.read('word/_rels/document.xml.rels')
    root = ET.fromstring(rels_xml)
    rel_map = {elem.attrib.get('Id'): elem.attrib.get('Target') for elem in root}

    doc_xml = z.read('word/document.xml')
    doc_tree = ET.fromstring(doc_xml)
    for p in doc_tree.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p'):
        text = ''.join(p.itertext()).strip()
        blips = p.findall('.//{http://schemas.openxmlformats.org/drawingml/2006/main}blip')
        if blips:
            for b in blips:
                r_id = b.attrib.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed')
                print(f'Text: "{text[:50]}" -> Image: {rel_map.get(r_id)}')
