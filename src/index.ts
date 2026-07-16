#!/usr/bin/env node
/**
 * Riven MCP server — exposes Riven chat, research, council, and usage tools
 * to any Model Context Protocol (MCP) client over stdio.
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

import { pollTaskUntilDone, RivenApiError, RivenClient } from "./riven-client.js";

const DEFAULT_API_BASE = "https://api.rivenai.io/v1";
const DEFAULT_COMPUTER_BASE = "https://computer.rivenai.io";

function requireApiKey(): string {
  const apiKey = process.env.RIVEN_API_KEY;
  if (!apiKey) {
    // eslint-disable-next-line no-console
    console.error(
      "riven-mcp: RIVEN_API_KEY is not set. Export RIVEN_API_KEY=rvn_... before starting the server."
    );
    process.exit(1);
  }
  return apiKey;
}

const apiKey = requireApiKey();
const apiBase = process.env.RIVEN_API_BASE ?? DEFAULT_API_BASE;
const computerBase = process.env.RIVEN_COMPUTER_BASE ?? DEFAULT_COMPUTER_BASE;

const riven = new RivenClient({ apiKey, apiBase, computerBase });

const server = new McpServer({
  name: "riven-mcp",
  version: "0.1.0",
});

function errorResult(err: unknown) {
  const message = err instanceof RivenApiError ? err.message : (err as Error).message ?? String(err);
  return {
    isError: true,
    content: [{ type: "text" as const, text: `Riven request failed: ${message}` }],
  };
}

server.registerTool(
  "riven_chat",
  {
    title: "Riven Chat",
    description:
      "Send a single prompt to a Riven chat model and return the completion text. " +
      "Use for quick, single-turn questions that don't need agentic research.",
    inputSchema: {
      prompt: z.string().describe("The user prompt to send to the model."),
      model: z
        .string()
        .optional()
        .describe(
          "Model id to use, e.g. 'rvn-assistant-v2' (flagship alias), 'glm-5.2', or " +
            "'qwen3.6-35b'. Defaults to 'rvn-assistant-v2' if omitted."
        ),
      system: z.string().optional().describe("Optional system prompt to steer the model."),
    },
  },
  async ({ prompt, model, system }) => {
    try {
      const messages = system
        ? [
            { role: "system" as const, content: system },
            { role: "user" as const, content: prompt },
          ]
        : [{ role: "user" as const, content: prompt }];
      const completion = await riven.chatCompletion(model ?? "rvn-assistant-v2", messages);
      const text = completion.choices[0]?.message?.content ?? "";
      return { content: [{ type: "text" as const, text }] };
    } catch (err) {
      return errorResult(err);
    }
  }
);

server.registerTool(
  "riven_research",
  {
    title: "Riven Research",
    description:
      "Create a Riven Computer research task for the given prompt, run it, poll until " +
      "it completes (or times out), and return a summary of the resulting thread. " +
      "Use for open-ended research questions that benefit from multi-step agentic work.",
    inputSchema: {
      prompt: z.string().describe("The research question or brief."),
      title: z.string().optional().describe("Short title for the task. Defaults to the prompt."),
      timeout_seconds: z
        .number()
        .int()
        .positive()
        .optional()
        .describe("Maximum time to wait for the task to finish. Defaults to 120 seconds."),
    },
  },
  async ({ prompt, title, timeout_seconds }) => {
    try {
      const task = await riven.createTask(
        title ?? prompt.slice(0, 80),
        prompt,
        "research"
      );
      await riven.runTask(task.id);
      const { task: finalTask, thread } = await pollTaskUntilDone(riven, task.id, {
        timeoutMs: (timeout_seconds ?? 120) * 1000,
      });
      const summary = thread.messages.map((m) => `[${m.role}] ${m.content}`).join("\n\n");
      const statusNote =
        finalTask.status === "completed"
          ? ""
          : `\n\n(Task status: ${finalTask.status} — it may not be fully finished yet.)`;
      return {
        content: [
          {
            type: "text" as const,
            text: `Task ${finalTask.id} (${finalTask.status}):\n\n${summary}${statusNote}`,
          },
        ],
      };
    } catch (err) {
      return errorResult(err);
    }
  }
);

server.registerTool(
  "riven_council",
  {
    title: "Riven Council",
    description:
      "Create a Riven Computer council task, which asks multiple models to answer the " +
      "same prompt and produces a synthesized verdict plus each model's individual answer. " +
      "Use when you want a cross-checked or debated answer rather than a single model's view.",
    inputSchema: {
      prompt: z.string().describe("The question or brief to put to the council."),
      title: z.string().optional().describe("Short title for the task. Defaults to the prompt."),
      timeout_seconds: z
        .number()
        .int()
        .positive()
        .optional()
        .describe("Maximum time to wait for the task to finish. Defaults to 120 seconds."),
    },
  },
  async ({ prompt, title, timeout_seconds }) => {
    try {
      const task = await riven.createTask(title ?? prompt.slice(0, 80), prompt, "council");
      await riven.runTask(task.id);
      const { task: finalTask, thread } = await pollTaskUntilDone(riven, task.id, {
        timeoutMs: (timeout_seconds ?? 120) * 1000,
      });
      const transcript = thread.messages.map((m) => `[${m.role}] ${m.content}`).join("\n\n");
      const statusNote =
        finalTask.status === "completed"
          ? ""
          : `\n\n(Task status: ${finalTask.status} — the council may not have finished yet.)`;
      return {
        content: [
          {
            type: "text" as const,
            text: `Council task ${finalTask.id} (${finalTask.status}):\n\n${transcript}${statusNote}`,
          },
        ],
      };
    } catch (err) {
      return errorResult(err);
    }
  }
);

server.registerTool(
  "riven_usage",
  {
    title: "Riven Usage",
    description: "Return current usage statistics for the authenticated Riven account.",
    inputSchema: {},
  },
  async () => {
    try {
      const usage = await riven.usage();
      return { content: [{ type: "text" as const, text: JSON.stringify(usage, null, 2) }] };
    } catch (err) {
      return errorResult(err);
    }
  }
);

async function main(): Promise<void> {
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

main().catch((err) => {
  // eslint-disable-next-line no-console
  console.error("riven-mcp: fatal error", err);
  process.exit(1);
});
