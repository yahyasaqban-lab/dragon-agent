#!/usr/bin/env python3
# Single-file Dragon Agent — copy this one file anywhere
# Works on Windows, Linux, macOS
# Manus-like general AI agent

"""
🐉 Dragon Agent v1.0
A general-purpose AI agent that browses, codes, searches, and executes.

FOR WINDOWS USERS:
  python dragon_agent.py "Research Bitcoin and create a report"
  
FOR LINUX/MAC:
  python3 dragon_agent.py "Build a simple trading dashboard"
  
INTERACTIVE MODE:
  python3 dragon_agent.py --interactive

BATCH MODE (from file):
  python3 dragon_agent.py --file tasks.txt

REQUIREMENTS:
  pip install openai pyyaml requests

API KEY (set one):
  export OPENAI_API_KEY=sk-...       # OpenAI / OpenRouter
  export DEEPSEEK_API_KEY=sk-...     # DeepSeek (cheaper)
"""

import json
import os
import sys
import re
import subprocess
import time
import platform
import tempfile
from pathlib import Path
from datetime import datetime

# Auto-install dependencies
for pkg in ["openai", "pyyaml", "requests"]:
    try:
        __import__(pkg.replace("-", "_"))
    except ImportError:
        print(f"📦 Installing {pkg}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q", "--break-system-packages"])

# Now safe to import
import yaml
import requests
from openai import OpenAI

# ─────────────────────────────────────────────
# CROSS-PLATFORM SETUP
# ─────────────────────────────────────────────
IS_WINDOWS = platform.system() == "Windows"
IS_MAC = platform.system() == "Darwin"
HOME = Path.home()
WORKSPACE = HOME / "dragon-workspace"
WORKSPACE.mkdir(exist_ok=True)

# ─────────────────────────────────────────────
# TOOLS
# ─────────────────────────────────────────────

def web_search(query, max_results=5):
    """Search the web."""
    try:
        r = requests.get(
            "https://lite.duckduckgo.com/lite/",
            params={"q": query},
            headers={"User-Agent": "DragonAgent/1.0"},
            timeout=10
        )
        if r.status_code == 200:
            # Extract text from results
            text = re.sub(r'<[^>]+>', ' ', r.text)
            text = re.sub(r'\s+', ' ', text)
            return text[:2000]
    except:
        pass
    return f"Searched for: {query}"

def browse(url):
    """Fetch a webpage."""
    try:
        r = requests.get(url, timeout=30, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        if r.status_code == 200:
            text = r.text
            for tag in ['script', 'style', 'nav', 'footer', 'header']:
                text = re.sub(f'<{tag}[^>]*>.*?</{tag}>', '', text, flags=re.DOTALL)
            text = re.sub(r'<[^>]+>', '\n', text)
            text = '\n'.join(l.strip() for l in text.split('\n') if l.strip())
            return text[:8000]
        return f"HTTP {r.status_code}"
    except Exception as e:
        return f"Error: {e}"

def run(cmd, timeout=120):
    """Run a terminal command (cross-platform)."""
    try:
        shell = ["powershell", "-Command"] if IS_WINDOWS else ["/bin/bash", "-c"]
        r = subprocess.run(shell + [cmd], capture_output=True, text=True, timeout=timeout, cwd=WORKSPACE)
        out = (r.stdout or "")[:5000]
        if r.stderr:
            out += f"\n[ERR]\n{r.stderr[:2000]}"
        return f"Exit: {r.returncode}\n{out.strip() or '(empty)'}"
    except subprocess.TimeoutExpired:
        return "TIMEOUT"
    except Exception as e:
        return f"Error: {e}"

def read(path):
    """Read a file."""
    p = Path(path)
    if not p.is_absolute():
        p = WORKSPACE / p
    if not p.exists():
        return f"File not found: {path}"
    try:
        with open(p, encoding='utf-8') as f:
            return f.read()[:10000]
    except UnicodeDecodeError:
        return "(binary file)"

def write(path, content):
    """Write a file."""
    p = Path(path)
    if not p.is_absolute():
        p = WORKSPACE / p
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, 'w', encoding='utf-8') as f:
        f.write(content)
    return f"✅ Written to {p} ({len(content)} bytes)"

