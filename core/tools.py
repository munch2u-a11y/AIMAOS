import os
import importlib
import importlib.util
import sys

class ToolRegistry:
    def __init__(self, tools_dir):
        self.tools_dir = tools_dir
        self.tools = {}
        self.load_tools()

    def load_tools(self):
        """Discovers and loads all tool modules in the tools directory."""
        if not os.path.exists(self.tools_dir):
            os.makedirs(self.tools_dir, exist_ok=True)
            # Create empty __init__.py if it doesn't exist
            with open(os.path.join(self.tools_dir, "__init__.py"), "w") as f:
                f.write("# AIMAOS agent tools package\n")

        # Load each tool module by absolute file path with a name unique to
        # this tools directory. Importing as the package name "tools." would
        # collide across agents: every AIMAOS agent has its own tools/ dir,
        # and whichever agent imported first would shadow all the others.
        ns = os.path.basename(os.path.dirname(self.tools_dir)) or "agent"
        ns = ns.replace("-", "_").replace(".", "_")

        for filename in os.listdir(self.tools_dir):
            if filename.endswith(".py") and not filename.startswith("__"):
                module_name = filename[:-3]
                try:
                    full_module_name = f"aimaos_tools_{ns}_{module_name}"
                    if full_module_name in sys.modules:
                        del sys.modules[full_module_name]

                    spec = importlib.util.spec_from_file_location(
                        full_module_name, os.path.join(self.tools_dir, filename))
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[full_module_name] = module
                    spec.loader.exec_module(module)
                    
                    # Verify tool interface
                    if hasattr(module, "TOOL_DEFINITION") and hasattr(module, "execute"):
                        tool_def = module.TOOL_DEFINITION
                        tool_name = tool_def.get("name")
                        if tool_name:
                            self.tools[tool_name] = {
                                "definition": tool_def,
                                "execute": module.execute,
                                "module": module
                            }
                except Exception as e:
                    print(f"Warning: Failed to load tool module '{module_name}': {e}", file=sys.stderr)

    def get_tool_definitions(self):
        """Returns tool definitions in LLM schema format."""
        return [t["definition"] for t in self.tools.values()]

    def execute_tool(self, name, arguments):
        """Executes a tool by name with arguments."""
        if name not in self.tools:
            return f"Error: Tool '{name}' not found in registry."
        
        try:
            # Ensure arguments is a dict
            if isinstance(arguments, str):
                import json
                try:
                    arguments = json.loads(arguments)
                except Exception:
                    return f"Error: Failed to parse tool arguments as JSON: {arguments}"
            
            # Execute tool function
            result = self.tools[name]["execute"](**arguments)
            return str(result)
        except TypeError as e:
            return f"Error: Invalid arguments for tool '{name}'. Detail: {e}"
        except Exception as e:
            import traceback
            return f"Error: Exception occurred while executing tool '{name}': {e}\n{traceback.format_exc()}"
