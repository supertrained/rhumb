import { useState, useCallback, type ReactNode } from "react";

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

export default function GuideSection({ guideContent }: GuideSectionProps) {
  const [isOpen, setIsOpen] = useState(false);

  if (!guideContent?.trim()) {
    return null;
  }

  // Simple markdown-to-HTML conversion for guide content
  function renderMarkdown(md: string): string {
    return md
      .replace(/^### (.+)$/gm, '<h3 class="text-base font-medium text-slate-200 mt-5 mb-2">$1</h3>')
      .replace(/^## (.+)$/gm, '<h2 class="text-lg font-display font-semibold text-slate-100 mt-6 mb-3">$1</h2>')
      .replace(/```(\w+)?\n([\s\S]*?)```/g, (_m, lang, code) => {
        return `<div class="relative my-4"><pre class="bg-slate-900 border border-slate-800 rounded-lg p-4 overflow-x-auto font-['JetBrains_Mono'] text-sm text-slate-300"><code class="${lang ? `language-${lang}` : ''}">${code.replace(/</g, '&lt;').replace(/>/g, '&gt;').trim()}</code></pre></div>`;
      })
      .replace(/`([^`]+)`/g, '<code class="bg-slate-800 text-amber px-1.5 py-0.5 rounded font-mono text-xs">$1</code>')
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" class="text-amber hover:underline underline-offset-2" target="_blank" rel="noreferrer">$1</a>')
      .replace(/^\- (.+)$/gm, '<li class="text-sm text-slate-400">$1</li>')
      .replace(/^(?!<[hld])(.*\S.*)$/gm, '<p class="text-sm text-slate-400 leading-relaxed mb-3">$1</p>');
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
        <div
          className="mt-5 rounded-lg border border-slate-800 bg-navy p-5 text-slate-300"
          dangerouslySetInnerHTML={{ __html: renderMarkdown(guideContent) }}
        />
      )}
    </section>
  );
}