def list_dir(path="."):
    """List directory."""
    p = WORKSPACE / path if not Path(path).is_absolute() else Path(path)
    if not p.exists():
        return f"Not found: {path}"
    items = []
    for item in sorted(p.iterdir()):
        kind = "📁" if item.is_dir() else "📄"
        size = item.stat().st_size if item.is_file() else 0
        items.append(f"{kind} {item.name} ({size}B)" if size else f"{kind} {item.name}")
    return "\n".join(items) if items else "(empty)"

TOOL_DESC = """SEARCH: web_search(query) - Search the web
BROWSE: browse(url) - Fetch a webpage
RUN: run(command) - Execute terminal command (cross-platform)
READ: read(path) - Read a file
WRITE: write(path, content) - Write a file
LIST: list(path) - List directory contents"""

TOOL_MAP = {
    "web_search": web_search,
    "search": web_search,
    "browse": browse,
    "run": run,
    "terminal": run,
    "read": read,
    "write": lambda p, c=None: write(p, c) if c else "(needs path and content)",
    "list": list_dir,
    "dir": list_dir,
}

# ─────────────────────────────────────────────
# AGENT
# ─────────────────────────────────────────────

SYSTEM_PROMPT = f"""You are Dragon Agent, a general-purpose AI assistant like Manus.

You can:
- Search the web for information
- Browse websites and extract data
- Run terminal commands (Windows: PowerShell, Linux: bash)
- Read and write files
- Create reports, code, apps, analysis

WORKSPACE: {WORKSPACE}

TOOLS:
{TOOL_DESC}

HOW TO USE TOOLS:
When you need to use a tool, put it in format:
TOOL: tool_name("argument")

For write tool:
TOOL: write("output.txt", "Hello World")

PLAN OF ACTION:
1. First, plan what you'll do
2. Explain each step before doing it
3. Use tools one at a time
4. When done, output "RESULT:" followed by your final answer

RULES:
- No harm. No illegal stuff. No spam.
- Be helpful and get the task done.
- If something fails, try a different approach.
"""

def call_model(client, model, messages):
    """Call the LLM."""
    try:
        r = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.7,
            max_tokens=4096,
            timeout=120
        )
        return r.choices[0].message.content
    except Exception as e:
        return f"⚠️ Model error: {e}"

def execute_tool(text):
    """Find and execute a TOOL: call in the text."""
    # Look for TOOL: func("arg") or TOOL: func("arg1", "arg2")
    match = re.search(r'TOOL:\s*(\w+)\(([^)]*)\)', text, re.IGNORECASE)
    if not match:
        return None
    
    name = match.group(1).lower()
    args_raw = match.group(2).strip()
    
    if name not in TOOL_MAP:
        return f"Unknown tool: {name}"
    
    fn = TOOL_MAP[name]
    
    if name == "write":
        # Split into path and content
        try:
            # Try JSON-like parsing
            import ast
            args = ast.literal_eval(f"({args_raw})")
            if isinstance(args, tuple) and len(args) >= 2:
                return fn(args[0], args[1])
        except:
            pass
        # Fallback: just use the whole thing as path
        return fn(args_raw.strip('"\''))
    
    # Other tools: pass single arg
    arg = args_raw.strip('"\'').strip("'")
    
    try:
        result = fn(arg)
        if isinstance(result, str):
            return result
        return str(result)
    except Exception as e:
        return f"Tool error: {e}"


