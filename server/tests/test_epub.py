import os
import pytest
from services.epub.parser import parse_epub, clean_html_to_text, extract_chapter_title

def test_clean_html_to_text():
    html = "<html><body><h1>Title</h1><p>Paragraph 1</p><p>Paragraph 2</p></body></html>"
    text = clean_html_to_text(html)
    assert "Title" in text
    assert "Paragraph 1" in text
    assert "Paragraph 2" in text
    assert "\n\n" in text

def test_extract_chapter_title():
    html_h1 = "<html><body><h1>Chapter One</h1></body></html>"
    assert extract_chapter_title(html_h1, 1) == "Chapter One"
    
    html_h2 = "<html><body><h2>The Beginning</h2></body></html>"
    assert extract_chapter_title(html_h2, 2) == "The Beginning"
    
    html_none = "<html><body><p>No header here</p></body></html>"
    assert extract_chapter_title(html_none, 3) == "Chapter 3"

# Note: Testing parse_epub would require a mock .epub file. 
# We can skip the full file parse test for now or create a minimal epub if needed.
