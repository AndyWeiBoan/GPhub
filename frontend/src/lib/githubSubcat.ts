/**
 * GitHub subcategory UI configuration.
 *
 * Subcategories are now assigned at crawl time (stored in items.github_subcat)
 * rather than being guessed on the frontend via keyword matching.
 * This file only holds the display metadata for the filter tabs.
 */
import type { GithubSubcat } from "./api";

export type { GithubSubcat };

export const GITHUB_SUBCATS: { value: GithubSubcat | ""; label: string; desc: string }[] = [
  { value: "",        label: "All GitHub",        desc: "All GitHub projects" },
  { value: "llm",     label: "Open-Source LLM",   desc: "Language models, fine-tuning, foundational models" },
  { value: "agent",   label: "AI Agents",          desc: "AI agents, multi-agent, agentic workflows" },
  { value: "context", label: "Context / Memory",   desc: "MCP, RAG, vector stores, memory, retrieval" },
  { value: "vision",  label: "Vision & Generation",desc: "Image generation, diffusion, multimodal, CV" },
  { value: "tool",    label: "AI Tools & Infra",   desc: "Dev tools, frameworks, SDKs, benchmarks, infra" },
];
