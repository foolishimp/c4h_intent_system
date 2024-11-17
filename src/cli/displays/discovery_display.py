# src/cli/displays/discovery_display.py
"""Discovery data display handler."""
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from rich.tree import Tree
from pathlib import Path
from typing import Dict, Any, Optional
import structlog

from src.cli.displays.base_display import BaseDisplay

logger = structlog.get_logger()

class DiscoveryDisplay(BaseDisplay):
    """Handles display of discovery results"""

    def display_data(self, data: Dict[str, Any]) -> None:
        """Display discovery stage data"""
        try:
            # Show overall summary first
            self._show_summary(data)
            
            # Show files table
            self._show_files_table(data.get('files', {}))
            
            # Show detailed file contents - this was missing/broken
            if 'discovery_output' in data:
                self._show_file_contents(data['discovery_output'])
            else:
                logger.warning("discovery.no_content", reason="discovery_output missing from data")

        except Exception as e:
            logger.error("discovery_display.error", error=str(e))
            self.show_error(f"Error displaying discovery data: {str(e)}")

    def _show_summary(self, data: Dict[str, Any]) -> None:
        """Show discovery summary"""
        summary = Table(show_header=False, box=None)
        summary.add_row("[bold cyan]Project Path:[/]", str(data.get('project_path', 'Not specified')))
        summary.add_row("[bold cyan]Files Found:[/]", str(len(data.get('files', {}))))
        summary.add_row("[bold cyan]Analysis Time:[/]", data.get('timestamp', 'Unknown'))
        
        self.console.print(Panel(
            summary,
            title="Discovery Summary",
            border_style="blue"
        ))

    def _show_files_table(self, files: Dict[str, Any]) -> None:
        """Display discovered files table with details"""
        if not files:
            self.console.print("[yellow]No files discovered[/]")
            return

        table = Table(title="Discovered Files")
        table.add_column("File Path", style="cyan")
        table.add_column("Type", style="green")
        table.add_column("Size", style="yellow")
        table.add_column("Status", style="blue")
        
        for file_path in sorted(files.keys()):
            path = Path(file_path)
            file_type = self._get_file_type(path)
            size = path.stat().st_size if path.exists() else 0
            
            table.add_row(
                str(path),
                file_type,
                f"{size:,} bytes",
                "✓ Analyzed"
            )

        self.console.print(table)

    def _show_file_contents(self, discovery_output: str) -> None:
        """Display detailed discovery output with syntax highlighting"""
        if not discovery_output:
            return

        self.console.print("\n[bold cyan]Detailed Analysis:[/]")
        
        # Split output into sections by file
        sections = discovery_output.split("== Start of File ==")
        for section in sections[1:]:  # Skip the first empty section
            try:
                lines = section.strip().split('\n')
                file_info = {}
                content_started = False
                content_lines = []
                
                # Parse section
                for line in lines:
                    if line.startswith("File:"):
                        file_info['path'] = line.split("File:", 1)[1].strip()
                    elif line.startswith("File Type:"):
                        file_info['type'] = line.split("File Type:", 1)[1].strip()
                    elif line.startswith("Size:"):
                        file_info['size'] = line.split("Size:", 1)[1].strip()
                    elif line.startswith("Last Modified:"):
                        file_info['modified'] = line.split("Last Modified:", 1)[1].strip()
                    elif line == "Contents:":
                        content_started = True
                    elif content_started and line != "== End of File ==":
                        content_lines.append(line)

                # Show file info
                if file_info:
                    info_table = Table(show_header=False, box=None)
                    info_table.add_row("[bold]Path:[/]", file_info.get('path', 'Unknown'))
                    info_table.add_row("[bold]Type:[/]", file_info.get('type', 'Unknown'))
                    info_table.add_row("[bold]Size:[/]", file_info.get('size', 'Unknown'))
                    info_table.add_row("[bold]Modified:[/]", file_info.get('modified', 'Unknown'))
                    
                    self.console.print(Panel(
                        info_table,
                        title="File Information",
                        border_style="blue"
                    ))

                    # Show content with syntax highlighting if it's a text file
                    if content_lines and not any(skip in file_info.get('type', '').lower() 
                                               for skip in ['binary', 'image', 'octet-stream']):
                        content = '\n'.join(content_lines)
                        self.console.print(Syntax(
                            content,
                            self._get_syntax_type(file_info.get('type', '')),
                            theme="monokai",
                            line_numbers=True,
                            word_wrap=True
                        ))
                    
                    self.console.print("\n" + "─" * 80 + "\n")  # Section separator

            except Exception as e:
                logger.error("file_content_display.error", 
                           file=file_info.get('path', 'Unknown'),
                           error=str(e))
                self.show_error(f"Error displaying file content: {str(e)}")

    def _get_file_type(self, path: Path) -> str:
        """Get friendly file type name"""
        suffix = path.suffix.lower()
        return {
            '.py': 'Python Source',
            '.java': 'Java Source',
            '.js': 'JavaScript',
            '.html': 'HTML',
            '.css': 'CSS',
            '.md': 'Markdown',
            '.txt': 'Text',
            '.yml': 'YAML',
            '.yaml': 'YAML',
            '.json': 'JSON'
        }.get(suffix, suffix[1:].upper() if suffix else 'Unknown')

    def _get_syntax_type(self, file_type: str) -> str:
        """Map file type to syntax highlighting type"""
        return {
            'python': 'python',
            'java': 'java',
            'javascript': 'javascript',
            'html': 'html',
            'css': 'css',
            'markdown': 'markdown',
            'text': 'text',
            'json': 'json',
            'yaml': 'yaml'
        }.get(file_type.lower().split('/')[-1], 'text')