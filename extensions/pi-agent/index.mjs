import { execFile } from "node:child_process";
import { fileURLToPath } from "node:url";
import { join } from "node:path";

const ROOT = fileURLToPath(new URL("../../", import.meta.url));
process.env.PI_PACKAGE_ROOT ??= ROOT;

async function runHook(name, payload, cwd, timeout) {
  const candidates = process.platform === "win32"
    ? [["py", ["-3"]], ["python", []], ["python3", []]]
    : [["python3", []], ["python", []]];

  for (const [command, prefix] of candidates) {
    const output = await new Promise((resolve) => {
      const child = execFile(
        command,
        [...prefix, join(ROOT, "hooks", name)],
        {
          cwd,
          env: {
            ...process.env,
            PLUGIN_ROOT: ROOT,
            PI_POWERSHELL: process.platform === "win32" ? "1" : "0",
          },
          timeout,
          maxBuffer: 64 * 1024,
        },
        (error, stdout) => {
          if (error?.code === "ENOENT") resolve(undefined);
          else resolve(error ? null : stdout);
        },
      );
      child.stdin?.end(JSON.stringify(payload));
    });
    if (output === undefined) continue;
    if (!output) return null;
    try {
      return JSON.parse(output);
    } catch {
      return null;
    }
  }
  return null;
}

export default function tokenEfficientRepoWork(pi) {
  let context = "";

  pi.on("session_start", async (_event, ctx) => {
    const result = await runHook(
      "session-start.py",
      { cwd: ctx.cwd, source: "startup" },
      ctx.cwd,
      15_000,
    );
    context = result?.hookSpecificOutput?.additionalContext ?? "";
    if (!result) ctx.ui.notify("agents-toolkit requires Python 3", "warning");
  });

  pi.on("before_agent_start", (event) => {
    if (context) return { systemPrompt: `${event.systemPrompt}\n\n${context}` };
  });

  pi.on("tool_call", async (event, ctx) => {
    if (event.toolName !== "bash") return;
    const command = event.input?.command;
    if (typeof command !== "string") return;
    const result = await runHook(
      "pre-tool-use.py",
      { tool_name: "Bash", tool_input: { command }, cwd: ctx.cwd },
      ctx.cwd,
      5_000,
    );
    const hook = result?.hookSpecificOutput;
    if (hook?.permissionDecision === "deny") {
      return { block: true, reason: hook.permissionDecisionReason };
    }
  });
}
