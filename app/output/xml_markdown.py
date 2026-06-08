"""
XML-Markdown hybrid output formatter.

Renders the context bundle as an XML document with CDATA-wrapped
code blocks — optimized for structured LLM prompts.
"""

from __future__ import annotations

from app.models.internal import ProjectContext


def render_xml_markdown(context: ProjectContext, summary: str, file_contents: dict[str, str]) -> str:
    """
    Render a ProjectContext and summary as an XML-Markdown hybrid string.

    Args:
        context: The aggregated project context.
        summary: The LLM-generated summary.
        file_contents: Mapping of relative path -> file content.

    Returns:
        A complete XML document.
    """
    lines: list[str] = []
    lines.append("<project>")
    lines.append(f"  <name>{context.name}</name>")
    
    lines.append("  <ai_summary>")
    lines.append(f"    <![CDATA[\n{summary}\n    ]]>")
    lines.append("  </ai_summary>")
    
    lines.append("  <structural_map>")
    lines.append("    <directory_tree>")
    lines.append(f"      <![CDATA[\n{context.directory_tree}\n      ]]>")
    lines.append("    </directory_tree>")
    lines.append("  </structural_map>")
    
    lines.append("  <files>")
    for path, content in file_contents.items():
        lang = ""
        is_truncated = "false"
        for f in context.files:
            if f.path == path:
                lang = f.language or ""
                if f.status == "truncated":
                    is_truncated = "true"
                break
                
        lines.append(f'    <file path="{path}" language="{lang}" truncated="{is_truncated}">')
        lines.append(f"      <![CDATA[\n{content}\n      ]]>")
        lines.append("    </file>")
        
    lines.append("  </files>")
    lines.append("</project>")
    
    return "\n".join(lines)
