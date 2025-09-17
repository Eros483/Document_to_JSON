import json
import re
import sys
import argparse
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import pdfplumber
import pandas as pd
from PIL import Image
import camelot

class PDFParser:
    """
    Handles content extraction, and semantic structures
    """
    def __init__(self, pdf_path: str):
        """
        Initialises PDF parsing class
        
        Args:
            pdf_path: Path of the pdf to be analyzed
        """
        self.pdf_path=Path(pdf_path)
        if not self.pdf_path.exists():
            raise FileNotFoundError(f"PDF File not found {pdf_path}")
        
        self.pages_data=[]
        self.current_section=None
        self.current_sub_section=None

    def _extract_paragraphs(self, text: str, page_num: int)->List[Dict[str, Any]]:
        """
        Extracts and structures parapgraphs as per provided text.
        - individual line extraction.
        - paragraph detection.
        - heading detection.

        Relies on helper function:
        - `_detect_section`
        - `_is_heading`
        - `_update_sections`

        Args:
            text: Content on a particular page.
            page_num: Page number of page being processed.
        
        Returns:
            List: Dictionaries containing parapgraphs and relevant content.
        """
        paragraphs=[]

        lines=text.split('\n') #individual lines
        current_paragraph=[]

        for line in lines:
            line=line.strip()
            if not line:
                if current_paragraph:
                    paragraph_text=' '.join(current_paragraph)
                    if paragraph_text:
                        section, sub_section=self._detect_section(paragraph_text)
                        paragraphs.append({
                            "type":"paragraph",
                            "section": section,
                            "sub_section": sub_section,
                            "text": paragraph_text
                        })
                    current_paragraph=[]
                continue
            
            if self._is_heading(line):
                if current_paragraph:
                    paragraph_text=" ".join(current_paragraph)
                    if paragraph_text:
                        section, sub_section=self._detect_section(paragraph_text)
                        paragraphs.append({
                            "type": "paragraph",
                            "section": section,
                            "text": paragraph_text
                        })
                    current_paragraph=[]

                self._update_sections(line)
            else:
                current_paragraph.append(line)
        
        if current_paragraph:
            paragraph_text=" ".join(current_paragraph)
            if paragraph_text:
                section, sub_section=self._detect_section(paragraph_text)
                paragraphs.append({
                    "type": "paragraph",
                    "section": section,
                    "sub_section": sub_section,
                    "text": paragraph_text
                })
        
        return paragraphs
    
    def _extract_tables_pdfplumber(self, page, page_num:int)->List[Dict[str, Any]]:
        """
        Extracts tables using pdfplumber.

        Args:
            page: Content in provided page.
            page_num: page number of provided page.
        
        Returns:
            list: dictionaries containing labelled tables and content
        """
        tables=[]

        try:
            page_tables=page.extract_tables()
            for i, table in enumerate(page_tables):
                if table and len(table)>0:
                    cleaned_table=[]
                    for row in table:
                        cleaned_row=[cell.strip() if cell else "" for cell in row]
                        if any(cleaned_row):
                            cleaned_table.append(cleaned_row)
                    
                    if cleaned_table:
                        tables.append({
                            "type":"table",
                            "section":self.current_section,
                            "sub_section":self.current_sub_section,
                            "description": f"table {i+1} from page {page_num}",
                            "table_data": cleaned_table
                        })
        
        except Exception as e:
            raise
        
        return tables
    
    def _extract_tables_with_camelot(self):
        """
        Utilises camelot as a fallback for extracting tables.
        """
        try:
            tables=camelot.read_pdf(str(self.pdf_path), pages='all')

            for i, table in enumerate(tables):
                df=table.df
                if not df.empty:
                    table_data=[df.columns.tolist()]+df.values.tolist()

                    page_num=table.page

                    #appending while maintaining order of pages
                    if page_num<=len(self.pages_data):
                        existing_tables=[
                            content for content in self.pages_data[page_num-1]["content"]
                            if content["type"]=="table"
                        ]

                        #implies no existing table found
                        if len(existing_tables)<=i:
                            self.pages_data[page_num-1]["content"].append({
                                "type":"table",
                                "section":self.current_section,
                                "sub_section":self.current_sub_section,
                                "description": f"extracted table from page {page_num}",
                                "table_data":table_data
                            })
        
        except Exception as e:
            raise
    
    def _detect_charts(self, page, page_num:int)->List[Dict[str, Any]]:
        """
        Detect, Extract and Return Chart information using basic chart properties, via detecting images.

        Args:
            page: content from which chart is to be detected.
            page_num: page number of provided page.

        Returns:
            list: Dictionary containing chart metadata and content.
        """
        charts=[]

        try:
            if hasattr(page, 'images') and page.images:
                for i, img in enumerate(page.images):
                    if img.get('width', 0)>100 and img.get('height', 0)>100:
                        charts.append({
                            "type": "chart",
                            "section": self.current_section,
                            "sub_section": self.current_sub_section,
                            "description": f"Chart/Image {i+1} detected on page {page_num}",
                            "image_info":{
                                "width": img.get("width"),
                                "height": img.get('height'),
                                "x0": img.get('x0'),
                                "y0": img.get('y0')
                            }
                        })
        
        except Exception as e:
            raise
        
        return charts
    
    def _is_heading(self, line: str)->bool:
        """
        Utilises regex to determine if a line is a heading.

        Args:
            line: Text to be classified as a heading
        
        Returns:
            bool: Whether the line is a heading or not
        """
        heading_patterns = [
            r'^[A-Z][A-Z\s]+$',  #all capitals
            r'^\d+\.?\s+[A-Z]',   #section numbers
            r'^[A-Z][^.]*:$',     #colon based enclosures
            r'^\s*[A-Z][a-z]+\s+[A-Z]',  #popular default title case 
        ]

        for pattern in heading_patterns:
            if re.match(pattern, line.strip()):
                return True

        return False

    def _update_sections(self, line:str):
        """
        Updates sections in the parent dictionary contained in `self`.

        Args:
            line: Classified line as per previous helpers.
        """
        line=line.strip()

        #regex-based heuristics to determine section or subsection
        if re.match(r'^\d+\.?\s+', line):
            self.current_section=line
            self.current_sub_section=None
        
        elif self.current_section:
            #if section found inside a section, likely to be a subsection
            self.current_sub_section=line
        
        else:
            self.current_section=line
    
    def _detect_section(self, text: str)->Tuple[Optional[str], Optional[str]]:
        """
        Retrieves stored section and subsection.
        """
        return self.current_section, self.current_sub_section
    
    def save_to_json(self, output_path: str, data: Dict[str, Any]):
        """
        Saves extracted data as a json file.

        Args:
            output_path: Storage point for file
            data: extracted content
        """
        try:
            output_file=Path(output_path)
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
        except Exception as e:
            raise

    def _process_page(self, page, page_num: int)->Dict[str, Any]:
        """
        Helper function to extract content from a single page.

        Relies on additional helper functions:
        - `_extract_paragraphs`
        - `_extract_tables_pdfplumber`
        - `_detect_charts`

        To ensure complete information extraction.
        """
        page_content={
            "page_number":page_num,
            "content":[]
        }

        #text extraction
        text=page.extract_text()
        if text:
            paragraphs=self._extract_paragraphs(text, page_num)
            page_content["content"].extend(paragraphs)
        
        #table extraction
        tables=self._extract_tables_pdfplumber(page, page_num)
        page_content["content"].extend(tables)

        #chart detection
        charts=self._detect_charts(page, page_num)
        page_content["content"].extend(charts)

        return page_content
    
    def parse_pdf(self)->Dict[str, Any]:
        """
        Function to extract content and return page data.
        - Utilises pre-defined helper `_process_page` for primary content extraction.
        - Utilises pre-defined helper `_extract_tables_with_camelot` for table extraction.

        Returns:
            Dict: Page and page data.
        """
        try:
            with pdfplumber.open(self.pdf_path) as pdf:
                for page_num, page in enumerate(pdf.pages, 1):
                    page_content=self._process_page(page, page_num)
                    self.pages_data.append(page_content)
            
            self._extract_tables_with_camelot()
            return {"pages": self.pages_data}

        except Exception as e:
            raise

def main():
    """
    Testing function for PDF parser.
    """
    parser = argparse.ArgumentParser(description='Parse PDF and extract structured content to JSON')
    parser.add_argument('input_pdf', help='Path to input PDF file')
    parser.add_argument('-o', '--output', help='Output JSON file path', 
                       default='extracted_content.json')
    
    args=parser.parse_args()

    try:
        pdf_parser=PDFParser(args.input_pdf)
        extracted_data=pdf_parser.parse_pdf()
        pdf_parser.save_to_json(args.output, extracted_data)
        print("Processing done, check local dir")
    
    except Exception as e:
        raise

if __name__=="__main__":
    main()