#!/usr/bin/env python3
"""
Dragon Agent — Cross-platform AI agent (Windows + Linux)
Manus-like: browses web, writes code, runs commands, produces results

Usage:
  python3 dragon_agent.py "Research Bitcoin price and create a report"
  python3 dragon_agent.py --config config.yaml "Build a trading dashboard"
"""

import json
import yaml
import os
import sys
import time
import subprocess
import re
import platform
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

# === Cross-platform imports ===
IS_WINDOWS = platform.system() == "Windows"

try:
    from openai import OpenAI
except ImportError:
    print("📦 Installing openai...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "openai", "pyyaml", "-q"])
    from openai import OpenAI

# === TOOL IMPORTS ===
try:
    import requests
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
    import requests

try:
    import httpx
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "httpx", "-q"])
    import httpx


# =====================================================================
# CONFIG
# =====================================================================

DEFAULT_CONFIG = """
agent:
  name: "Dragon Agent"
  version: "1.0.0"

model:
  provider: "deepseek"
  model: "deepseek-chat"
  temperature: 0.7
  max_tokens: 4096

tools:
  enabled: ["terminal", "filesystem", "search", "code"]

execution:
  max_iterations: 50
  timeout_minutes: 30
"""

def load_config(path=None):
    if path and Path(path).exists():
        with open(path) as f:
            return yaml.safe_load(f)
    return yaml.safe_load(DEFAULT_CONFIG)


# =====================================================================
# TOOL: Web Search
# =====================================================================

class WebSearch:
    def search(self, query, max_results=5):
        """Search the web via scraping or API."""
        try:
            # Scrape DuckDuckGo HTML results directly
            r = requests.get(
                f"https://html.duckduckgo.com/html/?q={requests.utils.quote(query)}",
                headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"},
                timeout=15
            )
            if r.status_code == 200:
                # Extract result links and snippets
                import re
                results = []
                # Find result blocks: <a rel="nofollow" class="result__a" href="...">TITLE</a>
                # and <a class="result__snippet" ...>SNIPPET</a>
                links = re.findall(r'class="result__a"[^>]*href="([^"]+)"[^>]*>([^<]+)</a>', r.text)
                snippets = re.findall(r'class="result__snippet"[^>]*>([^<]+)</a>', r.text)
                
                for i, (url, title) in enumerate(links[:max_results]):
                    snippet = snippets[i] if i < len(snippets) else ""
                    # Clean HTML entities
                    title = re.sub(r'<[^>]+>', '', title).strip()
                    snippet = re.sub(r'<[^>]+>', '', snippet).strip()
                    results.append({
                        "title": title,
                        "snippet": snippet[:300],
                        "url": url
                    })
                
                if results:
                    return results
                
                # Fallback: just return raw text
                text = re.sub(r'<[^>]+>', ' ', r.text)
                text = re.sub(r'\s+', ' ', text)[:1000]
                return [{"title": "Search results", "snippet": text, "url": ""}]
        except:
            pass
        
        return [{"title": f"Search: {query}", "snippet": "", "url": ""}]


# =====================================================================
# TOOL: Web Browser
# =====================================================================

