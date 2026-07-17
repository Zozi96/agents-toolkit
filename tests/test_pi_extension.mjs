import assert from "node:assert/strict";
import test from "node:test";
import extension from "../extensions/pi-agent/index.mjs";

test("Pi extension injects context, routes Bash, and fails open without Python", async () => {
  const handlers = {};
  const notifications = [];
  extension({ on: (name, handler) => { handlers[name] = handler; } });
  const ctx = {
    cwd: process.cwd(),
    ui: { notify: (...args) => notifications.push(args) },
  };

  await handlers.session_start({}, ctx);
  const before = await handlers.before_agent_start({ systemPrompt: "base" }, ctx);
  assert.match(before.systemPrompt, /Token-efficient repo workflow/);
  assert.match(before.systemPrompt, /Repository Context/);

  const blocked = await handlers.tool_call(
    { toolName: "bash", input: { command: "pytest" } },
    ctx,
  );
  assert.equal(blocked.block, true);
  assert.match(blocked.reason, /run_capped\.py/);
  assert.equal(
    await handlers.tool_call({ toolName: "bash", input: { command: "git status --short" } }, ctx),
    undefined,
  );

  const path = process.env.PATH;
  process.env.PATH = "";
  try {
    await handlers.session_start({}, ctx);
    assert.equal(
      await handlers.tool_call({ toolName: "bash", input: { command: "pytest" } }, ctx),
      undefined,
    );
  } finally {
    process.env.PATH = path;
  }
  assert.equal(notifications.at(-1)?.[1], "warning");
});
