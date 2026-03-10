"use client";

import React, { type ReactNode, useCallback, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface GuideSectionProps {
  guideContent?: string | null;
}

function CopyCodeButton({ code }: { code: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      const textArea = document.createElement("textarea");
      textArea.value = code;
      textArea.style.position = "fixed";
      textArea.style.left = "-9999px";
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand("copy");
      document.body.removeChild(textArea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }, [code]);

  return (
    <button
      type="button"
      onClick={handleCopy}
      className={`absolute top-2 right-2 px-2 py-1 text-xs rounded border transition-colors ${
        copied
          ? "border-emerald-500/50 text-emerald-400 bg-emerald-500/10"
          : "border-slate-700 text-slate-400 hover:border-slate-600 hover:text-slate-300"
      }`}
      title={copied ? "Copied" : "Copy code"}
    >
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

function CodeBlock({ code, language }: { code: string; language?: string }) {
  return (
    <div className="relative my-4">
      <CopyCodeButton code={code} />
      <pre className="bg-slate-900 border border-slate-800 rounded-lg p-4 pr-16 overflow-x-auto font-['JetBrains_Mono'] text-sm text-slate-300">
        <code className={language ? `language-${language}` : undefined}>{code}</code>
      </pre>
    </div>
  );
}

export function GuideSection({ guideContent }: GuideSectionProps) {
  const [isOpen, setIsOpen] = useState(false);

  if (!guideContent?.trim()) {
    return null;
  }

  return (
    <section className="bg-surface border border-slate-800 rounded-xl p-6" data-testid="guide-section">
      <button
        type="button"
        onClick={() => setIsOpen((value) => !value)}
        className="text-sm font-medium text-amber hover:underline underline-offset-2"
      >
        {isOpen ? "📖 Hide Integration Guide" : "📖 View Integration Guide"}
      </button>

      {isOpen && (
        <div className="mt-5 rounded-lg border border-slate-800 bg-navy p-5 text-slate-300">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              h2: ({ children }) => (
                <h2 className="text-lg font-display font-semibold text-slate-100 mt-6 mb-3 first:mt-0">
                  {children}
                </h2>
              ),
              h3: ({ children }) => (
                <h3 className="text-base font-medium text-slate-200 mt-5 mb-2">{children}</h3>
              ),
              p: ({ children }) => (
                <p className="text-sm text-slate-400 leading-relaxed mb-3 last:mb-0">{children}</p>
              ),
              ul: ({ children }) => (
                <ul className="list-disc ml-4 space-y-1 text-sm text-slate-400 mb-3">{children}</ul>
              ),
              ol: ({ children }) => (
                <ol className="list-decimal ml-4 space-y-1 text-sm text-slate-400 mb-3">{children}</ol>
              ),
              li: ({ children }) => <li>{children}</li>,
              a: ({ children, href }) => (
                <a
                  href={href}
                  className="text-amber hover:underline underline-offset-2"
                  target="_blank"
                  rel="noreferrer"
                >
                  {children}
                </a>
              ),
              table: ({ children }) => (
                <div className="my-4 overflow-x-auto">
                  <table className="w-full border-collapse text-xs text-slate-300">{children}</table>
                </div>
              ),
              th: ({ children }) => (
                <th className="border border-slate-700 px-2 py-1.5 text-left text-amber font-medium">
                  {children}
                </th>
              ),
              td: ({ children }) => (
                <td className="border border-slate-700 px-2 py-1.5 text-slate-300">{children}</td>
              ),
              pre: ({ children }) => <>{children}</>,
              code: ({ className, children }: { className?: string; children?: ReactNode }) => {
                const rawCode = String(children ?? "");
                const isBlock = Boolean(className?.includes("language-")) || rawCode.includes("\n");

                if (!isBlock) {
                  return (
                    <code className="bg-slate-800 text-amber px-1.5 py-0.5 rounded font-mono text-xs">
                      {children}
                    </code>
                  );
                }

                const language = className?.replace("language-", "");
                return <CodeBlock code={rawCode.replace(/\n$/, "")} language={language} />;
              },
            }}
          >
            {guideContent}
          </ReactMarkdown>
        </div>
      )}
    </section>
  );
}
