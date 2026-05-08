#!/usr/bin/env python3
"""
Dragon Agent — Cross-platform AI agent (Windows + Linux)
Manus-like: browses web, writes code, runs commands, produces results
Now with multi-agent orchestration: plan mode + parallel sub-agents

Usage:
  python3 dragon_agent.py "Research Bitcoin price and create a report"
  python3 dragon_agent.py --config config.yaml "Build a trading dashboard"
  python3 dragon_agent.py --plan "Create a weather app"  # Auto-plan and delegate
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
import threading
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

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
  version: "2.0.0"

model:
  provider: "deepseek"
  model: "deepseek-chat"
  temperature: 0.7
  max_tokens: 4096

tools:
  enabled: ["terminal", "filesystem", "search", "code"]

execution:
  max_iterations: 100
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
            r = requests.get(
                f"https://html.duckduckgo.com/html/?q={requests.utils.quote(query)}",
                headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"},
                timeout=15
            )
            if r.status_code == 200:
                results = []
                links = re.findall(r'class="result__a"[^>]*href="([^"]+)"[^>]*>([^<]+)</a>', r.text)
                snippets = re.findall(r'class="result__snippet"[^>]*>([^<]+)</a>', r.text)
                
                for i, (url, title) in enumerate(links[:max_results]):
                    snippet = snippets[i] if i < len(snippets) else ""
                    title = re.sub(r'<[^>]+>', '', title).strip()
                    snippet = re.sub(r'<[^>]+>', '', snippet).strip()
                    results.append({
                        "title": title,
                        "snippet": snippet[:300],
                        "url": url
                    })
                
                if results:
                    return results
                
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
                text = r.text
                text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
                text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
                text = re.sub(r'<[^>]+>', '\n', text)
                text = re.sub(r'\n\s*\n', '\n\n', text)
                text = '\n'.join(line.strip() for line in text.split('\n') if line.strip())
                return text[:10000]
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
# SUB-AGENT: Spawn parallel agents for subtasks
# =====================================================================

class SubAgent:
    """A lightweight sub-agent that can be spawned for parallel tasks."""

    @staticmethod
    def run_task(config, task, task_id=""):
        """Run a task in a sub-agent. Returns {'task_id': ..., 'result': ..., 'status': ...}."""
        agent = DragonAgent(config=config, silent=True)
        try:
            result = agent.run(task)
            return {
                "task_id": task_id,
                "result": result,
                "status": "completed"
            }
        except Exception as e:
            return {
                "task_id": task_id,
                "result": f"Error: {e}",
                "status": "failed"
            }


# =====================================================================
# AGENT CORE
# =====================================================================

class DragonAgent:
    def __init__(self, config=None, silent=False):
        self.config = config or load_config()
        self.max_iterations = self.config.get("execution", {}).get("max_iterations", 100)
        self.conversation = []
        self.result = None
        self.silent = silent
        self.sub_agent_results = {}  # For plan mode: task -> result
        
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
        
        if not silent:
            print(f"🐉 Dragon Agent v{self.config.get('agent', {}).get('version', '2.0')}")
            print(f"   Model: {self.config.get('model', {}).get('model', 'deepseek-chat')}")
            print(f"   Tools: {', '.join(self._tool_descriptions().keys())}")
            print()
    
    def _init_model(self):
        model_cfg = self.config.get("model", {})
        provider = model_cfg.get("provider", "deepseek")
        model = model_cfg.get("model", "deepseek-chat")
        
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
        elif provider == "ollama":
            try:
                self.client = OpenAI(api_key="ollama", base_url="http://localhost:11434/v1")
                self.client.models.list()  # verify it works
                self.model = model or "llama3"
                print(f"  🦙 Using local Ollama: {self.model}")
            except Exception as e:
                print(f"❌ Ollama not running: {e}")
                sys.exit(1)
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

            "agent": """AGENT: agent(task: str, task_id: str = "") -> dict
SPAWN a sub-agent to work on a task in parallel. Use for:
- Breaking large tasks into independent workstreams
- Researching multiple topics simultaneously
- Building multiple components at once
Returns {'task_id': ..., 'result': ..., 'status': 'completed'|'failed'}
NOTE: Each agent() call runs IN PARALLEL with other agent() calls.
Example: agent("Research Python async features", "task_1")"""
        }
    
    def _system_prompt(self, plan_mode=False):
        tools_desc = "\n\n".join(self._tool_descriptions().values())
        
        base = f"""You are Dragon Agent, a general-purpose AI agent that can:
