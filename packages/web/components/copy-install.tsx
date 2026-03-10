"use client";

import { useState, useCallback } from "react";

interface CopyInstallProps {
  command?: string;
  className?: string;
}

export function CopyInstall({
  command = "npm install -g rhumb",
  className = "",
}: CopyInstallProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback for older browsers
      const textArea = document.createElement("textarea");
      textArea.value = command;
      textArea.style.position = "fixed";
      textArea.style.left = "-9999px";
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand("copy");
      document.body.removeChild(textArea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }, [command]);

  return (
    <button
      onClick={handleCopy}
      className={`group relative px-5 py-2.5 rounded-lg border text-sm font-mono transition-all duration-200 ${
        copied
          ? "border-emerald-500/50 text-emerald-400 bg-emerald-500/10"
          : "border-slate-800 text-slate-500 hover:border-slate-700 hover:text-slate-400 hover:bg-slate-800/30"
      } ${className}`}
      title={copied ? "Copied!" : `Copy: ${command}`}
    >
      {copied ? (
        <span className="flex items-center gap-2">
          <span>✓ Copied — run in your terminal</span>
        </span>
      ) : (
        <span className="flex items-center gap-2">
          <span>$ {command}</span>
          <span className="text-slate-600 group-hover:text-slate-500 text-xs">⎘</span>
        </span>
      )}
    </button>
  );
}