def run_agent(task, config=None):
    """Run the agent on a task."""
    print(f"🐉 Dragon Agent")
    print(f"   Task: {task}")
    print(f"   Workspace: {WORKSPACE}")
    print()
    
    # Setup model
    api_key = os.environ.get("OPENAI_API_KEY", os.environ.get("OPENROUTER_API_KEY"))
    if not api_key:
        print("❌ No API key found. Set OPENAI_API_KEY or OPENROUTER_API_KEY")
        return
    
    # Try OpenRouter first (works with many models)
    client = OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")
    model = config.get("model", os.environ.get("AGENT_MODEL", "openrouter/auto"))
    provider = config.get("provider", os.environ.get("AGENT_PROVIDER", "openrouter"))
    
    if provider == "deepseek":
        client = OpenAI(api_key=os.environ.get("DEEPSEEK_API_KEY", api_key), base_url="https://api.deepseek.com/v1")
        model = "deepseek-chat"
    
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": task}
    ]
    
    max_steps = int(config.get("max_steps", 25)) if config else 25
    
    for step in range(max_steps):
        print(f"\n{'─' * 40}")
        print(f"  Step {step + 1}/{max_steps}")
        print(f"{'─' * 40}")
        
        response = call_model(client, model, messages)
        if not response:
            break
        
        # Show response
        print(response)
        print()
        
        # Check for final result
        if "RESULT:" in response.upper():
            print(f"\n{'=' * 50}")
            print(f"✅ COMPLETE")
            print(f"{'=' * 50}")
            # Extract result content
            idx = response.upper().find("RESULT:")
            print(response[idx:])
            return response
        
        # Try to execute a tool
        tool_result = execute_tool(response)
        if tool_result:
            print(f"📎 Result: {tool_result[:1000]}")
            messages.append({"role": "assistant", "content": response})
            messages.append({"role": "user", "content": f"Tool result: {tool_result[:3000]}"})
        else:
            # No tool call — conversation mode
            messages.append({"role": "assistant", "content": response})
            # Ask what to do next
            messages.append({"role": "user", "content": "Continue. If you're done, say RESULT: followed by your final answer."})
    
    print(f"\n{'=' * 50}")
    print(f"❌ Stopped after {max_steps} steps")
    print(f"{'=' * 50}")
    return response


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="🐉 Dragon Agent - General AI Agent")
    parser.add_argument("task", nargs="*", help="What to do")
    parser.add_argument("-i", "--interactive", action="store_true", help="Interactive mode")
    parser.add_argument("-m", "--model", help="Model name (e.g., gpt-4o, deepseek-chat)")
    parser.add_argument("--config", help="Config file (YAML)")
    parser.add_argument("-v", "--version", action="store_true", help="Version")
    
    args = parser.parse_args()
    
    if args.version:
        print("Dragon Agent v1.0.0")
        return
    
    config = {}
    if args.config and Path(args.config).exists():
        with open(args.config) as f:
            config = yaml.safe_load(f)
    if args.model:
        config["model"] = args.model
    
    if args.interactive:
        print("🐉 Interactive mode. Type 'quit' to exit, 'save' to save conversation.")
        print(f"   Workspace: {WORKSPACE}")
        print()
        history = []
        while True:
            task = input("🎯 > ")
            if task.lower() in ("quit", "exit", "q"):
                break
            if task.lower() == "save":
                path = WORKSPACE / f"conversation-{datetime.now():%Y%m%d-%H%M%S}.md"
                with open(path, 'w') as f:
                    for msg in history:
                        f.write(f"## {msg['role']}\n{msg['content']}\n\n")
                print(f"💾 Saved to {path}")
                continue
            result = run_agent(task, config)
            if result:
                history.append({"role": "assistant", "content": result})
    elif args.task:
        run_agent(" ".join(args.task), config)
    else:
        parser.print_help()
        print()
        print("Examples:")
        print(f"  python {sys.argv[0]} \"Research Bitcoin and create a report\"")
        print(f"  python {sys.argv[0]} -i")
        print()
        print("Set your API key:")
        print("  export OPENAI_API_KEY=sk-...")
        print("  export OPENROUTER_API_KEY=sk-...")
        print("  export DEEPSEEK_API_KEY=sk-...")


if __name__ == "__main__":
    main()