class WebBrowser:
    def __init__(self):
        self.playwright_available = False
        self._check_playwright()
    
    def _check_playwright(self):
        try:
            import playwright
            self.playwright_available = True
        except ImportError:
            pass
    
    def browse(self, url):
        """Fetch a URL and extract text content."""
        try:
            r = requests.get(url, timeout=30, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            if r.status_code == 200:
                # Basic HTML to text extraction
                text = r.text
                # Remove scripts and styles
                text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
                text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
                text = re.sub(r'<[^>]+>', '\n', text)
                text = re.sub(r'\n\s*\n', '\n\n', text)
                text = '\n'.join(line.strip() for line in text.split('\n') if line.strip())
                return text[:10000]  # Limit length
            return f"Error: HTTP {r.status_code}"
        except Exception as e:
            return f"Error browsing: {e}"


# =====================================================================
# TOOL: Terminal
# =====================================================================

class Terminal:
    def __init__(self):
        self.sandbox = False
    
    def run(self, command, timeout=120):
        """Run a terminal command. Cross-platform."""
        try:
            shell = "powershell" if IS_WINDOWS else "/bin/bash"
            shell_arg = "-c" if not IS_WINDOWS else "-Command"
            
            result = subprocess.run(
                [shell, shell_arg, command],
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**os.environ}
            )
            
            output = ""
            if result.stdout:
                output += result.stdout[:5000]
            if result.stderr:
                output += f"\n[STDERR]\n{result.stderr[:2000]}"
            
            return {
                "success": result.returncode == 0,
                "output": output.strip() or "(no output)",
                "return_code": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "output": "Command timed out", "return_code": -1}
        except Exception as e:
            return {"success": False, "output": f"Error: {e}", "return_code": -1}


# =====================================================================
# TOOL: Filesystem
# =====================================================================

