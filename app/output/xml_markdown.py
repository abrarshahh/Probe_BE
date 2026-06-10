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

    # Symbols
    if context.symbols:
        lines.append("  <symbols>")
        for sym in context.symbols:
            attrs = (
                f'name="{sym.name}" kind="{sym.kind}" file="{sym.file_path}" '
                f'start_line="{sym.start_line}" end_line="{sym.end_line}"'
            )
            if sym.parent:
                attrs += f' parent="{sym.parent}"'
            if sym.signature:
                lines.append(f"    <symbol {attrs}>")
                lines.append(f"      <![CDATA[{sym.signature}]]>")
                lines.append("    </symbol>")
            else:
                lines.append(f"    <symbol {attrs} />")
        lines.append("  </symbols>")

    # Test mapping
    if context.test_mapping:
        lines.append("  <test_mapping>")
        for test_file, sources in context.test_mapping.items():
            lines.append(f'    <test_file path="{test_file}">')
            for src in sources:
                lines.append(f'      <tests path="{src}" />')
            lines.append("    </test_file>")
        lines.append("  </test_mapping>")
    
    lines.append("  <files>")
    for path, content in file_contents.items():
        lang = ""
        is_truncated = "false"
        file_imports: list[str] = []
        for f in context.files:
            if f.path == path:
                lang = f.language or ""
                file_imports = f.imports
                if f.status == "truncated":
                    is_truncated = "true"
                break
                
        lines.append(f'    <file path="{path}" language="{lang}" truncated="{is_truncated}">')
        if file_imports:
            lines.append("      <imports>")
            for imp in file_imports:
                lines.append(f"        <import><![CDATA[{imp}]]></import>")
            lines.append("      </imports>")
        lines.append(f"      <content><![CDATA[\n{content}\n      ]]></content>")
        lines.append("    </file>")
        
    lines.append("  </files>")
    lines.append("</project>")
    
    return "\n".join(lines)