- Search the web and browse websites
- Write and execute code (Python, bash, etc.)
- Read and write files
- Run terminal commands
- Spawn sub-agents for parallel tasks
- Create reports, apps, analyses

You think step by step and use tools to accomplish the user's task.

AVAILABLE TOOLS:
{tools_desc}

RULES:
1. Always explain your plan first
2. Use tools one at a time — I'll return the result
3. Watch tool outputs and adjust your approach
4. When finished, say "DONE" and summarize what you did
5. If something fails, try a different approach
6. **Do NOT repeat the same tool call more than twice.** If you already got the data, stop.
7. **You have a maximum of 100 tool-using turns.** Be efficient. If you need more, auto-compaction will help manage context.

FORMAT your tool calls exactly like this:
TOOL: search("how to build a trading bot")

Then wait for my response with the result before the next step.

When you're done with the task, output:
DONE: (summary of what was accomplished)"""

        if plan_mode:
            base = f"""You are Dragon Agent in **PLAN MODE**. Your job is to decompose the user's task into discrete steps and delegate them to sub-agents.

AVAILABLE TOOLS:
{tools_desc}

PLAN MODE RULES:
1. First, analyze the task and break it into independent workstreams
2. For each workstream, use: agent(task, "task_id")
3. Multiple agent() calls run in PARALLEL — use this for independent work
4. After all sub-agents complete, collect results and produce the final output
5. Use other tools (search, browse, write) to supplement or assemble results
6. When done, say "DONE" with a summary

Example:
TOOL: agent("Research Python REST frameworks and recommend one", "research")
TOOL: agent("Write a sample API client using Flask", "prototype")

