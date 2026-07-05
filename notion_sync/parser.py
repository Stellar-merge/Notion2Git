import re
from typing import Dict, Any, List
from notion_sync.logger import logger

def parse_rich_text(rich_text_list: List[Dict[str, Any]]) -> str:
    """
    Parses a Notion rich_text list and returns standard Markdown string.
    Supports bold, italic, strikethrough, underline, inline code, inline equations, and links.
    """
    if not rich_text_list:
        return ""
        
    parts = []
    for item in rich_text_list:
        text_type = item.get("type")
        plain_text = item.get("plain_text", "")
        
        if text_type == "text":
            text_content = item.get("text", {}).get("content", "")
            link = item.get("text", {}).get("link")
            url = link.get("url") if link else None
        elif text_type == "equation":
            # Inline equation
            expr = item.get("equation", {}).get("expression", "")
            parts.append(f"${expr}$")
            continue
        elif text_type == "mention":
            text_content = plain_text
            url = item.get("href")
        else:
            text_content = plain_text
            url = None

        # Apply inline formatting annotations
        annotations = item.get("annotations", {})
        if annotations:
            # If code annotation is true, standard markdown inline code (backticks)
            # Annotations inside code blocks are ignored
            if annotations.get("code"):
                text_content = f"`{text_content}`"
            else:
                if annotations.get("bold"):
                    text_content = f"**{text_content}**"
                if annotations.get("italic"):
                    text_content = f"*{text_content}*"
                if annotations.get("strikethrough"):
                    text_content = f"~~{text_content}~~"
                if annotations.get("underline"):
                    text_content = f"<u>{text_content}</u>"

        # Apply hyperlink
        if url and not annotations.get("code"):
            # Avoid markdown links if text content is already empty or whitespace
            if text_content.strip():
                text_content = f"[{text_content}]({url})"
            else:
                text_content = url
                
        parts.append(text_content)
        
    return "".join(parts)

def parse_table(table_block: Dict[str, Any], children: List[Dict[str, Any]]) -> str:
    """
    Parses a Notion table block and its row children to return a Markdown table.
    """
    if not children:
        return ""
        
    has_header = table_block.get("table", {}).get("has_column_header", False)
    rows = []
    
    for child in children:
        if child.get("type") == "table_row":
            row_cells = child.get("table_row", {}).get("cells", [])
            parsed_cells = [parse_rich_text(cell).replace("|", "\\|") for cell in row_cells]
            rows.append(parsed_cells)
            
    if not rows:
        return ""
        
    # Markdown requires at least one header row. If has_header is False or the table lacks rows,
    # we treat the first row as header or generate a generic header
    header_row = rows[0]
    data_rows = rows[1:] if len(rows) > 1 else []
    
    if not has_header:
        # Generate generic header and put the first row in data rows
        header_row = [f"Col {i+1}" for i in range(len(rows[0]))]
        data_rows = rows
        
    # Build rows
    markdown_lines = []
    markdown_lines.append("| " + " | ".join(header_row) + " |")
    markdown_lines.append("| " + " | ".join(["---"] * len(header_row)) + " |")
    
    for row in data_rows:
        # Ensure row cell count matches header cell count
        if len(row) < len(header_row):
            row.extend([""] * (len(header_row) - len(row)))
        elif len(row) > len(header_row):
            row = row[:len(header_row)]
        markdown_lines.append("| " + " | ".join(row) + " |")
        
    return "\n".join(markdown_lines)
