import { useCallback, useState } from "react";

interface CopyTextButtonProps {
  text: string;
  label?: string;
  copiedLabel?: string;
  className?: string;
}

export default function CopyTextButton({
  text,
  label = "Copy text",
  copiedLabel = "Copied",
  className = "",
}: CopyTextButtonProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      const textArea = document.createElement("textarea");
      textArea.value = text;
      textArea.style.position = "fixed";
      textArea.style.left = "-9999px";
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand("copy");
      document.body.removeChild(textArea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }, [text]);

  return (
    <button
      type="button"
      onClick={handleCopy}
      className={`inline-flex items-center justify-center gap-2 rounded-xl border px-4 py-2.5 text-sm font-medium transition-all duration-200 ${
        copied
          ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
          : "border-slate-700 bg-slate-950/30 text-slate-200 hover:border-amber/40 hover:bg-amber/10 hover:text-slate-50"
      } ${className}`}
      title={copied ? copiedLabel : label}
    >
      <span>{copied ? copiedLabel : label}</span>
      <span className={`font-mono text-xs ${copied ? "text-emerald-300/80" : "text-slate-500"}`}>
        {copied ? "✓" : "⌘C"}
      </span>
    </button>
  );
}