{base}"""

        return base
    
    def run(self, task):
        """Execute a task from start to finish with auto-compact at 100 turns."""
        if not self.silent:
            print(f"🎯 Task: {task}")
            print(f"🧠 Planning...")
            print()
        
        self.conversation = [
            {"role": "system", "content": self._system_prompt()},
            {"role": "user", "content": task}
        ]
        
        ws = Path.cwd() / "workspace"
        ws.mkdir(exist_ok=True)
        
        for iteration in range(self.max_iterations):
            if not self.silent:
                print(f"\r{'─' * 40}")
                print(f"  Step {iteration + 1}/{self.max_iterations}")
                print(f"{'─' * 40}")
            
            # Get model response
            response = self._call_model()
            if not response:
                if not self.silent:
                    print("❌ Model call failed")
                break
            
            if not self.silent:
                print(response)
            
            # Check if done
            if "DONE" in response.upper() or "FINAL" in response.upper():
                self.result = response
                break
            
            # Parse and execute tool call(s)
            results = self._execute_tools(response)
            if results:
                for tool_name, tool_result in results:
                    if not self.silent:
                        truncated = tool_result[:500] + ("..." if len(tool_result) > 500 else "")
                        print(f"\n📎 {tool_name}: {truncated}")
                    self.conversation.append({"role": "user", "content": f"Tool ({tool_name}) result: {tool_result[:2000]}"})
            else:
                # No tool call — model is responding directly
                self.conversation.append({"role": "assistant", "content": response})
            
            # Auto-compact at 80% of max_iterations or when message count is large
            if len(self.conversation) > 60 or (iteration >= self.max_iterations * 0.8 and iteration > 20):
                self._auto_compact()
        
        if not self.silent:
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
    
    def _execute_tools(self, response):
        """Parse and execute ALL tool calls from the response.
        Parallel tool calls (multiple agent() calls) run concurrently.
        Returns list of (tool_name, result) tuples."""
        import re
        
        # Find ALL tool calls in the response
        tool_patterns = [
            re.findall(r'TOOL:\s*(\w+)\(([^)]*)\)', response, re.IGNORECASE),
            re.findall(r'`(\w+)\(([^)]*)\)`', response),
            re.findall(r'^(\w+)\(([^)]*)\)', response, re.MULTILINE),
        ]
        
        all_matches = []
        for matches in tool_patterns:
            if matches:
                all_matches = matches
                break
        
        if not all_matches:
            return None
        
        results = []
        agent_tasks = []  # For parallel execution
        
        for tool_name, args_raw in all_matches:
            tool_name = tool_name.lower()
            args = args_raw.strip().strip('"').strip("'")
            
            # Check if it's an agent() call — queue for parallel execution
            if tool_name in ("agent", "sub_agent"):
                agent_tasks.append((tool_name, args, args_raw))
            else:
                result = self._execute_single_tool(tool_name, args)
                results.append((tool_name, result))
        
        # Execute all agent() calls IN PARALLEL
        if agent_tasks:
            parallel_results = self._execute_parallel_agents(agent_tasks)
            results.extend(parallel_results)
        
        return results if results else None
    
    def _execute_single_tool(self, tool_name, args):
        """Execute a single tool call and return the result."""
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
        
        fn = tool_map.get(tool_name)
        if fn:
            try:
                result = fn()
                return json.dumps(result, ensure_ascii=False, default=str)[:3000]
            except Exception as e:
                return f"Tool error: {e}"
        
        return None
    
    def _execute_parallel_agents(self, agent_calls):
        """Execute multiple agent() calls IN PARALLEL using threads."""
        results = []
        
        def run_agent(tool_name, args, args_raw):
            """Parse the agent call and run it."""
            # Parse task from args (could be just a string, or task_id + task)
            task, task_id = self._parse_agent_call(args_raw)
            result = SubAgent.run_task(self.config, task, task_id)
            return (tool_name, json.dumps(result, ensure_ascii=False, default=str)[:3000])
        
        with ThreadPoolExecutor(max_workers=min(len(agent_calls), 5)) as executor:
            futures = {
                executor.submit(run_agent, tn, a, ar): (tn, a)
                for tn, a, ar in agent_calls
            }
            for future in as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as e:
                    tn, a = futures[future]
                    results.append((tn, f"Sub-agent error: {e}"))
        
        return results
    
    def _parse_agent_call(self, raw_args):
        """Parse agent("task", "task_id") or agent("task") call."""
        # Try to parse as JSON-like: "task", "task_id"
        parts = re.findall(r'"([^"]*)"', raw_args)
        if len(parts) >= 2:
            return parts[0], parts[1]
        if len(parts) == 1:
            return parts[0], ""
        # Fallback: split at comma
        if ',' in raw_args:
            task, tid = raw_args.split(',', 1)
            return task.strip().strip('"\''), tid.strip().strip('"\'')
        return raw_args.strip().strip('"\''), ""
    
    def _auto_compact(self):
        """Compress conversation to keep system prompt, last few exchanges, and a summary."""
        summary = f"[Compacted {len(self.conversation)} messages at {datetime.now().strftime('%H:%M:%S')}]"
        # Keep: system (first), summary note, user's original task (second), last 4 exchanges
        kept = self.conversation[:2]  # system + original user task
        kept.append({"role": "system", "content": summary})
        kept.extend(self.conversation[-6:])  # last 4 exchanges = 8 messages, keep last 6
        self.conversation = kept
    
    def _parse_write(self, args):
        """Parse write(path, content) call."""
        try:
            parts = json.loads(f"[{args}]")
            if len(parts) >= 2:
                return self.tools["filesystem"].write(parts[0].strip(), parts[1].strip())
        except:
            pass
        
        if ',' in args:
            path, content = args.split(',', 1)
            return self.tools["filesystem"].write(path.strip().strip('"').strip("'"), content.strip().strip('"').strip("'"))
        
        return f"Could not parse write call: {args}"


# =====================================================================
# PLAN MODE — Auto-break tasks into steps and delegate
# =====================================================================

class PlanAgent(DragonAgent):
    """Extended DragonAgent with automatic task planning."""

    def run(self, task):
        """Override run() with planning-first approach."""
        print(f"📋 Plan Mode: Decomposing task into sub-tasks...")
        print()

        # Step 1: Get the LLM to create a plan
        plan_prompt = f"""Break this task into 2-5 independent sub-tasks that can be worked on in parallel:

TASK: {task}

For each sub-task, specify:
- What to do (1-2 sentences)
- What tool to use (search, browse, code, terminal, write)

