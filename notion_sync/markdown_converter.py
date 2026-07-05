import os
import re
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from notion_sync.logger import logger
from notion_sync.parser import parse_rich_text, parse_table
from notion_sync.utils import download_image

class MarkdownConverter:
    def __init__(self, images_dir: Path, download_images: bool = True):
        self.images_dir = images_dir
        self.download_images = download_images
        self.code_blocks_count = 0
        self.downloaded_images: List[str] = []

    async def convert(self, page_id: str, title: str, blocks: List[Dict[str, Any]], page_file_path: Path) -> Tuple[str, int, List[str]]:
        """
        Converts a list of Notion blocks (potentially nested) into a single Markdown string.
        Returns a tuple of (markdown_content, code_blocks_count, downloaded_images).
        """
        self.code_blocks_count = 0
        self.downloaded_images = []
        self.current_images_dir = page_file_path.parent / "images"
        
        # Start the document with the page title as an H1 header
        markdown_lines = [f"# {title}\n"]
        
        body_content = await self.render_blocks(blocks, indent_level=0)
        markdown_lines.append(body_content)
        
        return "".join(markdown_lines), self.code_blocks_count, self.downloaded_images

    async def render_blocks(self, blocks: List[Dict[str, Any]], indent_level: int) -> str:
        """
        Recursively renders list of blocks to Markdown.
        """
        result = []
        
        for block in blocks:
            block_type = block.get("type")
            if not block_type:
                continue
                
            block_content = block.get(block_type, {})
            
            # Format indentation spaces
            indent = "    " * indent_level
            
            # 1. Handle blocks that don't need sub-rendering or are handled uniquely
            if block_type == "table":
                # Tables are parsed together with their row children
                table_children = block.get("children", [])
                table_md = parse_table(block, table_children)
                result.append(f"\n{indent}{table_md}\n")
                continue
                
            if block_type == "table_row":
                # Table rows are processed by their parent table; skip if orphans
                continue
                
            # Parse rich text content if the block type has rich_text property
            rich_text = block_content.get("rich_text", [])
            text_md = parse_rich_text(rich_text)
            
            block_md = ""
            
            if block_type == "paragraph":
                block_md = f"{text_md}\n"
                
            elif block_type == "heading_1":
                block_md = f"\n# {text_md}\n"
                
            elif block_type == "heading_2":
                block_md = f"\n## {text_md}\n"
                
            elif block_type == "heading_3":
                block_md = f"\n### {text_md}\n"
                
            elif block_type == "bulleted_list_item":
                block_md = f"- {text_md}\n"
                
            elif block_type == "numbered_list_item":
                # Markdown handles auto-numbering, so we can use '1.' for simplicity
                block_md = f"1. {text_md}\n"
                
            elif block_type == "to_do":
                checked = block_content.get("checked", False)
                box = "[x]" if checked else "[ ]"
                block_md = f"- {box} {text_md}\n"
                
            elif block_type == "quote":
                block_md = f"> {text_md}\n"
                
            elif block_type == "callout":
                icon = block_content.get("icon")
                icon_str = ""
                if icon:
                    if icon.get("type") == "emoji":
                        icon_str = icon.get("emoji", "") + " "
                block_md = f"> {icon_str}{text_md}\n"
                
            elif block_type == "code":
                self.code_blocks_count += 1
                language = block_content.get("language", "").lower()
                # Notion defaults to 'plain text' which we can map to empty for markdown
                if language == "plain text":
                    language = ""
                block_md = f"\n```{language}\n{text_md}\n```\n"
                
            elif block_type == "divider":
                block_md = "---\n"
                
            elif block_type == "equation":
                expression = block_content.get("expression", "")
                block_md = f"\n$$\n{expression}\n$$\n"
                
            elif block_type == "bookmark":
                url = block_content.get("url", "")
                caption_list = block_content.get("caption", [])
                caption = parse_rich_text(caption_list)
                title_str = caption if caption else url
                block_md = f"[{title_str}]({url})\n"
                
            elif block_type == "image":
                img_type = block_content.get("type")
                img_url = block_content.get(img_type, {}).get("url", "") if img_type else ""
                caption_list = block_content.get("caption", [])
                caption = parse_rich_text(caption_list) or "Image"
                
                if img_url:
                    if self.download_images:
                        # Use block ID as prefix to avoid filename collisions
                        local_path = await download_image(img_url, self.current_images_dir, f"img_{block['id']}")
                        if local_path:
                            # Extract filename and compute path relative to the root notes directory
                            filename = local_path.split("/")[-1]
                            full_img_path = self.current_images_dir / filename
                            relative_img_path = str(full_img_path.relative_to(self.images_dir)).replace("\\", "/")
                            self.downloaded_images.append(relative_img_path)
                            block_md = f"\n![{caption}]({local_path})\n"
                        else:
                            block_md = f"\n![{caption}]({img_url})\n"
                    else:
                        block_md = f"\n![{caption}]({img_url})\n"
                else:
                    block_md = ""
                    
            elif block_type == "toggle":
                # We render toggle blocks using HTML details/summary
                block_md = f"<details>\n<summary>{text_md}</summary>\n"
                
            elif block_type in ("column_list", "column", "synced_block"):
                # Layout wrappers are transparent in Markdown
                block_md = ""
                
            elif block_type == "child_page":
                child_title = block_content.get("title", "Subpage")
                # When encountering a child page block, we can render a relative link to it
                # We sanitize its title to match the filename convention
                from notion_sync.utils import sanitize_filename
                safe_name = sanitize_filename(child_title)
                block_md = f"\n[{child_title}](./{safe_name}.md)\n"
                
            else:
                # Unsupported blocks are output as comments or skipped
                logger.debug(f"Skipping unsupported block type: {block_type}")
                block_md = ""
                
            # Process children if they exist
            children = block.get("children", [])
            
            if children:
                if block_type in ("bulleted_list_item", "numbered_list_item", "to_do"):
                    # List items require children to be indented further
                    child_content = await self.render_blocks(children, indent_level + 1)
                    block_md = f"{indent}{block_md}{child_content}"
                elif block_type in ("quote", "callout"):
                    # Quotes/Callouts should wrap their children inside the blockquote indicator (>)
                    child_content = await self.render_blocks(children, indent_level)
                    # Prepend '> ' to all non-empty lines in child content
                    quoted_lines = []
                    for line in child_content.splitlines():
                        if line.strip():
                            quoted_lines.append(f"> {line}")
                        else:
                            quoted_lines.append(">")
                    quoted_child_md = "\n".join(quoted_lines) + "\n"
                    block_md = f"{indent}{block_md}{quoted_child_md}"
                elif block_type == "toggle":
                    # Toggle details need to wrap their children and close tags
                    child_content = await self.render_blocks(children, indent_level)
                    block_md = f"{indent}{block_md}\n{child_content}\n</details>\n"
                else:
                    # Generic children are rendered with same indentation level
                    child_content = await self.render_blocks(children, indent_level)
                    block_md = f"{indent}{block_md}\n{child_content}"
            else:
                # If toggle block has no children, we still need to close it
                if block_type == "toggle":
                    block_md = f"{indent}{block_md}\n</details>\n"
                else:
                    block_md = f"{indent}{block_md}"
                    
            result.append(block_md)
            
        return "".join(result)