class FileSystem:
    def __init__(self):
        # Use a named output dir so user can find files
        out_dir = os.environ.get("DRAGON_OUTPUT", str(Path.home() / "dragon-output"))
        self.workspace = Path(out_dir)
        self.workspace.mkdir(exist_ok=True)
        print(f"💾 Files saved to: {self.workspace}")
    
    def read(self, path):
        """Read file contents."""
        full = self._resolve(path)
        if not full.exists():
            return f"File not found: {path}"
        try:
            # Auto-detect encoding
            for enc in ['utf-8', 'latin-1', 'cp1252']:
                try:
                    with open(full, 'r', encoding=enc) as f:
                        content = f.read()
                    return content[:10000]
                except UnicodeDecodeError:
                    continue
            return "(binary file)"
        except Exception as e:
            return f"Error reading: {e}"
    
    def write(self, path, content):
        """Write content to file."""
        full = self._resolve(path)
        full.parent.mkdir(parents=True, exist_ok=True)
        with open(full, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Written to {path}"
    
    def list(self, path="."):
        """List directory contents."""
        full = self._resolve(path)
        if not full.exists() or not full.is_dir():
            return f"Directory not found: {path}"
        items = []
        for item in sorted(full.iterdir()):
            prefix = "[DIR]" if item.is_dir() else "[FILE]"
            size = item.stat().st_size if item.is_file() else 0
            items.append(f"{prefix} {item.name} ({size} bytes)" if size else f"{prefix} {item.name}")
        return "\n".join(items) if items else "(empty directory)"
    
    def _resolve(self, path):
        p = Path(path)
        if p.is_absolute():
            return p
        return self.workspace / p


# =====================================================================
# TOOL: Code Execution
# =====================================================================

class CodeRunner:
    def run_python(self, code, timeout=30):
        """Execute Python code and return the result."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            f.write(code)
            tmp = f.name
        
        try:
            result = subprocess.run(
                [sys.executable, tmp],
                capture_output=True, text=True, timeout=timeout,
                cwd=FileSystem().workspace
            )
            output = result.stdout[:5000] if result.stdout else ""
            if result.stderr:
                output += f"\nErrors:\n{result.stderr[:2000]}"
            return output or "(no output)"
        except subprocess.TimeoutExpired:
            return "Execution timed out"
        except Exception as e:
            return f"Error: {e}"
        finally:
            os.unlink(tmp)


# =====================================================================
# AGENT CORE
# =====================================================================

class DragonAgent:
    def __init__(self, config=None):
        self.config = config or load_config()
        self.max_iterations = self.config.get("execution", {}).get("max_iterations", 50)
        self.conversation = []
        self.result = None
        
        # Initialize tools
        self.tools = {
            "search": WebSearch(),
            "browser": WebBrowser(),
            "terminal": Terminal(),
            "filesystem": FileSystem(),
            "code": CodeRunner(),
        }
        
        # Initialize model
        self._init_model()
        
        print(f"🐉 Dragon Agent v{self.config.get('agent', {}).get('version', '1.0')}")
        print(f"   Model: {self.config.get('model', {}).get('model', 'gpt-4o')}")
        print(f"   Tools: {', '.join(self._tool_descriptions().keys())}")
        print()
    
    def _init_model(self):
        model_cfg = self.config.get("model", {})
        provider = model_cfg.get("provider", "openai")
        model = model_cfg.get("model", "gpt-4o")
        
        if provider == "deepseek":
            api_key = os.environ.get("DEEPSEEK_API_KEY")
            if not api_key:
                print("❌ Set DEEPSEEK_API_KEY for deepseek provider")
                sys.exit(1)
            self.client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com/v1")
            self.model = model or "deepseek-chat"
        elif provider == "openrouter" or not provider:
            api_key = os.environ.get("OPENROUTER_API_KEY")
            if not api_key:
                print("❌ Set OPENROUTER_API_KEY")
                sys.exit(1)
            self.client = OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")
            self.model = model or "mistralai/mistral-small-3.1-24b-instruct:free"
        else:
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                print("❌ Set OPENAI_API_KEY")
                sys.exit(1)
            self.client = OpenAI(api_key=api_key)
            self.model = model or "gpt-4o"
    
    def _tool_descriptions(self):
        """Tool definitions for the model."""
        return {
            "search": """SEARCH: web_search(query: str) -> list
Search the web for information. Use for research, news, facts.
Example: web_search("Bitcoin price today")""",

            "browse": """BROWSE: browse(url: str) -> str
Fetch and extract text content from a URL.
Example: browse("https://example.com")""",

            "terminal": """TERMINAL: run(command: str) -> dict
Execute a shell command. Returns {success, output, return_code}.
Use for installing packages, running scripts, git commands.
Example: run("pip list | grep requests")""",

            "filesystem_read": """READ: read(path: str) -> str
Read a file. Use for examining code, configs, data.
Example: read("data/input.csv")""",

            "filesystem_write": """WRITE: write(path: str, content: str) -> str
Write content to a file. Creates directories automatically.
Example: write("output/report.md", "# Report")""",

            "filesystem_list": """LIST: list(path: str) -> str
List directory contents.
Example: list(".")""",

            "python": """PYTHON: python(code: str) -> str
Execute Python code. Use for data analysis, calculations, prototyping.
Example: python("print(sum([1,2,3]))")""",
        }
    
    def _system_prompt(self):
        tools_desc = "\n\n".join(self._tool_descriptions().values())
        
        return f"""You are Dragon Agent, a general-purpose AI agent that can:
- Search the web and browse websites
- Write and execute code (Python, bash, etc.)
- Read and write files
- Run terminal commands
- Create reports, apps, analyses

You think step by step and use tools to accomplish the user's task.

AVAILABLE TOOLS:
{tools_desc}

RULES:
1. Always explain your plan first
2. Use tools one at a time — I'll return the result
3. Watch tool outputs and adjust your approach
4. When finished, summarize what you did and show the result
5. If something fails, try a different approach

FORMAT your tool calls exactly like this:
TOOL: search("how to build a trading bot")

Then wait for my response with the result before the next step."""
    
    def run(self, task):
        """Execute a task from start to finish."""
        print(f"🎯 Task: {task}")
        print(f"🧠 Planning...")
        print()
        
        self.conversation = [
            {"role": "system", "content": self._system_prompt()},
            {"role": "user", "content": task}
        ]
        
        # Start workspace
        ws = Path.cwd() / "workspace"
        ws.mkdir(exist_ok=True)
        
        for iteration in range(self.max_iterations):
            print(f"\r{'─' * 40}")
            print(f"  Step {iteration + 1}/{self.max_iterations}")
            print(f"{'─' * 40}")
            
            # Get model response
            response = self._call_model()
            if not response:
                print("❌ Model call failed")
                break
            
            print(response)
            
            # Check if done
            if "DONE" in response.upper() or "FINAL" in response.upper():
                self.result = response
                break
            
            # Parse and execute tool call
            result = self._execute_tool(response)
            if result:
                print(f"\n📎 Result: {result[:500]}...")
                self.conversation.append({"role": "user", "content": f"Tool result: {result[:2000]}"})
            else:
                # No tool call — model is responding directly
                self.conversation.append({"role": "assistant", "content": response})
        
        print(f"\n{'=' * 50}")
        print("✅ TASK COMPLETE")
        print(f"{'=' * 50}")
        
        return self.result or response
    
    def _call_model(self):
        """Call the LLM."""
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=self.conversation,
                temperature=float(self.config.get("model", {}).get("temperature", 0.7)),
                max_tokens=int(self.config.get("model", {}).get("max_tokens", 4096)),
                timeout=120
            )
            return resp.choices[0].message.content
        except Exception as e:
            return f"Error: {e}"
    
    def _execute_tool(self, response):
        """Parse and execute a tool call from the model's response."""
        import re
        
        # Try to find tool calls
        patterns = [
            r'TOOL:\s*(\w+)\(([^)]*)\)',
            r'`(\w+)\(([^)]*)\)`',
            r'(\w+)\(([^)]*)\)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, response)
            if match:
                tool_name = match.group(1).lower()
                args_raw = match.group(2)
                
                # Clean args
                args = args_raw.strip().strip('"').strip("'")
                
                # Map tool names
                tool_map = {
                    "search": lambda: self.tools["search"].search(args),
                    "web_search": lambda: self.tools["search"].search(args),
                    "browse": lambda: self.tools["browser"].browse(args),
                    "run": lambda: self.tools["terminal"].run(args),
                    "terminal": lambda: self.tools["terminal"].run(args),
                    "read": lambda: self.tools["filesystem"].read(args),
                    "write": lambda: self._parse_write(args),
                    "list": lambda: self.tools["filesystem"].list(args),
                    "python": lambda: self.tools["code"].run_python(args),
                    "code": lambda: self.tools["code"].run_python(args),
                }
                
                if tool_name in tool_map:
                    try:
                        return json.dumps(tool_map[tool_name](), ensure_ascii=False, default=str)[:3000]
                    except Exception as e:
                        return f"Tool error: {e}"
        
        return None
    
    def _parse_write(self, args):
        """Parse write(path, content) call."""
        try:
            # Try JSON first
            parts = json.loads(f"[{args}]")
            if len(parts) >= 2:
                return self.tools["filesystem"].write(parts[0].strip(), parts[1].strip())
        except:
            pass
        
        # Fallback: split at first comma
        if ',' in args:
            path, content = args.split(',', 1)
            return self.tools["filesystem"].write(path.strip().strip('"').strip("'"), content.strip().strip('"').strip("'"))
        
        return f"Could not parse write call: {args}"


# =====================================================================
# CLI
# =====================================================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Dragon Agent — General AI Agent")
    parser.add_argument("task", nargs="*", help="Task to execute")
    parser.add_argument("--config", "-c", help="Config file path")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive mode")
    parser.add_argument("--version", "-v", action="store_true", help="Show version")
    
    args = parser.parse_args()
    
    if args.version:
        print("Dragon Agent v1.0.0")
        return
    
    config = load_config(args.config)
    
    agent = DragonAgent(config)
    
    if args.interactive:
        print("🐉 Interactive mode. Type 'quit' to exit.")
        while True:
            task = input("\n🎯 > ")
            if task.lower() in ("quit", "exit", "q"):
                break
            agent.run(task)
    elif args.task:
        task = " ".join(args.task)
        agent.run(task)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