Return a JSON plan:
{{
  "plan": [
    {{"id": "task_1", "description": "...", "tools_needed": ["search"]}},
    {{"id": "task_2", "description": "...", "tools_needed": ["code", "write"]}}
  ]
}}"""

        plan_msg = [
            {"role": "system", "content": "You are a planning agent. Output clean JSON only."},
            {"role": "user", "content": plan_prompt}
        ]

        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=plan_msg,
                temperature=0.3,
                max_tokens=2048,
                timeout=60
            )
            plan_text = resp.choices[0].message.content
        except Exception as e:
            print(f"❌ Plan generation error: {e}")
            return super().run(task)

        # Extract JSON from response
        json_match = re.search(r'\{.*\}', plan_text, re.DOTALL)
        if not json_match:
            print("⚠️ Could not generate plan. Running directly.")
            return super().run(task)

        try:
            plan_data = json.loads(json_match.group())
            plan_steps = plan_data.get("plan", [])
        except json.JSONDecodeError:
            print("⚠️ Could not parse plan. Running directly.")
            return super().run(task)

        if not plan_steps:
            print("⚠️ Empty plan. Running directly.")
            return super().run(task)

        print(f"📋 Plan has {len(plan_steps)} steps:")
        for step in plan_steps:
            print(f"   • [{step['id']}] {step['description'][:80]}...")
        print()

        # Step 2: Execute sub-tasks in parallel
        results = []
        with ThreadPoolExecutor(max_workers=min(len(plan_steps), 5)) as executor:
            futures = {}
            for step in plan_steps:
                task_desc = f"{step['description']}\n\nSave results to files named after task_{step['id']}."
                future = executor.submit(SubAgent.run_task, self.config, task_desc, step['id'])
                futures[future] = step['id']

            for future in as_completed(futures):
                task_id = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                    status = result.get("status", "unknown")
                    r_preview = result.get("result", "")[:80]
                    print(f"   ✅ [{task_id}] {status} — {r_preview}")
                except Exception as e:
                    print(f"   ❌ [{task_id}] Error: {e}")

        print()

        # Step 3: Synthesize results
        synthesis_prompt = f"""Synthesize the following sub-task results into a final response for the user's original request.

ORIGINAL TASK: {task}

SUB-TASK RESULTS:
{json.dumps(results, indent=2, default=str)}

Provide a comprehensive, well-organized final answer. Include file paths, code snippets, and key findings."""

        self.conversation = [
            {"role": "system", "content": self._system_prompt()},
            {"role": "user", "content": synthesis_prompt}
        ]

        # Let the model run a few more turns to refine
        for _ in range(min(10, self.max_iterations)):
            response = self._call_model()
            if not response:
                break
            print(response)

            if "DONE" in response.upper():
                self.result = response
                break

            results = self._execute_tools(response)
            if results:
                for tn, tr in results:
                    print(f"\n📎 {tn}: {tr[:300]}...")
                    self.conversation.append({"role": "user", "content": f"Tool ({tn}) result: {tr[:2000]}"})
            else:
                self.conversation.append({"role": "assistant", "content": response})

        print(f"\n{'=' * 50}")
        print("✅ PLAN MODE COMPLETE")
        print(f"{'=' * 50}")

        return self.result or response


# =====================================================================
# CLI
# =====================================================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Dragon Agent — General AI Agent with Multi-Agent Orchestration")
    parser.add_argument("task", nargs="*", help="Task to execute")
    parser.add_argument("--config", "-c", help="Config file path")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive mode")
    parser.add_argument("--plan", "-p", action="store_true", help="Plan mode: auto-decompose & delegate")
    parser.add_argument("--version", "-v", action="store_true", help="Show version")
    
    args = parser.parse_args()
    
    if args.version:
        print("Dragon Agent v2.0.0 — Multi-Agent Orchestration")
        return
    
    config = load_config(args.config)
    
    if args.plan:
        agent = PlanAgent(config)
    else:
        agent = DragonAgent(config)
    
    if args.interactive:
        print("🐉 Interactive mode. Type 'quit' to exit. Type '!plan <task>' for plan mode.")
        while True:
            task = input("\n🎯 > ")
            if task.lower() in ("quit", "exit", "q"):
                break
            if task.lower().startswith("!plan"):
                p_agent = PlanAgent(config)
                p_agent.run(task[6:].strip())
            else:
                agent.run(task)
    elif args.task:
        task = " ".join(args.task)
        result = agent.run(task)
        if result:
            print(f"\n✅ {result}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
