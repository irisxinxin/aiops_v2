#!/usr/bin/env python3
import re

def add_spacing_to_text(text):
    """Add spaces between concatenated words in text"""
    # Add space before capital letters that follow lowercase letters
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
    # Add space before numbers that follow letters
    text = re.sub(r'([a-zA-Z])(\d)', r'\1 \2', text)
    # Add space after numbers that are followed by letters
    text = re.sub(r'(\d)([a-zA-Z])', r'\1 \2', text)
    return text

# Test
test_text = "Confirmedcatastrophicmonitoringinfrastructurefailure-Thisidenticalalerthasbeenanalyzed42+timeswith100%consistencyshowing7-8%actualCPUusageversusclaimed92%"
print("Original:", test_text)
print("Fixed:", add_spacing_to_text(test_text))
