/**
 * Minimal Riven API client used internally by the MCP server.
 *
 * Kept dependency-free (native fetch) so this server has a small, auditable
 * footprint independent of the `@rivenai/sdk` package.
 */

export interface RivenClientOptions {
  apiKey: string;
  apiBase: string;
  computerBase: string;
}

export interface ChatMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

export interface ChatCompletionResult {
  id: string;
  model: string;
  choices: Array<{
    message: ChatMessage;
    finish_reason: string | null;
  }>;
  [key: string]: unknown;
}

export interface Task {
  id: string;
  title: string;
  prompt: string;
  kind: string;
  status: string;
  [key: string]: unknown;
}

export interface TaskThread {
  task_id: string;
  messages: Array<{ role: string; content: string; [key: string]: unknown }>;
  [key: string]: unknown;
}

export class RivenApiError extends Error {
  constructor(message: string, public readonly statusCode?: number) {
    super(message);
    this.name = "RivenApiError";
  }
}

/** Thin wrapper around the Riven chat and Computer APIs. */
export class RivenClient {
  constructor(private readonly options: RivenClientOptions) {}

  private headers(): Record<string, string> {
    return {
      Authorization: `Bearer ${this.options.apiKey}`,
      "Content-Type": "application/json",
      "User-Agent": "riven-mcp/0.1.0",
    };
  }

  private async requestJson<T>(url: string, init: RequestInit): Promise<T> {
    const response = await fetch(url, { ...init, headers: this.headers() });
    const text = await response.text();
    let body: unknown = undefined;
    if (text) {
      try {
        body = JSON.parse(text);
      } catch {
        body = text;
      }
    }
    if (!response.ok) {
      const message =
        body && typeof body === "object" && "error" in (body as Record<string, unknown>)
          ? String((body as Record<string, unknown>).error)
          : `Riven API request failed with status ${response.status}`;
      throw new RivenApiError(message, response.status);
    }
    return (body ?? {}) as T;
  }

  async chatCompletion(model: string, messages: ChatMessage[]): Promise<ChatCompletionResult> {
    return this.requestJson<ChatCompletionResult>(`${this.options.apiBase}/chat/completions`, {
      method: "POST",
      body: JSON.stringify({ model, messages, stream: false }),
    });
  }

  async createTask(title: string, prompt: string, kind: string): Promise<Task> {
    return this.requestJson<Task>(`${this.options.computerBase}/v1/tasks`, {
      method: "POST",
      body: JSON.stringify({ title, prompt, kind }),
    });
  }

  async runTask(taskId: string): Promise<Task> {
    return this.requestJson<Task>(`${this.options.computerBase}/v1/tasks/${taskId}/run`, {
      method: "POST",
    });
  }

  async getTask(taskId: string): Promise<Task> {
    return this.requestJson<Task>(`${this.options.computerBase}/v1/tasks/${taskId}`, {
      method: "GET",
    });
  }

  async getTaskThread(taskId: string): Promise<TaskThread> {
    return this.requestJson<TaskThread>(
      `${this.options.computerBase}/v1/tasks/${taskId}/thread`,
      { method: "GET" }
    );
  }

  async usage(): Promise<Record<string, unknown>> {
    return this.requestJson<Record<string, unknown>>(`${this.options.computerBase}/v1/usage`, {
      method: "GET",
    });
  }
}

/**
 * Poll a task's thread until the task reaches a terminal status or the
 * timeout elapses. Returns the final task state and its thread.
 */
export async function pollTaskUntilDone(
  client: RivenClient,
  taskId: string,
  options: { intervalMs?: number; timeoutMs?: number } = {}
): Promise<{ task: Task; thread: TaskThread }> {
  const intervalMs = options.intervalMs ?? 2000;
  const timeoutMs = options.timeoutMs ?? 120_000;
  const deadline = Date.now() + timeoutMs;
  const terminalStatuses = new Set(["completed", "failed", "cancelled", "error"]);

  let task = await client.getTask(taskId);
  while (!terminalStatuses.has(task.status) && Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
    task = await client.getTask(taskId);
  }
  const thread = await client.getTaskThread(taskId);
  return { task, thread };
}
